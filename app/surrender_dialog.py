from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from .camera_capture import CameraCapture
from .supervision import DECLARATION
from .theme import STYLE


class ImageView(QLabel):
    def __init__(self):
        super().__init__()
        self.image = QImage()
        self.setMinimumSize(260, 160)
        self.setMaximumHeight(300)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:white; border:1px solid #E3D7C1; border-radius:10px;")

    def show_image(self, image):
        self.image = image
        self._render()

    def _render(self):
        if self.image.isNull():
            self.clear()
        else:
            self.setPixmap(QPixmap.fromImage(self.image).scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        self._render()
        super().resizeEvent(event)


class SurrenderDialog(QDialog):
    confirm_requested = Signal(str, bytes)

    def __init__(self, controller, token, parent=None, camera_factory=CameraCapture):
        # The main window may be minimized or hidden to tray while supervising.
        super().__init__(None, Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.controller, self.token = controller, token
        self.camera_factory = camera_factory
        self.backend = None
        self.photo = QImage()
        self.submitting = False
        self.cleaned = False
        self.setWindowTitle("奶龙投降书")
        self.setStyleSheet(STYLE)
        self.resize(540, 480)
        self.setMinimumSize(420, 390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        title = QLabel("再坚持一下，还是选择投降？")
        title.setStyleSheet("font-size:20px; font-weight:600;")
        layout.addWidget(title)
        self.pages = QStackedWidget()
        writing = QWidget()
        page = QVBoxLayout(writing)
        intro = QLabel("第一步 · 手动准确输入下方宣言\n我是废物\n\n计时仍在继续，取消可返回继续坚持。")
        intro.setWordWrap(True)
        page.addWidget(intro)
        self.declaration = QLineEdit()
        self.declaration.setAccessibleName("投降宣言")
        self.declaration.setPlaceholderText("请手动输入宣言")
        page.addWidget(self.declaration)
        self.next_button = QPushButton("下一步 · 拍照")
        self.next_button.setEnabled(False)
        self.next_button.clicked.connect(self.next_step)
        self.declaration.textChanged.connect(lambda text: self.next_button.setEnabled(text == DECLARATION))
        page.addWidget(self.next_button)
        page.addStretch()
        self.pages.addWidget(writing)
        camera_page = QWidget()
        camera_layout = QVBoxLayout(camera_page)
        self.camera_note = QLabel("第二步 · 实时预览 → 拍照 → 确认\n照片仅在确认后保存在本机，不使用麦克风。")
        self.camera_note.setWordWrap(True)
        camera_layout.addWidget(self.camera_note)
        self.preview = ImageView()
        camera_layout.addWidget(self.preview, 1)
        row = QHBoxLayout()
        self.capture_button = QPushButton("拍照")
        self.capture_button.clicked.connect(self.capture)
        self.retry_button = QPushButton("重新连接摄像头")
        self.retry_button.setObjectName("secondaryButton")
        self.retry_button.clicked.connect(self.open_camera)
        self.confirm_button = QPushButton("确认投降")
        self.confirm_button.setEnabled(False)
        self.confirm_button.clicked.connect(self.confirm)
        row.addWidget(self.capture_button)
        row.addWidget(self.retry_button)
        row.addWidget(self.confirm_button)
        camera_layout.addLayout(row)
        self.pages.addWidget(camera_page)
        layout.addWidget(self.pages, 1)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        cancel = QPushButton("继续坚持 / 取消")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)
        self.finished.connect(lambda *_: self.cleanup())

    def next_step(self):
        if self.controller.accept_writing(self.token, self.declaration.text()):
            self.declaration.clear()
            self.pages.setCurrentIndex(1)
            self.open_camera()

    def open_camera(self):
        if not self.controller.valid(self.token) or self.cleaned:
            return
        self.photo = QImage()
        self.preview.show_image(self.photo)
        self.confirm_button.setEnabled(False)
        self.capture_button.setText("拍照")
        self.controller.retake(self.token)
        if self.backend is not None:
            self.backend.stop()
            self.backend.deleteLater()
        self.backend = self.camera_factory(self)
        self.backend.preview.connect(self._live)
        self.backend.captured.connect(self._captured)
        self.backend.error.connect(self._error)
        self.message.setText("正在连接摄像头…")
        self.backend.start()

    def _live(self, image):
        if not self.cleaned and self.photo.isNull() and self.controller.valid(self.token):
            self.preview.show_image(image)
            self.message.setText("摄像头已连接，请主动点击拍照。")

    def _error(self, text):
        if not self.cleaned:
            self.message.setText(text)

    def capture(self):
        if not self.photo.isNull():
            self.photo = QImage()
            self.preview.show_image(self.photo)
            self.confirm_button.setEnabled(False)
            self.capture_button.setText("拍照")
            self.controller.retake(self.token)
            return
        if self.backend is not None and self.controller.valid(self.token):
            self.backend.capture()

    def _captured(self, image):
        if self.cleaned or image.isNull() or not self.controller.mark_captured(self.token):
            return
        self.photo = image.copy()
        self.preview.show_image(self.photo)
        self.capture_button.setText("重新拍照")
        self.confirm_button.setEnabled(True)
        self.message.setText("照片仅在内存中。确认后才会保存；配额已满则不存图，仍可投降。")

    def confirm(self):
        if self.submitting or self.photo.isNull() or not self.controller.valid(self.token):
            return
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not self.photo.save(buffer, "JPG", 90):
            self.message.setText("照片编码失败，请重新拍照。")
            return
        buffer.close()
        self.submitting = True
        self.confirm_button.setEnabled(False)
        self.confirm_requested.emit(self.token, bytes(data))

    def cleanup(self):
        if self.cleaned:
            return
        self.cleaned = True
        if self.backend is not None:
            self.backend.stop()
        self.photo = QImage()
        self.preview.show_image(QImage())
        self.declaration.clear()
