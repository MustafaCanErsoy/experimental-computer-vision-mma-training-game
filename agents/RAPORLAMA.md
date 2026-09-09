# Recognition reports

Every camera game session creates a local recognition journal under `%LOCALAPPDATA%\ShadowMMA\reports\recognition-<timestamp>-<id>`. Press `F8` during the game or run `Raporlar.cmd` to open the latest report without starting a camera. Reports and the current application interface use Turkish labels.

## Files and controls

| Item | Contents |
| --- | --- |
| `report.html` | Human-readable summary, event timeline, checks, and optional image gallery |
| `report.json` | Structured summary and retained detailed events |
| `events.jsonl` | Event-by-event journal for local investigation |
| `frame-*.jpg` | Optional selected frames around recorded events |
| `F9` / `--record-frames` | Opt in to saving subsequent event snapshots locally |
| `F10` | Restart camera preparation |

HTML/JSON summaries refresh periodically; closing the session flushes the final report. If an open browser page looks stale, refresh it. The JSON `closed` field indicates whether the session closed normally. Check `error` and `dropped_events` before treating a report as complete.

## Read the recognition pipeline in order

1. **Processed frames and visibility:** `frames.processed`, `valid`, and `body` show what the software observed. Invalid tracking can prevent a movement attempt from starting.
2. **Attempts and rejections:** attempt IDs connect detector decisions and their reasons. An attempt is a software state transition, not a count of all punches the person performed.
3. **Detected class:** `left_punch`, `right_punch`, or `uppercut` records the detector's decision.
4. **Event delivery:** event IDs connect emitted movements to the game response.
5. **Game result:** `hit` or `defeated` counts as scored; `wrong` means the detected class did not match the requested target. Compare `move` with `expected`.

An unrecognized physical movement may leave no attempt at all. A recognized movement may still fail the game prompt. None of these counters alone measures human movement accuracy.

## Threshold and timing fields

| JSON field | Meaning |
| --- | --- |
| `hareket_yuzdesi` | Overall movement threshold percentage |
| `ileri_yuzdesi` | Forward-motion threshold percentage |
| `yana_yuzdesi` | Sideways-motion threshold percentage |
| `yukari_yuzdesi` | Upward-motion threshold percentage |
| `kare_araligi_ms` | Sample interval in milliseconds |

Percentages are coarse, bounded diagnostic values relative to detector thresholds. They are not confidence probabilities, punch quality scores, or stored body coordinates. A threshold reading by itself is not enough to guarantee a hit; direction, visibility, detector state, and game state also matter.

`frames.processed / duration_s` is only a session-average processing estimate; startup and idle periods affect it. The laboratory's live FPS and model timings describe software processing. Neither proves the webcam's true sensor FPS or physical end-to-end latency. Low effective FPS is a suspected contributor to current recognition failures, not an established sole cause.

## Image recording and retention

Image recording is **off by default**. Enabling it saves selected JPEGs from a short event buffer, up to **180 images per session**, each at most **480 x 360** pixels. At most **5,000 detailed events** are retained; counters can continue after that limit, so the timeline may no longer represent every counted event. The report exposes the dropped-event count.

Disabling recording clears the current in-memory image buffer and stops future image saves. It does not delete previously saved files. Old session folders are not automatically removed. To remove a local session, close it and delete its report folder.

The report writer does not upload reports, record audio or continuous video, or persist raw body coordinates. Optional snapshots can show the player and surroundings; inspect files before choosing to share them. The repository excludes real session reports and images. Third-party native dependency network behavior remains a separate, incomplete audit; local report storage is not proof of total network isolation.

The laboratory's manually saved, participant-labelled evaluation report is separate from the game's automatic recognition journal. See [validation and measurement](TEST_PLANI.md).
