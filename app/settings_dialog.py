from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from .ai_panel import AiSettingsPanel
from .config_store import (ConfigWriteError, default_data_directory,
                           forget_data_directory, remembered_data_directory)
from .photo_storage import PhotoStorage
from .records_view import RecordsView
from .theme import STYLE
from .video_archive import WARNING_BYTES as VIDEO_WARNING_BYTES
from .video_archive import VideoArchive


class SettingsDialog(QDialog):
    preferences_changed = Signal()
    ai_changed = Signal(object)

    def __init__(self, config, records, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("奶龙劝学 — 设置")
        self.setStyleSheet(STYLE)
        self.resize(860, 580)
        self.setMinimumSize(660, 440)
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
        for text, callback in (("选择照片文件夹", self.choose_folder), ("查看照片文件夹", self.open_folder),
                               ("删除照片…", self.select_delete)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        storage_layout.addLayout(buttons)
        migration = QLabel("切换目录只影响以后确认保存的新文件，不移动或删除旧文件。\n"
                           "照片上限 100 MB（90 MB 起提示清理），录像上限 512 MB（400 MB 起提示清理）；都不会自动删除。\n"
                           "删除档案不会自动删除照片或录像；旧目录的文件可从对应事件查看或自行管理。")
        migration.setWordWrap(True)
        storage_layout.addWidget(migration)
        storage_layout.addSpacing(10)
        self.video_path_label = QLabel()
        self.video_path_label.setWordWrap(True)
        self.video_capacity_label = QLabel()
        self.video_capacity_label.setWordWrap(True)
        storage_layout.addWidget(self.video_path_label)
        storage_layout.addWidget(self.video_capacity_label)
        video_buttons = QHBoxLayout()
        for text, callback in (("选择录像文件夹", self.choose_video_folder),
                               ("查看录像文件夹", self.open_video_folder)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            video_buttons.addWidget(button)
        storage_layout.addLayout(video_buttons)
        storage_layout.addSpacing(10)
        self.data_dir_label = QLabel()
        self.data_dir_label.setWordWrap(True)
        storage_layout.addWidget(self.data_dir_label)
        reset = QPushButton("恢复默认数据目录")
        reset.clicked.connect(self.reset_data_directory)
        storage_layout.addWidget(reset)
        storage_layout.addStretch()
        self.tabs.addTab(storage_page, "存储与配额")
        self.ai = AiSettingsPanel(config)
        self.ai.saved.connect(self.ai_changed.emit)
        self.tabs.addTab(self.ai, "AI 接入")
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
        except ConfigWriteError as error:
            QMessageBox.warning(self, "设置未保存", str(error))
        except (OSError, ValueError):
            QMessageBox.warning(self, "设置未保存", "无法写入本地配置，原设置未修改。")

    def reset_data_directory(self):
        if forget_data_directory():
            QMessageBox.information(self, "已恢复默认数据目录",
                                    "重启程序后会重新使用默认目录。\n原目录与新目录里的文件都不会被删除。")
        else:
            QMessageBox.information(self, "当前就是默认数据目录",
                                    "没有找到自定义数据目录的记录。")

    def update_data_directory(self):
        remembered = remembered_data_directory()
        text = "数据目录：" + str(self.config.root)
        if remembered is not None:
            text += "\n（自定义目录；默认是 %s）" % default_data_directory()
        self.data_dir_label.setText(text)

    def update_capacity(self):
        path = self.config.values["photo_directory"]
        self.path_label.setText(f"照片路径：{path}")
        try:
            used, free, warning = PhotoStorage(path).usage()
            message = f"照片已用 {used / 1048576:.2f} MB / 100 MB   ·   剩余 {free / 1048576:.2f} MB"
            self.capacity_label.setText(message + ("\n照片已达到 90 MB，请手动清理；不会自动删除。" if warning else ""))
        except (OSError, ValueError):
            self.capacity_label.setText("照片目录不可访问，保存照片可能失败；紧急退出不受影响。")
        video_path = self.config.values.get("video_directory", "")
        self.video_path_label.setText(f"录像路径：{video_path}")
        try:
            used, free, warning = VideoArchive(video_path).usage()
            message = f"录像已用 {used / 1048576:.2f} MB / 512 MB   ·   剩余 {free / 1048576:.2f} MB"
            self.video_capacity_label.setText(message + (
                f"\n录像已达到 {VIDEO_WARNING_BYTES // 1048576} MB，请手动清理；不会自动删除。"
                if warning else ""))
        except (OSError, ValueError):
            self.video_capacity_label.setText("录像目录不可访问，保存录像可能失败；投降仍可确认。")
        try:
            self.update_data_directory()
        except Exception:
            pass

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

    def choose_video_folder(self):
        path = QFileDialog.getExistingDirectory(self, "选择本地录像目录", self.config.values.get("video_directory", ""))
        if not path:
            return
        try:
            archive = VideoArchive(path)
            archive.check_writable()
            self.config.save(video_directory=str(archive.directory))
            self.preferences_changed.emit()
            self.update_capacity()
        except (OSError, ValueError):
            QMessageBox.warning(self, "目录不可用", "请选择可写的本地文件夹。旧目录与旧录像保持不变。")

    def open_folder(self):
        self._open(Path(self.config.values["photo_directory"]), "照片目录不可访问。")

    def open_video_folder(self):
        self._open(Path(self.config.values.get("video_directory", "")), "录像目录不可访问。")

    @staticmethod
    def _open(path, message):
        try:
            path.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except OSError:
            QMessageBox.warning(None, "无法打开", message)

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
