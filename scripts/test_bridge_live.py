"""Launch real Godot and two successive Python producers; never imports camera libs."""
from pathlib import Path
import socket
import subprocess
import sys
from threading import Thread
from time import perf_counter, sleep

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shadowmma.core import Hit
from shadowmma.event_bridge import EventClient


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    executable = ROOT / ".tools/godot/Godot_v4.7.2-stable_win64_console.exe"
    process = subprocess.Popen([str(executable), "--headless", "--path", str(ROOT / "godot"),
                                "--script", "res://test_bridge_live.gd", "--",
                                "--source=synthetic", f"--port={port}"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    client = EventClient("synthetic", port)
    lines = []
    def read_output():
        for line in process.stdout:
            lines.append(line)
    reader = Thread(target=read_output, daemon=True)
    reader.start()
    start = perf_counter()
    stage, next_send, disconnect_until = 0, start, None
    disconnected = False
    classes = ("left_punch", "right_punch", "uppercut")
    moves = ["right_punch"]  # deliberate wrong class
    for floor, health in ((1, 4), (2, 4), (3, 5)):
        moves.extend(classes[(step+floor-1) % 3] for step in range(health))
    moves.append("left_punch")  # fresh run, same producer
    try:
        while process.poll() is None and perf_counter() - start < 23:
            now = perf_counter()
            if disconnect_until is not None:
                if now >= disconnect_until:
                    client = EventClient("synthetic", port)
                    disconnect_until = None
            else:
                client.poll(ready=True)
                if stage == 2 and now >= next_send and not disconnected:
                    # Abrupt socket loss exercises the heartbeat timeout, not graceful shutdown.
                    client.socket.close()
                    client.closed = True
                    disconnected = True
                    disconnect_until = now + 1.3
                    next_send = disconnect_until + .3
                    continue
                if stage < len(moves) and now >= next_send:
                    now = perf_counter()
                    if client.send_hit(Hit(moves[stage], now, now, 0.), now):
                        stage += 1
                        next_send = now + .3
            sleep(.01)
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
            reader.join(timeout=2)
            print("".join(lines))
            print("Last producer stage:", stage, "context:", client.context)
            raise RuntimeError("Godot live integration did not finish")
        reader.join(timeout=2)
        output = "".join(lines)
        print(output)
        if process.returncode or "failures: 0" not in output or "SCRIPT ERROR" in output:
            raise RuntimeError("Godot live integration failed")
        if {"cv2", "mediapipe", "shadowmma.vision"}.intersection(sys.modules):
            raise RuntimeError("Camera dependency imported by synthetic test")
        return 0
    finally:
        client.close()
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
        reader.join(timeout=2)
        process.stdout.close()


if __name__ == "__main__":
    sys.exit(main())
