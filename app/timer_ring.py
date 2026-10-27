from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class TimerRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = "30:00"
        self.caption = "等待开始"
        self.progress = 1.0
        self.setMinimumSize(280, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("剩余时间")

    def set_state(self, text, caption, progress):
        self.text, self.caption = text, caption
        self.progress = max(0.0, min(1.0, progress))
        self.setAccessibleDescription(f"{caption}，{text}")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = max(80, min(self.width() - 28, self.height() - 20, 330))
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        painter.setPen(QPen(QColor("#FBF0D6"), 15, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawEllipse(rect)
        painter.setPen(QPen(QColor("#FFCE54"), 15, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 90 * 16, -round(360 * 16 * self.progress))
        painter.setPen(QColor("#40301C"))
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(round(min(68, side / (len(self.text) * .68))))
        painter.setFont(font)
        painter.drawText(rect.adjusted(16, -18, -16, -18), Qt.AlignmentFlag.AlignCenter, self.text)
        font.setBold(False)
        font.setPixelSize(15)
        painter.setFont(font)
        painter.setPen(QColor("#887963"))
        caption = QRectF(rect.x(), rect.center().y() + 38, rect.width(), 30)
        painter.drawText(caption, Qt.AlignmentFlag.AlignCenter, self.caption)
