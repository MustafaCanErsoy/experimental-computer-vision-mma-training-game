"""Exercise the real Tk processing loop; optionally open a camera, never save frames.

Python socket connections are denied during this test. This is an application-level
offline check, not a change to Windows networking or an audit of native libraries.
"""
import argparse
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shadowmma.app import App
from shadowmma.metrics import percentiles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=None)
    args = parser.parse_args()
    result = {}
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden in smoke check")):
        app = App(args.camera or 0)
        app.root.update_idletasks()
        result["tk_requested_size"] = [app.root.winfo_reqwidth(), app.root.winfo_reqheight()]
        result["screen"] = [app.root.winfo_screenwidth(), app.root.winfo_screenheight()]

        def finish():
            result.update(processed_frames=len(app.software_ms), software=percentiles(app.software_ms),
                          inference=percentiles(app.inference_ms), camera_error=app.camera.error if app.camera else None,
                          human_movement_test="NOT_PERFORMED", frames_saved=0,
                          python_socket_connect="DENIED_DURING_TEST", visual_screenshot_review="NOT_PERFORMED")
            app.close()

        if args.camera is not None:
            app.toggle_camera()
        app.root.after(10000 if args.camera is not None else 300, finish)
        app.run()
    print(json.dumps(result, indent=2))
    if args.camera is not None and (not result["processed_frames"] or result["camera_error"]):
        raise RuntimeError("Camera UI smoke check failed")


if __name__ == "__main__":
    main()
