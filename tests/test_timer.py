import math

import pytest

from app.timer_controller import State, TimerController, elapsed_clock, format_time


@pytest.mark.parametrize("duration,expected", [(1800, None), (300, 5), (180, 3), (60, 1), (15, None)])
def test_start_thresholds(clock, duration, expected):
    timer = TimerController(clock)
    snapshot = timer.start(duration)
    assert snapshot.remaining_seconds == duration
    assert snapshot.reminder_minutes == expected
    assert timer.poll().reminder_minutes is None


def test_30_minutes_no_callback_drift(clock):
    timer = TimerController(clock)
    timer.start(1800)
    clock.advance(1412.4)
    assert timer.poll().remaining_seconds == 388
    clock.advance(388)
    assert timer.poll().state == State.BLOCKING
    assert timer.poll().remaining_seconds == 0


def test_each_minute_only_once(clock):
    timer = TimerController(clock)
    timer.start(360)
    for minute in (5, 4, 3, 2, 1):
        clock.advance(60)
        assert timer.poll().reminder_minutes == minute
        for _ in range(10):
            assert timer.poll().reminder_minutes is None
    assert timer.fired == {1, 2, 3, 4, 5}


def test_three_minutes_never_reminds_five_or_four(clock):
    timer = TimerController(clock)
    assert timer.start(180).reminder_minutes == 3
    for expected in (2, 1):
        clock.advance(60)
        assert timer.poll().reminder_minutes == expected
    assert timer.fired == {1, 2, 3}


def test_last_ten_seconds_and_exact_zero(clock):
    timer = TimerController(clock)
    timer.start(15)
    clock.advance(4.999)
    assert timer.poll().state == State.RUNNING
    clock.advance(0.001)
    for second in range(10, 0, -1):
        snapshot = timer.poll()
        assert snapshot.state == State.FINAL_10S
        assert snapshot.remaining_seconds == second
        assert snapshot.reminder_minutes is None
        clock.advance(1)
    assert timer.poll().state == State.BLOCKING


@pytest.mark.parametrize("elapsed,seconds", [(0, 15), (.01, 15), (.999, 15), (1, 14), (14.999, 1), (15, 0), (900, 0)])
def test_ceil_and_clamping(clock, elapsed, seconds):
    timer = TimerController(clock)
    timer.start(15)
    clock.advance(elapsed)
    assert timer.poll().remaining_seconds == seconds


def test_delayed_callbacks_coalesce(clock):
    timer = TimerController(clock)
    timer.start(360)
    clock.advance(205)
    assert timer.poll().reminder_minutes == 3
    assert timer.fired == {3, 4, 5}
    assert timer.poll().reminder_minutes is None


def test_wake_past_deadline_does_not_replay(clock):
    timer = TimerController(clock)
    timer.start(1800)
    clock.advance(4000)
    assert timer.poll().state == State.BLOCKING
    assert timer.poll().reminder_minutes is None


def test_clock_regression_never_increases_remaining(clock):
    timer = TimerController(clock)
    timer.start(120)
    clock.advance(10)
    assert timer.poll().remaining_seconds == 110
    clock.advance(-20)
    assert timer.poll().remaining_seconds == 110


def test_repeated_cycles_and_no_double_start(clock):
    timer = TimerController(clock)
    for _ in range(20):
        assert timer.start(60).reminder_minutes == 1
        with pytest.raises(RuntimeError):
            timer.start(30)
        clock.advance(60)
        assert timer.poll().state == State.BLOCKING
        assert timer.reset().state == State.IDLE
        assert timer.fired == set()


@pytest.mark.parametrize("duration", [0, -1, math.inf, math.nan, True])
def test_invalid_duration(clock, duration):
    with pytest.raises(ValueError):
        TimerController(clock).start(duration)


@pytest.mark.parametrize("seconds,expected", [(0, "00:00"), (1, "00:01"), (10, "00:10"), (1800, "30:00"), (14400, "240:00"), (-1, "00:00")])
def test_format(seconds, expected):
    assert format_time(seconds) == expected


def test_platform_clock_advances():
    from time import sleep

    clock = elapsed_clock()
    first = clock()
    sleep(0.035)
    assert clock() > first
