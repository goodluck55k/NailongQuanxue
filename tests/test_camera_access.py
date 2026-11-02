"""摄像头可用性诊断的判定与文案（不接触真实摄像头，只验证纯逻辑）。"""
from app import camera_access
from app.camera_access import BLOCKED, NONE, OK, UNKNOWN, Diagnosis


def test_blocked_state_is_reported_with_the_device_name():
    diagnosis = Diagnosis(BLOCKED, ["ASUS FHD webcam"], 0x80070005)

    assert diagnosis.blocked is True
    assert "ASUS FHD webcam" in diagnosis.message()
    assert "拒绝" in diagnosis.message()
    assert "设置 → 隐私和安全性 → 摄像头" in diagnosis.guide()[0]


def test_blocked_without_names_still_explains_what_to_do():
    diagnosis = Diagnosis(BLOCKED, [], 0x80070005)

    assert diagnosis.message()
    assert len(diagnosis.guide()) == 4


def test_none_and_unknown_have_distinct_messages():
    none = Diagnosis(NONE)
    unknown = Diagnosis(UNKNOWN, [], None, "probe: boom")

    assert "没有检测到摄像头" in none.message()
    assert "无法确认" in unknown.message()
    assert "boom" in unknown.message()
    assert none.message() != unknown.message()


def test_ok_state_does_not_pretend_to_be_an_error():
    diagnosis = Diagnosis(OK, ["ASUS FHD webcam"], 0)

    assert diagnosis.blocked is False


def test_privacy_settings_uri_points_at_the_windows_camera_page():
    assert camera_access._PRIVACY_URI == "ms-settings:privacy-webcam"


def test_diagnose_returns_a_known_state():
    # 本机可能授权、可能被拒、也可能没有摄像头，三种都要给出可用结论。
    diagnosis = camera_access.diagnose()

    assert diagnosis.state in {OK, BLOCKED, NONE, UNKNOWN}
    assert diagnosis.message()
