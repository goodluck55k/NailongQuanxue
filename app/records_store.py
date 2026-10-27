"""Versioned local archive. Deleting an archive never deletes unrelated files."""
import json
from pathlib import Path
import sqlite3

from .supervision import Event

FIELDS = {"event_id": "TEXT PRIMARY KEY", "occurred_at": "TEXT", "event_type": "TEXT",
          "mode": "TEXT", "round_index": "INTEGER", "configured_seconds": "REAL",
          "usage_seconds": "REAL", "break_seconds": "REAL", "declaration_confirmed": "INTEGER",
          "photo_status": "TEXT", "photo_path": "TEXT"}


class RecordsStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=0.1)
        self.connection.row_factory = sqlite3.Row
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version > 2:
            self.connection.close()
            raise sqlite3.DatabaseError("档案版本较新，请勿用旧版本覆盖")
        existing = self.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'").fetchone()
        if existing and version < 2:
            # Snapshot before an additive migration; never rewrite a shared DB.
            target = self.path.with_suffix(".pre-v11.sqlite3")
            if not target.exists():
                with sqlite3.connect(target) as backup:
                    self.connection.backup(backup)
        with self.connection:
            self.connection.execute("CREATE TABLE IF NOT EXISTS events (" + ",".join(
                f"{name} {kind}" for name, kind in FIELDS.items()) + ")")
            columns = {row[1] for row in self.connection.execute("PRAGMA table_info(events)")}
            for name, kind in FIELDS.items():
                if name not in columns:
                    self.connection.execute(f"ALTER TABLE events ADD COLUMN {name} {kind.replace(' PRIMARY KEY', '')}")
            self.connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS event_identifier ON events(event_id)")
            self.connection.execute("PRAGMA user_version=2")

    def append(self, event: Event):
        values = event.to_dict()
        with self.connection:
            self.connection.execute("INSERT OR IGNORE INTO events (" + ",".join(FIELDS) + ") VALUES ("
                                    + ",".join("?" for _ in FIELDS) + ")", [values[name] for name in FIELDS])

    def all(self):
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM events ORDER BY occurred_at DESC, rowid DESC")]

    def stats(self):
        counts = {row[0]: row[1] for row in self.connection.execute(
            "SELECT event_type,COUNT(*) FROM events GROUP BY event_type")}
        counts["SURRENDERS"] = counts.get("EARLY_SURRENDER", 0) + counts.get("BREAK_SURRENDER", 0)
        return counts

    def delete_photo(self, event_id):
        row = self.connection.execute("SELECT photo_path FROM events WHERE event_id=?", (event_id,)).fetchone()
        if not row:
            return
        if row[0]:
            path = Path(row[0])
            # Only paths explicitly stored by the application can be selected.
            if path.suffix.lower() != ".jpg" or path.is_symlink():
                raise ValueError("照片路径异常，未删除")
            path.unlink(missing_ok=True)
        with self.connection:
            self.connection.execute("UPDATE events SET photo_status='deleted',photo_path=NULL WHERE event_id=?", (event_id,))

    def delete_event(self, event_id):
        with self.connection:
            self.connection.execute("DELETE FROM events WHERE event_id=?", (event_id,))

    def mark_photos_deleted(self, paths):
        with self.connection:
            for path in paths:
                self.connection.execute("UPDATE events SET photo_status='deleted',photo_path=NULL WHERE photo_path=?", (str(path),))

    def clear(self):
        with self.connection:
            self.connection.execute("DELETE FROM events")

    def close(self):
        self.connection.close()
