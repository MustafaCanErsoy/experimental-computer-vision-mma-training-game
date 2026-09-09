"""Invented regressions for small and rising punches; no real landmark replay."""
import unittest
from test_core import armed, frame


def trajectory(points, side="left", dt=.13):
    d = armed()
    hits = []
    for i, point in enumerate(points + [(0., 0., 0.)]*10):
        hit = d.update(frame(.6+i*dt, side, point))
        if hit:
            hits.append(hit)
    return hits


class SensitivityTests(unittest.TestCase):
    def test_upward_candidate_does_not_survive_missing_hand(self):
        d=armed()
        self.assertIsNone(d.update(frame(.6,"left",(0.,-.16,0.))))
        self.assertIsNone(d.update(frame(.73,"left",(0.,-.40,0.))))
        self.assertIsNotNone(d.up_pending)
        self.assertIsNone(d.update(frame(.86,valid=False)))
        for i in range(10):
            self.assertIsNone(d.update(frame(.99+i*.13)))

    def test_two_axes_combine_without_requiring_large_single_axis(self):
        points=[(.07,0.,-.07),(.12,0.,-.12),(.17,0.,-.17),(.12,0.,-.12)]
        self.assertEqual([h.move for h in trajectory(points)],["left_punch"])

    def test_small_forward_and_sideways_punches(self):
        for side in ("left", "right"):
            for dt in (.10, .13, .20):
                for lateral in (False, True):
                    points = [(x,0.,0.) if lateral else (0.,0.,-x) for x in (.09,.16,.26,.26,.14)]
                    self.assertEqual([h.move for h in trajectory(points,side,dt)], [side+"_punch"])

    def test_upward_start_does_not_steal_a_forward_punch(self):
        # A relaxed hand first rises, then extends forward. Old code emitted
        # uppercut before the forward part was visible.
        points = [(0.,-.25,-.03),(0.,-.42,-.05),(0.,-.50,-.24),
                  (0.,-.55,-.36),(0.,-.30,-.20)]
        for side in ("left","right"):
            self.assertEqual([h.move for h in trajectory(points,side)], [side+"_punch"])

    def test_short_upward_strike_need_not_hold_peak(self):
        for side in ("left","right"):
            self.assertEqual([h.move for h in trajectory([(0.,-.16,0.),(0.,-.34,0.),(0.,-.14,0.)],side)], ["uppercut"])

    def test_jitter_and_one_visible_spike_still_do_not_count(self):
        for points in ([ (0.,0.,-x) for x in (.03,.08,.02,.09,.03)],
                       [(0.,-.5,0.)],[(0.,0.,-.5)]):
            self.assertEqual(trajectory(points), [])

    def test_other_hand_can_shift_a_little_without_canceling_punch(self):
        from dataclasses import replace
        d=armed()
        hits=[]
        for i,x in enumerate((.09,.16,.26,.26,.14,0.,0.,0.)):
            f=frame(.6+i*.13,"left",(0.,0.,-x))
            arms=dict(f.arms)
            arms["right"]=replace(arms["right"],wrist=(-.1,.2,-.4-x*.72))
            hit=d.update(replace(f,arms=arms))
            if hit: hits.append(hit.move)
        self.assertEqual(hits,["left_punch"])

    def test_two_equal_hands_are_not_a_single_punch(self):
        from dataclasses import replace
        d=armed()
        for i,x in enumerate((.09,.16,.24,.26,.14,0.,0.,0.)):
            f=frame(.6+i*.13,"left",(0.,0.,-x))
            arms=dict(f.arms)
            arms["right"]=replace(arms["right"],wrist=(-.1,.2,-.4-x))
            self.assertIsNone(d.update(replace(f,arms=arms)))
