from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from .photo_storage import PhotoStorage
from .records_view import RecordsView
from .theme import STYLE


class SettingsDialog(QDialog):
    preferences_changed = Signal()

    def __init__(self, config, records, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("奶龙劝学 — 设置")
        self.setStyleSheet(STYLE)
        self.resize(840, 550)
        self.setMinimumSize(640, 420)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        mode_page = QWidget()
        mode_layout = QVBoxLayout(mode_page)
        mode_layout.addWidget(QLabel("监督模式"))
        self.mode = QComboBox()
        self.mode.addItem("手动计时", "manual")
        self.mode.addItem("自动循环监督", "automatic")
        self.mode.setCurrentIndex(1 if config.values["mode"] == "automatic" else 0)
        self.mode.currentIndexChanged.connect(self.save_mode)
        mode_layout.addWidget(self.mode)
        note = QLabel("只影响下一次手动开始。当前监督模式和轮次已锁定。\n"
                      "自动循环：完成五分钟休息后进入下一轮；投降或紧急退出会结束整个循环。")
        note.setWordWrap(True)
        mode_layout.addWidget(note)
        mode_layout.addStretch()
        self.tabs.addTab(mode_page, "监督模式")
        storage_page = QWidget()
        storage_layout = QVBoxLayout(storage_page)
        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        self.capacity_label = QLabel()
        self.capacity_label.setWordWrap(True)
        storage_layout.addWidget(self.path_label)
        storage_layout.addWidget(self.capacity_label)
        buttons = QHBoxLayout()
        for text, callback in (("选择本地文件夹", self.choose_folder), ("查看文件夹", self.open_folder),
                               ("删除照片…", self.select_delete)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        storage_layout.addLayout(buttons)
        migration = QLabel("切换目录只影响以后确认保存的新照片，不移动或删除旧文件。\n"
                           "内部上限 100 × 1024 × 1024 字节，90 MB 起提示清理；不自动删除照片。\n"
                           "删除档案不会自动删除照片；旧目录的照片可从对应事件查看或自行管理。")
        migration.setWordWrap(True)
        storage_layout.addWidget(migration)
        storage_layout.addStretch()
        self.tabs.addTab(storage_page, "照片存储")
        self.records = RecordsView(records)
        self.tabs.addTab(self.records, "投降档案馆")
        layout.addWidget(self.tabs)
        close = QPushButton("完成")
        close.clicked.connect(self.accept)
        layout.addWidget(close)
        self.update_capacity()

    def save_mode(self):
        try:
            self.config.save(mode=self.mode.currentData())
            self.preferences_changed.emit()
        except (OSError, ValueError):
            QMessageBox.warning(self, "设置未保存", "无法写入本地配置，原设置未修改。")

    def update_capacity(self):
        path = self.config.values["photo_directory"]
        self.path_label.setText(f"照片路径：{path}")
        try:
            used, free, warning = PhotoStorage(path).usage()
            message = f"已用 {used / 1048576:.2f} MB / 100 MB   ·   剩余 {free / 1048576:.2f} MB"
            self.capacity_label.setText(message + ("\n已达到 90 MB，请手动清理；不会自动删除。" if warning else ""))
        except (OSError, ValueError):
            self.capacity_label.setText("目录不可访问，保存照片可能失败；紧急退出不受影响。")

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "选择本地照片目录", self.config.values["photo_directory"])
        if not path:
            return
        try:
            storage = PhotoStorage(path)
            storage.check_writable()
            self.config.save(photo_directory=str(storage.directory))
            self.preferences_changed.emit()
            self.update_capacity()
        except (OSError, ValueError):
            QMessageBox.warning(self, "目录不可用", "请选择可写的本地文件夹。旧目录与旧照片保持不变。")

    def open_folder(self):
        path = Path(self.config.values["photo_directory"])
        try:
            path.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except OSError:
            QMessageBox.warning(self, "无法打开", "照片目录不可访问。")

    def select_delete(self):
        directory = Path(self.config.values["photo_directory"]).resolve()
        names, _ = QFileDialog.getOpenFileNames(self, "选择要手动删除的照片", str(directory), "照片 (*.jpg *.jpeg)")
        if not names:
            return
        paths = [Path(name) for name in names]
        if any(path.is_symlink() or not path.resolve().is_relative_to(directory) for path in paths):
            QMessageBox.warning(self, "无法删除", "仅允许选择当前照片目录内的照片。")
            return
        answer = QMessageBox.question(self, "删除照片", f"删除选中的 {len(paths)} 张照片？档案记录仍保留。",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            try:
                for path in paths:
                    path.unlink(missing_ok=True)
                if self.records.store is not None:
                    self.records.store.mark_photos_deleted(paths)
                self.records.refresh()
                self.update_capacity()
            except Exception:
                QMessageBox.warning(self, "部分照片未删除", "请检查文件权限，未继续删除其他文件。")
