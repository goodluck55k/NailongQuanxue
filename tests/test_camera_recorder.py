import os
import time
from pathlib import Path

from app import camera_recorder


def use_temp_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(camera_recorder.tempfile, "gettempdir", lambda: str(tmp_path))
    return camera_recorder.clip_directory()


def test_stale_clips_are_removed_and_fresh_ones_kept(monkeypatch, tmp_path):
    folder = use_temp_dir(monkeypatch, tmp_path)
    old = folder / "clip-aaaaaaaa.mp4"
    fresh = folder / "clip-bbbbbbbb.mp4"
    foreign = folder / "notes.txt"
    for path in (old, fresh, foreign):
        path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    past = time.time() - camera_recorder.STALE_CLIP_SECONDS - 60
    os.utime(old, (past, past))
    os.utime(foreign, (past, past))

    removed = camera_recorder.cleanup_stale_clips()

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()
    assert foreign.exists()  # only this app's own clip naming is touched


def test_cleanup_on_a_missing_directory_is_harmless(monkeypatch, tmp_path):
    folder = tmp_path / "gone"
    monkeypatch.setattr(camera_recorder, "clip_directory", lambda: folder)
    assert camera_recorder.cleanup_stale_clips() == 0


def test_clip_directory_lives_under_the_app_temp_folder(monkeypatch, tmp_path):
    folder = use_temp_dir(monkeypatch, tmp_path)
    assert folder == Path(tmp_path) / "NailongQuanxue" / "clips"
    assert folder.is_dir()


def test_discard_retries_while_the_encoder_still_holds_the_file(monkeypatch, tmp_path):
    folder = use_temp_dir(monkeypatch, tmp_path)
    clip = folder / "clip-locked01.mp4"
    clip.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    handle = clip.open("rb")
    try:
        assert camera_recorder._discard(clip) is False
        assert clip.exists()
        assert str(clip) in camera_recorder._PENDING_DELETES
    finally:
        handle.close()

    camera_recorder._retry_pending_deletes()

    assert not clip.exists()
    assert str(clip) not in camera_recorder._PENDING_DELETES


def test_discard_deletes_a_free_file_immediately(monkeypatch, tmp_path):
    folder = use_temp_dir(monkeypatch, tmp_path)
    clip = folder / "clip-free0001.mp4"
    clip.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    assert camera_recorder._discard(clip) is True
    assert not clip.exists()
    assert (str(clip)) not in camera_recorder._PENDING_DELETES
