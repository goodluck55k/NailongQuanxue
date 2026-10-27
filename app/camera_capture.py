"""User-initiated still capture to memory. No microphone or captureToFile."""
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QCamera, QImageCapture, QMediaCaptureSession, QMediaDevices, QVideoSink


class CameraCapture(QObject):
    preview = Signal(QImage)
    captured = Signal(QImage)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False
        self.session = self.camera = self.capture_device = self.sink = None
        self.request_id = None

    def start(self):
        devices = QMediaDevices.videoInputs()
        if not devices:
            self.error.emit("没有可用摄像头。请连接摄像头后重试，或取消返回。")
            return
        self.active = True
        self.camera = QCamera(devices[0], self)
        self.session = QMediaCaptureSession(self)
        self.capture_device = QImageCapture(self)
        self.sink = QVideoSink(self)
        self.session.setCamera(self.camera)
        self.session.setImageCapture(self.capture_device)
        self.session.setVideoSink(self.sink)
        self.camera.errorOccurred.connect(lambda *_: self.error.emit(
            "摄像头无法使用，可能被占用或未获权限。请重试，或取消返回。") if self.active else None)
        self.capture_device.errorOccurred.connect(lambda *_: self.error.emit(
            "拍照失败，请重试；尚未保存任何照片。") if self.active else None)
        self.capture_device.imageCaptured.connect(self._captured)
        self.sink.videoFrameChanged.connect(self._preview)
        self.camera.start()

    def _preview(self, frame):
        if self.active and frame.isValid():
            image = frame.toImage()
            if not image.isNull():
                self.preview.emit(image)

    def capture(self):
        if not self.active or self.capture_device is None or not self.capture_device.isReadyForCapture():
            self.error.emit("摄像头尚未准备好，请稍后重试。")
            return
        self.request_id = self.capture_device.capture()
        if self.request_id < 0:
            self.request_id = None
            self.error.emit("拍照请求失败，请重试。")

    def _captured(self, identifier, image):
        if self.active and self.request_id == identifier and not image.isNull():
            self.request_id = None
            self.captured.emit(image.copy())

    def stop(self):
        self.active = False
        self.request_id = None
        if self.camera is not None:
            self.camera.stop()
        if self.session is not None:
            self.session.setCamera(None)
            self.session.setImageCapture(None)
            self.session.setVideoSink(None)
        for item in (self.camera, self.capture_device, self.sink, self.session):
            if item is not None:
                item.deleteLater()
        self.session = self.camera = self.capture_device = self.sink = None
