"""In-process Tk integration checks; no screen input, camera or human tests."""
from collections import deque
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch, Mock
from types import SimpleNamespace
import json
import unittest
from shadowmma.app import App
from shadowmma.core import Detector, extract
from camera_samples import landmarks, JAB
from shadowmma.metrics import save_report, Trial
from test_core import frame, armed


class AppTests(unittest.TestCase):
    def test_reprepare_during_hit_delivery_keeps_original_onset_without_crashing(self):
        a = self.app
        a.integrated = True
        a.detector = armed()
        a.detector.update(frame(.6,"left",(0.,0.,-.2)))
        a.pose = Mock()
        a.pose.process.return_value = ([], [])
        a.tower_client = Mock()
        # F10 is consumed by sync_tower after classification in this same frame.
        with patch("shadowmma.app.extract", return_value=frame(.7,"left",(0.,0.,-.5))), \
                patch("shadowmma.app.perf_counter", return_value=.71), \
                patch.object(a,"sync_tower",side_effect=lambda: setattr(a,"detector",None)):
            a.process_frame(None,.7)
        self.assertIsNone(a.detector)
        self.assertEqual(a.tower_client.send_hit.call_args.args[1],.5)

    def test_jab_and_partial_occlusion_never_send_unready_to_game(self):
        a = self.app
        a.tower_client = Mock(status="connected")
        a.camera = SimpleNamespace(close=lambda: None)
        a.detector = Detector(extract(*landmarks(), 0))
        samples = [(i*.1, 0., None) for i in range(7)]
        samples += [(.7+i*.1, factor, hidden) for i, (factor, hidden) in enumerate(JAB)]
        events = []
        for t, factor, hidden in samples:
            a.features = extract(*landmarks(factor, hidden), t)
            hit = a.detector.update(a.features)
            if hit:
                events.append(hit.move)
            with patch("shadowmma.app.perf_counter", return_value=t+.01):
                a.sync_tower()
            self.assertTrue(a.tower_client.poll.call_args.kwargs["ready"])
            if hidden or not a.features.guard:
                self.assertFalse(a.tower_client.poll.call_args.kwargs["guard"])
        self.assertEqual(events, ["left_punch"])
        a.features = extract(*landmarks(hidden=11), 2.)
        with patch("shadowmma.app.perf_counter", return_value=2.01):
            a.sync_tower()
        a.tower_client.poll.assert_called_with(ready=False, guard=False)

    def setUp(self):
        self.app = App()
        self.app.root.withdraw()

    def tearDown(self):
        self.app.close()

    def test_tower_link_starts_without_camera_and_blocks_lab_trials(self):
        client = Mock(status="Kule bağlantısı bekleniyor")
        with patch("shadowmma.app.Camera", side_effect=AssertionError("Camera must remain closed")):
            linked = App(tower_client=client)
            linked.root.withdraw()
            try:
                linked.tick()
                self.assertIsNone(linked.camera)
                self.assertIsNone(linked.pose)
                client.poll.assert_called_with(ready=False, guard=False)
                linked.detector = armed()
                linked.start_test()
                self.assertEqual(linked.phase, "idle")
                self.assertIn("Kule bağlantısı", linked.status.get())
                linked.invalidate_tracking(1., "test tracking loss")
                client.poll.assert_called_with(ready=False, guard=False)
            finally:
                linked.close()
            client.close.assert_called_once()

    def test_test_waits_for_guard_then_requires_explicit_label(self):
        a = self.app
        a.detector = Detector(frame(0))
        a.start_test()
        deadline = a.deadline
        a.advance_trial(deadline+.1)
        self.assertEqual(a.phase, "prepare")
        a.detector = armed()
        a.features = frame(deadline+.2)
        a.advance_trial(deadline+.2)
        self.assertEqual(a.phase, "active")
        a.advance_trial(a.deadline+.1)
        self.assertEqual(a.phase, "confirm")
        self.assertEqual(a.trials, [])
        a.confirm(True)
        self.assertEqual(len(a.trials), 1)
        self.assertFalse(a.trials[0].evaluable)  # no camera samples, not a miss
        self.assertEqual(a.phase, "prepare")

    def test_only_three_simple_choices_and_no_stance_selection(self):
        a = self.app
        self.assertEqual(tuple(a.move_box["values"]), ("Sol yumruk", "Sağ yumruk", "Aşağıdan vur"))
        self.assertFalse(hasattr(a, "stance_box"))

    def test_completed_test_returns_to_free_mode(self):
        a = self.app
        a.detector = armed()
        a.queue = deque()
        a.next_trial()
        self.assertEqual(a.phase, "idle")
        self.assertEqual(str(a.yes["state"]), "disabled")

    def test_restart_preserves_partial_trial_without_scoring_it(self):
        a = self.app
        a.detector = armed()
        a.start_test()
        a.phase = "active"
        a.current.events.append("left_punch")
        a.start_test()
        self.assertEqual(len(a.trials), 1)
        self.assertEqual(a.trials[0].aborted_reason, "test_restarted")
        self.assertFalse(a.trials[0].evaluable)

    def test_last_confirmation_is_not_added_twice(self):
        a = self.app
        a.current = Trial("left_punch", "left_punch")
        a.phase = "confirm"
        a.confirm(True)
        self.assertEqual(len(a.trials), 1)
        self.assertIsNone(a.current)

    def test_new_but_stale_frame_clears_ready_state_and_preview(self):
        a = self.app
        a.detector = armed()
        a.camera_opened_at = 1.
        a.camera = SimpleNamespace(error="", read=lambda: (1, 1., object()), close=lambda: None)
        with patch("shadowmma.app.perf_counter", return_value=2.):
            a.tick()
        self.assertEqual(a.detector.state, "settling")
        self.assertFalse(a.features.valid)
        self.assertIsNone(a.video.image)
        self.assertIn("eski", a.status.get())

    def test_fresh_queued_frame_does_not_send_false_before_processing(self):
        a = self.app
        a.tower_client = Mock(status="Kule bağlı")
        a.detector = armed()
        a.features = frame(1.)
        a.camera_opened_at = a.last_frame_time = 1.
        a.camera = SimpleNamespace(error="", read=lambda: (2, 1.26, object()), close=lambda: None)
        # A delayed GUI callback has a fresh frame waiting in the capture slot.
        with patch("shadowmma.app.perf_counter", return_value=1.27), \
                patch.object(a, "process_frame", side_effect=lambda _pixels, t: setattr(a, "features", frame(t))):
            a.tick()
        readiness = [call.kwargs["ready"] for call in a.tower_client.poll.call_args_list]
        self.assertTrue(readiness)
        self.assertTrue(all(readiness), readiness)

    def test_guard_prompt_disappears_on_tracking_loss_and_returns_on_recovery(self):
        a = self.app
        a.tower_client = Mock(status="Kule bağlı · gardını sabit tut; otomatik başlayacak")
        a.detector = armed()
        a.features = frame(1.)
        a.camera_opened_at = a.last_frame_time = 1.
        a.last_sequence = 1
        a.camera = SimpleNamespace(error="", read=lambda: (1, 1., object()), close=lambda: None)
        with patch("shadowmma.app.perf_counter", return_value=1.01):
            a.tick()
        self.assertIn("otomatik", a.tower_status.get())
        with patch("shadowmma.app.perf_counter", return_value=1.35):
            a.tick()
        a.tower_client.poll.assert_called_with(ready=False, guard=False)
        self.assertNotIn("otomatik", a.tower_status.get())
        self.assertIn("bekleniyor", a.tower_status.get())
        a.features = frame(1.4)
        a.last_frame_time = 1.4
        with patch("shadowmma.app.perf_counter", return_value=1.41):
            a.tick()
        a.tower_client.poll.assert_called_with(ready=True, guard=False)  # Guard must stabilize again.
        self.assertIn("otomatik", a.tower_status.get())

    def test_camera_guard_requires_stable_detector_and_current_guard_without_blocking_punches(self):
        a = self.app
        a.tower_client = Mock(status="connected")
        a.camera = SimpleNamespace(close=lambda: None)
        a.detector = Detector(frame(1.))
        a.features = frame(1.)
        with patch("shadowmma.app.perf_counter", return_value=1.01):
            a.sync_tower()
            a.tower_client.poll.assert_called_with(ready=True, guard=False)
            a.detector = armed()
            a.sync_tower()
            a.tower_client.poll.assert_called_with(ready=True, guard=True)
            a.features = frame(1., guard=False)
            a.sync_tower()
            a.tower_client.poll.assert_called_with(ready=True, guard=True)  # No boxing guard needed.
        with patch("shadowmma.app.perf_counter", return_value=1.4):
            a.sync_tower()
            a.tower_client.poll.assert_called_with(ready=False, guard=False)

    def test_missing_frames_make_confirmed_trial_unassessable(self):
        a = self.app
        a.current = Trial("left_punch", "left_punch", frames=40, valid_frames=40)
        a.phase, a.deadline, a.last_trial_sample = "active", 4., 2.
        a.invalidate_tracking(2.4, "Kamera karesi yok")
        a.advance_trial(4.01)
        a.confirm(True)
        self.assertFalse(a.trials[0].evaluable)
        self.assertGreater(a.trials[0].max_gap_s, 2.)

    def test_report_round_trip_numeric_only_and_stance_specific(self):
        trials = [Trial("left_punch", "left_punch", ["left_punch"], 100, 100, True, stance="orthodox"),
                  Trial("left_punch", "left_punch", [], 100, 100, True, stance="southpaw")]
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/"reports") as folder:
            path = save_report(folder, trials, "southpaw", [20., 30.], [12.], [30.])
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["summary_by_stance"]["orthodox"]["movement_recall"], 1.)
            self.assertEqual(data["summary_by_stance"]["southpaw"]["movement_recall"], 0.)
            self.assertNotIn("landmarks", data)
            self.assertNotIn("frames", data)


if __name__ == "__main__":
    unittest.main()
