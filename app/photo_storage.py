"""Only confirmed JPEG bytes are written. No intermediate images on disk."""
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import uuid

LIMIT_BYTES = 100 * 1024 * 1024
WARNING_BYTES = 90 * 1024 * 1024


def local_directory(path):
    text = os.fspath(path)
    if text.startswith(("\\\\", "//")) or "://" in text:
        raise ValueError("照片目录必须是本地文件夹，不能使用网络路径")
    result = Path(path).expanduser().absolute()
    if os.name == "nt":
        import ctypes
        drive = result.anchor
        api = ctypes.WinDLL("kernel32", use_last_error=True).GetDriveTypeW
        api.argtypes = [ctypes.c_wchar_p]
        if api(drive) == 4:
            raise ValueError("不支持网络映射盘")
    return result


@dataclass(frozen=True)
class SavedPhoto:
    status: str
    path: str | None = None


class PhotoStorage:
    def __init__(self, directory, limit=LIMIT_BYTES):
        self.directory = local_directory(directory)
        self.limit = limit

    def used_bytes(self):
        if not self.directory.exists():
            return 0
        total = 0
        for folder, dirs, files in os.walk(self.directory, followlinks=False):
            dirs[:] = [name for name in dirs if not (getattr((Path(folder) / name).stat(), "st_file_attributes", 0) & 0x400)
                       and not (Path(folder) / name).is_symlink()]
            for name in files:
                path = Path(folder) / name
                if not path.is_symlink():
                    total += path.stat().st_size
        return total

    def usage(self):
        used = self.used_bytes()
        return used, max(0, self.limit - used), used >= WARNING_BYTES

    def save_confirmed(self, jpeg_bytes, event_type):
        if not jpeg_bytes or not jpeg_bytes.startswith(b"\xff\xd8"):
            return SavedPhoto("save_failed")
        path = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            if self.used_bytes() + len(jpeg_bytes) > self.limit:
                return SavedPhoto("quota_exceeded")
            name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = self.directory / f"{name}_{event_type.lower()}_{uuid.uuid4().hex[:10]}.jpg"
            with path.open("xb") as stream:
                stream.write(jpeg_bytes)
            return SavedPhoto("saved", str(path))
        except OSError:
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            return SavedPhoto("save_failed")

    def check_writable(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        probe = self.directory / f".write-check-{uuid.uuid4().hex}.tmp"
        try:
            with probe.open("xb") as stream:
                stream.write(b"")
        finally:
            probe.unlink(missing_ok=True)
