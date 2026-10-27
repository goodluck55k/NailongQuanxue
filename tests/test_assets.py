import hashlib
from pathlib import Path

import pytest

from app.resources import asset_candidates, load_overlay

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_SHA = "0cdd2f63eb0f9e4dc1fe8b5b880dbb54c6a53edc137bfdd6f9704746e7fa3f11"


def test_source_resolution_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert asset_candidates() == [ROOT / "assets" / "overlay.jpg"]


def test_exe_external_then_bundled(tmp_path):
    exe = tmp_path / "public" / "ScreenBreak.exe"
    bundle = exe.parent / "_internal"
    assert asset_candidates(executable=exe, bundle_root=bundle) == [
        exe.parent / "assets" / "overlay.jpg", bundle / "assets" / "overlay.jpg"]


def test_missing_resource_safe_fallback(qapp, tmp_path):
    asset = load_overlay([tmp_path / "missing.jpg"])
    assert asset.pixmap.isNull()
    assert "白底" in asset.message


def test_invalid_image_safe_fallback(qapp, tmp_path):
    path = tmp_path / "overlay.jpg"
    path.write_bytes(b"invalid image")
    asset = load_overlay([path])
    assert asset.pixmap.isNull()
    assert "无法读取" in asset.message


def test_private_original_untouched_and_decodes(qapp):
    path = ROOT / "assets" / "overlay.jpg"
    if not path.exists():
        pytest.skip("Private local image is intentionally absent from public sources")
    if hashlib.sha256(path.read_bytes()).hexdigest() != PRIVATE_SHA:
        pytest.skip("User supplied a different local image")
    assert path.read_bytes()[:3] == b"\xff\xd8\xff"
    asset = load_overlay([path])
    assert (asset.pixmap.width(), asset.pixmap.height()) == (1102, 1536)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == PRIVATE_SHA
