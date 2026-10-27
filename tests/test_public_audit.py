import io
import zipfile

import pytest

from tools.scan_public import AuditError, Auditor


@pytest.mark.parametrize("name", ["assets/overlay.jpg", "_internal/assets/overlay.png", ".env", "ScreenBreakLocal.exe", "../image.jpg"])
def test_reject_private_names(name):
    with pytest.raises(AuditError):
        Auditor().check_entry(name, b"data")


def test_detect_renamed_private_image(tmp_path):
    private = tmp_path / "private.jpg"
    private.write_bytes(b"synthetic-private-image-bytes")
    with pytest.raises(AuditError):
        Auditor(private).check_entry("unrelated.bin", b"prefix" + private.read_bytes())


def test_inspect_nested_zip():
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("assets/overlay.jpg", b"private")
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("nested.zip", inner.getvalue())
    with pytest.raises(AuditError):
        Auditor().check_entry("public.zip", outer.getvalue())


def test_uninspectable_exe_fails_closed():
    with pytest.raises(AuditError, match="Cannot inspect executable"):
        Auditor().check_entry("ScreenBreak.exe", b"MZ-not-an-archive")


def test_compressed_renamed_image_inside_exe_rejected(tmp_path):
    from PyInstaller.archive.writers import CArchiveWriter

    image = tmp_path / "image.bin"
    image.write_bytes(b"private-fixture" * 100)
    executable = tmp_path / "ScreenBreak.exe"
    CArchiveWriter(str(executable), [("innocent.bin", str(image), True, "x")], "python311.dll")
    with pytest.raises(AuditError, match="Private image bytes"):
        Auditor(image).scan(executable)


def test_public_text_and_local_resource_reference_allowed():
    auditor = Auditor()
    auditor.check_entry("resources.py", b"path = 'assets/overlay.jpg'")
    assert auditor.report()["result"] == "PASS"


def test_private_absolute_path_rejected():
    path = "C:" + chr(92) + "Users" + chr(92) + "example" + chr(92) + "private"
    with pytest.raises(AuditError):
        Auditor().check_entry("leak.md", path.encode())


def test_manifest_prevents_path_escape(tmp_path):
    manifest = tmp_path / "PUBLIC_FILES.txt"
    manifest.write_text("../outside.txt\n", encoding="utf-8")
    with pytest.raises(AuditError):
        Auditor().source_manifest(tmp_path, manifest)


def test_v11_local_candidate_allows_only_declared_unchanged_assets():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    auditor = Auditor(allow_fixed_assets=True)
    for name in ("default_break.mp4", "fallback_overlay.jpg", "ui_reference.png"):
        auditor.check_entry("assets/" + name, (root / "assets" / name).read_bytes())
    with pytest.raises(AuditError):
        auditor.check_entry("assets/fallback_overlay.jpg", b"changed")
    assert auditor.report()["publication_authorized"] is False


@pytest.mark.parametrize("name", ["photos/user.jpg", "records.sqlite3", "settings.json", "pending-events.json"])
def test_personal_data_rejected(name):
    with pytest.raises(AuditError):
        Auditor(allow_fixed_assets=True).check_entry(name, b"private")


@pytest.mark.parametrize("name", ["assets/user.jpg", "misc/picture.png", "random.mp4"])
def test_v11_rejects_unlisted_media_anywhere(name):
    with pytest.raises(AuditError):
        Auditor(allow_fixed_assets=True).check_entry(name, b"private media")
