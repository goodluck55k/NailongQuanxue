"""One overlay per screen; live reconciliation for topology and DPI changes."""

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from .overlay_window import OverlayWindow
from .resources import fallback_asset
from .timer_controller import format_time
from .video_break import VideoBreak


class ScreenManager(QObject):
    released = Signal()
    release_requested = Signal()
    layout_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.app = QGuiApplication.instance()
        self.windows: dict[object, OverlayWindow] = {}
        self._connections: dict[object, list] = {}
        self.active = False
        self.pixmap = QPixmap()
        self.dialog = None
        self.video = None
        self.last_frame = None
        self.fallback_reason = None
        self.remaining = 300
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(50)
        self.refresh_timer.timeout.connect(self.reconcile)
        self.app.screenAdded.connect(self._screen_added)
        self.app.screenRemoved.connect(self._screen_removed)
        self.app.primaryScreenChanged.connect(self.schedule)
        for screen in self.app.screens():
            self._watch(screen)

    def _watch(self, screen):
        if screen in self._connections:
            return
        signals = [screen.geometryChanged, screen.availableGeometryChanged,
                   screen.logicalDotsPerInchChanged, screen.physicalDotsPerInchChanged]
        for signal in signals:
            signal.connect(self.schedule)
        self._connections[screen] = signals

    def _screen_added(self, screen):
        self._watch(screen)
        self.schedule()

    def _screen_removed(self, screen):
        # The removed QScreen can be destroyed immediately after this signal.
        for signal in self._connections.pop(screen, []):
            try:
                signal.disconnect(self.schedule)
            except RuntimeError:
                pass
        window = self.windows.pop(screen, None)
        if window is not None:
            self._dismiss_dialog()
            window.dispose()
        self.schedule()

    def schedule(self, *_):
        self.refresh_timer.start()

    def show_overlays(self, pixmap: QPixmap):
        if self.active:
            return
        self.pixmap = pixmap
        self.active = True
        self.last_frame = None
        self.fallback_reason = None
        self.reconcile()
        self.video = VideoBreak(self)
        self.video.frame_ready.connect(self._video_frame)
        self.video.failed.connect(self._video_failed)
        self.video.start()

    def _video_frame(self, image):
        if not self.active:
            return
        self.last_frame = image
        primary = self.windows.get(self.app.primaryScreen())
        if primary is not None:
            primary.set_frame(image)

    def _video_failed(self, reason):
        self.fallback_reason = reason
        self.last_frame = None
        for screen, window in self.windows.items():
            if screen == self.app.primaryScreen():
                window.set_fallback(self.pixmap, reason if self.pixmap.isNull() else None)

    def update_remaining(self, seconds):
        self.remaining = seconds
        for window in self.windows.values():
            window.rest_label.setText(format_time(seconds))

    def reconcile(self):
        screens = self.app.screens()
        primary = self.app.primaryScreen()
        if self.active:
            for screen in list(self.windows):
                if screen not in screens:
                    self._dismiss_dialog()
                    self.windows.pop(screen).dispose()
            for screen in screens:
                if screen not in self.windows:
                    window = OverlayWindow(self.pixmap)
                    window.release_requested.connect(self.request_release)
                    self.windows[screen] = window
                self.windows[screen].place_on_screen(screen, screen == primary)
                window = self.windows[screen]
                if screen == primary:
                    if self.last_frame is not None:
                        window.set_frame(self.last_frame)
                    else:
                        window.set_fallback(self.pixmap, self.fallback_reason if self.pixmap.isNull() else None)
                window.rest_label.setText(format_time(self.remaining))
        self.layout_changed.emit()

    def request_release(self):
        if not self.active:
            return
        self.release_requested.emit()

    def clear(self):
        self.active = False
        self.refresh_timer.stop()
        self._dismiss_dialog()
        # Release the desktop first, even if a media driver's stop is slow.
        for window in self.windows.values():
            window.hide()
            window.dispose()
        self.windows.clear()
        if self.video is not None:
            self.video.close()
            self.video = None
        self.last_frame = None
        self.pixmap = QPixmap()

    def _dismiss_dialog(self):
        if self.dialog is not None:
            dialog, self.dialog = self.dialog, None
            dialog.close()
            dialog.deleteLater()

    def shutdown(self):
        self.clear()
        self.app.screenAdded.disconnect(self._screen_added)
        self.app.screenRemoved.disconnect(self._screen_removed)
        self.app.primaryScreenChanged.disconnect(self.schedule)
        for signals in self._connections.values():
            for signal in signals:
                signal.disconnect(self.schedule)
        self._connections.clear()
