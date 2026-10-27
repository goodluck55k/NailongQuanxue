from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QPushButton
import pytest

from app.config_store import ConfigStore
from app.main_window import MainWindow
from app.overlay_window import OverlayWindow
from app.photo_storage import PhotoStorage
from app.reminder_window import ReminderWindow
from app.supervision import DECLARATION, Phase, Supervision
from app.usage_clock import ActiveClock


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


class FakeCamera(QObject):
    preview = Signal(QImage)
    captured = Signal(QImage)
    error = Signal(str)
    starts = 0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False

    def start(self):
        type(self).starts += 1
        self.active = True

    def capture(self):
        image = QImage(80, 60, QImage.Format.Format_RGB32)
        image.fill(QColor("#587AC2"))
        self.captured.emit(image)

    def stop(self):
        self.active = False


@pytest.fixture
def window(qapp, clock, tmp_path, monkeypatch):
    monkeypatch.setattr("app.screen_manager.VideoBreak", FakeVideo)
    FakeCamera.starts = 0
    win = MainWindow(Supervision(ActiveClock(clock), clock), ConfigStore(tmp_path), camera_factory=FakeCamera)
    win.show()
    yield win
    win.shutdown()
    win.close()
    win.deleteLater()


def answer(box, accepted):
    QTest.mouseClick(box.button(QMessageBox.StandardButton.Yes if accepted else QMessageBox.StandardButton.No),
                     Qt.MouseButton.LeftButton)


def open_preview(window):
    window.request_surrender()
    dialog = window.surrender
    assert dialog.declaration.text() == ""
    assert not dialog.next_button.isEnabled()
    dialog.declaration.setText(DECLARATION)
    QTest.mouseClick(dialog.next_button, Qt.MouseButton.LeftButton)
    QTest.mouseClick(dialog.capture_button, Qt.MouseButton.LeftButton)
    assert dialog.confirm_button.isEnabled()
    return dialog


def test_initial_ui_and_settings_only_three_sections(window):
    assert window.windowTitle() == "奶龙劝学"
    assert window.ring.text == "30:00"
    assert window.controller.phase == Phase.IDLE
    window.open_settings()
    assert [window.settings.tabs.tabText(i) for i in range(3)] == ["监督模式", "照片存储", "投降档案馆"]
    assert window.settings.tabs.count() == 3


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


def test_camera_only_after_step_two_cancel_writes_nothing(window):
    window.start_timer(90)
    window.request_surrender()
    assert FakeCamera.starts == 0
    dialog = window.surrender
    assert "紧急退出" not in [button.text() for button in dialog.findChildren(QPushButton)]
    for invalid in ("", "我是废物 ", "我是废勿"):
        dialog.declaration.setText(invalid)
        assert not dialog.next_button.isEnabled()
    dialog.declaration.setText(DECLARATION)
    dialog.next_step()
    assert FakeCamera.starts == 1
    assert "紧急退出" not in [button.text() for button in dialog.findChildren(QPushButton)]
    dialog.capture()
    backend = dialog.backend
    cancel = next(button for button in dialog.findChildren(QPushButton) if button.text() == "继续坚持 / 取消")
    QTest.mouseClick(cancel, Qt.MouseButton.LeftButton)
    assert not backend.active
    assert not list(window.config.root.rglob("*.jpg"))
    assert window.records.all() == []
    assert window.controller.phase == Phase.RUNNING


def test_confirm_saves_once_and_stops_automatic_loop(window):
    window.config.save(mode="automatic")
    window.start_timer(90)
    dialog = open_preview(window)
    token = dialog.token
    QTest.mouseClick(dialog.confirm_button, Qt.MouseButton.LeftButton)
    assert window.controller.phase == Phase.IDLE
    assert len(window.records.all()) == 1
    record = window.records.all()[0]
    assert record["event_type"] == "EARLY_SURRENDER"
    assert record["photo_status"] == "saved"
    assert Path(record["photo_path"]).read_bytes().startswith(b"\xff\xd8")
    window.confirm_surrender(token, b"\xff\xd8late")
    assert len(window.records.all()) == 1
    assert len(list(window.config.root.rglob("*.jpg"))) == 1


def test_quota_still_requires_real_capture_pipeline_and_records_no_file(window, monkeypatch):
    monkeypatch.setattr(PhotoStorage, "used_bytes", lambda self: self.limit)
    window.start_timer(90)
    dialog = open_preview(window)
    dialog.confirm()
    record = window.records.all()[0]
    assert record["photo_status"] == "quota_exceeded"
    assert record["photo_path"] is None
    assert not list(window.config.root.rglob("*.jpg"))
    assert window.controller.phase == Phase.IDLE


def test_camera_workflow_invalidated_at_usage_deadline(window, clock):
    window.start_timer(15)
    dialog = open_preview(window)
    backend = dialog.backend
    clock.advance(15)
    window.tick()
    assert window.surrender is None and not backend.active
    assert dialog.photo.isNull()
    assert window.controller.phase == Phase.BREAK_ACTIVE
    assert window.records.all() == []


def test_break_completion_cancels_photo_and_toast_five_seconds(window, clock):
    window.start_timer(1)
    clock.advance(1)
    window.tick()
    dialog = open_preview(window)
    clock.advance(300)
    window.tick()
    assert dialog.photo.isNull()
    assert window.surrender is None
    assert not window.screens.active
    assert window.controller.phase == Phase.IDLE
    assert [row["event_type"] for row in window.records.all()] == ["BREAK_COMPLETED"]
    assert window.reminder.mode == "completed"
    assert window.reminder.expiry.interval() == 5000


def test_emergency_cancels_camera_and_all_overlays(window, clock):
    window.start_timer(1)
    clock.advance(1)
    window.tick()
    dialog = open_preview(window)
    window.request_emergency()
    answer(window.emergency_dialog, False)
    assert window.controller.phase == Phase.BREAK_ACTIVE
    window.request_emergency()
    answer(window.emergency_dialog, True)
    assert window.controller.phase == Phase.IDLE
    assert not window.screens.windows
    assert dialog.photo.isNull() and not dialog.backend.active
    assert window.records.all()[0]["event_type"] == "EMERGENCY_EXIT"
    assert not list(window.config.root.rglob("*.jpg"))


def test_lock_cancels_camera_and_pauses_usage(window, clock):
    window.start_timer(90)
    dialog = open_preview(window)
    window.session_change("locked", True)
    clock.advance(1000)
    window.tick()
    assert window.ring.text == "01:30"
    assert window.surrender is None and not dialog.backend.active
    window.session_change("locked", False)
    assert window.surrender is None


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
    frame = overlay.grab().toImage()
    assert frame.pixelColor(0, 300) == QColor("#FFFFFF")
    assert frame.pixelColor(799, 300) == QColor("#FFFFFF")
    assert frame.pixelColor(250, 0) == QColor("#DD3344")
    assert frame.pixelColor(549, 599) == QColor("#DD3344")
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


def test_camera_failure_retry_preserves_emergency_exit(window):
    class UnavailableCamera(FakeCamera):
        def start(self):
            self.error.emit("摄像头被占用或权限被拒绝，请重试")

    window.camera_factory = UnavailableCamera
    window.start_timer(90)
    window.request_surrender()
    dialog = window.surrender
    dialog.declaration.setText(DECLARATION)
    dialog.next_step()
    assert "被占用" in dialog.message.text()
    assert not dialog.confirm_button.isEnabled()
    first = dialog.backend
    dialog.open_camera()
    assert dialog.backend is not first
    window.tray.emergency_action.trigger()
    answer(window.emergency_dialog, True)
    assert window.controller.phase == Phase.IDLE
    assert window.surrender is None
    assert not list(window.config.root.rglob("*.jpg"))


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
