"""Pure deadline-based timer; no Qt or wall-clock dependency."""

from dataclasses import dataclass
from enum import Enum
import math
import sys
import time
from typing import Callable


def elapsed_clock() -> Callable[[], float]:
    """Use the Windows boot clock (including sleep), otherwise monotonic time."""
    if sys.platform == "win32":
        import ctypes

        tick = ctypes.WinDLL("kernel32", use_last_error=True).GetTickCount64
        tick.argtypes = []
        tick.restype = ctypes.c_ulonglong
        return lambda: tick() / 1000.0
    return time.monotonic


class State(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    FINAL_10S = "final_10s"
    BLOCKING = "blocking"


@dataclass(frozen=True)
class Snapshot:
    state: State
    remaining_seconds: int
    reminder_minutes: int | None = None


def format_time(seconds: int) -> str:
    minutes, seconds = divmod(max(0, seconds), 60)
    return f"{minutes:02d}:{seconds:02d}"


class TimerController:
    def __init__(self, clock: Callable[[], float] | None = None):
        self.clock = clock if clock is not None else elapsed_clock()
        self.state = State.IDLE
        self.deadline = 0.0
        self.duration = 0.0
        self.fired: set[int] = set()
        self._remaining = 0.0

    def start(self, seconds: float) -> Snapshot:
        if self.state != State.IDLE:
            raise RuntimeError("A timer is already active")
        if isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Duration must be positive and finite")
        self.duration = seconds
        self.deadline = self.clock() + seconds
        self._remaining = seconds
        self.fired.clear()
        self.state = State.RUNNING
        return self.poll()

    def poll(self) -> Snapshot:
        if self.state in (State.IDLE, State.BLOCKING):
            return Snapshot(self.state, 0)
        # Never increase remaining time, even if an injected clock steps back.
        self._remaining = min(self._remaining, max(0.0, self.deadline - self.clock()))
        seconds = math.ceil(self._remaining)
        if self._remaining <= 0:
            self.state = State.BLOCKING
            return Snapshot(self.state, 0)
        due = [m for m in (5, 4, 3, 2, 1)
               if m not in self.fired and self._remaining <= m * 60 <= self.duration]
        self.fired.update(due)
        if self._remaining <= 10:
            self.state = State.FINAL_10S
            return Snapshot(self.state, seconds)
        # Delayed callbacks coalesce crossed thresholds into one notification.
        return Snapshot(self.state, seconds, min(due) if due else None)

    def reset(self) -> Snapshot:
        self.state = State.IDLE
        self.deadline = self.duration = self._remaining = 0.0
        self.fired.clear()
        return Snapshot(State.IDLE, 0)
