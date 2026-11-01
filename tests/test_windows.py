import tempfile
import time
from pathlib import Path
import uuid

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QPushButton
import pytest

from app.action_verdict import FAILED, NOT_PASSED, PASSED
from app.ai_config import AiSettings
from app.config_store import ConfigStore
from app.main_window import MainWindow
from app.overlay_window import OverlayWindow
from app.reminder_window import ReminderWindow
from app.supervision import DECLARATION, Phase, Supervision
from app.surrender_dialog import PAGE_RECORD, PAGE_RESULT, PAGE_VIDEO, LiveVerifier
from app.usage_clock import ActiveClock
from app.video_archive import SavedVideo, VideoArchive
from app.vision_api import Answer, VisionError


class FakeVideo(QObject):
    frame_ready = Signal(QImage)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False

    def start(self):
        self.active = True

    def close(self):
        self.active = False
        self.deleteLater()


def frame(color="#587AC2", size=(320, 240)):
    picture = QImage(size[0], size[1], QImage.Format.Format_RGB32)
    picture.fill(QColor(color))
    return picture


class FakeRecorder(QObject):
    """Stands in for the camera: writes a small MP4-shaped file and emits frames."""

    started = Signal()
    progress = Signal(int, int)
    preview = Signal(object)
    finished = Signal(str, object, int)
    failed = Signal(str)

    starts = 0
    error = ""
    frames = 8
    span = 11_000
    static = False

    def __init__(self, parent=None, clip_ms=12_000, sampler=None):
        super().__init__(parent)
        self.clip_ms = clip_ms
        self.path = None
        self.active = False

    @classmethod
    def reset(cls):
        cls.starts = 0
        cls.error = ""
        cls.frames = 8
        cls.span = 11_000
        cls.static = False

    def start(self):
        type(self).starts += 1
        self.active = True
        if type(self).error:
            self.failed.emit(type(self).error)
            return
        self.path = Path(tempfile.gettempdir()) / f"fake-clip-{uuid.uuid4().hex}.mp4"
        self.path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 128)
        self.started.emit()
        samples = []
        for index in range(type(self).frames):
            color = "#587AC2" if type(self).static else f"#{20 + (index * 31) % 200:02X}5A78"
            samples.append((index * 1000, frame(color)))
        self.preview.emit(samples[-1][1])
        self.progress.emit(type(self).span, self.clip_ms)
        self.finished.emit(str(self.path), samples, type(self).span)

    def stop_recording(self):
        self.active = False

    def stop(self):
        self.active = False

    def cleanup_file(self):
        if self.path is not None:
            Path(self.path).unlink(missing_ok=True)
            self.path = None


class FakeVerifier:
    answer = None
    error = None
    calls = 0

    def __init__(self, settings=None):
        self.settings = settings

    @classmethod
    def reset(cls):
        cls.answer = Answer(True, 2, True, True, 0.9, "两组前倾回正")
        cls.error = None
        cls.calls = 0

    def evaluate(self, prompt, images):
        type(self).calls += 1
        if type(self).error is not None:
            raise type(self).error
        return type(self).answer


@pytest.fixture
def window(qapp, clock, tmp_path, monkeypatch):
    monkeypatch.setattr("app.screen_manager.VideoBreak", FakeVideo)
    monkeypatch.setattr("app.surrender_dialog.VideoBreak", FakeVideo)
    monkeypatch.setattr("app.main_window.LiveVerifier", FakeVerifier)
    FakeRecorder.reset()
    FakeVerifier.reset()
    config = ConfigStore(tmp_path)
    win = MainWindow(Supervision(ActiveClock(clock), clock), config, camera_factory=FakeRecorder)
    win.show()
    yield win
    win.shutdown()
    win.close()
    win.deleteLater()


def answer(box, accepted):
    QTest.mouseClick(box.button(QMessageBox.StandardButton.Yes if accepted else QMessageBox.StandardButton.No),
                     Qt.MouseButton.LeftButton)


def wait_for(predicate, timeout=6000):
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        if predicate():
            return True
        QTest.qWait(10)
    return predicate()


def reach_video(window):
    window.request_surrender()
    dialog = window.surrender
    assert dialog.declaration.text() == ""
    assert not dialog.next_button.isEnabled()
    dialog.declaration.setText(DECLARATION)
    QTest.mouseClick(dialog.next_button, Qt.MouseButton.LeftButton)
    assert dialog.pages.currentIndex() == PAGE_VIDEO
    return dialog


def record_and_verify(window, timeout=6000):
    dialog = reach_video(window)
    QTest.mouseClick(dialog.start_record_button, Qt.MouseButton.LeftButton)
    assert dialog.pages.currentIndex() in (PAGE_RECORD, PAGE_RESULT)
    assert wait_for(lambda: dialog.verdict is not None, timeout)
    return dialog


def verified_passed(window):
    dialog = record_and_verify(window)
    assert dialog.verdict.status == PASSED, dialog.verdict.reason
    assert dialog.confirm_button.isEnabled()
    return dialog


def test_initial_ui_and_settings_four_sections(window):
    assert window.windowTitle() == "奶龙劝学"
    assert window.ring.text == "30:00"
    assert window.controller.phase == Phase.IDLE
    assert "未配置" in window.ai_status.text()
    window.open_settings()
    labels = [window.settings.tabs.tabText(index) for index in range(window.settings.tabs.count())]
    assert labels == ["监督模式", "存储与配额", "AI 接入", "投降档案馆"]


def test_unconfigured_api_prompts_once_and_can_be_postponed(window):
    window.maybe_prompt_ai()
    dialog = window.ai_dialog
    assert dialog is not None
    assert dialog.windowTitle() != ""
    assert not window.ai_settings.configured
    dialog.reject()
    assert window.ai_dialog is None
    window.maybe_prompt_ai()
    assert window.ai_dialog is None, "the reminder must not reappear in the same run"
    assert "未配置" in window.ai_status.text()
    assert window.ai_config_button.text() == "配置 AI"


def test_configured_api_skips_prompt_and_shows_status(window, tmp_path):
    window.config.save(ai={"protocol": "openai", "base_url": "https://api.example.com/v1",
                           "api_key": "sk-test", "model": "vision-1", "verified": True,
                           "verified_at": "2026-11-01T10:00:00+08:00"})
    window.refresh_ai()
    window.maybe_prompt_ai()
    assert window.ai_dialog is None
    assert "api.example.com" in window.ai_status.text()
    assert "vision-1" in window.ai_status.text()
    assert window.ai_config_button.text() == "AI 设置"


def test_live_verifier_refuses_unconfigured_settings():
    with pytest.raises(VisionError) as error:
        LiveVerifier(AiSettings()).evaluate("prompt", [b"\xff\xd8x"])
    assert error.value.kind == "config"


def test_no_camera_or_recording_before_the_demo_step(window):
    window.start_timer(90)
    window.request_surrender()
    dialog = window.surrender
    assert FakeRecorder.starts == 0
    assert "紧急退出" not in [button.text() for button in dialog.findChildren(QPushButton)]
    for invalid in ("", "我是废物 ", "我是废勿"):
        dialog.declaration.setText(invalid)
        assert not dialog.next_button.isEnabled()
    dialog.declaration.setText(DECLARATION)
    dialog.next_step()
    assert FakeRecorder.starts == 0, "watching the demo must not open the camera"
    QTest.mouseClick(dialog.start_record_button, Qt.MouseButton.LeftButton)
    assert FakeRecorder.starts == 1
    assert "紧急退出" not in [button.text() for button in dialog.findChildren(QPushButton)]


def test_verified_challenge_saves_clip_and_ends_supervision(window, tmp_path):
    window.start_timer(90)
    dialog = verified_passed(window)
    clip = dialog.clip_path
    assert clip is not None and Path(clip).exists()
    QTest.mouseClick(dialog.confirm_button, Qt.MouseButton.LeftButton)
    assert window.controller.phase == Phase.IDLE
    assert window.surrender is None
    records = window.records.all()
    assert len(records) == 1
    record = records[0]
    assert record["event_type"] == "EARLY_SURRENDER"
    assert record["video_status"] == "saved"
    assert record["ai_cycles"] == 2
    saved = Path(record["video_path"])
    assert saved.exists() and saved.parent == tmp_path / "videos"
    assert saved.read_bytes()[4:8] == b"ftyp"
    assert not Path(clip).exists(), "the temporary clip is removed after archiving"


def test_confirmation_is_recorded_once(window):
    window.config.save(mode="automatic")
    window.start_timer(90)
    dialog = verified_passed(window)
    token = dialog.token
    QTest.mouseClick(dialog.confirm_button, Qt.MouseButton.LeftButton)
    assert len(window.records.all()) == 1
    window.confirm_surrender(token, "", None)
    assert len(window.records.all()) == 1
    assert len(list((window.config.root / "videos").glob("*.mp4"))) == 1


def test_not_passed_keeps_confirm_disabled_and_retry_is_unlimited(window, monkeypatch):
    FakeVerifier.answer = Answer(False, 1, True, True, 0.5, "只有一组")
    window.start_timer(90)
    dialog = record_and_verify(window)
    assert dialog.verdict.status == NOT_PASSED
    assert not dialog.confirm_button.isEnabled()
    assert "未通过" in dialog.result_title.text()
    first_path = dialog.clip_path
    assert first_path is not None and Path(first_path).exists()
    FakeVerifier.answer = Answer(True, 2, True, True, 0.9, "两组")
    QTest.mouseClick(dialog.retry_button, Qt.MouseButton.LeftButton)
    assert FakeRecorder.starts == 2
    assert not Path(first_path).exists(), "a rejected take is discarded"
    assert wait_for(lambda: dialog.verdict is not None and dialog.verdict.passed)
    assert dialog.confirm_button.isEnabled()
    assert FakeVerifier.calls >= 2


def test_technical_failure_never_enables_confirmation(window, monkeypatch):
    FakeVerifier.error = VisionError("network", "无法连接")
    window.start_timer(90)
    dialog = record_and_verify(window)
    assert dialog.verdict.status == FAILED
    assert not dialog.confirm_button.isEnabled()
    assert "技术性失败" in dialog.message.text()
    assert "无法连接" in dialog.verdict.reason


def test_static_pose_is_rejected_even_when_the_model_claims_success(window):
    FakeRecorder.static = True
    FakeVerifier.answer = Answer(True, 3, True, True, 0.95, "看起来完成了")
    window.start_timer(90)
    dialog = record_and_verify(window)
    assert dialog.verdict.status == NOT_PASSED
    assert "静止" in dialog.verdict.reason
    assert not dialog.confirm_button.isEnabled()


def test_clip_with_too_few_frames_never_reaches_the_model(window):
    FakeRecorder.frames = 3
    window.start_timer(90)
    dialog = record_and_verify(window)
    assert dialog.verdict.status == FAILED
    assert "3 帧" in dialog.verdict.reason
    assert FakeVerifier.calls == 0
    assert not dialog.confirm_button.isEnabled()


def test_unconfigured_ai_cannot_pass_even_after_a_valid_recording(qapp, clock, tmp_path, monkeypatch):
    monkeypatch.setattr("app.screen_manager.VideoBreak", FakeVideo)
    monkeypatch.setattr("app.surrender_dialog.VideoBreak", FakeVideo)
    FakeRecorder.reset()
    config = ConfigStore(tmp_path / "plain")
    plain = MainWindow(Supervision(ActiveClock(clock), clock), config, camera_factory=FakeRecorder)
    try:
        plain.show()
        plain.start_timer(90)
        dialog = record_and_verify(plain)
        assert dialog.verdict.status == FAILED
        assert "配置" in dialog.verdict.reason or "尚未配置" in dialog.verdict.reason
        assert not dialog.confirm_button.isEnabled()
    finally:
        plain.shutdown()
        plain.close()
        plain.deleteLater()


def test_quota_exceeded_still_ends_supervision(window, monkeypatch):
    monkeypatch.setattr(VideoArchive, "used_bytes", lambda self: self.limit)
    window.start_timer(90)
    dialog = verified_passed(window)
    QTest.mouseClick(dialog.confirm_button, Qt.MouseButton.LeftButton)
    assert window.controller.phase == Phase.IDLE
    record = window.records.all()[0]
    assert record["video_status"] == "quota_exceeded"
    assert record["video_path"] is None
    assert "512 MB" in window.status_label.text()
    assert not list((window.config.root / "videos").glob("*.mp4"))


def test_clip_save_failure_still_allows_a_verified_surrender(window, monkeypatch):
    monkeypatch.setattr(VideoArchive, "save_confirmed",
                        lambda self, source, kind: SavedVideo("save_failed"))
    window.start_timer(90)
    dialog = verified_passed(window)
    QTest.mouseClick(dialog.confirm_button, Qt.MouseButton.LeftButton)
    assert window.controller.phase == Phase.IDLE
    assert window.records.all()[0]["video_status"] == "save_failed"
    assert "录像未能保存" in window.status_label.text()


def test_camera_failure_can_be_retried_and_emergency_exit_still_works(window):
    FakeRecorder.error = "摄像头被占用或权限被拒绝，请重试"
    window.start_timer(90)
    dialog = reach_video(window)
    QTest.mouseClick(dialog.start_record_button, Qt.MouseButton.LeftButton)
    assert "被占用" in dialog.record_status.text()
    assert not dialog.confirm_button.isEnabled()
    QTest.mouseClick(dialog.reconnect_button, Qt.MouseButton.LeftButton)
    assert FakeRecorder.starts == 2
    window.tray.emergency_action.trigger()
    answer(window.emergency_dialog, True)
    assert window.controller.phase == Phase.IDLE
    assert window.surrender is None
    assert not list(window.config.root.rglob("*.mp4"))


def test_cancel_after_recording_saves_nothing(window):
    window.start_timer(90)
    dialog = verified_passed(window)
    clip = Path(dialog.clip_path)
    cancel = next(button for button in dialog.findChildren(QPushButton)
                  if button.text() == "继续坚持 / 取消")
    QTest.mouseClick(cancel, Qt.MouseButton.LeftButton)
    assert window.surrender is None
    assert window.records.all() == []
    assert window.controller.phase == Phase.RUNNING
    videos = window.config.root / "videos"
    assert not videos.exists() or not list(videos.glob("*.mp4"))
    assert not list(window.config.root.rglob("*.mp4"))


def test_usage_deadline_invalidates_the_workflow(window, clock):
    window.start_timer(15)
    reach_video(window)
    clock.advance(15)
    window.tick()
    assert window.surrender is None
    assert window.controller.phase == Phase.BREAK_ACTIVE
    assert window.records.all() == []


def test_break_completion_cancels_the_recording(window, clock):
    window.start_timer(1)
    clock.advance(1)
    window.tick()
    dialog = reach_video(window)
    clock.advance(300)
    window.tick()
    assert window.surrender is None
    assert not window.screens.active
    assert window.controller.phase == Phase.IDLE
    assert [row["event_type"] for row in window.records.all()] == ["BREAK_COMPLETED"]
    assert window.reminder.mode == "completed"
    assert window.reminder.expiry.interval() == 5000


def test_lock_cancels_the_recording_and_pauses_usage(window, clock):
    window.start_timer(90)
    dialog = reach_video(window)
    QTest.mouseClick(dialog.start_record_button, Qt.MouseButton.LeftButton)
    window.session_change("locked", True)
    clock.advance(1000)
    window.tick()
    assert window.ring.text == "01:30"
    assert window.surrender is None
    window.session_change("locked", False)
    assert window.surrender is None


def test_ai_setup_can_be_opened_from_the_surrender_dialog(window):
    window.start_timer(90)
    dialog = reach_video(window)
    assert not dialog.ai_button.isHidden()
    dialog.ai_button.click()
    assert window.ai_dialog is not None


def test_inputs_lock_and_minimize_keeps_timing(window, clock):
    window.start_timer()
    assert not window.minutes.isEnabled() and not window.seconds.isEnabled()
    assert not window.start_button.isEnabled()
    window.showMinimized()
    clock.advance(23.2)
    window.tick()
    assert window.ring.text == "29:37"
    assert window.refresh.isActive()


def test_zero_input_rejected_and_long_duration_display(window):
    window.minutes.setValue(0)
    window.seconds.setValue(0)
    window.start_timer()
    assert window.controller.phase == Phase.IDLE
    window.minutes.setValue(120)
    assert window.ring.text == "120:00"


def test_reminder_reused_final_then_break(window, clock):
    window.start_timer(60)
    reminder = window.reminder
    assert reminder.expiry.interval() == 4000
    clock.advance(50)
    window.tick()
    assert window.reminder is reminder and reminder.mode == "final"
    assert not reminder.expiry.isActive()
    for second in range(10, 0, -1):
        window.tick()
        assert f"00:{second:02}" in reminder.label.text()
        clock.advance(1)
    window.tick()
    assert not reminder.isVisible()
    assert window.screens.active
    assert window.controller.phase == Phase.BREAK_ACTIVE


def test_mode_changes_only_affect_next_manual_start(window):
    window.start_timer(90)
    window.open_settings()
    window.settings.mode.setCurrentIndex(1)
    assert window.config.values["mode"] == "automatic"
    assert window.controller.mode == "manual"


def test_missing_video_and_image_still_have_controls(window, clock):
    window.start_timer(1)
    clock.advance(1)
    window.tick()
    window.screens.pixmap = QPixmap()
    window.screens._video_failed("测试：视频不可用")
    overlay = window.screens.windows[window.screens.app.primaryScreen()]
    assert overlay.original.isNull()
    assert overlay.release_button.isVisible()
    assert [button.text() for button in overlay.findChildren(QPushButton)] == ["解除限制"]
    assert overlay.release_button.geometry().right() == overlay.width() - 25
    assert overlay.grab().toImage().pixelColor(0, 0) == QColor("#FFFFFF")
    QTest.mouseClick(overlay.release_button, Qt.MouseButton.LeftButton)
    assert window.surrender is not None and window.surrender.isVisible()


def test_reconcile_reuses_one_video_and_existing_windows(window, clock):
    window.start_timer(1)
    clock.advance(1)
    window.tick()
    original = dict(window.screens.windows)
    video = window.screens.video
    for _ in range(8):
        window.screens.reconcile()
    assert window.screens.windows == original
    assert window.screens.video is video


def test_secondary_overlay_is_only_white(qapp):
    pixmap = QPixmap(100, 200)
    pixmap.fill(QColor("red"))
    overlay = OverlayWindow(pixmap)
    overlay.resize(800, 600)
    for item in (overlay.release_button, overlay.rest_label):
        item.hide()
    image = overlay.grab().toImage()
    assert image.pixelColor(400, 300) == QColor("#FFFFFF")
    overlay.dispose()


def test_white_margins_and_uncropped_image(qapp):
    pixmap = QPixmap(100, 200)
    pixmap.fill(QColor("#DD3344"))
    overlay = OverlayWindow(pixmap)
    overlay.primary = True
    overlay.resize(800, 600)
    for item in (overlay.release_button, overlay.rest_label):
        item.hide()
    picture = overlay.grab().toImage()
    assert picture.pixelColor(0, 300) == QColor("#FFFFFF")
    assert picture.pixelColor(799, 300) == QColor("#FFFFFF")
    assert picture.pixelColor(250, 0) == QColor("#DD3344")
    assert picture.pixelColor(549, 599) == QColor("#DD3344")
    overlay.dispose()


@pytest.mark.parametrize("available", [QRect(0, 0, 1920, 1040), QRect(-1280, -100, 1280, 984), QRect(0, 0, 160, 80)])
def test_reminder_within_available_geometry(available):
    assert available.contains(ReminderWindow.placement(available))


@pytest.mark.parametrize("size", [QSize(1920, 1080), QSize(1280, 1024), QSize(1080, 1920), QSize(800, 600)])
def test_image_aspect_center_unchanged_from_v1(size):
    target = OverlayWindow.image_rect(QSize(1102, 1536), size)
    assert QRect(QPoint(0, 0), size).contains(target)
    assert abs(target.width() / target.height() - 1102 / 1536) < .002


def test_real_four_second_reminder_expiry(qapp):
    reminder = ReminderWindow()
    reminder.show_minutes(3)
    QTest.qWait(1100)
    assert reminder.isVisible()
    QTest.qWait(3100)
    assert not reminder.isVisible()
    reminder.clear()
    reminder.close()


def test_active_close_keeps_counting_and_idle_close_shuts_down(window, clock):
    window.start_timer(90)
    window.close()
    clock.advance(5)
    window.tick()
    assert window.controller.phase == Phase.RUNNING
    assert window.ring.text == "01:25"
    assert not window._closing
    window.request_emergency()
    answer(window.emergency_dialog, True)
    window.close()
    assert window._closing


def test_repeated_emergency_recovers_hidden_confirmation(window, clock):
    window.start_timer(1)
    clock.advance(1)
    window.tick()
    window.showMinimized()
    window.request_emergency()
    box = window.emergency_dialog
    box.hide()
    window.request_emergency()
    assert box.isVisible()
    assert box.parentWidget() is None
    answer(box, True)
    assert window.controller.phase == Phase.IDLE
    assert window.emergency_dialog is None
    assert not window.screens.windows
    assert window.screens.video is None


def test_repeated_cancel_emergency_always_opens_fresh_usable_confirmation(window, clock):
    window.start_timer(1)
    clock.advance(1)
    window.tick()
    for _ in range(3):
        window.request_emergency()
        box = window.emergency_dialog
        assert box.isVisible()
        answer(box, False)
        assert window.emergency_dialog is None
        assert window.controller.phase == Phase.BREAK_ACTIVE
    window.request_emergency()
    answer(window.emergency_dialog, True)
    assert window.controller.phase == Phase.IDLE
    assert window.records.stats()["EMERGENCY_EXIT"] == 1


def test_database_failure_does_not_hold_desktop(window, clock, monkeypatch):
    import sqlite3

    def fail(_):
        raise sqlite3.OperationalError("test unavailable database")

    monkeypatch.setattr(window.records, "append", fail)
    window.start_timer(1)
    clock.advance(1)
    window.tick()
    window.request_emergency()
    answer(window.emergency_dialog, True)
    assert window.controller.phase == Phase.IDLE
    assert not window.screens.windows
    assert len(window.pending_events) == 1
    assert (window.config.root / "pending-events.json").is_file()
    assert "待保存" in window.status_label.text()


def test_destroyed_emergency_confirmation_can_be_recreated(window):
    from PySide6.QtCore import QCoreApplication, QEvent

    window.start_timer(90)
    window.request_emergency()
    window.emergency_dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert window.emergency_dialog is None
    window.request_emergency()
    assert window.emergency_dialog.isVisible()
    answer(window.emergency_dialog, True)
    assert window.controller.phase == Phase.IDLE


def test_overlay_withdrawn_before_media_driver_stop(window, clock, monkeypatch):
    window.start_timer(1)
    clock.advance(1)
    window.tick()
    video = window.screens.video
    checked = []

    def close():
        assert not window.screens.windows
        checked.append(True)

    monkeypatch.setattr(video, "close", close)
    window.request_emergency()
    answer(window.emergency_dialog, True)
    assert checked == [True]


def test_repeated_complete_gui_cycles_leave_no_player_or_window(window, clock):
    for _ in range(3):
        window.start_timer(1)
        clock.advance(1)
        window.tick()
        assert len(window.screens.windows) == len(window.screens.app.screens())
        clock.advance(300)
        window.tick()
        assert window.controller.phase == Phase.IDLE
        assert not window.screens.windows and window.screens.video is None
        assert not window.refresh.isActive()
    assert window.records.stats()["BREAK_COMPLETED"] == 3
