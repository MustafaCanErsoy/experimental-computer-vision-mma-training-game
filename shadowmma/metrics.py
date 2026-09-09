"""Explicitly labelled trial metrics; no video or landmark serialization."""
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
import tempfile
from math import isfinite
from pathlib import Path
from .core import MOVES, RULESET
from .assets import MODEL_SHA256
from . import __version__


def percentiles(values):
    if not values:
        return {"n": 0, "p50_ms": None, "p95_ms": None}
    values = sorted(values)
    return {"n": len(values), "p50_ms": round(values[(len(values)-1)//2], 2),
            "p95_ms": round(values[min(len(values)-1, int(.95*len(values)))], 2)}


@dataclass
class Trial:
    expected: str
    instruction: str
    events: list[str] = field(default_factory=list)
    frames: int = 0
    valid_frames: int = 0
    confirmed: bool = False
    max_gap_s: float = 0.
    return_ms: list[float] = field(default_factory=list)
    stance: str = "neutral"  # Historical export field; no stance choice in simple controls.
    frame_intervals_ms: list[float] = field(default_factory=list)
    aborted_reason: str | None = None

    @property
    def evaluable(self):
        return (not self.aborted_reason and self.confirmed and self.frames >= 15 and self.valid_frames/self.frames >= .9
                and self.max_gap_s <= .3)


def summarize(trials, software_ms=(), inference_ms=(), event_ms=(), optical_ms=None):
    included = [t for t in trials if t.evaluable]
    positives = [t for t in included if t.expected in MOVES]
    negatives = [t for t in included if t.expected == "none"]
    confusion = {m: dict(Counter((t.events[0] if t.events else "none") for t in included if t.expected == m))
                 for m in (*MOVES, "none")}
    exact = sum(t.events == [t.expected] for t in positives)
    correct_negative = sum(not t.events for t in negatives)
    emitted = sum(len(t.events) for t in included)
    matched = sum(t.expected in t.events for t in positives)
    ratio = lambda a, b: round(a/b, 4) if b else None
    return {
        "label_source": "user-confirmed instructed action; not expert technique ground truth",
        "confirmed_trials": sum(t.confirmed for t in trials), "evaluable_trials": len(included),
        "unassessable_trials": sum(t.confirmed and not t.evaluable and not t.aborted_reason for t in trials),
        "skipped_trials": sum(not t.confirmed and not t.aborted_reason for t in trials),
        "aborted_trials": sum(bool(t.aborted_reason) for t in trials),
        "positive_trials": len(positives), "negative_trials": len(negatives),
        "exact_movement_accuracy": ratio(exact, len(positives)),
        "trial_accuracy": ratio(exact+correct_negative, len(included)),
        "event_precision": ratio(matched, emitted), "movement_recall": ratio(matched, len(positives)),
        "missed_expected_movements": sum(t.expected not in t.events for t in positives),
        "wrong_class_trials": sum(bool(t.events) and t.events[0] != t.expected for t in positives),
        "false_positive_negative_trials": sum(bool(t.events) for t in negatives),
        "negative_false_positive_rate": ratio(sum(bool(t.events) for t in negatives), len(negatives)),
        "extra_events": sum(max(0, len(t.events)-1) for t in included),
        "confusion_first_event": confusion,
        "latency": {"frame_received_to_tk_submission": percentiles(software_ms),
                    "trial_processed_frame_interval": percentiles([v for t in trials for v in t.frame_intervals_ms]),
                    "inference": percentiles(inference_ms), "hit_frame_to_tk_submission": percentiles(event_ms),
                    "direction_to_motion_confirmation": percentiles([v for t in trials for v in t.return_ms]),
                    "optical_end_to_end_ms_user_measured": optical_ms,
                    "limitation": "Software timing excludes sensor/driver buffering and physical display refresh. Optical value needs external measurement."},
    }


def save_report(folder, trials, stance, software_ms, inference_ms, event_ms, optical_ms=None):
    import importlib.metadata
    import platform
    if optical_ms is not None and (not isfinite(optical_ms) or optical_ms < 0):
        raise ValueError("Harici gecikme negatif olmayan, sonlu bir sayi olmali.")
    stamp = datetime.now(timezone.utc)
    summary = summarize(trials, software_ms, inference_ms, event_ms, optical_ms)
    data = {"schema": 3, "ruleset": RULESET, "created_utc": stamp.isoformat(), "prototype": __version__, "selected_stance_at_export": stance,
            "versions": {p: importlib.metadata.version(p) for p in ("mediapipe", "opencv-contrib-python", "numpy")},
            "python": platform.python_version(), "model_sha256": MODEL_SHA256,
            "summary": summary,
            "summary_by_stance": {s: summarize([t for t in trials if t.stance == s])
                                  for s in sorted({t.stance for t in trials})},
            "trials": [asdict(t) for t in trials],
            "privacy": "No images, audio, video or body coordinates stored."}
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ("session-"+stamp.strftime("%Y%m%dT%H%M%S%fZ")+".json")
    atomic_json(path, data)
    return path


def atomic_json(path, data):
    """Publish only a complete UTF-8 JSON report; leave no partial final file."""
    content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".report-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
