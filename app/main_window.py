"""V1 window upgraded in place to V1.1's single-page supervision UI."""
import json
import sqlite3
import time
from shiboken6 import isValid

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
                               QLabel, QMainWindow, QMessageBox, QPushButton, QSpinBox,
                               QScrollArea, QVBoxLayout, QWidget)

from .camera_capture import CameraCapture
from .config_store import ConfigStore, duration_from_parts
from .photo_storage import PhotoStorage
from .records_store import RecordsStore
from .reminder_window import ReminderWindow
from .resources import fallback_asset
from .screen_manager import ScreenManager
from .settings_dialog import SettingsDialog
from .supervision import Event, Phase, Supervision
from .surrender_dialog import SurrenderDialog
from .theme import STYLE
from .timer_controller import format_time
from .timer_ring import TimerRing
from .tray_controller import TrayController, application_icon


class MainWindow(QMainWindow):
    quit_requested = Signal()

    def __init__(self, controller=None, config=None, records=None, camera_factory=CameraCapture):
        super().__init__()
        self.controller = controller or Supervision()
        self.config = config or ConfigStore()
        self.camera_factory = camera_factory
        self._closing = False
        self.surrender = self.settings = self.emergency_dialog = None
        self._last_phase = Phase.IDLE
        self._completed = False
        self._owns_records = records is None
        self.pending_events = []
        self._next_flush = 0
        self.records = records
        self._data_error = None
        if self.records is None:
            try:
                self.records = RecordsStore(self.config.root / "records.sqlite3")
            except (OSError, sqlite3.Error):
                self._data_error = "档案无法打开，原数据库保留。请检查本地数据目录；紧急退出仍可用。"
        pending = self.config.root / "pending-events.json"
        if pending.exists():
            try:
                self.pending_events = [Event(**value) for value in json.loads(pending.read_text(encoding="utf-8"))]
            except (OSError, ValueError, TypeError):
                self._data_error = "待保存档案无法读取，原文件保留，请检查本地数据目录。"
        self.setWindowTitle("奶龙劝学")
        self.setWindowIcon(application_icon())
        self.setStyleSheet(STYLE)
        area = QApplication.primaryScreen().availableGeometry()
        self.resize(min(960, area.width() - 32), min(700, area.height() - 48))
        self.setMinimumSize(min(640, area.width() - 32), min(460, area.height() - 48))
        root = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(root)
        scroll.setStyleSheet("QScrollArea {background:#FFF9EA; border:0;}")
        self.setCentralWidget(scroll)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(30, 24, 30, 20)
        layout.setSpacing(18)
        header = QHBoxLayout()
        brand = QVBoxLayout()
        title = QLabel("奶龙劝学")
        title.setStyleSheet("font-size:32px; font-weight:800;")
        subtitle = QLabel("少玩一会儿，多学一点")
        subtitle.setObjectName("muted")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        header.addLayout(brand)
        header.addStretch()
        self.settings_button = QPushButton("⚙  设置")
        self.settings_button.setObjectName("secondaryButton")
        self.settings_button.clicked.connect(self.open_settings)
        header.addWidget(self.settings_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)
        card = QFrame()
        card.setObjectName("mainCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 5)
        shadow.setColor(Qt.GlobalColor.lightGray)
        card.setGraphicsEffect(shadow)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 20, 28, 22)
        self.round_label = QLabel("准备好，给自己留一点休息时间")
        self.round_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.round_label.setObjectName("muted")
        card_layout.addWidget(self.round_label)
        center = QHBoxLayout()
        self.ring = TimerRing()
        center.addWidget(self.ring, 2)
        decoration = QVBoxLayout()
        self.mascot = QLabel()
        self.mascot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        asset = fallback_asset()
        if not asset.pixmap.isNull():
            self.mascot.setPixmap(asset.pixmap.scaled(150, 210, Qt.AspectRatioMode.KeepAspectRatio,
                                                      Qt.TransformationMode.SmoothTransformation))
        decoration.addWidget(self.mascot)
        encouragement = QLabel("专注一点\n你会更棒的 ♡")
        encouragement.setAlignment(Qt.AlignmentFlag.AlignCenter)
        encouragement.setStyleSheet("font-size:18px; color:#967649; padding:8px;")
        decoration.addWidget(encouragement)
        center.addLayout(decoration, 1)
        card_layout.addLayout(center, 1)
        inputs = QHBoxLayout()
        self.minutes = QSpinBox()
        self.minutes.setRange(0, 999)
        self.minutes.setValue(int(self.config.values["minutes"]))
        self.minutes.setAccessibleName("分钟")
        self.seconds = QSpinBox()
        self.seconds.setRange(0, 59)
        self.seconds.setValue(int(self.config.values["seconds"]))
        self.seconds.setAccessibleName("秒钟")
        for label, spin in (("分钟", self.minutes), ("秒钟", self.seconds)):
            group = QVBoxLayout()
            group.addWidget(QLabel(label))
            group.addWidget(spin)
            inputs.addLayout(group)
            spin.valueChanged.connect(self._idle_duration_changed)
            spin.editingFinished.connect(self.save_inputs)
        card_layout.addLayout(inputs)
        actions = QHBoxLayout()
        self.start_button = QPushButton("▶  开始计时")
        self.start_button.setMinimumHeight(50)
        self.start_button.clicked.connect(self.start_timer)
        self.stop_button = QPushButton("↻  重置")
        self.stop_button.setObjectName("secondaryButton")
        self.stop_button.setMinimumHeight(50)
        self.stop_button.clicked.connect(self.stop_or_reset)
        actions.addWidget(self.start_button, 1)
        actions.addWidget(self.stop_button, 1)
        card_layout.addLayout(actions)
        layout.addWidget(card, 1)
        footer = QLabel("计时结束后将进入 5 分钟全屏休息")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setObjectName("muted")
        layout.addWidget(footer)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.reminder = ReminderWindow()
        self.screens = ScreenManager(self)
        self.screens.release_requested.connect(self.request_surrender)
        self.screens.layout_changed.connect(self.reminder.reposition)
        self.screens.layout_changed.connect(self.raise_workflow)
        self.tray = TrayController(self)
        self.tray.show_requested.connect(self.restore)
        self.tray.surrender_requested.connect(self.request_surrender)
        self.tray.emergency_requested.connect(self.request_emergency)
        self.tray.quit_requested.connect(self.close)
        self.refresh = QTimer(self)
        self.refresh.setInterval(100)
        self.refresh.setTimerType(Qt.TimerType.PreciseTimer)
        self.refresh.timeout.connect(self.tick)
        self._idle_duration_changed()
        if self._data_error or self.config.error:
            self.status_label.setText(self._data_error or self.config.error)

    def input_seconds(self):
        return duration_from_parts(self.minutes.lineEdit().text(), self.seconds.lineEdit().text())

    def save_inputs(self):
        if self.controller.phase == Phase.IDLE:
            try:
                total = self.input_seconds()
                self.config.save(minutes=total // 60, seconds=total % 60)
            except (OSError, ValueError):
                self.status_label.setText("设置尚未保存，请检查输入和本地数据目录。")

    def _idle_duration_changed(self, *_):
        if self.controller.phase == Phase.IDLE:
            total = self.minutes.value() * 60 + self.seconds.value()
            self.ring.set_state(format_time(total), "本轮已结束" if self._completed else "等待开始", 1)

    def start_timer(self, seconds=None):
        if self.controller.phase != Phase.IDLE:
            return
        self.status_label.setText(self._data_error or "")
        if seconds is None or isinstance(seconds, bool):
            try:
                seconds = self.input_seconds()
            except ValueError as error:
                self.status_label.setText(str(error))
                return
            self.save_inputs()
        self._completed = False
        view = self.controller.start(seconds, self.config.values["mode"])
        self.refresh.start()
        self._render(view)

    def tick(self):
        if self._closing:
            return
        self._render(self.controller.poll())

    def _render(self, view):
        phase = self.controller.phase
        if self.surrender is not None and not self.controller.valid(self.surrender.token):
            self.cancel_surrender()
        if phase != Phase.BREAK_ACTIVE and self.screens.active:
            self.screens.clear()
        if phase == Phase.BREAK_ACTIVE:
            if self.settings is not None:
                self.settings.reject()
            self.reminder.clear()
            if not self.screens.active:
                self.screens.show_overlays(fallback_asset().pixmap)
            self.screens.update_remaining(view.remaining)
        elif phase == Phase.RUNNING:
            if view.final:
                self.reminder.show_final(view.remaining)
            elif view.reminder is not None:
                self.reminder.show_minutes(view.reminder)
        active = phase != Phase.IDLE
        self.minutes.setEnabled(not active)
        self.seconds.setEnabled(not active)
        self.start_button.setEnabled(not active)
        self.stop_button.setText("停止计时" if phase == Phase.RUNNING else "解除限制" if active else "↻  重置")
        self.tray.set_active(active)
        if phase == Phase.IDLE:
            self.refresh.stop()
            if self.emergency_dialog is not None:
                box, self.emergency_dialog = self.emergency_dialog, None
                if isValid(box):
                    box.reject()
                    box.deleteLater()
            if self._last_phase != Phase.IDLE:
                self.reminder.clear()
                self._completed = True
            self._idle_duration_changed()
            self.round_label.setText("本轮已结束，再出发也要照顾好自己" if self._completed else "准备好，给自己留一点休息时间")
        else:
            caption = "休息中" if phase == Phase.BREAK_ACTIVE else "监督中 · 已暂停" if self.controller.active.paused else "监督中"
            duration = 300 if phase == Phase.BREAK_ACTIVE else self.controller.configured
            self.ring.set_state(format_time(view.remaining), caption, view.remaining / duration)
            self.round_label.setText(f"第 {self.controller.round_index} 轮 · " +
                                     ("自动循环监督" if self.controller.mode == "automatic" else "手动计时"))
        self._last_phase = phase
        while self.controller.events:
            event = self.controller.events.pop(0)
            self.pending_events.append(event)
            if event.event_type == "BREAK_COMPLETED":
                self.reminder.show_completed(self.controller.round_index if self.controller.mode == "automatic" else None)
        self.flush_events()

    def flush_events(self):
        if not self.pending_events:
            return
        if time.monotonic() < self._next_flush:
            return
        try:
            if self.records is None:
                raise sqlite3.OperationalError("Archive unavailable")
            for event in self.pending_events:
                self.records.append(event)
            self.pending_events.clear()
            (self.config.root / "pending-events.json").unlink(missing_ok=True)
        except (OSError, sqlite3.Error):
            self._next_flush = time.monotonic() + 5
            self.status_label.setText("档案尚未写入，已保留待保存事件。请检查数据目录；解除和紧急退出不受影响。")
            try:
                self.config.root.mkdir(parents=True, exist_ok=True)
                (self.config.root / "pending-events.json").write_text(
                    json.dumps([event.to_dict() for event in self.pending_events], ensure_ascii=False), encoding="utf-8")
            except OSError:
                self.status_label.setText("数据目录不可写，新事件无法持久保存。原档案未修改；紧急退出仍可用。")

    def stop_or_reset(self):
        if self.controller.phase == Phase.IDLE:
            self.minutes.setValue(int(self.config.values["minutes"]))
            self.seconds.setValue(int(self.config.values["seconds"]))
            self._completed = False
            self._idle_duration_changed()
        else:
            self.request_surrender()

    def request_surrender(self):
        self.tick()
        if self.controller.phase == Phase.IDLE:
            return
        if self.surrender is not None:
            self.raise_workflow()
            return
        token = self.controller.request_surrender()
        if token is None:
            self.tick()
            return
        dialog = SurrenderDialog(self.controller, token, self, self.camera_factory)
        self.surrender = dialog
        dialog.confirm_requested.connect(self.confirm_surrender)
        dialog.finished.connect(lambda *_: self._surrender_closed(token))
        dialog.show()
        self.center_dialog(dialog)
        dialog.declaration.setFocus()

    def _surrender_closed(self, token):
        if self.controller.valid(token):
            self.controller.cancel_surrender()
        if self.surrender is not None and self.surrender.token == token:
            dialog, self.surrender = self.surrender, None
            dialog.cleanup()
            dialog.deleteLater()

    def cancel_surrender(self):
        if self.surrender is not None:
            dialog, self.surrender = self.surrender, None
            dialog.cleanup()
            dialog.reject()
            dialog.deleteLater()

    def confirm_surrender(self, token, jpeg_bytes):
        event = self.controller.confirm_surrender(token)
        self.cancel_surrender()
        if event is None:
            self.tick()
            return
        try:
            saved = PhotoStorage(self.config.values["photo_directory"]).save_confirmed(jpeg_bytes, event.event_type)
            event.photo_status, event.photo_path = saved.status, saved.path
        except (OSError, ValueError):
            event.photo_status = "save_failed"
        self.pending_events.append(event)
        self.tick()
        if event.photo_status == "quota_exceeded":
            self.status_label.setText("已结束监督。照片超过 100 MB 配额，未保存新照片。" +
                                      ("档案待保存，请检查数据目录。" if self.pending_events else "档案已记录。"))
        elif event.photo_status == "save_failed":
            self.status_label.setText("已结束监督，照片未能保存。请检查照片目录；档案标记为保存失败。")
        self.restore()

    def request_emergency(self):
        if self.controller.phase == Phase.IDLE:
            return
        if self.emergency_dialog is not None:
            if isValid(self.emergency_dialog):
                self.emergency_dialog.showNormal()
                self.center_dialog(self.emergency_dialog)
                self.emergency_dialog.raise_()
                self.emergency_dialog.activateWindow()
                return
            self.emergency_dialog = None
        # A dialog owned by the minimized/hidden main window can disappear with
        # its Windows owner. This independent window remains usable over video.
        box = QMessageBox(None)
        box.setStyleSheet(STYLE)
        box.setWindowTitle("紧急退出监督")
        box.setText("立即结束整个监督循环并返回待机？无需填写宣言或拍照。")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.button(QMessageBox.StandardButton.Yes).setText("结束监督")
        box.button(QMessageBox.StandardButton.No).setText("继续坚持")
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.setEscapeButton(QMessageBox.StandardButton.No)
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        box.setWindowModality(Qt.WindowModality.NonModal)
        self.emergency_dialog = box
        box.finished.connect(lambda answer, current=box: self._emergency_answer(answer, current))
        box.destroyed.connect(lambda *_: self._emergency_destroyed(box))
        box.showNormal()
        self.center_dialog(box)
        box.raise_()
        box.activateWindow()

    def _emergency_destroyed(self, box):
        if self.emergency_dialog is box:
            self.emergency_dialog = None

    def _emergency_answer(self, answer, box):
        if self.emergency_dialog is not box:
            return
        self.emergency_dialog = None
        box.deleteLater()
        if answer == QMessageBox.StandardButton.Yes:
            event = self.controller.emergency()
            # Withdraw every blocker before stopping media/camera drivers or
            # writing an archive; a slow device must not trap the desktop.
            self.refresh.stop()
            self.reminder.clear()
            self.screens.clear()
            self.cancel_surrender()
            if event is not None:
                self.pending_events.append(event)
            self.tick()
            self.restore()

    def open_settings(self):
        if self.settings is not None:
            self.settings.raise_()
            return
        dialog = SettingsDialog(self.config, self.records, self)
        self.settings = dialog
        dialog.finished.connect(self._settings_closed)
        dialog.show()
        self.center_dialog(dialog)

    def _settings_closed(self, *_):
        if self.settings is not None:
            dialog, self.settings = self.settings, None
            dialog.deleteLater()

    def session_change(self, reason, paused):
        self.controller.session_pause(reason, paused)
        if paused:
            self.cancel_surrender()
        self.tick()

    def center_dialog(self, dialog):
        screen = QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            dialog.resize(min(dialog.width(), area.width() - 32), min(dialog.height(), area.height() - 32))
            dialog.move(area.center() - dialog.rect().center())

    def raise_workflow(self):
        for dialog in (self.surrender, self.emergency_dialog):
            if dialog is not None and isValid(dialog):
                dialog.showNormal()
                dialog.raise_()
                dialog.activateWindow()

    def restore(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.raise_workflow()

    def closeEvent(self, event):
        if self._closing:
            event.accept()
        elif self.controller.phase == Phase.IDLE:
            self.shutdown()
            event.accept()
            self.quit_requested.emit()
        else:
            event.ignore()
            if self.tray.icon.isSystemTrayAvailable():
                self.hide()
            else:
                self.showMinimized()
                self.status_label.setText("系统托盘不可用，已最小化到任务栏，计时继续。")

    def shutdown(self, *_):
        if self._closing:
            return
        self._closing = True
        self.refresh.stop()
        self.controller.stop()
        self.cancel_surrender()
        for dialog in (self.settings, self.emergency_dialog):
            if dialog is not None:
                dialog.close()
        self.reminder.clear()
        self.reminder.close()
        self.screens.shutdown()
        self.tray.close()
        self._next_flush = 0
        self.flush_events()
        if self.records is not None and self._owns_records:
            self.records.close()
