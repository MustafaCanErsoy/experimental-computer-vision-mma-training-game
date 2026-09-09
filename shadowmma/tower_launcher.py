"""Owned, jointly stopped game/producer processes; camera mode can auto-start."""
from pathlib import Path
import os
import socket
import subprocess
import tempfile
import sys
import ctypes
from time import monotonic, sleep

from .paths import ROOT, DATA, GODOT, RECOGNITION_REPORTS, python_command
from .process_job import ProcessJob


def game_command(source=None, port=28741, *, stop_file=None, headless=False, report_file=None):
    if not GODOT.is_file():
        raise FileNotFoundError("Godot eksik. Kurulum.cmd ile kurun veya ZIP paketini yeniden tamamen cikartin.")
    if not (ROOT / "godot/project.godot").is_file():
        raise FileNotFoundError("Oyun dosyalari eksik. ZIP paketini tamamen cikartin.")
    command = [str(GODOT), "--path", str(ROOT / "godot")]
    if headless:
        command.append("--headless")
    user = []
    if source and source != "keyboard":
        user += [f"--source={source}", f"--port={port}"]
    if stop_file:
        user.append(f"--stop-file={stop_file}")
    if report_file:
        user.append(f"--report-file={report_file}")
    return command + (["--", *user] if user else [])


def launch(source=None, port=28741):
    try:
        return subprocess.call(game_command(source, port), cwd=ROOT)
    except OSError as exc:
        print(str(exc))
        return 1


class Session:
    def __init__(self):
        self.children = []
        self.job = None
        self.temporary = None
        self.log = None
        self.log_path = None
        self.stop_file = None

    def start(self, source="keyboard", port=28741, camera=0, *, headless=False, no_camera=False, record_frames=False):
        if self.children:
            raise RuntimeError("Bir seans zaten acik.")
        if source not in ("keyboard", "synthetic", "camera") or not 1 <= port <= 65535 or camera < 0:
            raise ValueError("Gecersiz kaynak, port veya kamera indeksi.")
        if source != "keyboard":
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                if os.name == "nt":
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError as exc:
                    raise OSError(f"Yerel port {port} kullanilamiyor. Baska port secin.") from exc
        game_command(source, port)
        if source == "camera":
            from .assets import validate_model
            validate_model()
        try:
            self.job = ProcessJob()
            self.temporary = tempfile.TemporaryDirectory(prefix="shadowmma-session-")
            self.stop_file = Path(self.temporary.name) / "stop"
            logs = DATA / "reports"
            logs.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix="launcher-", suffix=".log", dir=logs)
            self.log_path = Path(name)
            self.log = os.fdopen(fd, "w", encoding="utf-8")
            from .diagnostics import session_folder
            report_dir = session_folder(RECOGNITION_REPORTS) if source == "camera" else None
            self._spawn(game_command(source, port, stop_file=self.stop_file, headless=headless,
                                     report_file=report_dir / "report.html" if report_dir else None))
            if source != "keyboard":
                options = []
                if source == "camera":
                    options += ["--report-dir", str(report_dir)]
                    if not no_camera:
                        options.append("--auto-camera")
                    if record_frames:
                        options.append("--record-frames")
                self._spawn(python_command("--worker", source, "--port", str(port), "--camera", str(camera),
                                           "--stop-file", str(self.stop_file), *options))
        except Exception:
            self.close()
            raise

    def _spawn(self, command):
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        external = os.name == "nt" and getattr(sys, "frozen", False) and command[0] == str(GODOT)
        if external:
            # Godot must not inherit Python's bundled native DLL search directory.
            ctypes.windll.kernel32.SetDllDirectoryW(None)
            bundle = Path(sys._MEIPASS).resolve()
            env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                                         if p and not Path(p).resolve().is_relative_to(bundle))
        try:
            child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=self.log, stderr=self.log,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        finally:
            if external:
                ctypes.windll.kernel32.SetDllDirectoryW(str(sys._MEIPASS))
        self.children.append(child)
        self.job.add(child)

    def poll(self):
        """Return (index, exit code) for the first ended child, or None."""
        for index, child in enumerate(self.children):
            code = child.poll()
            if code is not None:
                return index, code
        return None

    def close(self):
        try:
            if self.stop_file:
                self.stop_file.touch()
            deadline = monotonic() + 3
            for child in self.children:
                try:
                    child.wait(timeout=max(.01, deadline - monotonic()))
                except subprocess.TimeoutExpired:
                    child.terminate()
                    child.wait(timeout=3)
        finally:
            if self.job:
                self.job.close()
            self.children.clear()
            if self.log:
                self.log.close()
            if self.temporary:
                self.temporary.cleanup()
            self.job = self.log = self.temporary = self.stop_file = None


def run_session(source, port, camera, *, headless=False, seconds=None, no_camera=False, record_frames=False):
    session = Session()
    try:
        session.start(source, port, camera, headless=headless, no_camera=no_camera, record_frames=record_frames)
        start = monotonic()
        while True:
            ended = session.poll()
            if ended is not None:
                index, code = ended
                if code:
                    print(f"Alt surec {index} hata ile kapandi ({code}). Kayit: {session.log_path}")
                return 1 if code else 0
            if seconds is not None and monotonic() - start >= seconds:
                return 0
            sleep(.05)
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc))
        if getattr(sys, "frozen", False) and not headless:
            from tkinter import Tk, messagebox
            window = Tk()
            window.withdraw()
            messagebox.showerror("ShadowMMA başlatılamadı", str(exc), parent=window)
            window.destroy()
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        session.close()
