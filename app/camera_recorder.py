"""Records the surrender clip from the camera and samples frames while it runs.

No audio input is ever attached to the capture session, so the recorder has no
microphone source. The finished file is a temporary clip: it is handed to the
archive only after the user confirms a verified challenge, and it is deleted
when the dialog closes.
"""
import tempfile
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtMultimedia import (QCamera, QMediaCaptureSession, QMediaDevices, QMediaFormat,
                                  QMediaRecorder, QVideoSink)

from .frame_sampler import FrameSampler

DEFAULT_CLIP_MS = 12000
MIN_CLIP_MS = 6000
# A recorder that never reaches StoppedState must not trap the dialog.
STOP_WATCHDOG_MS = 12000
TICK_MS = 100
MIN_FRAMES = 6


def clip_directory():
    folder = Path(tempfile.gettempdir()) / "NailongQuanxue" / "clips"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


STALE_CLIP_SECONDS = 24 * 3600


_PENDING_DELETES = []
_RETRY_TIMER = None


def _retry_pending_deletes():
    global _RETRY_TIMER
    for path in list(_PENDING_DELETES):
        try:
            Path(path).unlink(missing_ok=True)
            _PENDING_DELETES.remove(path)
        except OSError:
            continue
    if not _PENDING_DELETES and _RETRY_TIMER is not None:
        _RETRY_TIMER.stop()


def _retry_timer():
    global _RETRY_TIMER
    if _RETRY_TIMER is None:
        from PySide6.QtCore import QCoreApplication
        if QCoreApplication.instance() is None:
            return None
        _RETRY_TIMER = QTimer()
        _RETRY_TIMER.setInterval(250)
        _RETRY_TIMER.timeout.connect(_retry_pending_deletes)
    return _RETRY_TIMER


def _discard(path):
    """Delete a clip, retrying while the muxer still holds the file open.

    The encoder closes the file a moment after ``QMediaRecorder.stop()``, so a
    single ``unlink()`` can hit a sharing violation on Windows.
    """
    try:
        Path(path).unlink(missing_ok=True)
        return True
    except OSError:
        pass
    key = str(path)
    if key not in _PENDING_DELETES:
        _PENDING_DELETES.append(key)
    timer = _retry_timer()
    if timer is not None and not timer.isActive():
        timer.start()
    return False


def cleanup_stale_clips(max_age_seconds=STALE_CLIP_SECONDS, now=None):
    """Delete clips this app abandoned in an earlier crash.

    Only files this module created (``clip-<hex>.mp4``) inside the app's own
    temporary directory are touched, so unrelated user files stay safe.
    """
    folder = clip_directory()
    cutoff = (time.time() if now is None else now) - max_age_seconds
    removed = 0
    for path in folder.glob("clip-*.mp4"):
        try:
            if path.is_file() and not path.is_symlink() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


class CameraRecorder(QObject):
    started = Signal()
    progress = Signal(int, int)
    preview = Signal(object)
    finished = Signal(str, object, int)
    failed = Signal(str)

    def __init__(self, parent=None, clip_ms=DEFAULT_CLIP_MS, sampler=None):
        super().__init__(parent)
        self.clip_ms = int(clip_ms)
        self.sampler = sampler or FrameSampler()
        self.camera = self.session = self.recorder = self.sink = None
        self.active = False
        self.recording = False
        self.path = None
        self.clock = QElapsedTimer()
        self.ticker = QTimer(self)
        self.ticker.setInterval(TICK_MS)
        self.ticker.setTimerType(Qt.TimerType.PreciseTimer)
        self.ticker.timeout.connect(self._tick)
        self.watchdog = QTimer(self)
        self.watchdog.setSingleShot(True)
        self.watchdog.setInterval(STOP_WATCHDOG_MS)
        self.watchdog.timeout.connect(self._stop_timeout)
        self.stopping = False
        self._last_preview = -1000

    def start(self):
        if self.active:
            return
        devices = QMediaDevices.videoInputs()
        if not devices:
            self.failed.emit(
                "没有可用摄像头。请连接摄像头，并在 Windows 设置 → 隐私和安全性 → 摄像头 里"
                "允许本程序访问摄像头后重试，或取消返回。")
            return
        try:
            self.path = clip_directory() / f"clip-{uuid.uuid4().hex}.mp4"
            self.sampler.reset()
            self.recording = False
            self.stopping = False
            self.active = True
            self._last_preview = -1000
            self.camera = QCamera(devices[0], self)
            self.session = QMediaCaptureSession(self)
            self.sink = QVideoSink(self)
            self.recorder = QMediaRecorder(self)
            # Deliberately no audio input: the capture session has one source.
            self.session.setCamera(self.camera)
            self.session.setVideoSink(self.sink)
            self.session.setRecorder(self.recorder)
            self.recorder.setOutputLocation(QUrl.fromLocalFile(str(self.path)))
            self.recorder.setMediaFormat(self._format())
            self.recorder.setQuality(QMediaRecorder.Quality.NormalQuality)
            self.camera.errorOccurred.connect(self._camera_error)
            self.recorder.errorOccurred.connect(self._recorder_error)
            self.recorder.recorderStateChanged.connect(self._state)
            self.sink.videoFrameChanged.connect(self._frame)
            self.camera.activeChanged.connect(self._active)
            self.camera.start()
        except (RuntimeError, ValueError):
            self.fail("摄像头无法启动，可能被占用或未授权。请重试，或取消返回。")

    @staticmethod
    def _format():
        for video in (QMediaFormat.VideoCodec.H264, QMediaFormat.VideoCodec.MPEG4):
            candidate = QMediaFormat(QMediaFormat.FileFormat.MPEG4)
            candidate.setVideoCodec(video)
            if candidate.isSupported(QMediaFormat.ConversionMode.Encode):
                return candidate
        return QMediaFormat()

    def _active(self, active):
        if active and self.active and not self.recording and not self.stopping:
            self._begin()

    def _begin(self):
        try:
            self.recorder.record()
        except RuntimeError:
            self.fail("无法开始录像，请检查摄像头是否被其他程序占用。")
            return
        self.recording = True
        self.clock.start()
        self.ticker.start()
        self.started.emit()

    def _tick(self):
        if not self.recording or self.stopping:
            return
        elapsed = self.clock.elapsed()
        self.progress.emit(elapsed, self.clip_ms)
        if elapsed >= self.clip_ms:
            self.stop_recording()

    def _frame(self, frame):
        if not self.active or not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        elapsed = self.clock.elapsed() if self.recording else 0
        # Repainting the dialog at 30 fps is wasted work; 10 fps is enough.
        if elapsed - self._last_preview >= 100:
            self._last_preview = elapsed
            self.preview.emit(image)
        if self.recording:
            self.sampler.offer(image, elapsed)

    def stop_recording(self):
        """Natural end, or the user stops after MIN_CLIP_MS."""
        if not self.active or not self.recording or self.stopping:
            return
        if self.clock.elapsed() < MIN_CLIP_MS:
            self.fail("动作录像至少需要 6 秒，请再录一次。")
            return
        self.stopping = True
        self.ticker.stop()
        try:
            self.recorder.stop()
        except RuntimeError:
            self.fail("停止录像失败，请重试。")
            return
        self.watchdog.start()

    def _state(self, state):
        if self.stopping and state == QMediaRecorder.RecorderState.StoppedState:
            self._finish()

    def _finish(self):
        if not self.stopping:
            return
        self.watchdog.stop()
        self.recording = False
        self.stopping = False
        self.ticker.stop()
        path, frames, span = self.path, self.sampler.frames(), self.sampler.span_ms()
        if frames and path is not None and path.is_file() and path.stat().st_size > 0 and len(frames) >= MIN_FRAMES:
            self._teardown(keep_file=True)
            self.finished.emit(str(path), frames, span)
            return
        self.fail("录像没有产生可用的画面，请重新录制。")

    def _stop_timeout(self):
        self.fail("录像未能正常结束，请重新录制。")

    def _camera_error(self, *_):
        if self.active:
            self.fail("摄像头无法使用，可能被占用或未获权限。请重试，或取消返回。")

    def _recorder_error(self, *_):
        if self.active:
            self.fail("录像失败，请检查摄像头后重试。")

    def fail(self, message):
        if not self.active and not message:
            return
        self.active = False
        self.recording = False
        self.stopping = False
        self.ticker.stop()
        self.watchdog.stop()
        self._teardown(keep_file=False)
        self.failed.emit(message)

    def stop(self):
        """Cancel: release the device and drop the temporary clip."""
        self.active = False
        self.recording = False
        self.stopping = False
        self.ticker.stop()
        self.watchdog.stop()
        self._teardown(keep_file=False)

    def release(self):
        """Release the camera but keep a finished clip on disk."""
        self.active = False
        self.recording = False
        self.stopping = False
        self.ticker.stop()
        self.watchdog.stop()
        self._teardown(keep_file=True)

    def cleanup_file(self):
        if self.path is None:
            return
        _discard(self.path)
        self.path = None

    def _teardown(self, keep_file):
        path = self.path
        if self.recorder is not None:
            try:
                self.recorder.recorderStateChanged.disconnect(self._state)
            except (RuntimeError, TypeError):
                pass
            if self.recorder.recorderState() == QMediaRecorder.RecorderState.RecordingState:
                try:
                    self.recorder.stop()
                except RuntimeError:
                    pass
        if self.camera is not None:
            try:
                self.camera.stop()
            except RuntimeError:
                pass
            for signal, slot in ((self.camera.errorOccurred, self._camera_error),
                                 (self.camera.activeChanged, self._active)):
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        for signal, slot in ((self.sink.videoFrameChanged if self.sink else None, self._frame),
                             (self.recorder.errorOccurred if self.recorder else None, self._recorder_error)):
            if signal is not None:
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        if self.session is not None:
            self.session.setVideoSink(None)
            self.session.setRecorder(None)
            self.session.setCamera(None)
        for item in (self.camera, self.recorder, self.sink, self.session):
            if item is not None:
                item.deleteLater()
        self.camera = self.recorder = self.sink = self.session = None
        if not keep_file and path is not None:
            _discard(path)
        self.path = path if keep_file else None
