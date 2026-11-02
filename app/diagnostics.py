"""主线程卡死诊断：崩溃栈 + 事件循环心跳看门狗。

设计要点：
- ``faulthandler`` 打开后，Qt 主线程真的卡住时也会把栈写进日志；
- 心跳由主线程的 QTimer 更新，看门狗在独立线程里比较时间差；
- 超过阈值就 dump 所有线程的 Python 栈，然后重新计时，避免刷屏；
- 只看时间差，不阻塞、不发信号、不碰 Qt 对象，绝不反过来拖慢 UI。
"""
import faulthandler
import logging
import threading
import time

_log = logging.getLogger("NailongQuanxue")

# 超过这个秒数没有心跳，就认为主线程被卡住了
DEFAULT_THRESHOLD = 5.0
HEARTBEAT_INTERVAL_MS = 250


class Watchdog:
    def __init__(self, threshold=DEFAULT_THRESHOLD, stream=None):
        self.threshold = threshold
        self.stream = stream
        self.last_beat = time.monotonic()
        self.stalls = 0
        self._stop = threading.Event()
        self._thread = None

    def beat(self):
        """主线程每个心跳周期调用一次。"""
        self.last_beat = time.monotonic()

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="ui-watchdog", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.wait(0.5):
            if time.monotonic() - self.last_beat <= self.threshold:
                continue
            self.stalls += 1
            self.last_beat = time.monotonic()
            self._dump()

    def _dump(self):
        _log.error("主线程超过 %.1f 秒没有响应，导出线程栈（第 %d 次）",
                   self.threshold, self.stalls)
        stream = self.stream
        try:
            if stream is not None and hasattr(stream, "fileno"):
                stream.write("\n=== UI stall %s ===\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
                stream.flush()
                faulthandler.dump_traceback(file=stream, all_threads=True)
                stream.flush()
                return
            # faulthandler 只认真实文件描述符；没有就退回 stderr，绝不静默失败。
            faulthandler.dump_traceback(all_threads=True)
        except Exception:  # 诊断本身绝不能把程序拖垮
            pass


def install_faulthandler(path):
    """把崩溃/卡死栈写进日志目录；打不开就退回 stderr。"""
    try:
        handle = open(path, "a", encoding="utf-8")
        faulthandler.enable(file=handle, all_threads=True)
        return handle
    except OSError:
        try:
            faulthandler.enable(all_threads=True)
        except Exception:
            pass
        return None
