from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QPushButton, QWidget


class OverlayWindow(QWidget):
    release_requested = Signal()

    def __init__(self, pixmap: QPixmap = None):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("奶龙劝学 — 五分钟休息")
        self.original = pixmap if pixmap is not None else QPixmap()
        self.primary = False
        self.scaled = QPixmap()
        self._cache_key = None
        self._allow_close = False
        self.release_button = QPushButton("解除限制", self)
        self.release_button.setMinimumHeight(44)
        self.release_button.setStyleSheet(
            "QPushButton {background:#FFCE54; color:#40301C; border:2px solid #EAB83E;"
            "border-radius:8px; font:16px 'Microsoft YaHei UI'; padding:8px 16px;}"
            "QPushButton:focus {border:2px solid #725021;}")
        self.release_button.clicked.connect(self.release_requested)
        self.rest_label = QLabel("05:00", self)
        self.rest_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rest_label.setStyleSheet("background:#FFF9EA; color:#40301C; border-radius:12px;"
                                      "font:600 24px 'Microsoft YaHei UI';")
        self.fallback_message = "休息一下\n让眼睛离开屏幕，起身活动。"

    def place_on_screen(self, screen, primary: bool):
        self.winId()
        self.windowHandle().setScreen(screen)
        self.setGeometry(screen.geometry())
        self.primary = primary
        self.release_button.setVisible(primary)
        self.rest_label.setVisible(primary)
        self.showFullScreen()
        # Some window managers replace geometry on the fullscreen transition.
        self.setGeometry(screen.geometry())
        self._position_button()
        self.update()

    def _position_button(self):
        width = min(150, max(1, self.width() - 48))
        height = min(48, max(1, self.height() - 24))
        self.release_button.setGeometry(max(0, self.width() - width - 24),
                                        max(0, self.height() - height - 24), width, height)
        self.rest_label.setGeometry(max(0, self.width() - 164), 24, 140, 54)
        self.release_button.raise_()
        self.rest_label.raise_()

    def set_frame(self, image):
        self.original = QPixmap.fromImage(image)
        self._cache_key = None
        self.update()

    def set_fallback(self, pixmap, message=None):
        self.original = pixmap
        self._cache_key = None
        if message:
            self.fallback_message = message + "\n让眼睛离开屏幕，起身活动。"
        self.update()

    def resizeEvent(self, event):
        self._position_button()
        super().resizeEvent(event)

    @staticmethod
    def image_rect(image_size: QSize, window_size: QSize) -> QRect:
        size = image_size.scaled(window_size, Qt.AspectRatioMode.KeepAspectRatio)
        return QRect((window_size.width() - size.width()) // 2,
                     (window_size.height() - size.height()) // 2,
                     size.width(), size.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        if not self.primary:
            return
        if not self.original.isNull():
            target = self.image_rect(self.original.size(), self.size())
            dpr = self.devicePixelRatioF()
            key = (target.width(), target.height(), dpr)
            if key != self._cache_key:
                self.scaled = self.original.scaled(
                    round(target.width() * dpr), round(target.height() * dpr),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                self.scaled.setDevicePixelRatio(dpr)
                self._cache_key = key
            painter.drawPixmap(target.topLeft(), self.scaled)
        else:
            painter.setPen(QColor("#18344F"))
            font = painter.font()
            font.setPointSize(24)
            painter.setFont(font)
            painter.drawText(self.rect().adjusted(24, 24, -24, -90),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                             self.fallback_message)

    def closeEvent(self, event):
        if self._allow_close:
            event.accept()
        else:
            event.ignore()
            self.release_requested.emit()

    def dispose(self):
        self._allow_close = True
        self.close()
        self.deleteLater()
