"""Three simple motion controls; human accuracy is unvalidated."""
from dataclasses import dataclass, field
from math import sqrt, isfinite
from statistics import median

MOVES = ("left_punch", "right_punch", "uppercut")
LABELS = {"left_punch": "Sol yumruk", "right_punch": "Sağ yumruk", "uppercut": "Aşağıdan vur",
          "raise_hands": "İki eli birlikte kaldır", "walk": "Yerinde / yana adım",
          "return_guard": "Elleri serbest bırak"}
RULESET = "simple-motion-v2"


def norm(v):
    return sqrt(sum(x*x for x in v))


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


@dataclass(frozen=True)
class Arm:
    wrist: tuple[float, float, float]  # shoulder-relative image x/y and estimated world z
    angle: float = 0.  # legacy measurement slot, no form/angle requirement
    inward_sign: float = 1.


@dataclass(frozen=True)
class Features:
    t: float
    arms: dict[str, Arm]
    center: tuple[float, float]
    width: float
    guard: bool  # legacy field: visible hands, not a boxing posture
    valid: bool = True
    reason: str = ""
    body_tracked: bool = False


def extract(image, world, t):
    """Anatomical hands before preview mirroring. No face/elbow/hip requirement."""
    def invalid(reason):
        return Features(t, {}, (0., 0.), 0., False, False, reason)
    if not image or not world or len(image) != 33 or len(world) != 33:
        return invalid("Vücut bulunamadı; omuzların ve ellerin görünsün.")
    def visible(i):
        p, w = image[i], world[i]
        return (all(isfinite(v) for v in (p.x, p.y, p.visibility, p.presence, w.x, w.y, w.z))
                and min(p.visibility, p.presence) >= .65
                and .025 < p.x < .975 and .025 < p.y < .975)
    if not all(visible(i) for i in (11, 12)):
        return invalid("Omuzlar takip edilemiyor; kameraya dön.")
    width = abs(image[11].x-image[12].x)
    if not .10 < width < .65:
        return invalid("Kameraya önden dön; iki omzun görünsün.")
    xyz = lambda i: (world[i].x, world[i].y, world[i].z)
    scale = norm(sub(xyz(11), xyz(12)))
    if not .15 < scale < .8:
        return invalid("Vücut ölçeği güvenilir değil.")
    center = ((image[11].x+image[12].x)/2, (image[11].y+image[12].y)/2)
    missing = [name for i, name in ((15, "sol el"), (16, "sağ el")) if not visible(i)]
    if missing:
        return Features(t, {}, center, width, False, False, "Net görünmüyor: " + ", ".join(missing) + ".", True)
    arms = {}
    for side, s, w, other in (("left", 11, 15, 12), ("right", 12, 16, 11)):
        rel = ((image[w].x-image[s].x)/width, (image[w].y-image[s].y)/width,
               (world[w].z-world[s].z)/scale)
        arms[side] = Arm(rel, inward_sign=1. if image[other].x > image[s].x else -1.)
    return Features(t, arms, center, width, True, body_tracked=True)


@dataclass
class Calibration:
    samples: list[Features] = field(default_factory=list)
    baseline: Features | None = None
    seconds: float = .6
    min_samples: int = 4

    def update(self, f):
        if not f.valid:
            self.samples.clear()
            return 0.
        if self.samples:
            prev, first = self.samples[-1], self.samples[0]
            if (not 0 < f.t-prev.t <= .25 or abs(f.width/prev.width-1) > .25
                    or any(norm(sub(f.arms[s].wrist, first.arms[s].wrist)) > .22 for s in f.arms)):
                self.samples.clear()
        self.samples.append(f)
        elapsed = f.t-self.samples[0].t
        if elapsed >= self.seconds and len(self.samples) >= self.min_samples:
            arms = {s: Arm(tuple(median(x.arms[s].wrist[i] for x in self.samples) for i in range(3)),
                           inward_sign=f.arms[s].inward_sign) for s in f.arms}
            self.baseline = Features(f.t, arms, f.center, f.width, True, body_tracked=True)
        return min(1., elapsed/self.seconds, len(self.samples)/self.min_samples)


@dataclass(frozen=True)
class Hit:
    move: str
    peak_t: float
    confirmed_t: float
    angle: float = 0.
    confirmed: bool = True


class Detector:
    """Settle -> visible directional travel -> one event -> partial release.

    No target, stance, elbow angle, guard or fixed room position enters the
    classification. Two coherent observations reject an isolated landmark spike;
    the earlier may be partway out, so the peak need not be held. After a hit,
    partial return then settled hands prevents scoring the release or held pose.
    """
    PUNCH_DISTANCE = .20
    UP_DISTANCE = .30
    UP_DECISION_SECONDS = .28

    def __init__(self, baseline):
        self.base = baseline
        self.previous = None
        self.started = 0.
        self.start_arms = baseline.arms.copy()
        self.last_result = ""
        self.checks = {}
        self.measures = {}
        self.cooldown_until = 0.
        self.attempt_started = False
        self.reset("Ellerini kısa bir an rahatça sabit tut.")

    def reset(self, reason):
        self.state, self.since, self.candidate, self.evidence = "settling", None, None, None
        self.reason = reason
        self.settle_arms = None
        self.release_side = None
        self.up_since = None
        self.up_pending = None

    def cancel(self, reason):
        self.last_result = "Sayılmadı: " + reason
        self.reset(reason)

    def in_guard(self, f):
        """Legacy wire readiness now means briefly settled hands in any pose."""
        return f.valid and self.state == "ready"

    @staticmethod
    def direction(delta):
        sideways, up, forward = abs(delta[0]), -delta[1], -delta[2]
        # A hand often rises as it extends from a relaxed resting position.
        # Observable forward/side travel takes priority over that initial lift.
        if ((forward > .08 and forward >= max(0., up)*.30)
                or (sideways > .08 and sideways >= abs(delta[1])*.55)):
            return "punch", norm((sideways, max(0., forward)))
        if up > .10 and up > max(sideways, forward)*1.8:
            return "uppercut", up
        return "", 0.

    def finish(self, move, side, f, peak_t, distance):
        self.candidate = (move, peak_t, 0.)
        self.evidence = (move, peak_t, 0.)
        self.state = "cooldown"
        self.release_side, self.release_distance = side, distance
        self.cooldown_until = f.t+.25
        self.up_pending = None
        self.last_result = "Algılandı: " + LABELS[move]
        self.reason = "Yön doğrulandı; " + LABELS[move] + "."
        return Hit(move, peak_t, f.t)

    def update(self, f):
        self.attempt_started = False
        prev = self.previous
        self.previous = f
        if not f.valid:
            self.cancel(f.reason or "Eller görünmedi; hareket doğrulanamadı.")
            return None
        if prev is None or not prev.valid or not 0 < f.t-prev.t <= .25:
            self.cancel("Takip kuruldu; ellerini kısa bir an sabit tut." if prev is None or not prev.valid
                        else "Kare akışı kesildi; hareket doğrulanamadı.")
            return None
        dt = f.t-prev.t
        speeds = {s: norm(sub(f.arms[s].wrist, prev.arms[s].wrist))/dt for s in f.arms}
        if max(speeds.values()) > 18 or abs(f.width/prev.width-1) > .3:
            self.cancel("Ani takip sıçraması; hareket doğrulanamadı.")
            return None
        if self.state == "cooldown":
            self.reason = "Algılandı; elini biraz geri çek, sonraki harekete hazırlan."
            distance = norm(sub(f.arms[self.release_side].wrist, self.start_arms[self.release_side].wrist))
            if f.t >= self.cooldown_until and distance <= max(.18, self.release_distance*.55):
                self.reset("Ellerini rahat bırak; sonraki hareket hazırlanıyor.")
            return None
        if self.state == "settling":
            if self.settle_arms is None or max(norm(sub(f.arms[s].wrist, self.settle_arms[s].wrist)) for s in f.arms) > .10:
                self.settle_arms, self.since = f.arms.copy(), f.t
            if f.t-self.since >= .25 and max(speeds.values()) < .8:
                self.state, self.start_arms = "ready", f.arms.copy()
                self.reason = "Hazır: sol yumruk, sağ yumruk veya aşağıdan yukarı vur."
            return None
        deltas = {s: sub(f.arms[s].wrist, self.start_arms[s].wrist) for s in f.arms}
        distances = {s: norm(v) for s, v in deltas.items()}
        side = max(distances, key=distances.get)
        if self.up_pending and max(distances.values()) < .10:
            side = self.up_pending["side"]
        if self.state == "ready":
            if distances[side] <= .10:
                return None
            self.state, self.started = "outbound", prev.t
            self.attempt_started = True
            self.checks = {}
            self.measures = {}
            self.since = None
        other = "right" if side == "left" else "left"
        direction, extent = self.direction(deltas[side])
        previous_delta = sub(prev.arms[side].wrist, self.start_arms[side].wrist)
        previous_direction, previous_extent = self.direction(previous_delta)
        coherent = (direction != "" and previous_direction == direction and previous_extent >= .08
                    and extent >= previous_extent*.8)
        dominant = distances[other] < max(.10, distances[side]*.85)
        threshold = self.UP_DISTANCE if direction == "uppercut" else self.PUNCH_DISTANCE
        percentage = lambda value, goal: max(0, min(300, round(value/goal*20)*5))
        self.measures = {"hareket_yuzdesi": percentage(extent, threshold),
                         "ileri_yuzdesi": percentage(-deltas[side][2], self.PUNCH_DISTANCE),
                         "yana_yuzdesi": percentage(abs(deltas[side][0]), self.PUNCH_DISTANCE),
                         "yukari_yuzdesi": percentage(-deltas[side][1], self.UP_DISTANCE),
                         "kare_araligi_ms": round(dt*1000)}
        self.checks = {side: {"el_gorunur": True, "tek_el_baskin": dominant,
                              "yon_belirgin": bool(direction), "mesafe_yeterli": extent >= threshold,
                              "ardisik_hareket": coherent, "yukari_yon": direction == "uppercut"}}
        if not dominant:
            self.cancel("İki el birlikte hareket etti; tek elle vur.")
            return None
        if direction == "punch":
            self.up_pending, self.up_since = None, None
            if extent >= threshold and coherent:
                return self.finish(side+"_punch", side, f, f.t, distances[side])
        elif direction == "uppercut":
            self.up_since = self.up_since if self.up_since is not None else f.t
            if extent >= threshold and coherent and (self.up_pending is None or extent >= self.up_pending["up"]):
                self.up_pending = {"side": side, "peak_t": f.t, "distance": distances[side],
                                   "up": extent, "checks": self.checks, "measures": self.measures}
        if self.up_pending:
            pending = self.up_pending
            # A short decision window lets the forward part of a rising punch
            # emerge. An observed reversal also completes a short vertical move;
            # no held peak or full guard return is required.
            if side != pending["side"]:
                self.up_pending, self.up_since = None, None
            elif (f.t-self.up_since >= self.UP_DECISION_SECONDS
                  or -deltas[side][1] < pending["up"]*.70):
                self.checks, self.measures = pending["checks"], pending["measures"]
                return self.finish("uppercut", side, f, pending["peak_t"], pending["distance"])
        self.reason = (("Sol" if side == "left" else "Sağ") + " el izleniyor: " +
                       ("hareket yönü belirginleşmedi." if not direction else
                        f"hareket %{self.measures['hareket_yuzdesi']}; %100'de yeterli." if extent < threshold else
                        "yukarı mı öne mi gittiği ayrılıyor." if self.up_pending else "sonraki net kare bekleniyor."))
        if max(distances.values()) < .09:
            self.cancel("Hareket yönü yeterince belirginleşmeden el geri döndü.")
        elif max(speeds.values()) < .12:
            self.since = self.since if self.since is not None else f.t
            if f.t-self.since >= .65:
                self.cancel("Hareket durdu; ellerin yeni konumuna otomatik hazırlanılıyor.")
        else:
            self.since = None
        return None
