from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .timer_controller import format_time


class ReminderWindow(QWidget):
    """One non-activating, click-through surface for both notification types."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle("奶龙劝学 提醒")
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.addWidget(self.label)
        self.setStyleSheet("ReminderWindow {background:#FFF9EA; border:1px solid #E7CD89;}"
                           "QLabel {color:#40301C; font:14px 'Microsoft YaHei UI';}")
        self.expiry = QTimer(self)
        self.expiry.setSingleShot(True)
        self.expiry.timeout.connect(self.hide)
        self.mode: str | None = None

    @staticmethod
    def placement(available: QRect) -> QRect:
        margin = min(16, max(0, min(available.width(), available.height()) // 10))
        width = max(1, min(260, available.width() - 2 * margin))
        height = max(1, min(90, available.height() - 2 * margin))
        return QRect(available.right() - margin - width + 1,
                     available.bottom() - margin - height + 1, width, height)

    def reposition(self):
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(self.placement(screen.availableGeometry()))

    def show_minutes(self, minutes: int):
        self.mode = "minutes"
        self.label.setText(f"距离强制休息还有 {minutes} 分钟")
        self.reposition()
        self.show()
        self.expiry.start(4000)

    def show_final(self, seconds: int):
        self.expiry.stop()
        self.mode = "final"
        text = f"即将休息\n{format_time(seconds)}"
        if self.label.text() != text:
            self.label.setText(text)
        if not self.isVisible():
            self.reposition()
            self.show()

    def clear(self):
        self.expiry.stop()
        self.mode = None
        self.hide()

    def show_completed(self, next_round=None):
        self.mode = "completed"
        self.label.setText(f"休息完成，已进入第 {next_round} 轮监督" if next_round else "五分钟休息完成，做得很好！")
        self.reposition()
        self.show()
        self.expiry.start(5000)
