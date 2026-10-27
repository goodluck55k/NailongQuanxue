"""Non-running preferences only. Never restore a timer, camera or overlay."""
import json
import os
from pathlib import Path


def data_directory():
    override = os.environ.get("NAILONG_DATA_DIR")
    return Path(override) if override else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "NailongQuanxue"


def duration_from_parts(minutes, seconds):
    for value in (minutes, seconds):
        if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit():
            raise ValueError("请输入有效的整数分钟与秒钟")
    minute, second = int(minutes), int(seconds)
    if not (0 <= minute <= 999 and 0 <= second <= 59) or minute * 60 + second == 0:
        raise ValueError("分钟需为 0–999，秒钟需为 0–59，总时长需大于零")
    return minute * 60 + second


class ConfigStore:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else data_directory()
        self.path = self.root / "settings.json"
        self.values = {"minutes": 30, "seconds": 0, "mode": "manual",
                       "photo_directory": str(self.root / "photos"), "schema_version": 2}
        self.error = None
        source = self.path
        legacy = self.root.parent / "ScreenBreak" / "settings.json"
        if not source.exists() and legacy.exists():
            source = legacy
        if source.exists():
            try:
                stored = json.loads(source.read_text(encoding="utf-8"))
                if not isinstance(stored, dict):
                    raise ValueError("Invalid configuration")
                merged = self.values | stored
                duration_from_parts(merged["minutes"], merged["seconds"])
                if merged["mode"] not in ("manual", "automatic"):
                    raise ValueError("Invalid mode")
                # Ignore old running-state fields; preserve unrelated preferences.
                for key in ("running", "deadline", "active_session", "camera_active"):
                    merged.pop(key, None)
                self.values = merged
            except (OSError, ValueError, KeyError, TypeError):
                self.error = "配置无法读取，已安全进入待机；原配置文件保留。"

    def save(self, **changes):
        values = self.values | changes | {"schema_version": 2}
        duration_from_parts(values["minutes"], values["seconds"])
        if values["mode"] not in ("manual", "automatic"):
            raise ValueError("Invalid mode")
        self.root.mkdir(parents=True, exist_ok=True)
        if self.error and self.path.exists():
            # Preserve corrupt input instead of silently overwriting it.
            backup = self.path.with_suffix(".json.backup")
            if not backup.exists():
                backup.write_bytes(self.path.read_bytes())
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        self.values = values
        self.error = None
