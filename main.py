"""奶龙劝学 entry point. No network, elevation or global input hooks."""

import argparse
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import sys


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


def write_self_check(path):
    """把本机环境与摄像头诊断写成 JSON，供打包后核对（不弹窗、不上传）。"""
    import json
    from PySide6.QtCore import qVersion
    from PySide6.QtWidgets import QApplication
    from app.camera_access import diagnose
    from app.config_store import data_directory

    QApplication(sys.argv[:1])
    diagnosis = diagnose()
    payload = {
        "version": "2.0.0",
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
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def main():
    parser = argparse.ArgumentParser(description="奶龙劝学 — 少玩一会儿，多学一点")
    parser.add_argument("--test-seconds", type=positive_seconds,
                       help="自动开始指定秒数的开发计时，例如 15")
    parser.add_argument("--self-check", metavar="PATH",
                       help="只写一份环境与摄像头诊断 JSON 后退出（用于打包核对）")
    args = parser.parse_args()
    if args.self_check:
        return write_self_check(args.self_check)
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.main_window import MainWindow
    from app.windows_session_events import WindowsSessionEvents

    configure_logging()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("奶龙劝学")
    app.setApplicationVersion("2.0.0")
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
