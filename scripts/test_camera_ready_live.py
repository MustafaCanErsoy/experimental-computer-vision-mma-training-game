"""Real extract/Tk/Detector/UDP/Godot; invented landmarks, no camera."""
from pathlib import Path
import socket
import subprocess
import sys
import json
from threading import Thread
from time import perf_counter, sleep
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from shadowmma.app import App
from camera_samples import landmarks
from shadowmma.event_bridge import EventClient
from shadowmma.diagnostics import session_folder
import numpy as np


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    game = subprocess.Popen([str(ROOT / ".tools/godot/Godot_v4.7.2-stable_win64_console.exe"),
                             "--headless", "--path", str(ROOT / "godot"), "--script", "res://test_camera_ready_live.gd",
                             "--", "--source=camera", f"--port={port}"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            creationflags=subprocess.CREATE_NO_WINDOW)
    lines = []
    state = {"stage": "CALIBRATION"}

    def read_output():
        for line in game.stdout:
            lines.append(line)
            if line.startswith("CAMERA_READY_STAGE:"):
                state["stage"] = line.strip().split(":", 1)[1]

    reader = Thread(target=read_output, daemon=True)
    reader.start()
    pixels = np.zeros((256, 256, 3), dtype=np.uint8)

    class Capture:
        error, backend = "", "SYNTHETIC_TEST"
        sequence, last = 0, 0.

        def read(self):
            now = perf_counter()
            if now - self.last >= .09:
                self.sequence += 1
                self.last = now - .005
            return self.sequence, self.last, pixels

        def close(self):
            pass

    class Pose:
        samples = {}
        paths = {
            "LEFT_PUNCH": [(0.,-.25,-.03),(0.,-.42,-.05),(0.,-.50,-.24),(0.,-.55,-.36),(0.,-.30,-.20)],
            "RIGHT_PUNCH": [(0.,0.,-.09),(0.,0.,-.16),(0.,0.,-.26),(0.,0.,-.26),(0.,0.,-.14)],
            "UPPERCUT": [(0.,-.16,0.),(0.,-.34,0.),(0.,-.14,0.)]}

        def process(self, _pixels, _received):
            stage = state["stage"]
            if stage in ("LEFT_PUNCH", "RIGHT_PUNCH", "UPPERCUT"):
                index = self.samples.get(stage, 0)
                self.samples[stage] = index+1
                path = [(0.,0.,0.)]*12+self.paths[stage]+[(0.,0.,0.)]*10
                if index < len(path):
                    image, world = landmarks()
                    dx,dy,dz = path[index]
                    wrist = 16 if stage == "RIGHT_PUNCH" else 15
                    image[wrist].x += dx*.3
                    image[wrist].y += dy*.3
                    world[wrist].z += dz*.3
                    return image, world
            return landmarks(hidden=11 if state["stage"] == "LOSE_TRACKING" else None)

        def close(self):
            pass

    class DelayedApp(App):
        delayed_ticks = 0

        def tick(self):
            if state["stage"] == "RUNNING":
                # Camera capture continues to have a current sample after this
                # delayed UI callback. Prior Features alone would be stale.
                sleep(.27)
                self.delayed_ticks += 1
            super().tick()

    client = EventClient("camera", port)
    report_dir = session_folder(ROOT / "build")
    app = None
    try:
        with patch("shadowmma.app.Camera", side_effect=lambda _index: Capture()) as camera_factory, \
                patch("shadowmma.app.Pose", side_effect=Pose), \
                patch("shadowmma.vision.Camera.__init__", side_effect=AssertionError("Physical camera forbidden")):
            app = DelayedApp(tower_client=client, auto_start=True, integrated=True, report_dir=report_dir,
                             record_frames=True)

            def monitor():
                if game.poll() is not None:
                    app.close()
                else:
                    app.root.after(30, monitor)

            app.root.after(30, monitor)
            app.root.after(42000, app.close)
            app.run()
        game.wait(timeout=3)
        reader.join(timeout=2)
        output = "".join(lines)
        print(output)
        assert game.returncode == 0 and "failures: 0" in output and "SCRIPT ERROR" not in output, output
        assert app.delayed_ticks >= 3, app.delayed_ticks
        camera_factory.assert_called_once_with(0)
        report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
        recognized = [e for e in report["events"] if e["kind"] == "detected"]
        scored = [e for e in report["events"] if e["kind"] == "game" and e["detail"] == "hit"]
        assert len(recognized) == len(scored) == 3, report["counts"]
        assert [e["move"] for e in recognized] == ["left_punch", "right_punch", "uppercut"], recognized
        assert [e["attempt"] for e in recognized] == [e["attempt"] for e in scored], (recognized, scored)
        assert report["counts"]["motion"] >= 3 and report["ruleset"] == "simple-motion-v2"
        assert all(e["measures"]["hareket_yuzdesi"] >= 100 for e in recognized)
        assert report["counts"].get("wrong_target",0) == 0
        assert report["images_saved"] > 0 and report["closed"], report["counts"]
        assert all((report_dir / im["file"]).is_file() for e in report["events"] for im in e["images"])
        print("REPORT_OK: automatic preparation; three simple moves, three matching game receipts; local test stills:", report_dir)
        print("Delayed real Tk callbacks:", app.delayed_ticks, "; camera opened: false")
    finally:
        if app and not app.closed:
            app.close()
        client.close()
        if game.poll() is None:
            game.terminate()
        game.wait(timeout=5)
        reader.join(timeout=2)
        game.stdout.close()


if __name__ == "__main__":
    main()
