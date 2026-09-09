# Experimental Computer Vision MMA Training Game

[![CI](https://github.com/MustafaCanErsoy/experimental-computer-vision-mma-training-game/actions/workflows/ci.yml/badge.svg)](https://github.com/MustafaCanErsoy/experimental-computer-vision-mma-training-game/actions/workflows/ci.yml)

**ShadowMMA** is an experimental Windows shadowboxing game that connects webcam pose tracking to a small 3D tower encounter. It explores teaching simple movement prompts through play: **left punch, right punch, and uppercut**.

> **Prototype status:** Real movement recognition is still unreliable. Movements can be missed or assigned to the wrong class, preventing progress in camera mode. Low effective processing FPS is a suspected contributor; the root cause has not been isolated. This is a computer vision experiment, not a validated MMA coaching system.

The public documentation is in English. The current game, launcher, and generated report interface are primarily in Turkish. The application and local data folders retain the name **ShadowMMA**. Current application version: **0.1.9** (`simple-motion-v2`).

## What is implemented

- Direct camera game startup, automatic camera activation, and brief automatic calibration.
- Three movement classes based on observed hand motion, without professional stance or punch-form requirements.
- A Godot tower encounter with prompts, enemies, score, combos, and floor progression.
- Keyboard and synthetic input modes for checking gameplay independently of recognition.
- Local HTML, JSON, and JSONL recognition reports showing detected movements, rejection reasons, and game responses.
- Optional event snapshots, disabled by default, for reviewing what the tracker saw around an event.

## Run from source on Windows

Use **64-bit Python 3.12** with the Windows `py` launcher. Setup needs an internet connection to install the pinned Python dependencies, download the pose model, and install the project-local Godot runtime. This checkout targets **Godot 4.7.2**; the setup scripts verify the model and engine download hashes.

```powershell
git clone https://github.com/MustafaCanErsoy/experimental-computer-vision-mma-training-game.git
cd experimental-computer-vision-mma-training-game
.\Kurulum.cmd
```

Start the camera game:

```powershell
.\ShadowMMA.cmd
```

**This command opens the webcam automatically.** Keep your shoulders and hands visible, then hold your hands comfortably still for the short preparation step. No in-game camera button is required. Camera prompts have no countdown; recognition must still succeed for a hit to score.

To explore the game without a webcam:

```powershell
.\KuleDemo.cmd
```

| Command | Purpose |
| --- | --- |
| `ShadowMMA.cmd` | Camera game with automatic startup |
| `KuleDemo.cmd` | Keyboard game, camera stays closed |
| `Baslat.cmd --play synthetic` | Game driven by generated movement events, camera stays closed |
| `Baslat.cmd --launcher` | Choose an input source |
| `Baslat.cmd` | Tracking laboratory; camera activation is manual |
| `Raporlar.cmd` | Open the latest local recognition report without opening the camera |
| `Test.cmd` | Run the local Python test suite |

Use `ShadowMMA.cmd --camera 1` to select a different camera index. See [setup and packaging](agents/PAKET.md) for manual installation and build commands.

## Controls

| Key | Action |
| --- | --- |
| `F8` | Open the current recognition report in camera mode |
| `F9` | Enable or disable recording subsequent event snapshots locally |
| `F10` | Restart camera preparation/calibration |
| `P` | Pause; press again to allow resuming |
| `R` | Start a new session |
| `F` | Finish the session |
| `Esc` | Quit |
| `W`, `A`, `S`, `D` | Move in keyboard mode |
| `1`, `2`, `3` | Left punch, right punch, uppercut in keyboard mode |
| `E` | Use the stairs when the floor is clear and you are close enough |

Camera mode includes automatic approach and floor transitions when tracking is ready. Keyboard and synthetic scores are kept separate from camera scores.

## Recognition reports

Camera sessions create `recognition-*/report.html`, `report.json`, and `events.jsonl` under `%LOCALAPPDATA%\ShadowMMA\reports`. The report separates an attempted movement, a detected class, an emitted event, and the game's acceptance or rejection. A detected punch does not necessarily match the current target.

Images are saved only after opting in with `F9` or `--record-frames`. Recording is limited to selected event JPEGs, rather than continuous video. Turning it off does not delete images already saved. The application report writer does not upload reports, record audio, or persist raw body coordinates. No real user sessions or camera images are included in this repository.

See [report fields, limits, and interpretation](agents/RAPORLAMA.md).

## How it works

```text
Webcam -> OpenCV latest-frame capture -> MediaPipe pose landmarks
       -> Python movement rules -> loopback UDP events -> Godot game
                              -> local recognition reports
```

- `shadowmma/vision.py`: capture and pose model adapter.
- `shadowmma/core.py`: calibration and three-class movement detector.
- `shadowmma/diagnostics.py`: recognition journal and HTML report.
- `shadowmma/event_bridge.py`: event transport over `127.0.0.1`.
- `godot/`: encounter state, tower scene, and local progress storage.
- `tests/` and `scripts/test_*.py`: local regression and integration checks.

Godot owns gameplay state; Python supplies observations. The bridge carries numeric events and status, not camera frames. Setup downloads dependencies and assets. No account or cloud AI API key is required. Third-party native dependency network behavior has not been fully audited, so this repository does not claim verified network isolation.

## Limitations and validation

- Real human movement accuracy remains unvalidated and has been insufficient in practical trials.
- The camera requests 30 FPS, but that does not establish the actual capture rate or processed pose rate. Inference time, lighting, tracking visibility, and sampling gaps may affect recognition.
- A single webcam provides ambiguous depth and can lose hands behind the body or face. Short movements can fall between processed frames.
- Automated tests exercise synthetic observations and software behavior. Passing them does not establish physical recognition accuracy or sensor-to-screen latency.
- Only three basic gestures are supported. There is no assessment of punch power, professional technique, or a complete MMA curriculum.
- Windows is the supported development target. Simultaneous game sessions and other operating systems have not been validated.

Run the existing local checks after setup:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\test_camera_ready_live.py
```

The second command uses synthetic camera observations with the real adapter and game processes; it does not open a physical webcam. See [validation and measurement](agents/TEST_PLANI.md) for what these checks establish.

## GitHub automation

**CI** runs Windows tests on pushes to `main` and pull requests. **CD** runs the same checks, builds the portable Windows ZIP, and validates the extracted application. A manual CD run provides a downloadable artifact; pushing a version tag matching the application version publishes it as an experimental GitHub prerelease with a SHA256 checksum.

The YAML workflows run on GitHub-hosted machines. See [CI/CD usage and release instructions](agents/CI_CD.md). No real camera or user session data is used in these checks.

## Third-party notices

Dependency and model notices are preserved in [agents/licenses](agents/licenses). The packaging script also collects installed dependency and engine notices into each local build. Model files, engine binaries, virtual environments, and generated builds are downloaded or produced locally rather than stored in Git.

No project-wide license has been declared for the original application code. Included third-party licenses apply to their respective components.
