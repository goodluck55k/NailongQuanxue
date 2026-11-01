import pytest

from app.action_verdict import (MAX_PLAUSIBLE_CYCLES, MIN_MOTION, NOT_PASSED, PASSED, REQUIRED_CYCLES,
                                check_evidence, decide, failure, prompt_for)
from app.vision_api import Answer


def answer(passed=True, cycles=2, hand=True, lean=True, reason=""):
    return Answer(passed=passed, cycles=cycles, hand=hand, lean=lean, confidence=0.9, reason=reason)


def moving():
    return [0.01, 0.02, 0.03, 0.01, 0.02]


def test_full_two_cycle_clip_passes():
    verdict = decide(answer(), moving())
    assert verdict.status == PASSED and verdict.passed
    assert not verdict.technical
    assert verdict.cycles == 2
    assert "2 组" in verdict.reason
    assert verdict.label() == "动作验证通过"


def test_static_pose_never_passes_even_when_model_claims_success():
    verdict = decide(answer(passed=True, cycles=3), [MIN_MOTION / 10] * 5)
    assert verdict.status == NOT_PASSED
    assert "静止" in verdict.reason


def test_missing_requirements_are_listed():
    one_cycle = decide(answer(cycles=1), moving())
    assert one_cycle.status == NOT_PASSED and "不足 2 组" in one_cycle.reason
    no_hand = decide(answer(hand=False), moving())
    assert "手" in no_hand.reason
    no_lean = decide(answer(lean=False), moving())
    assert "前倾" in no_lean.reason
    both = decide(answer(passed=True, hand=False, lean=False), moving())
    assert both.status == NOT_PASSED
    assert both.reason.startswith("模型自述通过，但")


def test_model_rejection_is_reported_with_its_reason():
    verdict = decide(answer(passed=False, reason="动作幅度太小"), moving())
    assert verdict.status == NOT_PASSED
    assert "动作幅度太小" in verdict.reason


def test_implausible_cycle_counts_are_rejected():
    for cycles in (-1, MAX_PLAUSIBLE_CYCLES + 1):
        verdict = decide(answer(cycles=cycles), moving())
        assert verdict.status == NOT_PASSED
        assert "异常" in verdict.reason


def test_required_cycles_is_configurable():
    assert REQUIRED_CYCLES == 2
    assert decide(answer(cycles=3), moving(), required=3).passed
    assert not decide(answer(cycles=2), moving(), required=3).passed


def test_empty_or_missing_trace_still_follows_the_model():
    assert decide(answer(), []).passed
    assert decide(answer(), None).passed


def test_evidence_checks():
    assert check_evidence(10, 11_000, 12_000) is None
    too_few = check_evidence(3, 12_000, 12_000)
    assert too_few is not None and too_few.technical and "3 帧" in too_few.reason
    too_short = check_evidence(10, 3_000, 12_000)
    assert too_short is not None and "时长过短" in too_short.reason
    assert failure("x").technical


def test_prompt_states_the_rules_and_the_json_contract():
    text = prompt_for(8, 11.5)
    for fragment in ("前倾", "回正", "两组", "腹部", "不要求声音", "11.5 秒", "8 张",
                     "按时间顺序", "相邻两帧间隔约 1.64 秒",
                     "motion_cycles", "无法确定时判定未通过"):
        assert fragment in text
    assert "```" not in text


@pytest.mark.parametrize("cycles", [0, 1])
def test_too_few_cycles(cycles):
    assert decide(answer(cycles=cycles), moving()).status == NOT_PASSED
