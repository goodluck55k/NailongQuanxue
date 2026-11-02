"""Rules that turn a model answer plus local motion evidence into a verdict.

Qt-free so the decision table can be tested directly. Every ambiguous or
incomplete input resolves to a non-pass: a technical failure must never look
like success.
"""
from dataclasses import dataclass

from .vision_api import Answer

PASSED = "passed"
NOT_PASSED = "not_passed"
FAILED = "failed"

REQUIRED_CYCLES = 2
MIN_FRAMES = 6
MIN_MOTION = 0.0025
MAX_PLAUSIBLE_CYCLES = 8


@dataclass(frozen=True)
class Verdict:
    status: str
    reason: str
    cycles: int | None = None

    @property
    def passed(self):
        return self.status == PASSED

    @property
    def technical(self):
        return self.status == FAILED

    def label(self):
        return {PASSED: "动作验证通过", NOT_PASSED: "动作验证未通过",
                FAILED: "未能完成验证"}.get(self.status, "未验证")


def failure(message):
    return Verdict(FAILED, message)


def decide(answer: Answer, motion, required=REQUIRED_CYCLES):
    """motion: normalized mean frame-to-frame difference, one value per interval."""
    trace = [float(value) for value in (motion or [])]
    if trace and max(trace) < MIN_MOTION:
        return Verdict(NOT_PASSED, "画面几乎静止，未检测到前倾与回正的动作变化")
    if answer.cycles < 0 or answer.cycles > MAX_PLAUSIBLE_CYCLES:
        return Verdict(NOT_PASSED, f"模型给出的动作次数异常（{answer.cycles}），按未通过处理")
    missing = []
    if answer.cycles < required:
        missing.append(f"完整动作不足 {required} 组")
    if not answer.hand:
        missing.append("未见手放在腹部附近")
    if not answer.lean:
        missing.append("未见明显前倾与回正")
    if missing:
        detail = "；".join(missing)
        if answer.passed:
            detail = "模型自述通过，但" + detail
        return Verdict(NOT_PASSED, detail, answer.cycles)
    if getattr(answer, "sequence", None) is False:
        return Verdict(NOT_PASSED, "模型认为动作顺序不成立（未做到「手放腹部 → 前倾 → 回正」的先后顺序）",
                       answer.cycles)
    if not answer.passed:
        reason = answer.reason or "模型判断动作未达到标准"
        return Verdict(NOT_PASSED, f"模型判断：{reason}", answer.cycles)
    return Verdict(PASSED, f"检测到 {answer.cycles} 组前倾—回正动作，手已放在腹部附近",
                   answer.cycles)


def check_evidence(frame_count, span_ms, clip_ms, min_frames=MIN_FRAMES, min_span_ratio=0.6):
    """Reject a clip that cannot possibly show two cycles."""
    if frame_count < min_frames:
        return failure(f"录像只抽到 {frame_count} 帧画面，不足以判断动作，请重新录制")
    if clip_ms <= 0 or span_ms < clip_ms * min_span_ratio:
        return failure("录像时长过短，无法确认两组动作，请重新录制")
    return None


def prompt_for(frame_count, span_seconds):
    step = span_seconds / (frame_count - 1) if frame_count > 1 else 0.0
    return (
        "用户需要模仿“奶龙大笑”的动作：一只手放在腹部附近，身体明显前倾再回正，"
        "连续完成至少两组。“前倾—回正”算一组；只摆一个姿势不动、只前倾不回正、"
        "或只有一组，都不算通过。不要求声音、音色、音高或面部表情。\n"
        f"下面是按时间顺序从同一段 {span_seconds:.1f} 秒录像中均匀抽取的 {frame_count} 张画面："
        f"第 1 帧约 0.0 秒，相邻两帧间隔约 {step:.2f} 秒，最后一帧约 {span_seconds:.1f} 秒。"
        "请按这个顺序判断动作是否发生。\n"
        "判断规则：\n"
        "1. 只依据画面中可见的身体姿态；画面静止或变化轻微时判定未通过。\n"
        "2. 两组动作必须是两次可见的“前倾—回正”，前后姿态要有明显差异。\n"
        "3. 无法确定时判定未通过，不要猜测。\n"
        "只输出一个 JSON 对象，不要代码块、不要解释：\n"
        '{"pass": true 或 false, "motion_cycles": 整数, "hand_on_belly": true 或 false, '
        '"lean_observed": true 或 false, "sequence_verified": true 或 false, '
        '"confidence": 0 到 1 的小数, "reason": "不超过 40 字的中文说明"}\n'
        '只有当 motion_cycles 不少于 2、hand_on_belly 与 lean_observed 都为 true、'
        'sequence_verified 也为 true 时，pass 才能为 true。\n'
        'sequence_verified 表示画面顺序确实是「手放在腹部 → 身体前倾 → 回正」，'
        '而不是明显乱序或只有一次弯腰。'
    )
