import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from shadowmma.diagnostics import RecognitionReport, render_html
from shadowmma.core import Calibration
from test_core import frame, armed
from shadowmma.app import App


class ReportTests(unittest.TestCase):
    def test_progress_is_whitelisted_and_wrong_target_has_its_own_total(self):
        self.report.add("motion","progress",measures={"hareket_yuzdesi":75,"ileri_yuzdesi":65,
                        "wrist_x":.25,"yukari_yuzdesi":float("nan"),"yana_yuzdesi":True})
        self.assertEqual(self.report.events[-1]["measures"],{"hareket_yuzdesi":75,"ileri_yuzdesi":65})
        self.report.add("game","wrong class",detail="wrong")
        self.assertEqual(self.report.counts["wrong_target"],1)
        self.assertEqual(self.report.counts["scored"],0)

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.folder = Path(self.temporary.name) / "deneme"
        self.now = 10.
        self.report = RecognitionReport(self.folder, clock=lambda: self.now)

    def tearDown(self):
        self.report.close()
        self.temporary.cleanup()

    def test_default_never_saves_pixels_and_jsonl_survives_without_final_flush(self):
        self.report.observe(np.zeros((48, 64, 3), dtype=np.uint8), valid=True, body=True, guard=True)
        self.report.add("detected", "Sol yumruk", move="left_punch", evidence=True)
        self.assertEqual(list(self.folder.glob("*.jpg")), [])
        rows = [json.loads(line) for line in (self.folder / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[-1]["move"], "left_punch")
        self.assertNotIn("landmarks", str(rows))
        self.assertEqual(len(self.report.buffer), 0)

    def test_visual_opt_in_has_limits_and_stops_collecting_when_disabled(self):
        r = self.report
        r.MAX_IMAGES = 3
        r.set_frames(True)
        for i in range(20):
            self.now += .2
            r.observe(np.full((480, 640, 3), i, dtype=np.uint8), valid=True, body=True, guard=False)
        self.assertEqual(len(r.buffer), 8)
        r.add("candidate", "Uzanış", evidence=True)
        r.add("detected", "Sol yumruk", evidence=True)
        self.assertEqual(r.images, 3)
        self.assertEqual(len(list(self.folder.glob("*.jpg"))), 3)
        from PIL import Image
        for p in self.folder.glob("*.jpg"):
            with Image.open(p) as image:
                self.assertEqual(image.size, (480, 360))
        r.set_frames(False)
        self.assertEqual(len(r.buffer), 0)
        r.observe(np.zeros((48, 64, 3), dtype=np.uint8), valid=False, body=False, guard=False)
        r.add("rejected", "Kayıp", evidence=True)
        self.assertEqual(r.events[-1]["images"], [])

    def test_event_limit_keeps_summary_counts_and_bounded_journal(self):
        self.report.MAX_EVENTS = 3
        for _ in range(10):
            self.report.add("detected", "Sol yumruk", move="left_punch")
        self.assertEqual(len(self.report.events), 3)
        self.assertEqual(self.report.counts["detected"], 10)
        self.assertEqual(self.report.dropped, 8)

    def test_disk_failure_does_not_raise_into_camera_loop(self):
        with patch("shadowmma.diagnostics.atomic_json", side_effect=OSError("disk full")):
            self.report.flush(force=True)
        self.assertIn("disk full", self.report.error)
        self.report.add("tracking", "Takip sürüyor")

    def test_existing_report_directory_is_never_overwritten(self):
        original = self.report.path.read_bytes()
        other = RecognitionReport(self.folder)
        other.add("detected", "Different session")
        other.close()
        self.assertTrue(other.error)
        self.assertEqual(self.report.path.read_bytes(), original)

    def test_slow_snapshot_does_not_block_observations_or_accumulate_jobs(self):
        from threading import Event
        release, started = Event(), Event()
        r = RecognitionReport(Path(self.temporary.name)/"async", async_writes=True)
        original = r._write_snapshot
        def slow(data):
            started.set()
            release.wait(3.)
            original(data)
        try:
            with patch.object(r, "_write_snapshot", side_effect=slow):
                r.last_write = -10.
                r.flush()
                self.assertTrue(started.wait(1.))
                first = r.future
                self.assertFalse(first.done())
                r.add("detected", "Sol yumruk", move="left_punch")
                r.last_write = -10.
                r.flush()
                self.assertIs(r.future, first)
                self.assertEqual(r.counts["detected"], 1)
                release.set()
                r.close()
            final = json.loads((r.folder/"report.json").read_text(encoding="utf-8"))
            self.assertTrue(final["closed"])
            self.assertEqual(final["counts"]["detected"], 1)
        finally:
            release.set()
            r.close()

    def test_html_embedded_data_cannot_close_script_or_inject_markup(self):
        self.report.add("tracking", '</script><img src=x onerror="alert(1)">')
        self.report.flush(force=True)
        html = self.report.path.read_text(encoding="utf-8")
        self.assertNotIn('</script><img src=x', html)
        self.assertIn('\\u003c/script>', html)
        self.report.close()
        data = json.loads((self.folder / "report.json").read_text(encoding="utf-8"))
        self.assertTrue(data["closed"])
        self.assertEqual(data["events"][-1]["title"], "Seans kapandı")


class AutomaticReportingTests(unittest.TestCase):
    def test_subsecond_motion_evidence_and_all_three_totals_are_preserved(self):
        from test_core import punch
        with TemporaryDirectory() as folder:
            a = App(integrated=True, report_dir=Path(folder)/"session")
            try:
                a.detector = armed()
                for t, distance in ((.6,.12),(.7,.26)):
                    before = a.detector.state
                    hit = a.detector.update(frame(t,"left",(0.,0.,-distance)))
                    a.record_detection(before, hit)
                rows = [r for r in a.report.events if r["kind"] == "motion"]
                self.assertEqual(len(rows), 2)
                self.assertFalse(rows[0]["checks"]["left"]["mesafe_yeterli"])
                self.assertTrue(rows[1]["checks"]["left"]["mesafe_yeterli"])
                self.assertEqual(rows[0]["measures"]["hareket_yuzdesi"],60)
                self.assertEqual(rows[1]["measures"]["hareket_yuzdesi"],130)
                self.assertEqual(a.report.counts["move_left_punch"], 1)
                self.assertFalse(a.active_attempt)
            finally:
                a.close()

    def test_calibration_progress_waits_for_enough_samples(self):
        c = Calibration()
        for i in range(4):
            progress = c.update(frame(i/7.49))
        self.assertLess(progress, 1.)
        self.assertIsNone(c.baseline)
        for i in range(4, 7):
            progress = c.update(frame(i/7.49))
        self.assertEqual(progress, 1.)
        self.assertIsNotNone(c.baseline)

    def test_automatic_mode_opens_fake_camera_calibrates_without_buttons_and_closes(self):
        with TemporaryDirectory() as folder:
            with patch("shadowmma.app.Camera") as camera, patch("shadowmma.app.Pose") as pose:
                camera.return_value.error = ""
                camera.return_value.read.return_value = None
                a = App(auto_start=True, integrated=True, report_dir=Path(folder)/"session")
                try:
                    a.root.update()
                    a.start_automatic()  # Idempotent after scheduled startup.
                    camera.assert_called_once_with(0)
                    pose.assert_called_once_with()
                    self.assertIsNotNone(a.calibration)
                    self.assertEqual(a.root.state(), "withdrawn")
                finally:
                    a.close()
                camera.return_value.close.assert_called_once()
                pose.return_value.close.assert_called_once()
                self.assertTrue(json.loads((Path(folder)/"session/report.json").read_text(encoding="utf-8"))["closed"])

    def test_single_frame_extension_is_reported_once_as_rejected_attempt(self):
        with TemporaryDirectory() as folder:
            a = App(integrated=True, report_dir=Path(folder)/"session")
            try:
                a.detector = armed()
                for f in [frame(.6, "left", (0.,0.,-.8), 165., False)] + [frame(.7+i*.1) for i in range(15)]:
                    before = a.detector.state
                    hit = a.detector.update(f)
                    a.record_detection(before, hit)
                rows = a.report.events
                rejected = [r for r in rows if r["kind"] == "rejected"]
                self.assertEqual(len(rejected), 1)
                self.assertEqual(rejected[0]["attempt"], 1)
                self.assertIn("belirginleşmeden", rejected[0]["title"])
                self.assertEqual(a.report.counts["detected"], 0)
            finally:
                a.close()
