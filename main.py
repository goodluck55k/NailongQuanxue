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


def configure_logging():
    try:
        from app.config_store import data_directory
        folder = data_directory() / "logs"
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


def main():
    parser = argparse.ArgumentParser(description="奶龙劝学 — 少玩一会儿，多学一点")
    parser.add_argument("--test-seconds", type=positive_seconds,
                       help="自动开始指定秒数的开发计时，例如 15")
    parser.add_argument("--self-check", nargs="?", const="", default=None, metavar="PATH",
                       help="只写一份环境与摄像头诊断 JSON 后退出；省略 PATH 时写入数据目录")
    args = parser.parse_args()
    if args.self_check is not None:
        try:
            return write_self_check(args.self_check)
        except Exception as error:  # 自检失败也不能甩出 Traceback
            print("自检未能完成：%s: %s" % (type(error).__name__, error), file=sys.stderr)
            return 2
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.main_window import MainWindow
    from app.windows_session_events import WindowsSessionEvents

    configure_logging()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("奶龙劝学")
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()

    session_events = WindowsSessionEvents(app, window)
    window.quit_requested.connect(app.quit)
    app.applicationStateChanged.connect(lambda *_: QTimer.singleShot(0, window.tick))
    app.commitDataRequest.connect(window.shutdown)
    app.aboutToQuit.connect(window.shutdown)
    app.aboutToQuit.connect(session_events.close)

    def on_exception(kind, value, traceback):
        # Do not log locals, camera frames or the declaration text.
        logging.getLogger("NailongQuanxue").critical("Unexpected application error: %s", kind.__name__)
        window.shutdown()
        QMessageBox.critical(None, "奶龙劝学", "发生错误，本次监督已结束。请查看本地日志；不会自动恢复监督。")
        app.exit(1)

    sys.excepthook = on_exception
    window.show()
    if args.test_seconds is not None:
        QTimer.singleShot(0, lambda: window.start_timer(args.test_seconds))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
