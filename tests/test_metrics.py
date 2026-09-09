import unittest
from shadowmma.metrics import Trial, summarize


def trial(expected, events, confirmed=True, valid=100):
    return Trial(expected, expected, events=events, frames=100, valid_frames=valid, confirmed=confirmed)


class MetricTests(unittest.TestCase):
    def test_unknown_accuracy_has_no_fake_zero(self):
        s = summarize([])
        self.assertIsNone(s["trial_accuracy"])
        self.assertIsNone(s["latency"]["frame_received_to_tk_submission"]["p95_ms"])
        self.assertIsNone(s["latency"]["optical_end_to_end_ms_user_measured"])

    def test_miss_wrong_false_positive_and_duplicate_are_separate(self):
        s = summarize([trial("left_punch", ["left_punch"]), trial("right_punch", []), trial("uppercut", ["left_punch"]),
                       trial("uppercut", ["uppercut", "uppercut"]), trial("none", ["left_punch"]),
                       trial("none", [])])
        self.assertEqual(s["exact_movement_accuracy"], .25)
        self.assertEqual(s["missed_expected_movements"], 2)
        self.assertEqual(s["wrong_class_trials"], 1)
        self.assertEqual(s["false_positive_negative_trials"], 1)
        self.assertEqual(s["extra_events"], 1)
        self.assertEqual(s["event_precision"], .4)

    def test_unconfirmed_and_low_visibility_excluded(self):
        s = summarize([trial("left_punch", [], False), trial("left_punch", [], valid=40), trial("left_punch", ["left_punch"])])
        self.assertEqual(s["skipped_trials"], 1)
        self.assertEqual(s["unassessable_trials"], 1)
        self.assertEqual(s["missed_expected_movements"], 0)

    def test_camera_stall_excluded_even_if_visible_frames_good(self):
        t = trial("left_punch", [])
        t.max_gap_s = .7
        self.assertFalse(t.evaluable)

    def test_aborted_trial_is_neither_skip_nor_miss(self):
        t = trial("left_punch", [])
        t.aborted_reason = "camera_error"
        s = summarize([t])
        self.assertEqual(s["aborted_trials"], 1)
        self.assertEqual(s["skipped_trials"], 0)
        self.assertEqual(s["missed_expected_movements"], 0)
        self.assertEqual(s["evaluable_trials"], 0)


if __name__ == "__main__":
    unittest.main()
