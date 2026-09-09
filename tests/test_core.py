"""Synthetic trajectories and negative controls, not human recognition evidence."""
import unittest
from dataclasses import replace
from shadowmma.core import Arm, Features, Calibration, Detector, extract, MOVES
from camera_samples import landmarks


def frame(t, side=None, delta=(0., 0., 0.), elbow=85., guard=False, valid=True, center=(.5, .4)):
    arms = {"left": Arm((.1, .2, -.4), 85., -1.), "right": Arm((-.1, .2, -.4), 85., 1.)}
    if side:
        a = arms[side]
        arms[side] = Arm(tuple(x+y for x, y in zip(a.wrist, delta)), elbow, a.inward_sign)
    return Features(round(t, 6), arms, center, .25, guard, valid, "test visibility lost" if not valid else "", valid)


def armed():
    d = Detector(frame(0))
    for i in range(6):
        d.update(frame(i*.1))
    assert d.state == "ready"
    return d


def punch(d, side="left", upward=False, offset=.6, dt=.1, lateral=False):
    results = []
    for i, factor in enumerate((.25, .55, .85, 1., .95, .6, .2, 0., 0., 0., 0., 0.)):
        delta = (0., -.75*factor, 0.) if upward else (
            ((-.75 if side == "left" else .75)*factor, 0., 0.) if lateral else (0., 0., -.75*factor))
        event = d.update(frame(offset+i*dt, side, delta, elbow=60., guard=False))
        if event:
            results.append(event)
    return results


class DetectorTests(unittest.TestCase):
    def test_three_classes_without_stance_guard_or_straight_elbow(self):
        self.assertEqual(MOVES, ("left_punch", "right_punch", "uppercut"))
        for side in ("left", "right"):
            for upward in (False, True):
                for dt in (.1, .16, .2):
                    events = punch(armed(), side, upward, dt=dt)
                    self.assertEqual([e.move for e in events], ["uppercut" if upward else side+"_punch"])
                    self.assertLessEqual(events[0].confirmed_t, .6+4*dt if upward else .6+2*dt)
                    self.assertTrue(events[0].confirmed)

    def test_image_plane_punches_do_not_require_estimated_forward_depth(self):
        for side in ("left", "right"):
            self.assertEqual([e.move for e in punch(armed(), side, lateral=True)], [side+"_punch"])

    def test_landmarks_classify_all_three_and_ignore_hidden_face_elbows_hips(self):
        for side, upward, expected in (("left",False,"left_punch"), ("right",False,"right_punch"),
                                        ("left",True,"uppercut"), ("right",True,"uppercut")):
            for hidden in (None, 0, 13, 14, 23, 24):
                d = Detector(extract(*landmarks(side=side), 0))
                hits = []
                factors = [0.]*7 + [.25,.55,.85,1.,.6,.2] + [0.]*8
                for i,factor in enumerate(factors):
                    event = d.update(extract(*landmarks(factor, hidden, side=side, upward=upward), i*.1))
                    if event:
                        hits.append(event.move)
                self.assertEqual(hits, [expected], (side,upward,hidden))

    def test_single_frame_spike_and_subthreshold_jitter_never_score(self):
        for amounts in ([.8]+[0.]*12, [.03,.08,.01,.09,0.]*6):
            d = armed()
            for i,amount in enumerate(amounts):
                self.assertIsNone(d.update(frame(.6+i*.1, "left", (0.,0.,-amount))))

    def test_held_extension_scores_immediately_once_and_never_rearms(self):
        d = armed()
        amounts = [.2,.5,.8]+[.8]*100
        hits = [d.update(frame(.6+i*.1, "left", (0.,0.,-a))) for i,a in enumerate(amounts)]
        self.assertEqual([h.move for h in hits if h], ["left_punch"])
        self.assertEqual(d.state, "cooldown")

    def test_return_and_idle_do_not_duplicate_then_second_hand_can_punch(self):
        d = armed()
        self.assertEqual(len(punch(d)),1)
        for i in range(15):
            self.assertIsNone(d.update(frame(1.8+i*.1)))
        self.assertEqual([e.move for e in punch(d,"right",offset=3.3)],["right_punch"])

    def test_partial_release_rearms_without_exact_start_pose(self):
        d = armed()
        for t,a in ((.6,.2),(.7,.5),(.8,.8),(.9,.5),(1.,.22)):
            d.update(frame(t,"left",(0.,0.,-a)))
        for i in range(8):
            self.assertIsNone(d.update(frame(1.1+i*.1,"left",(0.,0.,-.22))))
        self.assertEqual(d.state,"ready")

    def test_body_translation_without_relative_hand_movement_is_not_a_hit(self):
        d = armed()
        for i in range(30):
            self.assertIsNone(d.update(frame(.6+i*.1,center=(.2+i*.02,.4))))
        self.assertEqual(d.state,"ready")
        # No return to a room marker or recalibration needed.
        hits=[]
        for i,a in enumerate((.2,.5,.8)):
            hit=d.update(frame(3.6+i*.1,"left",(0.,0.,-a),center=(.8,.4)))
            if hit:
                hits.append(hit.move)
        self.assertEqual(hits,["left_punch"])

    def test_tracking_loss_cannot_supply_direction_evidence_or_score_return(self):
        d=armed()
        d.update(frame(.6,"left",(0.,0.,-.2)))
        self.assertIsNone(d.update(frame(.7,valid=False)))
        self.assertIsNone(d.update(frame(.8,"left",(0.,0.,-.8))))
        for i in range(15):
            self.assertIsNone(d.update(frame(.9+i*.1)))
        self.assertEqual(d.state,"ready")
        self.assertIn("Takip kuruldu",d.last_result)

    def test_stale_duplicate_time_and_implausible_jump_reset(self):
        for t in (1.5,.5,.51):
            d=armed()
            self.assertIsNone(d.update(frame(t,"left",(0.,0.,-.8))))
            self.assertEqual(d.state,"settling")

    def test_both_hands_raise_or_extend_is_ambiguous(self):
        for upward in (True,False):
            d=armed()
            for i,a in enumerate((.2,.5,.8,.5,0.,0.,0.,0.)):
                f=frame(.6+i*.1,"left",(0.,-a,0.) if upward else (0.,0.,-a))
                arms=dict(f.arms)
                arms["right"]=replace(arms["right"],wrist=(-.1,.2-a,-.4) if upward else (-.1,.2,-.4-a))
                self.assertIsNone(d.update(replace(f,arms=arms)))

    def test_downward_and_backward_release_are_not_punches(self):
        for delta in ((0.,1.,0.),(0.,0.,1.)):
            d=armed()
            for i in range(20):
                self.assertIsNone(d.update(frame(.6+i*.1,"left",tuple(v*min(i*.05,.8) for v in delta))))

    def test_moving_on_initial_tracking_waits_for_still_hands(self):
        d=Detector(frame(0))
        for i in range(10):
            self.assertIsNone(d.update(frame(i*.1,"left",(0.,0.,-.08*i))))
        self.assertNotEqual(d.state,"ready")

    def test_short_direction_check_is_preserved_for_report(self):
        d=armed()
        d.update(frame(.6,"left",(0.,0.,-.12)))
        self.assertFalse(d.checks["left"]["mesafe_yeterli"])
        hit=d.update(frame(.7,"left",(0.,0.,-.5)))
        self.assertIsNotNone(hit)
        self.assertTrue(d.checks["left"]["ardisik_hareket"])

    def test_changed_resting_hand_position_recovers_without_recalibration(self):
        d = armed()
        for i in range(20):
            self.assertIsNone(d.update(frame(.6+i*.1,"left",(0.,.25,0.))))
        self.assertEqual(d.state,"ready")
        self.assertEqual(d.start_arms["left"].wrist[1],.45)


class CalibrationTests(unittest.TestCase):
    def test_relaxed_hands_prepare_in_under_one_second_at_observed_low_fps(self):
        c=Calibration()
        for i in range(7):
            progress=c.update(frame(i/7.49,guard=False))
        self.assertEqual(progress,1.)
        self.assertIsNotNone(c.baseline)

    def test_moving_or_invisible_hands_and_sparse_frames_cannot_prepare(self):
        for mode in ("moving","invisible","sparse"):
            c=Calibration()
            for i in range(10):
                c.update(frame(i*(.3 if mode=="sparse" else .1),"left",(0.,0.,i*.2 if mode=="moving" else 0.),valid=mode!="invisible"))
            self.assertIsNone(c.baseline)

    def test_screen_translation_does_not_restart_preparation(self):
        c=Calibration()
        for i in range(10):
            c.update(frame(i*.1,center=(.2+i*.03,.4)))
        self.assertIsNotNone(c.baseline)


class FeatureTests(unittest.TestCase):
    def test_only_shoulders_and_hands_required(self):
        for hidden in (0,13,14,23,24):
            self.assertTrue(extract(*landmarks(hidden=hidden),1.).valid)
        for hidden in (15,16):
            f=extract(*landmarks(hidden=hidden),1.)
            self.assertFalse(f.valid)
            self.assertTrue(f.body_tracked)
            self.assertEqual(f.arms,{})
        for hidden in (11,12):
            self.assertFalse(extract(*landmarks(hidden=hidden),1.).body_tracked)

    def test_unreliable_or_clipped_hands_are_not_exposed(self):
        self.assertFalse(extract([],[],0.).valid)
        for attr,value in (("x",.999),("visibility",.2),("presence",.2)):
            image,world=landmarks()
            setattr(image[15],attr,value)
            self.assertFalse(extract(image,world,0).valid)
        image,world=landmarks()
        world[15].z=float("nan")
        self.assertFalse(extract(image,world,0).valid)

    def test_extraction_removes_shared_translation_and_scale(self):
        image,world=landmarks()
        base=extract(image,world,0)
        for p in image:
            p.x=.5+(p.x-.5)*.8+.05
            p.y=.5+(p.y-.5)*.8
        for p in world:
            p.x=p.x*.8+.1
            p.y*=.8
            p.z=p.z*.8+.2
        f=extract(image,world,1)
        for s in f.arms:
            for a,b in zip(base.arms[s].wrist,f.arms[s].wrist):
                self.assertAlmostEqual(a,b)


if __name__=="__main__":
    unittest.main()
