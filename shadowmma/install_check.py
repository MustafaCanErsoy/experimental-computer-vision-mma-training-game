"""Explicit offline diagnostic: real Tk + model inference on a blank RAM image."""
import json
import socket
from unittest.mock import patch


def check_install(output):
    result = {"camera_opened": False, "frames_saved": 0, "ok": False}
    try:
        with patch.object(socket.socket, "connect", side_effect=AssertionError("External connections forbidden")):
            from .assets import validate_model
            from .tower_launcher import game_command
            from .vision import Camera, Pose
            from .launcher_ui import Launcher
            from .app import App
            import numpy as np
            validate_model()
            game_command()
            with patch.object(Camera, "__init__", side_effect=AssertionError("Camera forbidden")):
                launcher = Launcher()
                launcher.root.update()
                result["launcher_size"] = [launcher.root.winfo_width(), launcher.root.winfo_height()]
                launcher.close()
                app = App(0)
                app.root.update()
                assert app.camera is None
                app.close()
                pose = Pose()
                try:
                    landmarks, _ = pose.process(np.zeros((256, 256, 3), dtype=np.uint8), 1.)
                    result["blank_image_landmarks"] = len(landmarks)
                finally:
                    pose.close()
            result["ok"] = True
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
