import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from shadowmma.paths import ROOT
from shadowmma.tower_launcher import Session, game_command


class LauncherTests(unittest.TestCase):
    def test_missing_game_starts_no_children(self):
        with patch("shadowmma.tower_launcher.GODOT", Path("missing.exe")):
            session = Session()
            with self.assertRaisesRegex(FileNotFoundError, "Godot"):
                session.start()
            self.assertFalse(session.children)

    def test_busy_port_is_preserved(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as busy:
            busy.bind(("127.0.0.1", 0))
            session = Session()
            with self.assertRaisesRegex(OSError, "port"):
                session.start("synthetic", busy.getsockname()[1])
            self.assertFalse(session.children)
            self.assertGreater(busy.fileno(), 0)

    def test_invalid_source_does_not_start(self):
        with self.assertRaises(ValueError):
            Session().start("unknown")

    def test_source_and_stop_path_are_separate_arguments(self):
        command = game_command("synthetic", 28742, stop_file=Path("C:/test folder/stop"))
        self.assertIn("--source=synthetic", command)
        self.assertIn(f"--stop-file={Path('C:/test folder/stop')}", command)
        self.assertNotIn("--source=keyboard", game_command("keyboard"))

    def test_worker_start_failure_reaps_already_started_game(self):
        children = []
        popen = subprocess.Popen

        def spawn(command, **kwargs):
            if children:
                raise OSError("worker unavailable")
            child = popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
            children.append(child)
            return child

        with patch("shadowmma.tower_launcher.subprocess.Popen", side_effect=spawn):
            session = Session()
            with self.assertRaisesRegex(OSError, "worker unavailable"):
                session.start("synthetic", free_port())
        self.assertIsNotNone(children[0].poll())
        self.assertFalse(session.children)
        session.close()  # Closing twice is safe.

    def test_managed_synthetic_game_stops_both_cleanly(self):
        session = Session()
        try:
            session.start("synthetic", free_port(), headless=True)
            children = session.children[:]
            time.sleep(1.5)
            self.assertIsNone(session.poll())
            with self.assertRaises(RuntimeError):
                session.start()
        finally:
            session.close()
        self.assertEqual([p.returncode for p in children], [0, 0])
        log = session.log_path.read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("SCRIPT ERROR", log)

    def test_camera_worker_stays_closed_and_obeys_stop(self):
        # The real worker and Tk run with camera construction forbidden.
        code = '''
from pathlib import Path
from unittest.mock import patch
from shadowmma.workers import camera
with patch("shadowmma.vision.Camera.__init__", side_effect=AssertionError("Camera opened")):
    camera(port=PORT, stop_file=Path(STOP))
'''
        with tempfile.TemporaryDirectory() as folder:
            token = Path(folder)/"stop"
            token.touch()
            result = subprocess.run([sys.executable, "-c", code.replace("PORT", str(free_port())).replace("STOP", repr(str(token)))], cwd=ROOT, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows job contract")
    def test_killed_supervisor_leaves_no_child(self):
        import ctypes
        from ctypes import wintypes as w
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        api.OpenProcess.restype = w.HANDLE
        api.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        api.CloseHandle.argtypes = [w.HANDLE]
        code = '''
import subprocess,sys,time
from shadowmma.process_job import ProcessJob
job=ProcessJob()
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])
job.add(child)
print(child.pid,flush=True)
time.sleep(30)
'''
        parent = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, stdout=subprocess.PIPE, text=True)
        handle = None
        try:
            pid = int(parent.stdout.readline())
            handle = api.OpenProcess(0x100000, False, pid)
            self.assertTrue(handle)
            parent.terminate()
            parent.wait(timeout=5)
            self.assertEqual(api.WaitForSingleObject(handle, 5000), 0)
        finally:
            if parent.poll() is None:
                parent.terminate()
                parent.wait(timeout=5)
            parent.stdout.close()
            if handle:
                api.CloseHandle(handle)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
