"""主线程卡死诊断：看门狗必须在主线程停顿时导出线程栈。"""
import io
import threading
import time

from app import diagnostics


def test_watchdog_reports_a_stall(tmp_path):
    # faulthandler 需要真实文件描述符，所以这里用文件而不是 StringIO。
    path = tmp_path / "stall.log"
    with open(path, "a", encoding="utf-8") as stream:
        watchdog = diagnostics.Watchdog(threshold=0.3, stream=stream)
        watchdog.start()
        try:
            time.sleep(1.4)  # 不调用 beat()，模拟主线程卡住
        finally:
            watchdog.stop()
    text = path.read_text(encoding="utf-8")
    assert watchdog.stalls >= 1
    assert "UI stall" in text
    assert "Thread 0x" in text or "File \"" in text


def test_watchdog_stays_quiet_when_beating():
    stream = io.StringIO()
    watchdog = diagnostics.Watchdog(threshold=2.0, stream=stream)
    watchdog.start()
    try:
        for _ in range(6):
            watchdog.beat()
            time.sleep(0.2)
    finally:
        watchdog.stop()
    assert watchdog.stalls == 0
    assert stream.getvalue() == ""


def test_watchdog_beat_comes_from_calling_thread():
    watchdog = diagnostics.Watchdog(threshold=60)
    before = watchdog.last_beat
    time.sleep(0.05)
    watchdog.beat()
    assert watchdog.last_beat > before
    assert watchdog._thread is None
    watchdog.beat()
    assert threading.current_thread().name != "ui-watchdog"


def test_install_faulthandler_survives_unwritable_path(tmp_path):
    handle = diagnostics.install_faulthandler(tmp_path / "no-such-dir" / "crash.log")
    assert handle is None or handle.closed is False


def test_install_faulthandler_writes_to_readable_file(tmp_path):
    handle = diagnostics.install_faulthandler(tmp_path / "crash.log")
    assert handle is not None
    handle.close()
