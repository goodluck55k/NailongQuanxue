"""Exactly one silent player; decoded frames are painted by the overlay widget.

Using QVideoSink avoids native video surfaces hiding release/emergency controls.
No audio output object is attached, so the MP4's AAC track has no output device.
"""
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink

from .resources import resource_path


class VideoBreak(QObject):
    frame_ready = Signal(QImage)
    failed = Signal(str)

    def __init__(self, parent=None, source=None):
        super().__init__(parent)
        self.path = source or resource_path("default_break.mp4")
        self.player = QMediaPlayer(self)
        self.sink = QVideoSink(self)
        self.player.setVideoSink(self.sink)
        self.player.setAudioOutput(None)
        self.player.setLoops(QMediaPlayer.Loops.Infinite)
        self.player.errorOccurred.connect(lambda *_: self.fallback("视频播放失败，使用备用图片"))
        self.sink.videoFrameChanged.connect(self._frame)
        self.player.tracksChanged.connect(lambda: self.player.setActiveAudioTrack(-1))
        self.watchdog = QTimer(self)
        self.watchdog.setSingleShot(True)
        self.watchdog.setInterval(8000)
        self.watchdog.timeout.connect(lambda: self.fallback("视频无有效画面，使用备用图片"))
        self.active = False
        self.fallback_active = False
        self.frames = 0
        self.black_frames = 0

    def start(self):
        if self.active:
            return
        self.active = True
        if not self.path.is_file():
            self.fallback("内置视频缺失，使用备用图片")
            return
        self.player.setSource(QUrl.fromLocalFile(str(self.path)))
        self.watchdog.start()
        self.player.play()

    def _frame(self, frame):
        if not self.active or self.fallback_active or not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        # Sustained all-black frames are treated as a failed decoder output.
        sample = image.scaled(8, 8)
        black = all(max(sample.pixelColor(x, y).red(), sample.pixelColor(x, y).green(),
                        sample.pixelColor(x, y).blue()) < 8 for x in range(8) for y in range(8))
        self.black_frames = self.black_frames + 1 if black else 0
        if self.black_frames >= 90:
            self.fallback("持续黑画面，使用备用图片")
            return
        self.frames += 1
        self.watchdog.start()
        self.frame_ready.emit(image.copy())

    def fallback(self, reason):
        if self.fallback_active or not self.active:
            return
        self.fallback_active = True
        self.watchdog.stop()
        self.player.stop()
        self.failed.emit(reason)

    def close(self):
        self.active = False
        self.watchdog.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        self.player.setVideoSink(None)
        self.deleteLater()
