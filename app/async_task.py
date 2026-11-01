"""Run a blocking call off the Qt main thread and deliver its outcome."""
from PySide6.QtCore import QObject, QRunnable, Signal

from PySide6.QtCore import QThreadPool

_ACTIVE = set()


class _Signals(QObject):
    done = Signal(object, object)


class _Task(QRunnable):
    def __init__(self, work, signals):
        super().__init__()
        self.work = work
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        try:
            result = self.work()
        except BaseException as error:  # noqa: BLE001 - reported to the UI, never raised here
            self.signals.done.emit(None, error)
            return
        self.signals.done.emit(result, None)


def run_async(work, callback, pool=None):
    """work() runs in a worker thread; callback(result, error) runs in the UI thread."""
    signals = _Signals()
    _ACTIVE.add(signals)

    def finish(result, error):
        _ACTIVE.discard(signals)
        try:
            callback(result, error)
        finally:
            signals.deleteLater()

    signals.done.connect(finish)
    task = _Task(work, signals)
    (pool or QThreadPool.globalInstance()).start(task)
    return task
