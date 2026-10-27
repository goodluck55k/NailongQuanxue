import pytest

from app.supervision import BREAK_SECONDS, DECLARATION, Phase, Supervision
from app.usage_clock import ActiveClock


@pytest.fixture
def system(clock):
    return Supervision(ActiveClock(clock), clock)


def test_active_clock_multiple_pause_reasons(clock):
    active = ActiveClock(clock)
    clock.advance(10)
    assert active() == 10
    active.pause("locked")
    clock.advance(30)
    active.pause("suspend")
    active.resume("locked")
    clock.advance(50)
    assert active() == 10
    active.resume("suspend")
    clock.advance(3)
    assert active() == 13


@pytest.mark.parametrize("seconds,expected", [(15, None), (90, None), (180, 3), (330, None), (7200, None)])
def test_v11_durations(system, seconds, expected):
    assert system.start(seconds).reminder == expected


@pytest.mark.parametrize("seconds", [0, -1, 60000, float("nan"), True])
def test_invalid_duration(system, seconds):
    with pytest.raises(ValueError):
        system.start(seconds)


def test_usage_pauses_but_break_counts_lock_sleep(system, clock):
    system.start(90)
    clock.advance(20)
    system.session_pause("lock", True)
    clock.advance(600)
    assert system.poll().remaining == 70
    system.session_pause("lock", False)
    clock.advance(70)
    assert system.poll().phase == Phase.BREAK_ACTIVE
    system.session_pause("lock", True)
    clock.advance(600)
    assert system.poll().completed_round == 1
    assert len(system.events) == 1
    assert system.events[0].event_type == "BREAK_COMPLETED"


def test_auto_next_round_waits_for_unlock(system, clock):
    system.start(15, "automatic")
    clock.advance(15)
    system.poll()
    system.session_pause("lock", True)
    clock.advance(1000)
    system.session_pause("lock", False)
    assert system.phase == Phase.RUNNING
    assert system.round_index == 2
    assert system.poll().remaining == 15


def test_manual_300_seconds_not_video_cycles(system, clock):
    system.start(15)
    clock.advance(15)
    assert system.poll().remaining == 300
    clock.advance(299.9)
    assert system.poll().remaining == 1
    clock.advance(.1)
    assert system.poll().phase == Phase.IDLE
    system.poll()
    assert len(system.events) == 1


def test_old_workflow_cancelled_at_usage_deadline(system, clock):
    system.start(15)
    token = system.request_surrender()
    assert system.accept_writing(token, DECLARATION)
    assert system.mark_captured(token)
    clock.advance(15)
    assert system.confirm_surrender(token) is None
    assert system.phase == Phase.BREAK_ACTIVE
    assert not system.events
    assert system.request_surrender() != token


def test_break_completion_wins_confirmation_race(system, clock):
    system.start(1, "automatic")
    clock.advance(1)
    system.poll()
    token = system.request_surrender()
    system.accept_writing(token, DECLARATION)
    system.mark_captured(token)
    clock.advance(BREAK_SECONDS)
    assert system.confirm_surrender(token) is None
    assert [e.event_type for e in system.events] == ["BREAK_COMPLETED"]
    assert system.round_index == 2


@pytest.mark.parametrize("break_stage,kind", [(False, "EARLY_SURRENDER"), (True, "BREAK_SURRENDER")])
def test_surrender_ends_entire_auto_loop_once(system, clock, break_stage, kind):
    system.start(15, "automatic")
    if break_stage:
        clock.advance(15)
        system.poll()
    token = system.request_surrender()
    for invalid in ("", " 我是废物", "我是废物 ", "我是废勿"):
        assert not system.accept_writing(token, invalid)
    assert system.accept_writing(token, DECLARATION)
    assert system.confirm_surrender(token) is None
    system.mark_captured(token)
    event = system.confirm_surrender(token)
    assert event.event_type == kind
    assert event.declaration_confirmed
    assert system.confirm_surrender(token) is None
    assert system.phase == Phase.IDLE


def test_lock_invalidates_photo_and_never_reopens_camera(system):
    system.start(60)
    token = system.request_surrender()
    system.accept_writing(token, DECLARATION)
    system.mark_captured(token)
    system.session_pause("lock", True)
    system.session_pause("lock", False)
    assert system.workflow is None
    assert system.confirm_surrender(token) is None


def test_emergency_without_photo_ends_loop(system):
    system.start(60, "automatic")
    system.request_surrender()
    assert system.emergency().event_type == "EMERGENCY_EXIT"
    assert system.phase == Phase.IDLE
    assert system.emergency() is None
