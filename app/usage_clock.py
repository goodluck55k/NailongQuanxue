"""Awake, unlocked elapsed time; the V1 deadline timer consumes this clock."""
import ctypes
import sys
import time


def awake_clock():
    if sys.platform != "win32":
        return time.monotonic
    query = ctypes.WinDLL("kernel32", use_last_error=True).QueryUnbiasedInterruptTime
    query.argtypes = [ctypes.POINTER(ctypes.c_ulonglong)]
    query.restype = ctypes.c_int

    def read():
        value = ctypes.c_ulonglong()
        if not query(ctypes.byref(value)):
            raise OSError("Cannot read Windows awake clock")
        return value.value / 10_000_000
    return read


class ActiveClock:
    def __init__(self, source=None):
        self.source = source or awake_clock()
        self.reasons: set[str] = set()
        self._total = 0.0
        self._last = self.source()

    def __call__(self):
        now = self.source()
        if not self.reasons:
            self._total += max(0.0, now - self._last)
        self._last = now
        return self._total

    def pause(self, reason):
        self()
        self.reasons.add(reason)

    def resume(self, reason):
        self()
        self.reasons.discard(reason)

    @property
    def paused(self):
        return bool(self.reasons)
