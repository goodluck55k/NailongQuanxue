import hashlib
from pathlib import Path

from PySide6.QtGui import QImage

from app.resources import resource_path
from app.video_break import VideoBreak
from tools.scan_public import FIXED_ASSETS


def test_fixed_resources_unchanged_and_cwd_independent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name, expected in FIXED_ASSETS.items():
        path = resource_path(name)
        assert path.is_absolute() and path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected


def test_frozen_resource_path_never_uses_cwd_or_external_video(tmp_path, monkeypatch):
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert resource_path("default_break.mp4") == tmp_path / "assets" / "default_break.mp4"


def test_missing_video_fallback_and_no_audio_output(qapp, tmp_path):
    backend = VideoBreak(source=tmp_path / "missing.mp4")
    errors = []
    backend.failed.connect(errors.append)
    backend.start()
    assert backend.fallback_active and errors
    assert backend.player.audioOutput() is None
    backend.close()


def test_sustained_black_frames_switch_to_fallback(qapp):
    backend = VideoBreak()
    backend.active = True
    image = QImage(16, 16, QImage.Format.Format_RGB32)
    image.fill(0)

    class Frame:
        def isValid(self):
            return True

        def toImage(self):
            return image

    for _ in range(90):
        backend._frame(Frame())
    assert backend.fallback_active
    backend.close()
