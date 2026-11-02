"""Non-running preferences only. Never restore a timer, camera or overlay."""
import errno
import json
import logging
import os
import time
from pathlib import Path


class ConfigWriteError(OSError):
    """写入本地配置失败，带一条用户能看懂的中文说明和失败阶段。"""

    def __init__(self, path, cause, stages=None):
        self.path = Path(path)
        self.cause = cause
        self.stages = dict(stages or {})
        self.errno_value = getattr(cause, "errno", None)
        self.winerror = getattr(cause, "winerror", None)
        self.failed_stage = next((name for name, value in self.stages.items()
                                  if isinstance(value, str) and value != "ok"), "")
        super().__init__(getattr(cause, "errno", None), getattr(cause, "strerror", str(cause)))

    def __str__(self):
        text = "无法写入配置文件 %s：%s" % (self.path, describe_os_error(self.cause, self.path))
        if self.failed_stage:
            text += "（失败阶段：%s）" % self.failed_stage
        return text


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
    # A committed location file is authoritative; legacy registry and pointer
    # entries are only consulted until the first successful new-style change.
    for key in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(key)
        if base:
            pointer = Path(base) / "NailongQuanxue" / "location.txt"
            try:
                text = pointer.read_text(encoding="utf-8").strip()
                if text:
                    return Path(text)
            except OSError:
                pass
            break
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
    """Atomically commit one authoritative pointer; leave legacy stores untouched."""
    import tempfile

    for key in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(key)
        if base:
            pointer = Path(base) / "NailongQuanxue" / "location.txt"
            break
    else:
        raise OSError("无法确定数据目录指针的位置")
    pointer.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=pointer.parent,
                                         prefix=".location-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(str(folder))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, pointer)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return True


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
    """Copy a consistent data snapshot without overwriting existing files."""
    import shutil
    import sqlite3
    from contextlib import closing

    source, target = Path(source).resolve(), Path(target).resolve()
    copied = []

    def relative_internal(value):
        if not isinstance(value, str) or not value:
            return None
        path = Path(value)
        if not path.is_absolute():
            return None
        try:
            return path.resolve().relative_to(source)
        except ValueError:
            return None

    def copy_path(relative):
        origin, destination = source / relative, target / relative
        if not origin.exists():
            return
        if destination.exists():
            raise FileExistsError("目标位置已有数据，未覆盖：%s" % destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if origin.is_dir():
            shutil.copytree(origin, destination)
        else:
            with origin.open("rb") as src, destination.open("xb") as dst:
                shutil.copyfileobj(src, dst)
            shutil.copystat(origin, destination)
        copied.append(str(relative))

    try:
        if source == target or source in target.parents or target in source.parents:
            raise ValueError("新旧数据目录不能相同或互相包含")
        target.mkdir(parents=True, exist_ok=True)
        settings_path = source / "settings.json"
        settings = None
        media_dirs = {Path("photos"), Path("videos")}
        if settings_path.is_file():
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            for key in ("photo_directory", "video_directory"):
                relative = relative_internal(settings.get(key))
                if relative is not None:
                    if relative == Path('.'):
                        raise ValueError("媒体目录不能是数据目录本身")
                    media_dirs.add(relative)
                    settings[key] = str(target / relative)
        for name in ("settings.json", "pending-events.json", "records.sqlite3",
                     "records.sqlite3-wal", "records.sqlite3-shm"):
            if (target / name).exists():
                raise FileExistsError("目标位置已有数据，未覆盖：%s" % (target / name))
        # Copy parent directories first, then skip paths already included in them.
        roots = []
        copied_media = set()
        for relative in sorted(media_dirs, key=lambda path: len(path.parts)):
            if not any(parent == relative or parent in relative.parents for parent in roots):
                copy_path(relative)
                roots.append(relative)
        if settings is not None:
            with (target / "settings.json").open("x", encoding="utf-8") as handle:
                json.dump(settings, handle, ensure_ascii=False, indent=2)
            copied.append("settings.json")
        copy_path(Path("pending-events.json"))
        database = source / "records.sqlite3"
        if database.is_file():
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as src:
                with closing(sqlite3.connect(target / "records.sqlite3")) as dst:
                    src.backup(dst)
                    columns = {row[1] for row in dst.execute("PRAGMA table_info(events)")}
                    with dst:
                        for column in ("photo_path", "video_path"):
                            if column not in columns:
                                continue
                            rows = dst.execute(
                                f"SELECT rowid, {column} FROM events WHERE {column} IS NOT NULL"
                            ).fetchall()
                            for rowid, value in rows:
                                relative = relative_internal(value)
                                if relative is None:
                                    continue
                                if (relative not in copied_media and
                                        not any(root == relative or root in relative.parents for root in roots)):
                                    copy_path(relative)
                                    copied_media.add(relative)
                                dst.execute(f"UPDATE events SET {column}=? WHERE rowid=?",
                                            (str(target / relative), rowid))
            copied.append("records.sqlite3")
    except (OSError, ValueError, TypeError, sqlite3.Error, shutil.Error) as error:
        return copied, [str(error)]
    return copied, []


def staged_write(target, payload):
    """按阶段写文件，返回 (stages, error)。

    阶段：ensure_dir → create → write → flush → close → replace。
    出错时 stages 里保留每个阶段的结果，便于定位到底是哪一步被拒绝。
    """
    target = Path(target)
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    stages = {}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        stages["ensure_dir"] = _stage_error(error)
        return stages, error
    stages["ensure_dir"] = "ok"

    handle = None
    try:
        handle = open(target, "wb")
        stages["create"] = "ok"
    except OSError as error:
        stages["create"] = _stage_error(error)
        return stages, error
    try:
        handle.write(data)
        stages["write"] = "ok"
        handle.flush()
        stages["flush"] = "ok"
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
    except OSError as error:
        stages.setdefault("write", _stage_error(error))
        try:
            handle.close()
        except OSError:
            pass
        try:
            target.unlink()
        except OSError:
            pass
        return stages, error
    finally:
        try:
            if handle is not None and not handle.closed:
                handle.close()
        except OSError:
            pass
    stages["close"] = "ok"
    return stages, None


def _stage_error(error):
    return "%s errno=%s winerror=%s" % (type(error).__name__, getattr(error, "errno", None),
                                        getattr(error, "winerror", None))


def executable_directory():
    """返回当前程序所在目录（打包后是 EXE 目录，源码运行时是项目目录）。"""
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def portable_directory():
    """程序所在目录下的便携数据目录（用户把程序放在受限目录时用得上）。"""
    return executable_directory() / "NailongData"


def probe_environment():
    """一次性探测几个关键位置是否可写，用于诊断与自动降级。"""
    data = data_directory()
    ok_data, reason_data = writable(data)
    exe_dir = executable_directory()
    ok_exe, reason_exe = writable(exe_dir)
    temp_dir = None
    for key in ("TEMP", "TMP"):
        value = os.environ.get(key)
        if value:
            temp_dir = Path(value)
            break
    ok_temp = False
    reason_temp = ""
    if temp_dir is not None:
        ok_temp, reason_temp = writable(temp_dir)
    return {
        "executable": sys_executable(),
        "frozen": bool(getattr(__import__("sys"), "frozen", False)),
        "data_directory": str(data),
        "data_writable": ok_data,
        "data_reason": reason_data,
        "exe_directory": str(exe_dir),
        "exe_writable": ok_exe,
        "exe_reason": reason_exe,
        "temp_directory": str(temp_dir) if temp_dir else "",
        "temp_writable": ok_temp,
        "temp_reason": reason_temp,
        "portable_directory": str(portable_directory()),
        "portable_writable": writable(portable_directory())[0],
    }


def sys_executable():
    import sys
    return sys.executable


def usable_data_directory():
    """选一个真正能写的数据目录。

    顺序：显式设置/记忆的目录 → 默认用户目录（可写才用）→ 程序目录下的 NailongData。
    程序目录若也只能读，则仍然返回默认目录，交给界面提示。
    """
    preferred = data_directory()
    try:
        if writable(preferred)[0]:
            return preferred
    except OSError:
        pass
    portable = portable_directory()
    try:
        if writable(portable)[0]:
            return portable
    except OSError:
        pass
    return preferred


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
            return Path(usable_data_directory())
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
        stages = {}
        for attempt in range(3):
            stages, error = staged_write(temporary, payload)
            if error is not None:
                last = error
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
                if attempt < 2:
                    time.sleep(0.12 * (attempt + 1))
                continue
            try:
                temporary.replace(self.path)
                stages["replace"] = "ok"
                last = None
                break
            except OSError as exc:
                last = exc
                stages["replace"] = _stage_error(exc)
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
                if attempt < 2:
                    time.sleep(0.12 * (attempt + 1))
        if last is not None:
            logging.getLogger("NailongQuanxue").error(
                "Config save failed at stage %s: %s (stages=%s)",
                next((name for name, value in stages.items()
                      if isinstance(value, str) and value != "ok"), "unknown"),
                self.path, stages, exc_info=last)
            # 不要留下半成品；也不要在写失败时清空用户原有配置。
            raise ConfigWriteError(self.path, last, stages) from last
        self.values = values
        self.error = None
