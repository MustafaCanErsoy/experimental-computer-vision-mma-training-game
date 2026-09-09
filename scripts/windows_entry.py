"""PyInstaller windowed entry; keep diagnostic output out of console windows."""
import os
import sys
from shadowmma.paths import DATA

if sys.stdout is None or sys.stderr is None:
    try:
        (DATA / "reports").mkdir(parents=True, exist_ok=True)
        stream = (DATA / "reports/launcher-runtime.log").open("a", encoding="utf-8", buffering=1)
    except OSError:
        stream = open(os.devnull, "w")
    sys.stdout = sys.stdout or stream
    sys.stderr = sys.stderr or stream

from shadowmma.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
