"""Bounded in-memory sampling of the camera stream that is being recorded.

Frames are taken from the same QVideoSink that feeds the recorder, so they are
the frames of the saved clip. Nothing is written to disk, nothing is kept after
the verdict, and the buffer is capped so a long or stalled stream cannot grow
without bound.
"""
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage

SAMPLE_INTERVAL_MS = 250
MAX_SAMPLES = 96
FRAME_WIDTH = 640
MOTION_WIDTH = 64
MOTION_HEIGHT = 48
JPEG_QUALITY = 72


class FrameSampler:
    def __init__(self, interval_ms=SAMPLE_INTERVAL_MS, max_width=FRAME_WIDTH,
                 limit=MAX_SAMPLES):
        self.interval_ms = interval_ms
        self.max_width = max_width
        self.limit = limit
        self.samples: list[tuple[int, QImage]] = []
        self._last_ms = None

    def reset(self):
        self.samples = []
        self._last_ms = None

    def offer(self, image, elapsed_ms):
        """Store a downscaled copy at most every interval_ms; never blocks."""
        if image is None or image.isNull() or len(self.samples) >= self.limit:
            return False
        elapsed_ms = max(0, int(elapsed_ms))
        if self._last_ms is not None and elapsed_ms - self._last_ms < self.interval_ms:
            return False
        self._last_ms = elapsed_ms
        width = min(self.max_width, image.width())
        scaled = (image.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
                  if width < image.width() else image.copy())
        self.samples.append((elapsed_ms, scaled))
        return True

    def frames(self):
        return list(self.samples)

    def count(self):
        return len(self.samples)

    def span_ms(self):
        if len(self.samples) < 2:
            return 0
        return self.samples[-1][0] - self.samples[0][0]

    def select_even(self, limit):
        """Evenly spaced selection in time order, always including both ends."""
        return self.select_even_images(self.samples, limit)

    @staticmethod
    def select_even_images(samples, limit):
        if not samples or limit < 1:
            return []
        if len(samples) <= limit:
            return [image for _, image in samples]
        if limit == 1:
            return [samples[len(samples) // 2][1]]
        step = (len(samples) - 1) / (limit - 1)
        picked = [samples[round(index * step)] for index in range(limit)]
        return [image for _, image in picked]

    @staticmethod
    def _gray_bytes(image):
        gray = image.scaled(MOTION_WIDTH, MOTION_HEIGHT).convertToFormat(
            QImage.Format.Format_Grayscale8)
        stride, height = gray.bytesPerLine(), gray.height()
        # constBits() is a view onto QImage-owned memory; copy it so the buffer
        # stays valid after the temporary QImage goes away.
        data = bytes(gray.constBits())
        return data, stride, height

    def motion_trace(self, images=None):
        """Mean absolute gray-level difference between consecutive frames (0..1)."""
        images = list(images if images is not None else [image for _, image in self.samples])
        trace = []
        previous = None
        for image in images:
            if image is None or image.isNull():
                continue
            current = self._gray_bytes(image)
            if previous is not None and previous[1] == current[1] and previous[2] == current[2]:
                old, new, stride, height = previous[0], current[0], current[1], current[2]
                total = 0
                for row in range(height):
                    offset = row * stride
                    total += sum(abs(new[offset + x] - old[offset + x]) for x in range(MOTION_WIDTH))
                trace.append(total / (MOTION_WIDTH * height * 255.0))
            previous = current
        return trace

    @staticmethod
    def encode_jpeg(images, quality=JPEG_QUALITY):
        encoded = []
        for image in images:
            if image is None or image.isNull():
                continue
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            if image.save(buffer, "JPG", quality):
                encoded.append(bytes(data))
            buffer.close()
        return encoded

    def clear(self):
        self.samples = []
        self._last_ms = None
