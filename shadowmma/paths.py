"""Read-only bundle resources and writable per-user data are separate."""
import os
from pathlib import Path
import sys

FROZEN = getattr(sys, "frozen", False)
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ShadowMMA" if FROZEN else ROOT
RECOGNITION_REPORTS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ShadowMMA/reports"
GODOT = ROOT / ("runtime/godot/Godot_v4.7.2-stable_win64.exe" if FROZEN else ".tools/godot/Godot_v4.7.2-stable_win64.exe")


def python_command(*args):
    return [sys.executable, *([] if FROZEN else ["-m", "shadowmma"]), *args]
