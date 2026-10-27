"""V1.1 coordinator, reusing V1 TimerController's tested reminder/deadline core."""
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import math
import uuid

from .timer_controller import State, TimerController, elapsed_clock
from .usage_clock import ActiveClock

BREAK_SECONDS = 300
DECLARATION = "我是废物"


class Phase(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    BREAK_ACTIVE = "break_active"


@dataclass
class Event:
    event_id: str
    occurred_at: str
    event_type: str
    mode: str
    round_index: int
    configured_seconds: float
    usage_seconds: float
    break_seconds: float
    declaration_confirmed: bool = False
    photo_status: str = "not_applicable"
    photo_path: str | None = None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class View:
    phase: Phase
    remaining: int
    reminder: int | None = None
    final: bool = False
    completed_round: int | None = None


class Supervision:
    def __init__(self, active_clock=None, rest_clock=None):
        self.active = active_clock or ActiveClock()
        self.rest_clock = rest_clock or elapsed_clock()
        self.usage = TimerController(self.active)
        self.phase = Phase.IDLE
        self.mode = "manual"
        self.round_index = 0
        self.configured = 1800.0
        self.session_id = ""
        self.break_started = None
        self.workflow = None
        self.events: list[Event] = []

    def start(self, seconds, mode="manual"):
        if self.phase != Phase.IDLE:
            raise RuntimeError("Supervision already active")
        if isinstance(seconds, bool) or not math.isfinite(seconds) or not 0 < seconds <= 59999:
            raise ValueError("Duration must be between 1 and 59999 seconds")
        if mode not in ("manual", "automatic"):
            raise ValueError("Unknown supervision mode")
        self.mode, self.configured = mode, seconds
        self.session_id = uuid.uuid4().hex
        self.round_index = 1
        self.workflow = None
        self.phase = Phase.RUNNING
        self.usage.reset()
        snapshot = self.usage.start(seconds)
        return View(self.phase, snapshot.remaining_seconds, snapshot.reminder_minutes,
                    snapshot.state == State.FINAL_10S)

    def poll(self):
        if self.phase == Phase.IDLE:
            return View(self.phase, 0)
        if self.phase == Phase.RUNNING:
            snapshot = self.usage.poll()
            if snapshot.state == State.BLOCKING:
                self.workflow = None
                self.phase = Phase.BREAK_ACTIVE
                self.break_started = self.rest_clock()
                return View(self.phase, BREAK_SECONDS)
            return View(self.phase, snapshot.remaining_seconds, snapshot.reminder_minutes,
                        snapshot.state == State.FINAL_10S)
        remaining = max(0.0, BREAK_SECONDS - self.break_elapsed())
        if remaining > 0:
            return View(self.phase, math.ceil(remaining))
        completed_round = self.round_index
        self.events.append(self._event("BREAK_COMPLETED"))
        self.workflow = None
        self.break_started = None
        self.usage.reset()
        if self.mode == "automatic":
            self.round_index += 1
            self.phase = Phase.RUNNING
            snapshot = self.usage.start(self.configured)
            return View(self.phase, snapshot.remaining_seconds, snapshot.reminder_minutes,
                        snapshot.state == State.FINAL_10S, completed_round)
        self.phase = Phase.IDLE
        return View(self.phase, 0, completed_round=completed_round)

    def break_elapsed(self):
        return max(0.0, self.rest_clock() - self.break_started) if self.break_started is not None else 0.0

    def _event(self, kind, declaration=False):
        used = self.configured if self.phase == Phase.BREAK_ACTIVE else min(
            self.configured, max(0.0, self.configured - max(0.0, self.usage.deadline - self.active())))
        return Event(f"{self.session_id}:{self.round_index}", datetime.now().astimezone().isoformat(),
                     kind, self.mode, self.round_index, self.configured, used,
                     self.break_elapsed(), declaration)

    def request_surrender(self):
        self.poll()
        if self.phase == Phase.IDLE:
            return None
        if self.workflow is None:
            self.workflow = {"token": uuid.uuid4().hex, "phase": self.phase,
                             "round": self.round_index, "stage": "writing"}
        return self.workflow["token"]

    def valid(self, token):
        return bool(self.workflow and self.workflow["token"] == token
                    and self.workflow["phase"] == self.phase
                    and self.workflow["round"] == self.round_index)

    def accept_writing(self, token, text):
        self.poll()
        if self.valid(token) and self.workflow["stage"] == "writing" and text == DECLARATION:
            self.workflow["stage"] = "camera"
            return True
        return False

    def mark_captured(self, token):
        self.poll()
        if self.valid(token) and self.workflow["stage"] in ("camera", "preview"):
            self.workflow["stage"] = "preview"
            return True
        return False

    def retake(self, token):
        if self.valid(token):
            self.workflow["stage"] = "camera"

    def confirm_surrender(self, token):
        # This check and transition run in the Qt main thread before any write.
        self.poll()
        if not self.valid(token) or self.workflow["stage"] != "preview":
            return None
        kind = "EARLY_SURRENDER" if self.phase == Phase.RUNNING else "BREAK_SURRENDER"
        event = self._event(kind, declaration=True)
        self.stop()
        return event

    def emergency(self):
        self.poll()
        if self.phase == Phase.IDLE:
            return None
        event = self._event("EMERGENCY_EXIT")
        self.stop()
        return event

    def cancel_surrender(self):
        self.workflow = None

    def session_pause(self, reason, paused):
        if paused:
            self.active.pause(reason)
            self.cancel_surrender()
        else:
            # Complete an expired break before releasing the active-time gate.
            self.poll()
            self.active.resume(reason)

    def stop(self):
        self.phase = Phase.IDLE
        self.workflow = None
        self.break_started = None
        self.usage.reset()
