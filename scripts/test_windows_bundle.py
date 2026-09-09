"""Extract and exercise the actual ZIP with no project/Python on runtime PATH."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("zip", nargs="?", type=Path)
    args = parser.parse_args()
    archive = args.zip or Path(json.loads((ROOT / "build/latest-package.json").read_text())["zip"])
    # Retained for inspection/reproduction; unique folder, no existing files replaced.
    target = Path(tempfile.mkdtemp(prefix="paket sınama ", dir=ROOT / "build"))
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.namelist():
            if not (target / entry).resolve().is_relative_to(target.resolve()):
                raise RuntimeError("Unsafe ZIP path")
        bundle.extractall(target)
    package = target / "ShadowMMA"
    exe = package / "ShadowMMA.exe"
    godot = package / "runtime/godot/Godot_v4.7.2-stable_win64.exe"
    env = dict(os.environ, PATH=str(Path(os.environ["SystemRoot"]) / "System32"),
               LOCALAPPDATA=str(target / "local"), APPDATA=str(target / "roaming"))
    for key in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        env.pop(key, None)
    flags = subprocess.CREATE_NO_WINDOW
    results = []

    def run(*arguments, expected=0, timeout=25):
        result = subprocess.run([str(exe), *map(str, arguments)], cwd=target, env=env,
                                capture_output=True, timeout=timeout, creationflags=flags)
        if result.returncode != expected:
            raise AssertionError(f"{arguments}: exit {result.returncode}; logs under {target / 'local'}")

    manifest = json.loads((package / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        with (package / name).open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == expected, name
    results.append("All manifest file hashes verified")
    run("--check-install", target / "install.json")
    diagnostic = json.loads((target / "install.json").read_text(encoding="utf-8"))
    assert diagnostic["ok"] and not diagnostic["camera_opened"], diagnostic
    results.append("Frozen Tk/launcher/lab and blank-image model inference; camera forbidden")
    for source in ("keyboard", "synthetic", "camera"):
        run("--play", source, "--port", free_port(), "--no-camera", "--headless", "--smoke-seconds", "3")
        results.append(f"Managed {source} startup/shutdown (camera stays closed)")
    report_paths = list((target / "local/ShadowMMA/reports").glob("recognition-*/report.json"))
    assert len(report_paths) == 1
    report = json.loads(report_paths[0].read_text(encoding="utf-8"))
    assert report["closed"] and report["frames"].get("processed", 0) == 0 and report["images_saved"] == 0
    assert report_paths[0].with_name("report.html").is_file() and (package / "Raporlar.cmd").is_file()
    results.append("Frozen automatic local HTML/JSON journal closes; no frames or camera")
    run("--no-camera", "--headless", "--smoke-seconds", "3")
    assert len(list((target / "local/ShadowMMA/reports").glob("recognition-*/report.json"))) == 2
    results.append("Default frozen entry selects camera game; explicit no-camera prevents capture")
    run("--play", "keyboard", "--smoke-seconds", "3")
    results.append("Packaged keyboard game opens with real GPU rendering")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as busy:
        busy.bind(("127.0.0.1", 0))
        run("--play", "synthetic", "--port", busy.getsockname()[1], "--headless", expected=1)
    results.append("Busy port rejected")
    for path, source in ((godot, "keyboard"), (package / "assets/pose_landmarker_lite.task", "camera"),
                         (package / "godot/project.godot", "keyboard")):
        backup = path.with_suffix(path.suffix + ".test-backup")
        path.rename(backup)
        try:
            run("--play", source, "--port", free_port(), "--no-camera", "--headless", expected=1)
        finally:
            backup.rename(path)
        results.append(f"Missing {path.name} rejected")
    fixture = package / "godot/test_packaged_bridge.gd"
    shutil.copy2(ROOT / "scripts/test_packaged_bridge.gd", fixture)
    port = free_port()
    token = target / "stop-worker"
    producer = subprocess.Popen([str(exe), "--worker", "synthetic", "--port", str(port), "--stop-file", str(token)],
                                cwd=target, env=env, creationflags=flags)
    try:
        game = subprocess.run([str(godot), "--headless", "--path", str(package / "godot"),
                               "--script", "res://test_packaged_bridge.gd", "--", "--source=synthetic", f"--port={port}"],
                              cwd=target, env=env, capture_output=True, timeout=20, creationflags=flags)
        assert game.returncode == 0 and b"PACKAGED_BRIDGE_OK" in game.stdout, game.stdout + game.stderr
        assert producer.poll() is None
    finally:
        token.touch()
        try:
            producer.wait(timeout=5)
        except subprocess.TimeoutExpired:
            producer.terminate()
            producer.wait(timeout=5)
    assert producer.returncode == 0
    results.append("Packaged Python -> packaged Godot handshake, explicit resume and scored hit")
    logs = list((target / "local").rglob("*.log")) + list((target / "roaming").rglob("*.log"))
    for log in logs:
        content = log.read_text(encoding="utf-8", errors="replace")
        assert "SCRIPT ERROR" not in content and "Traceback" not in content, str(log)
    results.append("No script errors or Python tracebacks in isolated runtime logs")
    report = {"checks": results, "passed": len(results), "package": str(archive), "extracted": str(package),
              "camera_opened": False, "clean_machine": False, "runtime_path": env["PATH"]}
    (ROOT / "build/package-validation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
