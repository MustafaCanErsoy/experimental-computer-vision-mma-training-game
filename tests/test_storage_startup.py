"""Local-only regressions for incomplete installs and interrupted report writes."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from shadowmma.assets import ROOT, validate_model
from shadowmma.metrics import atomic_json


class StartupStorageTests(unittest.TestCase):
    def test_tower_cli_does_not_import_camera_dependencies(self):
        code = '''
import sys
from unittest.mock import patch
from shadowmma.__main__ import main
with patch("sys.argv", ["shadowmma", "--tower-demo"]), patch("shadowmma.tower_launcher.launch", return_value=0) as launch:
    assert main() == 0
    launch.assert_called_once_with()
assert not {"cv2", "mediapipe", "shadowmma.vision", "shadowmma.app"}.intersection(sys.modules)
'''
        result = subprocess.run([sys.executable, "-S", "-c", code],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_help_does_not_need_installed_vision_packages(self):
        result = subprocess.run([sys.executable, "-S", "-m", "shadowmma", "--help"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--camera", result.stdout)

    def test_missing_dependencies_offer_setup_instead_of_traceback(self):
        result = subprocess.run([sys.executable, "-S", "-m", "shadowmma"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Kurulum.cmd", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_invalid_camera_index_exits_before_opening_camera(self):
        result = subprocess.run([sys.executable, "-S", "-m", "shadowmma", "--camera", "-1"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("sifir", result.stderr)

    def test_bad_or_missing_model_has_actionable_error(self):
        with TemporaryDirectory(dir=ROOT/"reports") as folder:
            path = Path(folder)/"model.task"
            with self.assertRaisesRegex(FileNotFoundError, "Kurulum.cmd"):
                validate_model(path)
            path.write_bytes(b"broken model")
            with self.assertRaisesRegex(ValueError, "Kurulum.cmd"):
                validate_model(path)

    def test_atomic_report_failure_leaves_previous_report_and_no_temp(self):
        with TemporaryDirectory(dir=ROOT/"reports") as folder:
            path = Path(folder)/"session.json"
            atomic_json(path, {"value": "önceki"})
            with patch("shadowmma.metrics.os.replace", side_effect=OSError("disk unavailable")):
                with self.assertRaises(OSError):
                    atomic_json(path, {"value": "yeni"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"value": "önceki"})
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_nonfinite_report_data_is_rejected_before_file_write(self):
        with TemporaryDirectory(dir=ROOT/"reports") as folder:
            path = Path(folder)/"session.json"
            with self.assertRaises(ValueError):
                atomic_json(path, {"value": float("nan")})
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
