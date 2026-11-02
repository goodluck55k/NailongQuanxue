"""奶龙劝学 entry point. No network, elevation or global input hooks."""

import argparse
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import sys

APP_VERSION = "2.0.1"


def positive_seconds(value):
    seconds = float(value)
    if not math.isfinite(seconds) or not 0 < seconds <= 59999:
        raise argparse.ArgumentTypeError("测试时长必须大于 0 且不超过 59999 秒")
    return seconds


def log_folder():
    """日志目录；优先可写的数据目录，拿不到就退回用户主目录。"""
    try:
        from app.config_store import usable_data_directory
        return usable_data_directory() / "logs"
    except Exception:
        return Path(os.path.expanduser("~")) / "NailongQuanxue-logs"


def configure_logging():
    try:
        folder = log_folder()
        folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(folder / "screenbreak.log", maxBytes=256_000,
                                      backupCount=2, encoding="utf-8")
        logging.basicConfig(level=logging.INFO, handlers=[handler],
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    except OSError:
        logging.basicConfig(level=logging.INFO, handlers=[logging.NullHandler()])


def default_self_check_path():
    """没有指定路径时，写到当前用户数据目录下（通常是可写的）。"""
    from app.config_store import data_directory
    return data_directory() / "diagnostics" / "self-check.json"


def write_self_check(path=None):
    """把本机环境与摄像头诊断写成 JSON，供打包后核对（不弹窗、不上传）。

    目标路径写不进去时打印一句能看懂的中文原因，而不是抛 Python Traceback。
    """
    import json
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication
    from app.camera_access import diagnose
    from app.config_store import data_directory, describe_os_error

    target = Path(path) if path else default_self_check_path()
    if target.exists() and target.is_dir():
        print("自检：%s 是一个目录，请指定一个文件路径，例如 C:\\Temp\\self-check.json" % target,
              file=sys.stderr)
        return 2

    if QApplication.instance() is None:
        QApplication(sys.argv[:1])
    diagnosis = diagnose()
    payload = {
        "version": APP_VERSION,
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "qt": qVersion(),
        "data_directory": str(data_directory()),
        "camera": {
            "state": diagnosis.state,
            "names": diagnosis.names,
            "activation_hr": None if diagnosis.activation is None else hex(diagnosis.activation),
            "error": diagnosis.error,
            "message": diagnosis.message(),
        },
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as error:
        print("自检结果无法写入 %s：%s" % (target, describe_os_error(error, target)), file=sys.stderr)
        print("可以不带参数重新运行（默认写到 %s），或换一个自己确认可写的目录。"
              % default_self_check_path(), file=sys.stderr)
        return 2
    print("自检结果已写入：%s" % target)
    return 0


def write_save_probe(path=None):
    """分阶段试写一个临时文件，报告每一步的结果（不碰用户真实配置）。"""
    import json
    from app.config_store import (data_directory, probe_environment, staged_write,
                                  usable_data_directory)

    folder = Path(path) if path else data_directory()
    target = folder / "save-probe.json"
    stages, error = staged_write(target, '{"probe": true}')
    if error is None:
        try:
            target.unlink()
        except OSError:
            pass
    payload = {
        "target": str(target),
        "ok": error is None,
        "stages": stages,
        "error": None if error is None else "%s errno=%s winerror=%s" % (
            type(error).__name__, getattr(error, "errno", None), getattr(error, "winerror", None)),
        "data_directory": str(data_directory()),
        "usable_data_directory": str(usable_data_directory()),
        "environment": probe_environment(),
        "settings_roundtrip": settings_roundtrip(usable_data_directory()),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    ok = bool(payload["settings_roundtrip"].get("ok"))
    return 0 if ok else 2


def settings_roundtrip(folder):
    """在给定目录里跑一遍真实的 save_settings + 重新读取 + DPAPI 解密。

    用独立的 probe-root 子目录和假 Key，绝不碰用户的 settings.json。
    """
    import shutil
    from app.ai_config import AiSettings, read_settings, save_settings
    from app.config_store import ConfigStore

    root = Path(folder) / "probe-root"
    result = {"root": str(root)}
    try:
        shutil.rmtree(root, ignore_errors=True)
        store = ConfigStore(root)
        sample = AiSettings(protocol="openai", base_url="https://api.deepseek.com",
                            model="probe-model", api_key="sk-probe-not-a-real-key")
        written = save_settings(store, sample, verified=False)
        raw = (root / "settings.json").read_text(encoding="utf-8")
        reloaded = read_settings(__import__("json").loads(raw))
        result.update({
            "ok": (written.base_url == sample.base_url
                   and written.model == sample.model
                   and reloaded.api_key == sample.api_key
                   and reloaded.protocol == "openai"),
            "sealed_in_file": "dpapi:" in raw,
            "plaintext_key_in_file": sample.api_key in raw,
            "recovered_key": reloaded.api_key == sample.api_key,
            "protocol": reloaded.protocol,
            "base_url": reloaded.base_url,
            "model": reloaded.model,
        })
    except Exception as error:  # noqa: BLE001 - 诊断命令要报告而不是抛出
        result.update({"ok": False, "error": "%s: %s" % (type(error).__name__, error)})
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return result


def gui_save_test():
    """在真实 Qt 界面里点一次「保存配置」，验证打包后的保存链路（含 DPAPI）。

    会临时覆盖数据目录里的 settings.json，结束后按原字节还原。
    """
    import json
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from app.ai_config import read_settings
    from app.ai_panel import AiSettingsPanel
    from app.config_store import ConfigStore, usable_data_directory

    report = {"data_directory": str(usable_data_directory())}
    app = QApplication.instance() or QApplication([])
    store = ConfigStore(usable_data_directory())
    original = store.path.read_bytes() if store.path.exists() else None
    panel = None
    try:
        panel = AiSettingsPanel(store)
        panel.show()
        app.processEvents()
        panel.protocol.setCurrentIndex(0)
        panel.base_url.setText("https://api.deepseek.com")
        panel.api_key.setText("sk-probe-not-a-real-key")
        panel.model.setText("probe-model")
        app.processEvents()
        QTest.mouseClick(panel.save_button, Qt.LeftButton)
        for _ in range(20):
            app.processEvents()
            QTest.qWait(50)
        report["status_text"] = panel.status.text()
        raw = store.path.read_text(encoding="utf-8") if store.path.exists() else ""
        reloaded = read_settings(json.loads(raw)) if raw else None
        report.update({
            "file_written": bool(raw),
            "sealed_in_file": "dpapi:" in raw,
            "plaintext_key_in_file": "sk-probe-not-a-real-key" in raw,
            "protocol": reloaded.protocol if reloaded else "",
            "base_url": reloaded.base_url if reloaded else "",
            "model": reloaded.model if reloaded else "",
            "key_recovered": bool(reloaded and reloaded.api_key == "sk-probe-not-a-real-key"),
        })
        report["ok"] = bool(report["file_written"] and report["sealed_in_file"]
                            and not report["plaintext_key_in_file"]
                            and report["key_recovered"]
                            and report["model"] == "probe-model")
    except Exception as error:  # noqa: BLE001 - 诊断命令要报告而不是抛出
        report.update({"ok": False, "error": "%s: %s" % (type(error).__name__, error)})
    finally:
        try:
            if panel is not None:
                panel.close()
        except Exception:
            pass
        try:
            if original is None:
                store.path.unlink(missing_ok=True)
            else:
                store.path.write_bytes(original)
        except OSError as error:
            report["restore_error"] = str(error)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 2


def main():
    parser = argparse.ArgumentParser(description="奶龙劝学 — 少玩一会儿，多学一点")
    parser.add_argument("--test-seconds", type=positive_seconds,
                       help="自动开始指定秒数的开发计时，例如 15")
    parser.add_argument("--self-check", nargs="?", const="", default=None, metavar="PATH",
                       help="只写一份环境与摄像头诊断 JSON 后退出；省略 PATH 时写入数据目录")
    parser.add_argument("--save-probe", nargs="?", const="", default=None, metavar="DIR",
                       help="分阶段测试目录是否可写（不修改用户配置），输出 JSON 后退出")
    parser.add_argument("--ui-save-test", action="store_true",
                       help="在真实界面里点一次「保存配置」并校验结果（测试用，会还原原配置）")
    args = parser.parse_args()
    if args.ui_save_test:
        return gui_save_test()
    if args.save_probe is not None:
        try:
            return write_save_probe(args.save_probe)
        except Exception as error:  # noqa: BLE001 - 诊断命令失败也要给中文说明
            print("保存探测未能完成：%s: %s" % (type(error).__name__, error), file=sys.stderr)
            return 2
    if args.self_check is not None:
        try:
            return write_self_check(args.self_check)
        except Exception as error:  # 自检失败也不能甩出 Traceback
            print("自检未能完成：%s: %s" % (type(error).__name__, error), file=sys.stderr)
            return 2
    import time
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.diagnostics import Watchdog, install_faulthandler
    from app.main_window import MainWindow
    from app.windows_session_events import WindowsSessionEvents

    started = time.monotonic()
    log = logging.getLogger("NailongQuanxue")
    configure_logging()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("奶龙劝学")
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)

    try:
        window = MainWindow()
    except Exception as error:  # 启动失败也要给中文提示，不能只甩 Traceback
        log.exception("Startup failed")
        QMessageBox.critical(None, "奶龙劝学",
                             "启动失败：%s\n\n本地日志：%s" % (error, log_folder()))
        return 1
    log.info("主窗口构建完成，用时 %.0f ms", (time.monotonic() - started) * 1000)

    session_events = WindowsSessionEvents(app, window)
    window.quit_requested.connect(app.quit)
    app.applicationStateChanged.connect(lambda *_: QTimer.singleShot(0, window.tick))
    app.commitDataRequest.connect(window.shutdown)
    app.aboutToQuit.connect(window.shutdown)
    app.aboutToQuit.connect(session_events.close)

    # 卡死诊断：faulthandler 记录崩溃栈，看门狗在主线程停顿时导出所有线程栈。
    stream = install_faulthandler(log_folder() / "crash.log")
    watchdog = Watchdog(stream=stream)
    watchdog.start()
    heartbeat = QTimer()
    heartbeat.setInterval(250)
    heartbeat.timeout.connect(watchdog.beat)
    heartbeat.start()
    app.aboutToQuit.connect(watchdog.stop)

    def on_exception(kind, value, traceback):
        # Do not log locals, camera frames or the declaration text.
        log.critical("Unexpected application error: %s", kind.__name__, exc_info=(kind, value, traceback))
        window.shutdown()
        QMessageBox.critical(None, "奶龙劝学", "发生错误，本次监督已结束。请查看本地日志；不会自动恢复监督。")
        app.exit(1)

    sys.excepthook = on_exception
    window.show()
    log.info("界面已显示，启动总耗时 %.0f ms", (time.monotonic() - started) * 1000)
    if args.test_seconds is not None:
        QTimer.singleShot(0, lambda: window.start_timer(args.test_seconds))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
