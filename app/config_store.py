"""Non-running preferences only. Never restore a timer, camera or overlay."""
import errno
import json
import logging
import os
import time
from pathlib import Path


class ConfigWriteError(OSError):
    """写入本地配置失败，带一条用户能看懂的中文说明。"""

    def __init__(self, path, cause):
        self.path = Path(path)
        self.cause = cause
        self.errno_value = getattr(cause, "errno", None)
        super().__init__(getattr(cause, "errno", None), getattr(cause, "strerror", str(cause)))

    def __str__(self):
        return ("无法写入配置文件 %s：%s"
                % (self.path, describe_os_error(self.cause, self.path)))


def describe_os_error(error, path=None):
    """把 OSError 翻成一句能指导操作的中文，绝不只显示错误码。"""
    code = getattr(error, "errno", None)
    where = ("（%s）" % path) if path else ""
    if code in (errno.EACCES, errno.EPERM):
        return ("Windows 拒绝访问%s。常见原因：安全软件（如腾讯电脑管家、迈克菲的"
                "文件夹保护/勒索防护）拦截了本程序，或该文件夹的权限不允许当前用户写入。"
                "请把本程序加入安全软件的信任列表后重试。" % where)
    if code == errno.ENOSPC:
        return "磁盘空间不足%s，请清理后重试。" % where
    if code == errno.EROFS:
        return "目标位置是只读的%s，请换一个可写目录。" % where
    if code in (errno.ENOENT, errno.ENOTDIR):
        return "路径不存在或不可用%s。" % where
    if code == errno.EBUSY:
        return "文件正被其他程序占用%s，请关闭后重试。" % where
    message = getattr(error, "strerror", None) or str(error) or type(error).__name__
    return "%s%s" % (message, where)


def writable(folder):
    """检查目录能否真正写入（读权限正常不代表能写）。"""
    folder = Path(folder)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return False, describe_os_error(error, folder)
    probe = folder / ".write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True, ""
    except OSError as error:
        try:
            probe.unlink()
        except OSError:
            pass
        return False, describe_os_error(error, folder)


_REGISTRY_PATH = r"Software\NailongQuanxue"


def default_data_directory():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "NailongQuanxue"


def _pointer_files():
    """记住“数据目录改到哪”的指针文件。

    只用当前用户的应用数据目录这类持久位置：旧版曾把指针写进临时目录，
    而临时目录可能被清理、被策略禁用，甚至 ``tempfile.gettempdir()`` 本身
    就会抛 FileNotFoundError；这里只在旧指针确实存在时才把它当成只读兼容项。
    """
    files = []
    for key in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(key)
        if base:
            files.append(Path(base) / "NailongQuanxue" / "location.txt")
    legacy = _legacy_temp_pointer()
    if legacy is not None:
        files.append(legacy)
    return files


def _legacy_temp_pointer():
    """旧版放在 %TEMP% 的指针文件；环境变量缺失或目录不可用就跳过。"""
    for key in ("TEMP", "TMP"):
        base = os.environ.get(key)
        if not base:
            continue
        try:
            folder = Path(base)
            if folder.is_dir():
                return folder / "NailongQuanxue-location.txt"
        except OSError:
            continue
    return None


def _registry_data_directory():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_PATH) as key:
            value, _kind = winreg.QueryValueEx(key, "DataDirectory")
    except (ImportError, OSError):
        return None
    return Path(value) if isinstance(value, str) and value else None


def _store_registry_data_directory(folder):
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REGISTRY_PATH) as key:
            winreg.SetValueEx(key, "DataDirectory", 0, winreg.REG_SZ, str(folder))
        return True
    except (ImportError, OSError):
        return False


def _clear_registry_data_directory():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, "DataDirectory")
        return True
    except (ImportError, OSError):
        return False


def remembered_data_directory():
    """读取用户改过的数据目录：先看 HKCU，再看几个固定位置的指针文件。"""
    try:
        registered = _registry_data_directory()
    except Exception:
        registered = None
    if registered is not None:
        return registered
    try:
        pointers = _pointer_files()
    except Exception:
        return None
    for pointer in pointers:
        try:
            text = pointer.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not text:
            continue
        try:
            candidate = Path(text)
        except (OSError, ValueError):
            continue
        if str(candidate).strip():
            return candidate
    return None


def remember_data_directory(folder):
    """把新数据目录写到注册表和指针文件（能写哪个写哪个）。"""
    folder = Path(folder)
    written = _store_registry_data_directory(folder)
    for pointer in _pointer_files():
        try:
            pointer.parent.mkdir(parents=True, exist_ok=True)
            pointer.write_text(str(folder), encoding="utf-8")
            written = True
        except OSError:
            continue
    return written


def forget_data_directory():
    removed = _clear_registry_data_directory()
    for pointer in _pointer_files():
        try:
            pointer.unlink()
            removed = True
        except OSError:
            continue
    return removed


def relocate_data(source, target):
    """把已有设置、档案、照片和录像复制到新目录；只复制，不删除原文件。"""
    import shutil

    source, target = Path(source), Path(target)
    copied, errors = [], []
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return copied, [describe_os_error(error, target)]
    for name in ("settings.json", "pending-events.json"):
        origin = source / name
        if origin.is_file():
            try:
                shutil.copy2(origin, target / name)
                copied.append(name)
            except OSError as error:
                errors.append(describe_os_error(error, origin))
    for pattern in ("records.sqlite3", "records.sqlite3-wal", "records.sqlite3-shm"):
        origin = source / pattern
        if origin.is_file():
            try:
                shutil.copy2(origin, target / pattern)
                copied.append(pattern)
            except OSError as error:
                errors.append(describe_os_error(error, origin))
    for folder in ("photos", "videos"):
        origin = source / folder
        if origin.is_dir():
            try:
                shutil.copytree(origin, target / folder, dirs_exist_ok=True)
                copied.append(folder + "/")
            except OSError as error:
                errors.append(describe_os_error(error, origin))
    return copied, errors


def data_directory():
    """解析数据目录。任何一步失败都不能让程序启动崩溃。"""
    override = os.environ.get("NAILONG_DATA_DIR")
    if override:
        try:
            return Path(override)
        except (OSError, ValueError):
            pass
    try:
        remembered = remembered_data_directory()
    except Exception:  # 指针文件、注册表都可能因为策略或权限不可用
        remembered = None
    if remembered is not None:
        return remembered
    try:
        return default_data_directory()
    except (OSError, ValueError):
        return Path(os.environ.get("USERPROFILE") or os.path.expanduser("~")) / "NailongQuanxue"


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
        self.root = self._resolve_root(root)
        self.path = self.root / "settings.json"
        self.values = {"minutes": 30, "seconds": 0, "mode": "manual",
                       "photo_directory": str(self.root / "photos"),
                       "video_directory": str(self.root / "videos"), "schema_version": 3}
        self.error = None
        try:
            self._load()
        except (OSError, ValueError, KeyError, TypeError):
            self.error = "配置无法读取，已安全进入待机；原配置文件保留。"

    @staticmethod
    def _resolve_root(root):
        """解析根目录时任何失败都要能退回默认值，不能让启动崩掉。"""
        if root is not None:
            try:
                return Path(root)
            except (OSError, ValueError):
                pass
        try:
            return Path(data_directory())
        except Exception:
            pass
        try:
            return default_data_directory()
        except (OSError, ValueError):
            return Path(os.path.expanduser("~")) / "NailongQuanxue"

    def _load(self):
        source = self.path
        try:
            legacy = self.root.parent / "ScreenBreak" / "settings.json"
            has_legacy = legacy.exists()
        except OSError:
            has_legacy = False
        try:
            has_source = source.exists()
        except OSError:
            has_source = False
        if not has_source and has_legacy:
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
        values = self.values | changes | {"schema_version": 3}
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
        payload = json.dumps(values, ensure_ascii=False, indent=2)
        last = None
        for attempt in range(3):
            try:
                temporary.write_text(payload, encoding="utf-8")
                temporary.replace(self.path)
                last = None
                break
            except OSError as error:
                # 安全软件扫描、另一个进程短暂占用都会造成瞬时 EACCES，重试即可。
                last = error
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
                if attempt < 2:
                    time.sleep(0.12 * (attempt + 1))
        if last is not None:
            logging.getLogger("NailongQuanxue").error(
                "Config save failed: %s", self.path, exc_info=last)
            # 不要留下半成品；也不要在写失败时清空用户原有配置。
            raise ConfigWriteError(self.path, last) from last
        self.values = values
        self.error = None
