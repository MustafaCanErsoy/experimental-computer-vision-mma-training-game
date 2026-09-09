"""Version 1 numeric-only loopback producer. No camera or game rules imported."""
import json
import math
import socket
from collections import deque
from time import perf_counter
from uuid import uuid4

from .core import MOVES

DEFAULT_PORT = 28741
STATE_FIELDS = {"v", "type", "client", "source", "session", "link", "lease",
                "encounter", "prompt", "phase", "paused", "move"}


class EventClient:
    def __init__(self, source, port=DEFAULT_PORT, clock=perf_counter):
        if source not in ("synthetic", "camera") or not 1 <= port <= 65535:
            raise ValueError("Invalid local source or port")
        self.source, self.clock = source, clock
        self.client = uuid4().hex
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.connect(("127.0.0.1", port))
        self.socket.setblocking(False)
        self.context = None
        self.context_since = self.last_received = 0.
        self.last_send = -math.inf
        self.last_ready = None
        self.last_guard = False
        self.guard_event = 0
        self.session = None
        self.retired_sessions = set()
        self.last_lease = 0
        self.event = 0
        self.closed = False
        self.diagnostics = deque(maxlen=128)
        self.pending_hits = {}
        self.commands = deque(maxlen=16)
        self.command_id = 0
        self.last_diagnostic_send = -math.inf
        self.last_delivery = ""

    @property
    def status(self):
        if self.context is None:
            return "Kule bağlantısı bekleniyor"
        if self.context["phase"] == "results":
            return "Tırmanış bitti · oyunda R ile yeni seans"
        if not self.last_ready:
            return "Kule bağlı · algılama hazır değil"
        if self.source == "camera" and self.context["paused"]:
            return "Kule bağlı · eller görünürken otomatik devam. Elle duraklattıysan oyunda P."
        return "Kule bağlı · oyunda P ile devam et" if self.context["paused"] else "Kule bağlı"

    def send(self, payload):
        if self.closed:
            return False
        packet = {"v": 1, "source": self.source, "client": self.client, **payload}
        data = json.dumps(packet, allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(data) > 1024:
            return False
        try:
            self.socket.send(data)
            return True
        except (BlockingIOError, OSError):
            return False  # No retry queue: a missed movement must not arrive later.

    def accept_state(self, data, now):
        if not isinstance(data, dict) or data.keys() != STATE_FIELDS:
            return False
        if (type(data["v"]) is not int or data["v"] != 1 or data["type"] != "state"
                or data["client"] != self.client or data["source"] != self.source
                or type(data["paused"]) is not bool
                or type(data["lease"]) is not int or not 0 < data["lease"] <= 2147483647
                or data["move"] not in MOVES or data["phase"] not in ("approach", "fight", "cleared", "results")):
            return False
        for key in ("session", "link", "encounter", "prompt"):
            if not isinstance(data[key], str) or not 0 < len(data[key]) <= 80:
                return False
        session = data["session"]
        if session in self.retired_sessions:
            return False
        if session == self.session and data["lease"] <= self.last_lease:
            return False
        if session != self.session:
            self.command_id = 0
            if self.session is not None:
                self.retired_sessions.add(self.session)
            self.session = session
        identity = lambda c: tuple(c[k] for k in ("session", "link", "encounter", "prompt", "paused"))
        if self.context is None or identity(data) != identity(self.context):
            self.context_since = now
        self.context, self.last_lease, self.last_received = data, data["lease"], now
        return True

    def poll(self, ready=False, guard=False):
        if self.closed:
            return
        now = self.clock()
        # Expire before receiving: motion begun during a gap cannot use a new lease.
        if now - self.last_received > .75:
            self.context = None
        for _ in range(64):
            try:
                raw = self.socket.recv(1025)
            except (BlockingIOError, OSError):
                break
            if len(raw) > 1024:
                continue
            try:
                data = json.loads(raw)
            except (ValueError, UnicodeError):
                continue
            if isinstance(data, dict) and data.get("type") == "receipt":
                self.accept_receipt(data)
            elif isinstance(data, dict) and data.get("type") == "control":
                self.accept_control(data)
            else:
                self.accept_state(data, now)
        for event, pending in list(self.pending_hits.items()):
            if now-pending["sent"] > 1.5:
                self.diagnostics.append({**pending, "event": event, "kind": "delivery", "outcome": "unconfirmed"})
                del self.pending_hits[event]
        guard = bool(ready and guard and self.source == "camera")
        if now - self.last_send >= .1 or ready != self.last_ready or guard != self.last_guard:
            if self.context:
                self.send({"type": "pulse", "link": self.context["link"],
                           "lease": self.context["lease"], "ready": bool(ready)})
                if self.source == "camera":
                    self.guard_event += 1
                    self.send({"type": "guard", "link": self.context["link"],
                               "lease": self.context["lease"], "event": self.guard_event, "held": guard})
            else:
                self.send({"type": "hello"})
            self.last_send, self.last_ready, self.last_guard = now, ready, guard

    def send_hit(self, hit, started_t):
        """Forward the observed class, with the context valid at motion onset.

        Detector receives no requested class. Angle/landmarks never cross the bridge.
        """
        now, c = self.clock(), self.context
        reason = ("no_context" if c is None else
                  "not_ready" if not self.last_ready else "paused" if c["paused"] else
                  "not_fighting" if c["phase"] != "fight" else
                  "stale_context" if now-self.last_received > .25 else "")
        if (c is None or not self.last_ready or c["paused"] or c["phase"] != "fight"
                or now - self.last_received > .25 or hit.move not in MOVES
                or not all(math.isfinite(t) for t in (started_t, hit.peak_t, hit.confirmed_t, now))
                or not self.context_since <= started_t <= hit.peak_t <= hit.confirmed_t <= now
                or now - hit.confirmed_t > .25 or not hit.confirmed):
            self.last_delivery = reason or "motion_context_or_time_invalid"
            self.diagnostics.append({"kind": "delivery", "outcome": self.last_delivery, "move": hit.move,
                                     "expected": c["move"] if c else "", "event": 0})
            return False
        self.event += 1
        sent = self.send({"type": "hit", "link": c["link"], "lease": c["lease"],
                          "event": self.event, "encounter": c["encounter"], "prompt": c["prompt"],
                          "move": hit.move, "age_ms": int((now - hit.confirmed_t) * 1000)})
        self.last_delivery = "sent" if sent else "send_failed"
        if sent:
            self.pending_hits[self.event] = {"sent": now, "move": hit.move, "expected": c["move"],
                                            "session": c["session"], "link": c["link"]}
        self.diagnostics.append({"kind": "delivery", "outcome": self.last_delivery, "move": hit.move,
                                 "expected": c["move"], "event": self.event})
        return sent

    def accept_receipt(self, data):
        if set(data) != {"v", "type", "source", "client", "session", "link", "event", "outcome"} or data["type"] != "receipt":
            return False
        event = data["event"]
        if type(event) is not int or event not in self.pending_hits:
            return False
        pending = self.pending_hits[event]
        if (type(data["v"]) is not int or data["v"] != 1 or data["source"] != self.source
                or data["client"] != self.client or data["session"] != pending["session"]
                or data["link"] != pending["link"] or data["outcome"] not in
                ("hit", "defeated", "wrong", "inactive", "duplicate", "late", "stale_prompt", "stale_lease")):
            return False
        self.diagnostics.append({**pending, "kind": "game", "outcome": data["outcome"], "event": event})
        del self.pending_hits[event]
        return True

    def accept_control(self, data):
        c = self.context
        if (c is None or set(data) != {"v", "type", "source", "client", "session", "link", "id", "action"}
                or type(data["v"]) is not int or data["v"] != 1 or data["client"] != self.client
                or data["source"] != self.source or data["session"] != c["session"] or data["link"] != c["link"]
                or type(data["id"]) is not int or not self.command_id < data["id"] <= 2147483647
                or data["action"] not in ("frames_on", "frames_off", "calibrate")):
            return False
        self.command_id = data["id"]
        self.commands.append(data["action"])
        return True

    def publish_diagnostic(self, status, result, recording=False):
        now, c = self.clock(), self.context
        if c and self.source == "camera" and now-self.last_diagnostic_send >= .2:
            self.send({"type": "diagnostic", "link": c["link"], "lease": c["lease"],
                       "status": str(status)[:180], "result": str(result)[:180], "recording": bool(recording)})
            self.last_diagnostic_send = now

    def close(self):
        if not self.closed:
            if self.context:
                self.send({"type": "pulse", "link": self.context["link"],
                           "lease": self.context["lease"], "ready": False})
            self.socket.close()
            self.closed = True
