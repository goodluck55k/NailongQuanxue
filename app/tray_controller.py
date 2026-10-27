from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def application_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#FFCE54"))
    painter.drawRoundedRect(3, 3, 58, 58, 18, 18)
    painter.setBrush(QColor("#40301C"))
    painter.drawEllipse(17, 23, 7, 9)
    painter.drawEllipse(40, 23, 7, 9)
    painter.setPen(QColor("#40301C"))
    painter.drawArc(23, 34, 18, 11, 180 * 16, 180 * 16)
    painter.end()
    return QIcon(pixmap)


class TrayController(QObject):
    show_requested = Signal()
    surrender_requested = Signal()
    emergency_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.icon = QSystemTrayIcon(application_icon(), self)
        self.icon.setToolTip("奶龙劝学 — 少玩一会儿，多学一点")
        self.menu = QMenu()
        self.menu.addAction("显示主界面", self.show_requested.emit)
        self.stop_action = self.menu.addAction("申请停止监督", self.surrender_requested.emit)
        self.emergency_action = self.menu.addAction("紧急退出", self.emergency_requested.emit)
        self.quit_action = self.menu.addAction("退出软件", self.quit_requested.emit)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        self.set_active(False)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.icon.show()

    def _activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_requested.emit()

    def set_active(self, active):
        self.stop_action.setEnabled(active)
        self.emergency_action.setEnabled(active)
        self.quit_action.setEnabled(not active)

    def close(self):
        self.icon.hide()
        self.menu.close()
        self.menu.deleteLater()
