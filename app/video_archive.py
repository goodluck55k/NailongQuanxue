"""Confirmed MP4 clips only. Quota is enforced; nothing is deleted automatically."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import os
import uuid

from .photo_storage import local_directory

LIMIT_BYTES = 512 * 1024 * 1024
WARNING_BYTES = 400 * 1024 * 1024
CHUNK = 1024 * 1024


def looks_like_mp4(path):
    """Minimal structural check: ISO-BMFF 'ftyp' box near the start."""
    try:
        with Path(path).open("rb") as stream:
            header = stream.read(12)
    except OSError:
        return False
    return len(header) >= 12 and header[4:8] == b"ftyp"


@dataclass(frozen=True)
class SavedVideo:
    status: str
    path: str | None = None


class VideoArchive:
    def __init__(self, directory, limit=LIMIT_BYTES):
        self.directory = local_directory(directory)
        self.limit = limit

    def used_bytes(self):
        if not self.directory.exists():
            return 0
        total = 0
        for folder, dirs, files in os.walk(self.directory, followlinks=False):
            dirs[:] = [name for name in dirs
                       if not (getattr((Path(folder) / name).stat(), "st_file_attributes", 0) & 0x400)
                       and not (Path(folder) / name).is_symlink()]
            for name in files:
                path = Path(folder) / name
                if not path.is_symlink():
                    total += path.stat().st_size
        return total

    def usage(self):
        used = self.used_bytes()
        return used, max(0, self.limit - used), used >= WARNING_BYTES

    def save_confirmed(self, source, event_type):
        """Move the finished clip in, or fail without touching the archive."""
        source = Path(source)
        if not looks_like_mp4(source):
            return SavedVideo("save_failed")
        try:
            size = source.stat().st_size
        except OSError:
            return SavedVideo("save_failed")
        if size <= 0:
            return SavedVideo("save_failed")
        path = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            if self.used_bytes() + size > self.limit:
                return SavedVideo("quota_exceeded")
            name = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_{event_type.lower()}_{uuid.uuid4().hex[:10]}.mp4"
            path = self.directory / name
            with source.open("rb") as reader, path.open("xb") as writer:
                while True:
                    block = reader.read(CHUNK)
                    if not block:
                        break
                    writer.write(block)
            return SavedVideo("saved", str(path))
        except OSError:
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            return SavedVideo("save_failed")

    def check_writable(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        probe = self.directory / f".write-check-{uuid.uuid4().hex}.tmp"
        try:
            with probe.open("xb") as stream:
                stream.write(b"")
        finally:
            probe.unlink(missing_ok=True)
