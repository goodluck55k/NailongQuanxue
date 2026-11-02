import json
from pathlib import Path
import sqlite3

import pytest

from app import config_store
from app.config_store import (ConfigStore, ConfigWriteError, duration_from_parts,
                              relocate_data, writable)
from app.photo_storage import PhotoStorage, WARNING_BYTES, local_directory
from app.records_store import RecordsStore
from app.supervision import Event


@pytest.mark.parametrize("minutes,seconds,total", [(0, 15, 15), (1, 30, 90), (5, 30, 330), (999, 59, 59999)])
def test_duration_parts(minutes, seconds, total):
    assert duration_from_parts(minutes, seconds) == total


@pytest.mark.parametrize("minutes,seconds", [(0, 0), (-1, 0), (1000, 0), (1, 60), ("", "15"), ("a", 1), ("1.5", 0), (True, 0)])
def test_invalid_inputs(minutes, seconds):
    with pytest.raises(ValueError):
        duration_from_parts(minutes, seconds)


def test_preferences_restart_idle_and_preserve_unknown_keys(tmp_path):
    config = ConfigStore(tmp_path)
    assert config.values["minutes"] == 30 and config.values["mode"] == "manual"
    config.save(minutes=1, seconds=30, mode="automatic", legacy_extra="preserved")
    loaded = ConfigStore(tmp_path)
    assert loaded.values["seconds"] == 30
    assert loaded.values["legacy_extra"] == "preserved"
    assert "deadline" not in loaded.values


def test_corrupt_config_preserved(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not-json")
    config = ConfigStore(tmp_path)
    assert config.error
    config.save(minutes=10)
    assert path.with_suffix(".json.backup").read_text() == "not-json"


def test_local_paths_only():
    for value in ("//server/photos", "\\\\server\\photos", "https://example.com/photos"):
        with pytest.raises(ValueError):
            local_directory(value)


def test_quota_includes_new_encoded_bytes_and_never_deletes(tmp_path):
    storage = PhotoStorage(tmp_path, limit=100)
    old = tmp_path / "old.jpg"
    old.write_bytes(b"x" * 90)
    assert storage.save_confirmed(b"\xff\xd8" + b"x" * 20, "EARLY_SURRENDER").status == "quota_exceeded"
    assert list(tmp_path.iterdir()) == [old]
    assert old.stat().st_size == 90


def test_warning_exact_boundary(tmp_path):
    storage = PhotoStorage(tmp_path)
    path = tmp_path / "old.jpg"
    with path.open("wb") as stream:
        stream.truncate(WARNING_BYTES - 1)
    assert not storage.usage()[2]
    with path.open("ab") as stream:
        stream.write(b"x")
    assert storage.usage()[2]


def test_unique_confirmed_jpg_no_intermediates(tmp_path):
    storage = PhotoStorage(tmp_path)
    first = storage.save_confirmed(b"\xff\xd8hello", "EARLY_SURRENDER")
    second = storage.save_confirmed(b"\xff\xd8hello", "EARLY_SURRENDER")
    assert first.status == second.status == "saved"
    assert first.path != second.path
    assert len(list(tmp_path.iterdir())) == 2


def test_directory_unwritable_or_gone_returns_save_failed(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_bytes(b"file")
    storage = PhotoStorage(blocked)
    assert storage.save_confirmed(b"\xff\xd8photo", "BREAK_SURRENDER").status == "save_failed"


def make_event(kind, identifier):
    return Event(identifier, "2026-10-27T16:00:00+08:00", kind, "automatic", 2, 90, 70, 20)


def test_event_idempotency_classification_and_photo_deletion(tmp_path):
    store = RecordsStore(tmp_path / "records.sqlite3")
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"local")
    for index, kind in enumerate(("EARLY_SURRENDER", "BREAK_SURRENDER", "BREAK_COMPLETED", "EMERGENCY_EXIT")):
        event = make_event(kind, str(index))
        if index == 0:
            event.photo_status, event.photo_path = "saved", str(photo)
        store.append(event)
        store.append(event)
    assert len(store.all()) == 4
    assert store.stats()["SURRENDERS"] == 2
    store.delete_photo("0")
    assert not photo.exists()
    assert len(store.all()) == 4
    assert next(row for row in store.all() if row["event_id"] == "0")["photo_status"] == "deleted"
    store.clear()
    assert not store.all()
    store.close()


def test_legacy_database_additive_migration_backup(tmp_path):
    path = tmp_path / "records.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE events(event_id TEXT PRIMARY KEY,event_type TEXT)")
        connection.execute("INSERT INTO events VALUES ('old','EARLY_SURRENDER')")
    store = RecordsStore(path)
    assert store.all()[0]["event_id"] == "old"
    assert path.with_suffix(".pre-v11.sqlite3").exists()
    store.close()


def test_change_photo_directory_preserves_old_data(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    photo = old / "existing.jpg"
    photo.write_bytes(b"existing")
    config = ConfigStore(tmp_path / "data")
    config.save(photo_directory=str(new))
    assert photo.read_bytes() == b"existing"
    assert not new.exists()


def test_settings_delete_marks_archives_but_clear_does_not_delete_photos(tmp_path):
    store = RecordsStore(tmp_path / "records.sqlite3")
    photo = tmp_path / "remaining.jpg"
    photo.write_bytes(b"photo")
    event = make_event("EARLY_SURRENDER", "test")
    event.photo_path, event.photo_status = str(photo), "saved"
    store.append(event)
    store.mark_photos_deleted([photo])
    assert store.all()[0]["photo_status"] == "deleted"
    store.clear()
    assert photo.exists()
    store.close()


def test_video_columns_and_deletion_round_trip(tmp_path):
    store = RecordsStore(tmp_path / "records.sqlite3")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    event = make_event("EARLY_SURRENDER", "video")
    event.video_status, event.video_path = "saved", str(clip)
    event.ai_cycles, event.ai_reason = 2, "两组前倾回正"
    store.append(event)
    row = store.all()[0]
    assert row["video_status"] == "saved" and row["video_path"] == str(clip)
    assert row["ai_cycles"] == 2 and row["ai_reason"] == "两组前倾回正"
    store.delete_video("video")
    assert not clip.exists()
    assert store.all()[0]["video_status"] == "deleted"
    assert store.all()[0]["video_path"] is None
    store.close()


def test_delete_video_refuses_other_suffixes_and_missing_files(tmp_path):
    store = RecordsStore(tmp_path / "records.sqlite3")
    other = tmp_path / "clip.avi"
    other.write_bytes(b"x")
    event = make_event("EARLY_SURRENDER", "wrong")
    event.video_status, event.video_path = "saved", str(other)
    store.append(event)
    with pytest.raises(ValueError):
        store.delete_video("wrong")
    assert other.exists()
    store.delete_video("does-not-exist")
    store.close()


def test_v2_archive_is_backed_up_before_v3_migration(tmp_path):
    path = tmp_path / "records.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE events(event_id TEXT PRIMARY KEY,occurred_at TEXT,event_type TEXT,"
            "mode TEXT,round_index INTEGER,configured_seconds INTEGER,usage_seconds INTEGER,"
            "break_seconds INTEGER,declaration_confirmed INTEGER,photo_status TEXT,photo_path TEXT)")
        connection.execute(
            "INSERT INTO events VALUES ('v2','2026-10-27T16:00:00+08:00','EARLY_SURRENDER',"
            "'automatic',2,90,70,20,1,'saved',NULL)")
        connection.execute("PRAGMA user_version = 2")
    store = RecordsStore(path)
    row = store.all()[0]
    assert row["event_id"] == "v2"
    assert row["video_status"] == "not_applicable"
    assert row["video_path"] is None
    assert row["ai_cycles"] is None
    assert path.with_suffix(".pre-v3.sqlite3").exists()
    store.close()


def test_video_directory_defaults_inside_data_directory(tmp_path):
    config = ConfigStore(tmp_path)
    assert config.values["video_directory"] == str(tmp_path / "videos")
    assert config.values["schema_version"] == 3


def test_unwritable_config_reports_reason_not_errno(tmp_path, monkeypatch):
    store = ConfigStore(tmp_path)

    def refuse(self, *_args, **_kwargs):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "write_text", refuse)
    with pytest.raises(ConfigWriteError) as caught:
        store.save(minutes=10)
    message = str(caught.value)
    assert "拒绝访问" in message
    assert "13" not in message
    assert str(tmp_path / "settings.json") in message


def test_writable_probe_detects_denied_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "write_text", lambda self, *a, **k: (_ for _ in ()).throw(
        PermissionError(13, "Permission denied", str(self))))
    ok, reason = writable(tmp_path)
    assert ok is False and "拒绝访问" in reason


def test_data_directory_pointer_roundtrip(tmp_path, monkeypatch):
    pointer = tmp_path / "location.txt"
    monkeypatch.setattr(config_store, "_pointer_files", lambda: [pointer])
    monkeypatch.setattr(config_store, "_registry_data_directory", lambda: None)
    monkeypatch.setattr(config_store, "_store_registry_data_directory", lambda folder: False)
    monkeypatch.setattr(config_store, "_clear_registry_data_directory", lambda: False)
    target = tmp_path / "custom"
    assert config_store.remember_data_directory(target) is True
    assert pointer.read_text(encoding="utf-8") == str(target)
    assert config_store.remembered_data_directory() == target
    assert config_store.forget_data_directory() is True
    assert config_store.remembered_data_directory() is None


def test_relocate_data_copies_without_deleting(tmp_path):
    source = tmp_path / "old"
    target = tmp_path / "new"
    (source / "photos").mkdir(parents=True)
    (source / "settings.json").write_text('{"minutes": 30}', encoding="utf-8")
    (source / "records.sqlite3").write_bytes(b"sqlite")
    (source / "photos" / "a.jpg").write_bytes(b"\xff\xd8\xff")
    copied, errors = relocate_data(source, target)
    assert errors == []
    assert set(copied) == {"settings.json", "records.sqlite3", "photos/"}
    assert (target / "photos" / "a.jpg").is_file()
    assert (source / "settings.json").is_file()