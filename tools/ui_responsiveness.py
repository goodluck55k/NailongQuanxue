"""真实 Qt 窗口下的 UI 响应性检查（不是只看进程活着）。

用 windows 平台插件创建真窗口，模拟点击，同时用 50 ms 心跳测量事件循环最大停顿；
再验证：主窗口可用、计时器在走、设置对话框能开能关、AI 配置页能操作、
投降对话框能打开并取消、后台任务运行期间界面仍可交互、关窗能正常退出。
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "windows"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.async_task import run_async  # noqa: E402
from app.config_store import ConfigStore  # noqa: E402
from app.main_window import MainWindow  # noqa: E402
from app.supervision import DECLARATION, Supervision  # noqa: E402

REPORT = {"checks": [], "max_gap_ms": 0.0}


def record(name, ok, detail=""):
    REPORT["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + ((" — " + detail) if detail else ""))


class Heartbeat:
    """每 50 ms 记一次时间戳，最大间隔就是主线程最长停顿。"""

    def __init__(self):
        self.last = time.perf_counter()
        self.started = self.last
        self.step = "startup"
        self.gaps = []
        self.timer = QTimer()
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.beat)

    step = "startup"

    def beat(self):
        now = time.perf_counter()
        gap = (now - self.last) * 1000
        self.gaps.append(gap)
        if gap > 120:
            REPORT.setdefault("slow_frames", []).append(
                {"gap_ms": round(gap, 1), "step": self.step, "at_s": round(now - self.started, 2)})
        self.last = now

    def start(self):
        self.timer.start()

    def stop(self):
        self.timer.stop()
        self.max_gap = round(max(self.gaps), 1) if self.gaps else 0.0
        REPORT["max_gap_ms"] = self.max_gap
        return self.max_gap


def main():
    data = Path(tempfile.mkdtemp(prefix="nailong-ui-"))
    app = QApplication(sys.argv[:1])
    config = ConfigStore(data)
    controller = Supervision()
    window = MainWindow(controller=controller, config=config)
    beat = Heartbeat()
    paint_started = time.perf_counter()
    window.show()
    beat.start()
    QTest.qWait(1200)
    REPORT["first_paint_ms"] = round((time.perf_counter() - paint_started) * 1000, 1)
    # 首帧绘制（字体、样式、托盘图标）算启动成本，交互阶段的停顿单独统计。
    beat.gaps.clear()
    beat.last = time.perf_counter()
    beat.step = "interaction"

    record("主窗口可见", window.isVisible())
    record("主窗口可用（没有被模态框禁用）", window.isEnabled())
    record("可写目录时不显示数据目录横幅", not window.data_banner.isVisible())

    beat.step = "start-timer"
    QTest.mouseClick(window.start_button, Qt.MouseButton.LeftButton)
    QTest.qWait(1200)
    remaining_one = controller.poll().remaining
    QTest.qWait(1500)
    remaining_two = controller.poll().remaining
    record("计时开始后倒计时在减少", remaining_two < remaining_one,
           "%.1f → %.1f" % (remaining_one, remaining_two))

    beat.step = "open-settings"
    window.open_settings()
    QTest.qWait(700)
    opened = window.settings is not None and window.settings.isVisible()
    record("设置对话框能打开", opened)
    if opened:
        window.settings.accept()
        QTest.qWait(500)
        record("设置对话框能关闭", window.settings is None or not window.settings.isVisible())

    beat.step = "open-ai"
    window.open_ai_setup()
    QTest.qWait(700)
    ai_open = window.ai_dialog is not None and window.ai_dialog.isVisible()
    record("AI 配置对话框能打开", ai_open)
    if ai_open:
        panel = window.ai_dialog.panel
        panel.base_url.setText("https://api.deepseek.com")
        panel.model.setText("deepseek-flash")
        panel.api_key.setText("sk-ui-check-not-real")
        QTest.mouseClick(panel.save_button, Qt.MouseButton.LeftButton)
        QTest.qWait(900)
        record("点保存后立刻给出结果（不卡住）", bool(panel.status.text()),
               panel.status.text()[:60])
        window.ai_dialog.reject()
        QTest.qWait(500)
        record("AI 对话框能关闭", window.ai_dialog is None or not window.ai_dialog.isVisible())

    beat.step = "open-surrender"
    window.request_surrender()
    QTest.qWait(800)
    dialog = window.surrender
    record("投降对话框能打开", dialog is not None and dialog.isVisible())
    if dialog is not None and dialog.isVisible():
        record("宣言输入框初始为空且下一步禁用",
               dialog.declaration.text() == "" and not dialog.next_button.isEnabled())
        dialog.declaration.setText(DECLARATION)
        QTest.qWait(200)
        record("输入宣言后下一步可用", dialog.next_button.isEnabled())
        QTest.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)
        QTest.qWait(700)
        record("投降对话框能取消", window.surrender is None or not window.surrender.isVisible())
        record("取消后计时仍在继续", controller.phase.value == "running")

    done = {}
    run_async(lambda: (time.sleep(1.2), "ok")[1],
              lambda result, error: done.update(result=result, error=error))
    QTest.qWait(250)
    before = window.isEnabled()
    QTest.qWait(250)
    record("后台任务运行期间主窗口保持可用", before and window.isEnabled())
    QTest.qWait(1400)
    record("后台任务结果回到 UI 线程", done.get("result") == "ok" and done.get("error") is None)

    gap = beat.stop()
    record("事件循环最大停顿 < 500 ms", gap < 500.0, "%.1f ms" % gap)

    beat.step = "shutdown"
    window.shutdown()
    QTest.qWait(300)
    record("关闭后控制器回到待机", controller.phase.value == "idle")
    app.quit()

    REPORT["result"] = "PASS" if all(item["ok"] for item in REPORT["checks"]) else "FAIL"
    print(json.dumps(REPORT, ensure_ascii=False, indent=2))
    return 0 if REPORT["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
