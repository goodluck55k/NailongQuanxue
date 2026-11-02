"""启动路径不能依赖系统临时目录：它可能缺失、被清理或被策略禁用。"""
import ast
from pathlib import Path

from app import config_store
from app.camera_recorder import clip_directory


def test_config_store_never_imports_tempfile():
    tree = ast.parse(Path(config_store.__file__).read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    imported |= {node.module for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom) and node.module}
    assert "tempfile" not in imported


def test_pointer_files_survive_missing_temp(monkeypatch):
    monkeypatch.setenv("TEMP", "Z:\\definitely-missing-temp")
    monkeypatch.setenv("TMP", "Z:\\definitely-missing-temp")
    pointers = config_store._pointer_files()
    assert pointers, "至少要包含应用数据目录里的指针"
    assert all("definitely-missing-temp" not in str(path) for path in pointers)


def test_remembered_directory_ignores_broken_sources(monkeypatch):
    def explode(*_args, **_kwargs):
        raise FileNotFoundError("[Errno 2] No usable temporary directory found")

    monkeypatch.setattr(config_store, "_registry_data_directory", lambda: None)
    monkeypatch.setattr(config_store, "_pointer_files", explode)
    assert config_store.remembered_data_directory() is None
    assert config_store.data_directory() == config_store.default_data_directory()


def test_config_store_falls_back_when_probe_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    def explode(*_args, **_kwargs):
        raise OSError("no temp")

    monkeypatch.setattr(config_store, "remembered_data_directory", explode)
    store = config_store.ConfigStore()
    assert store.root == tmp_path / "NailongQuanxue"
    assert store.values["minutes"] == 30


def test_legacy_temp_pointer_is_still_read(monkeypatch, tmp_path):
    fake_temp = tmp_path / "temp"
    fake_temp.mkdir()
    target = tmp_path / "moved-data"
    (fake_temp / "NailongQuanxue-location.txt").write_text(str(target), encoding="utf-8")
    monkeypatch.setenv("TEMP", str(fake_temp))
    monkeypatch.setenv("TMP", str(fake_temp))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "no-local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "no-roaming"))
    monkeypatch.setattr(config_store, "_registry_data_directory", lambda: None)
    assert config_store.remembered_data_directory() == target


def test_clip_directory_falls_back_to_data_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMP", str(tmp_path / "missing-temp"))
    monkeypatch.setenv("TMP", str(tmp_path / "missing-temp"))
    monkeypatch.setenv("NAILONG_DATA_DIR", str(tmp_path / "data"))
    folder = clip_directory()
    assert folder == tmp_path / "data" / "clips"
    assert folder.is_dir()
