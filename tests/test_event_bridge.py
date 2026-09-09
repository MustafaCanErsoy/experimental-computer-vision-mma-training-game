"""No-camera protocol and real Detector -> numeric adapter regressions."""
import json
import socket
import unittest
from unittest.mock import patch

from shadowmma.core import Hit
from shadowmma.event_bridge import EventClient
from test_core import armed, punch


class EventBridgeTests(unittest.TestCase):
    def test_game_receipt_requires_matching_sent_event_and_rejects_replays(self):
        self.now = 10.1
        self.client.send_hit(Hit("left_punch", 10.02, 10.09, 150.), 10.01)
        p = {"v": 1, "type": "receipt", "source": "camera", "client": self.client.client,
             "session": "session", "link": "link", "event": 1, "outcome": "wrong"}
        self.assertFalse(self.client.accept_receipt({**p, "event": True}))
        self.assertFalse(self.client.accept_receipt({**p, "link": "old"}))
        self.assertTrue(self.client.accept_receipt(p))
        self.assertFalse(self.client.accept_receipt(p))
        self.assertEqual(self.client.diagnostics[-1]["outcome"], "wrong")
        self.assertEqual(self.client.diagnostics[-1]["expected"], "right_punch")

    def test_missing_receipt_is_unknown_not_claimed_as_score(self):
        self.now = 10.1
        self.client.send_hit(Hit("left_punch", 10.02, 10.09, 150.), 10.01)
        self.now = 12.
        self.client.poll()
        self.assertEqual(self.client.diagnostics[-1]["outcome"], "unconfirmed")
        self.assertEqual(self.client.pending_hits, {})

    def test_controls_are_bound_to_session_and_not_replayed(self):
        p = {"v": 1, "type": "control", "source": "camera", "client": self.client.client,
             "session": "session", "link": "link", "id": 1, "action": "frames_on"}
        self.assertFalse(self.client.accept_control({**p, "session": "old"}))
        self.assertFalse(self.client.accept_control({**p, "action": "upload"}))
        self.assertTrue(self.client.accept_control(p))
        self.assertFalse(self.client.accept_control(p))
        self.assertEqual(list(self.client.commands), ["frames_on"])

    def test_turkish_diagnostic_fits_packet_and_carries_no_images(self):
        self.client.publish_diagnostic("Görüntü şüpheli "*30, "Sayılmadı "*30, True)
        raw, _ = self.server.recvfrom(1024)
        p = json.loads(raw)
        self.assertEqual(p["type"], "diagnostic")
        self.assertTrue(p["recording"])
        self.assertLessEqual(len(raw), 1024)
        self.assertNotIn("images", p)

    def setUp(self):
        self.now = 10.
        self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server.bind(("127.0.0.1", 0))
        self.server.settimeout(.2)
        self.client = EventClient("camera", self.server.getsockname()[1], clock=lambda: self.now)
        self.state = {"v": 1, "type": "state", "source": "camera", "client": self.client.client,
                      "session": "session", "link": "link", "lease": 1, "encounter": "session:1",
                      "prompt": "1", "phase": "fight", "paused": False, "move": "right_punch"}
        self.client.accept_state(self.state, self.now)
        self.client.last_ready = True

    def tearDown(self):
        self.client.close()
        self.server.close()

    def test_observed_class_and_numeric_whitelist_over_real_loopback(self):
        self.now = 10.1
        self.assertTrue(self.client.send_hit(Hit("left_punch", 10.02, 10.09, 150.), 10.01))
        raw, peer = self.server.recvfrom(1024)
        packet = json.loads(raw)
        self.assertEqual(peer[0], "127.0.0.1")
        self.assertEqual(packet["move"], "left_punch")  # Godot requested cross; no class substitution.
        self.assertEqual(set(packet), {"v", "type", "source", "client", "link", "lease", "event",
                                       "encounter", "prompt", "move", "age_ms"})

    def test_prompt_change_during_motion_drops_hit(self):
        self.now = 10.1
        self.client.accept_state({**self.state, "lease": 2, "prompt": "2"}, self.now)
        self.assertFalse(self.client.send_hit(Hit("left_punch", 10.08, 10.1, 150.), 10.01))

    def test_expired_paused_future_and_invalid_hits_are_not_queued(self):
        self.now = 10.1
        invalid = [Hit("left_punch", 10.01, 10.2, 150.), Hit("unknown", 10.01, 10.09, 0.),
                   Hit("left_punch", float("nan"), 10.09, 0.), Hit("left_punch", 10.01, 10.09, 0., False)]
        for hit in invalid:
            self.assertFalse(self.client.send_hit(hit, 10.0))
        self.client.context["paused"] = True
        self.assertFalse(self.client.send_hit(Hit("left_punch", 10.01, 10.09, 0.), 10.0))
        self.client.context["paused"] = False
        self.now = 11.
        self.assertFalse(self.client.send_hit(Hit("left_punch", 10.01, 10.09, 0.), 10.0))
        self.assertEqual(self.client.event, 0)

    def test_state_reordering_restart_and_retired_sessions(self):
        self.assertTrue(self.client.accept_state({**self.state, "lease": 3}, 10.1))
        self.assertFalse(self.client.accept_state({**self.state, "lease": 2}, 10.2))
        self.assertTrue(self.client.accept_state({**self.state, "session": "new", "lease": 1}, 10.3))
        self.assertFalse(self.client.accept_state({**self.state, "lease": 99}, 10.4))
        self.assertEqual(self.client.context["session"], "new")

    def test_results_stop_hits_and_restart_requires_new_motion(self):
        self.now = 10.1
        self.assertTrue(self.client.accept_state(
            {**self.state, "lease": 2, "prompt": "2", "phase": "results"}, self.now))
        self.assertIn("Tırmanış bitti", self.client.status)
        self.assertFalse(self.client.send_hit(Hit("left_punch", 10.1, 10.1, 0.), 10.1))
        self.now = 10.2
        self.assertTrue(self.client.accept_state(
            {**self.state, "session": "new-run", "link": "new-link", "lease": 1}, self.now))
        self.now = 10.3
        self.assertFalse(self.client.send_hit(Hit("left_punch", 10.2, 10.3, 0.), 10.1))
        self.assertTrue(self.client.send_hit(Hit("left_punch", 10.25, 10.3, 0.), 10.21))
        self.assertFalse(self.client.accept_state({**self.state, "lease": 99}, self.now))

    def test_malformed_states_never_replace_context(self):
        for data in ([], {**self.state, "image": "no"}, {**self.state, "lease": True},
                     {**self.state, "source": "synthetic"}, {**self.state, "paused": 1},
                     {**self.state, "prompt": []}, {**self.state, "v": True}):
            self.assertFalse(self.client.accept_state(data, 10.2))
        self.assertEqual(self.client.last_lease, 1)

    def test_timeout_clears_context_and_restarts_hello(self):
        self.now = 11.
        self.client.poll(True)
        packet = json.loads(self.server.recvfrom(1024)[0])
        self.assertEqual(packet["type"], "hello")
        self.assertIsNone(self.client.context)

    def test_fresh_lease_does_not_change_motion_context_start(self):
        self.client.accept_state({**self.state, "lease": 2}, 10.1)
        self.assertEqual(self.client.context_since, 10.)
        self.now = 10.2
        self.assertTrue(self.client.send_hit(Hit("left_punch", 10.05, 10.18, 0.), 10.02))

    def test_source_not_ready_cannot_emit(self):
        self.client.last_ready = False
        self.now = 10.1
        self.assertFalse(self.client.send_hit(Hit("left_punch", 10.02, 10.09, 0.), 10.01))

    def test_paused_connection_does_not_advertise_resume_when_unready(self):
        self.client.context["paused"] = True
        self.client.last_ready = False
        self.assertNotIn("P ile devam", self.client.status)
        self.client.last_ready = True
        self.assertIn("otomatik", self.client.status)
        self.assertNotIn("P ile devam", self.client.status)
        self.client.source = "synthetic"
        self.assertIn("P ile devam", self.client.status)

    def test_camera_guard_is_a_separate_ordered_numeric_message(self):
        self.now = 10.1
        self.client.poll(ready=True, guard=True)
        pulse = json.loads(self.server.recvfrom(1024)[0])
        guard = json.loads(self.server.recvfrom(1024)[0])
        self.assertEqual(pulse["type"], "pulse")
        self.assertNotIn("guard", pulse)
        self.assertEqual(set(guard), {"v", "type", "source", "client", "link", "lease", "event", "held"})
        self.assertTrue(guard["held"])
        self.now += .01
        self.client.poll(ready=False, guard=True)
        self.server.recvfrom(1024)
        lost = json.loads(self.server.recvfrom(1024)[0])
        self.assertFalse(lost["held"])
        self.assertGreater(lost["event"], guard["event"])

    def test_detector_class_is_forwarded_without_requested_input(self):
        detector = armed()
        self.client.context_since = 0.
        # Same real heuristic cycle as core tests, no camera or target supplied to Detector.
        hits = punch(detector)
        self.assertEqual(len(hits), 1)
        self.now = hits[0].confirmed_t
        self.client.last_received = self.now
        with patch.object(self.client, "send", return_value=True) as send:
            self.assertTrue(self.client.send_hit(hits[0], detector.started))
            self.assertEqual(send.call_args.args[0]["move"], hits[0].move)


if __name__ == "__main__":
    unittest.main()
