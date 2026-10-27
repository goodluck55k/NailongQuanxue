"""Observe session/power messages for this window. Never intercept system input."""
import ctypes
from ctypes import wintypes
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer


class WindowsSessionEvents(QAbstractNativeEventFilter):
    def __init__(self, app, window):
        super().__init__()
        self.app, self.window = app, window
        self.hwnd = int(window.winId())
        self.registered = False
        self.wts = None
        if sys.platform == "win32":
            self.wts = ctypes.WinDLL("wtsapi32", use_last_error=True)
            self.wts.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]
            self.wts.WTSUnRegisterSessionNotification.argtypes = [wintypes.HWND]
            self.registered = bool(self.wts.WTSRegisterSessionNotification(self.hwnd, 0))
            if not self.registered:
                window.status_label.setText("会话通知注册失败，锁屏计时暂停尚不可保证，请重启应用后重试。")
            app.installNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):
        if sys.platform != "win32" or bytes(event_type) not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if int(msg.hWnd or 0) != self.hwnd:
            return False, 0
        change = None
        if msg.message == 0x02B1:  # WM_WTSSESSION_CHANGE
            if msg.wParam in (7, 8):
                change = ("locked", msg.wParam == 7)
            elif msg.wParam in (1, 2, 3, 4):
                change = ("disconnected", msg.wParam in (2, 4))
        elif msg.message == 0x0218:  # WM_POWERBROADCAST
            if msg.wParam == 4:
                change = ("suspended", True)
            elif msg.wParam in (7, 18):
                change = ("suspended", False)
        if change is not None:
            # Native notifications already run on the GUI thread. Settle time
            # immediately at suspend/lock; don't postpone it until after sleep.
            self.window.session_change(*change)
        return False, 0

    def close(self):
        if sys.platform == "win32":
            self.app.removeNativeEventFilter(self)
            if self.registered:
                self.wts.WTSUnRegisterSessionNotification(self.hwnd)
                self.registered = False
