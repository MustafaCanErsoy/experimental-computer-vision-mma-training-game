# Windows setup and local packaging

ShadowMMA 0.1.9 is an experimental camera-controlled game. Human movement recognition remains unreliable; installation or software-test success does not establish recognition accuracy. The current application interface is primarily in Turkish.

## Source installation

Install 64-bit Python 3.12 with its Windows `py` launcher, then run `Kurulum.cmd` from the repository. It creates `.venv`, installs `requirements.lock.txt`, downloads the pinned pose model, and installs Godot 4.7.2 into `.tools/godot`. Setup requires internet access.

Equivalent commands from the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe scripts\setup.py
.\.venv\Scripts\python.exe scripts\setup_godot.py
```

`ShadowMMA.cmd` launches the game and opens the webcam automatically. Briefly keep your shoulders and hands visible and your hands still for preparation. `KuleDemo.cmd` starts keyboard gameplay without opening the webcam. `Baslat.cmd --launcher` opens the source selector. `Baslat.cmd` opens a laboratory window with manual camera activation.

In camera mode, `F8` opens the report, `F9` toggles subsequent local snapshots, and `F10` restarts preparation. Camera prompts have no countdown. Recognition still has to produce the requested class for the game to accept a hit. See [recognition reports](RAPORLAMA.md).

## Build a portable folder and ZIP

After source installation, run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.lock.txt
.\.venv\Scripts\python.exe scripts\build_windows.py
.\.venv\Scripts\python.exe scripts\test_windows_bundle.py
```

The build checks pinned versions, hashes, and third-party notices. It produces a new `dist/windows-<timestamp>/` directory containing the application folder, ZIP, and checksum. `build/latest-package.json` identifies the latest output. Each bundle includes a manifest with file hashes, dependency versions, and source Git state.

Extract the entire ZIP before opening `ShadowMMA.exe`. Keep its `_internal`, `godot`, `runtime`, `assets`, and `agents` directories together. Python and Godot do not need separate installation for that bundle. The EXE defaults to automatic camera gameplay; `ShadowMMA.exe --launcher` exposes the other modes. This is a local unsigned prototype bundle.

## Troubleshooting

- Missing model or engine: rerun the setup scripts, or fully re-extract a built ZIP.
- Wrong camera: use `ShadowMMA.cmd --camera 1` (or another available index).
- Local event port busy: use a different port, for example `ShadowMMA.cmd --port 28742`.
- Camera prepared but no scoring: open the report and compare the detected class with the expected target. Calibration alone does not establish successful recognition.
- Slow tracking: check processed FPS, model time, and sample gaps. The requested camera FPS is not a measured processing rate.
- Logs and camera reports: `%LOCALAPPDATA%\ShadowMMA\reports`. Laboratory reports saved manually are under the checkout's `reports/` directory.

Use one game session at a time. Close the game before replacing its bundle. For a camera-free startup check, run:

```powershell
.\.venv\Scripts\python.exe -m shadowmma --play camera --no-camera --headless --smoke-seconds 3
```

Always retain `--no-camera` in that command when testing startup without physical camera access.
