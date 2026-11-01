import pytest

from app.video_archive import (LIMIT_BYTES, WARNING_BYTES, SavedVideo, VideoArchive, looks_like_mp4)


def mp4(path, size=100):
    payload = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * max(0, size - 12)
    path.write_bytes(payload)
    return path


def test_looks_like_mp4_rejects_other_files(tmp_path):
    assert looks_like_mp4(mp4(tmp_path / "good.mp4"))
    assert not looks_like_mp4(tmp_path / "short.bin")  # missing file
    text = tmp_path / "text.mp4"
    text.write_bytes(b"not a video at all")
    assert not looks_like_mp4(text)


def test_save_confirmed_copies_with_unique_names(tmp_path):
    archive = VideoArchive(tmp_path / "videos")
    source = mp4(tmp_path / "clip.mp4", 2048)
    first = archive.save_confirmed(source, "early_surrender")
    second = archive.save_confirmed(source, "break_surrender")
    assert first.status == second.status == "saved"
    assert first.path != second.path
    assert first.path.endswith(".mp4")
    assert "early_surrender" in first.path
    assert source.exists(), "the archive copies, it never moves the user's clip"
    with open(first.path, "rb") as saved, open(source, "rb") as original:
        assert saved.read() == original.read()


def test_rejects_missing_empty_and_non_mp4_sources(tmp_path):
    archive = VideoArchive(tmp_path / "videos")
    assert archive.save_confirmed(tmp_path / "missing.mp4", "early").status == "save_failed"
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    assert archive.save_confirmed(empty, "early").status == "save_failed"
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"x" * 100)
    assert archive.save_confirmed(fake, "early").status == "save_failed"
    assert not (tmp_path / "videos").exists() or not list((tmp_path / "videos").iterdir())


def test_quota_is_enforced_before_copying(tmp_path):
    archive = VideoArchive(tmp_path / "videos", limit=1000)
    source = mp4(tmp_path / "clip.mp4", 900)
    assert archive.save_confirmed(source, "early").status == "saved"
    assert archive.save_confirmed(source, "early").status == "quota_exceeded"
    assert archive.used_bytes() == 900


def test_usage_reports_warning_threshold(tmp_path):
    archive = VideoArchive(tmp_path / "videos", limit=WARNING_BYTES + 100)
    directory = tmp_path / "videos"
    directory.mkdir()
    old = mp4(directory / "old.mp4", 10)
    used, free, warning = archive.usage()
    assert used == old.stat().st_size
    assert free == WARNING_BYTES + 100 - used
    assert warning is False
    big = directory / "big.mp4"
    with big.open("wb") as stream:
        stream.truncate(WARNING_BYTES)
    assert archive.usage()[2] is True


def test_used_bytes_ignores_symlinks_and_missing_directories(tmp_path):
    directory = tmp_path / "videos"
    assert VideoArchive(directory).used_bytes() == 0
    directory.mkdir()
    (directory / "a.mp4").write_bytes(b"x" * 40)
    assert VideoArchive(directory).used_bytes() == 40


def test_network_paths_are_rejected():
    for value in ("//server/videos", "\\\\server\\videos", "https://example.com/videos"):
        with pytest.raises(ValueError):
            VideoArchive(value)


def test_check_writable_creates_the_folder_and_leaves_no_probe(tmp_path):
    directory = tmp_path / "videos" / "nested"
    VideoArchive(directory).check_writable()
    assert directory.is_dir()
    assert list(directory.iterdir()) == []


def test_default_limits():
    assert LIMIT_BYTES == 512 * 1024 * 1024
    assert WARNING_BYTES == 400 * 1024 * 1024
    assert SavedVideo("saved", "x").path == "x"
