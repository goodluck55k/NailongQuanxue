import pytest
from PySide6.QtGui import QColor, QImage

from app.frame_sampler import (FRAME_WIDTH, JPEG_QUALITY, MAX_SAMPLES, SAMPLE_INTERVAL_MS,
                               FrameSampler)


def image(width=800, height=600, color="#204060"):
    picture = QImage(width, height, QImage.Format.Format_RGB32)
    picture.fill(QColor(color))
    return picture


def half_dark(width=800, height=600):
    picture = QImage(width, height, QImage.Format.Format_RGB32)
    picture.fill(QColor("#ffffff"))
    for y in range(height // 2):
        for x in range(0, width, 7):
            picture.setPixelColor(x, y, QColor("#000000"))
    return picture


def test_offer_throttles_by_interval_and_downscales():
    sampler = FrameSampler()
    assert sampler.offer(image(), 0) is True
    assert sampler.offer(image(), 100) is False
    assert sampler.offer(image(), SAMPLE_INTERVAL_MS) is True
    assert sampler.offer(image(), 1000) is True
    assert sampler.count() == 3
    first = sampler.frames()[0][1]
    assert first.width() == FRAME_WIDTH
    assert first.height() == round(600 * FRAME_WIDTH / 800)


def test_sampler_caps_the_buffer_and_span():
    sampler = FrameSampler(interval_ms=10, limit=4)
    for index in range(10):
        sampler.offer(image(), index * 10)
    assert sampler.count() == 4
    assert sampler.span_ms() == 30
    assert sampler.offer(image(), 500) is False
    sampler.clear()
    assert sampler.count() == 0 and sampler.span_ms() == 0


def test_invalid_images_are_ignored():
    sampler = FrameSampler()
    assert sampler.offer(None, 0) is False
    assert sampler.offer(QImage(), 0) is False
    assert sampler.count() == 0


def test_select_even_images_keeps_both_ends():
    sampler = FrameSampler(interval_ms=1, limit=20)
    for index in range(20):
        sampler.offer(image(color=QColor(0, index * 10, 0).name()), index)
    picked = sampler.select_even(5)
    assert len(picked) == 5
    assert picked[0] is sampler.samples[0][1]
    assert picked[-1] is sampler.samples[-1][1]
    assert len(sampler.select_even(100)) == 20
    assert FrameSampler.select_even_images([], 5) == []


def test_motion_trace_is_zero_for_identical_frames_and_large_for_change():
    flat = image()
    still = FrameSampler()
    assert still.motion_trace([flat, flat, flat]) == [0.0, 0.0]
    changed = still.motion_trace([flat, half_dark()])
    assert len(changed) == 1
    assert changed[0] > 0.01
    assert still.motion_trace([]) == []


def test_encode_jpeg_produces_valid_jpeg_bytes():
    encoded = FrameSampler.encode_jpeg([image(), image()])
    assert len(encoded) == 2
    for data in encoded:
        assert isinstance(data, bytes)
        assert data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9")
    assert FrameSampler.encode_jpeg([None, QImage()]) == []
    assert JPEG_QUALITY == 72
    assert MAX_SAMPLES == 96
