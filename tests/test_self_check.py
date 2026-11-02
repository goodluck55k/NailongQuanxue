"""`--self-check` 必须能写到指定路径，且写不进去时给中文原因而不是 Traceback。"""
from pathlib import Path

import main as entry


def test_self_check_defaults_to_data_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("NAILONG_DATA_DIR", str(tmp_path))
    assert entry.write_self_check() == 0
    target = tmp_path / "diagnostics" / "self-check.json"
    assert target.is_file()
    text = target.read_text(encoding="utf-8")
    assert entry.APP_VERSION in text
    assert '"camera"' in text


def test_self_check_honours_explicit_path(tmp_path):
    target = tmp_path / "custom.json"
    assert entry.write_self_check(str(target)) == 0
    assert target.is_file()


def test_self_check_rejects_directory(tmp_path, capsys):
    assert entry.write_self_check(str(tmp_path)) == 2
    assert "是一个目录" in capsys.readouterr().err


def test_self_check_denied_path_has_no_traceback(tmp_path, monkeypatch, capsys):
    def refuse(self, *_args, **_kwargs):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(Path, "write_text", refuse)
    assert entry.write_self_check(str(tmp_path / "denied.json")) == 2
    error = capsys.readouterr().err
    assert "无法写入" in error
    assert "拒绝访问" in error
    assert "Traceback" not in error


def test_self_check_failure_message_mentions_workaround(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "write_text", lambda self, *a, **k: (_ for _ in ()).throw(
        PermissionError(13, "Permission denied", str(self))))
    entry.write_self_check(str(tmp_path / "x.json"))
    error = capsys.readouterr().err
    assert "--self-check" in error or "不带参数" in error
