"""Visible Windows source smoke. --full-break runs a real 300-second break.

No real camera image is captured by this test. Data and screenshots stay in build.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-break", action="store_true")
    parser.add_argument("--report", type=Path, default=ROOT / "build" / "v11-native-smoke.json")
    args = parser.parse_args()
    os.environ["QT_QPA_PLATFORM"] = "windows"
    os.environ["NAILONG_DATA_DIR"] = str(ROOT / "build" / ("full-break-data" if args.full_break else "native-smoke-data"))
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtMultimedia import QMediaDevices
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.main_window import MainWindow
    from app.supervision import Phase
    from app.windows_session_events import WindowsSessionEvents

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    win = MainWindow()
    bridge = WindowsSessionEvents(app, win)
    win.show()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {"platform": app.platformName(), "full_300s_break": args.full_break,
              "screens": [{"geometry": [s.geometry().width(), s.geometry().height()], "dpr": s.devicePixelRatio()}
                          for s in app.screens()], "camera_devices": len(QMediaDevices.videoInputs()),
              "session_notifications_registered": bridge.registered, "checks": [], "countdown": [],
              "loops_observed": 0}
    phase = "usage"
    start = time.monotonic()
    last_position = 0
    break_start = None
    last_checkpoint = 0

    def finish(code):
        timer.stop()
        report["result"] = "PASS" if code == 0 else "INTERRUPTED" if code == 2 else "FAIL"
        report["elapsed_seconds"] = round(time.monotonic() - start, 3)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        win.shutdown()
        bridge.close()
        win.close()
        app.exit(code)

    def inspect():
        nonlocal phase, last_position, break_start, last_checkpoint
        try:
            elapsed_now = time.monotonic() - start
            if elapsed_now - last_checkpoint >= 10:
                last_checkpoint = elapsed_now
                checkpoint = {"elapsed_seconds": round(elapsed_now, 2), "phase": phase,
                              "core_phase": win.controller.phase.value, "ring": win.ring.text,
                              "loops": report["loops_observed"]}
                (args.report.parent / "v11-smoke-checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
            if phase == "usage":
                if win.reminder.mode == "final":
                    text = win.reminder.label.text().splitlines()[-1]
                    if not report["countdown"] or report["countdown"][-1] != text:
                        report["countdown"].append(text)
                if win.controller.phase == Phase.BREAK_ACTIVE:
                    assert report["countdown"] == [f"00:{i:02}" for i in range(10, 0, -1)]
                    assert win.screens.active
                    # Account for player/window initialization before this
                    # observer sees BREAK_ACTIVE; the clock already started.
                    break_start = time.monotonic() - win.controller.break_elapsed()
                    phase = "video"
            elif phase == "video":
                video = win.screens.video
                assert video is not None and video.player.audioOutput() is None
                position = video.player.position()
                if last_position - position > 1000:
                    report["loops_observed"] += 1
                last_position = position
                if time.monotonic() - break_start > 11:
                    assert video.frames > 30 and not video.fallback_active
                    assert report["loops_observed"] >= 1
                    report["decoded_frames_at_11s"] = video.frames
                    report["video_size"] = [win.screens.last_frame.width(), win.screens.last_frame.height()]
                    report["checks"] += ["full final countdown", "real video decode and loop", "no audio output attached"]
                    primary = win.screens.windows[app.primaryScreen()]
                    assert primary.geometry() == app.primaryScreen().geometry()
                    assert primary.release_button.isVisible()
                    assert not hasattr(primary, "emergency_button")
                    QTest.mouseClick(primary.release_button, Qt.MouseButton.LeftButton)
                    assert win.surrender is not None
                    if report["camera_devices"] == 0:
                        win.surrender.declaration.setText("我是废物")
                        win.surrender.next_step()
                        assert "没有可用摄像头" in win.surrender.message.text()
                        report["checks"].append("real no-camera error and cancellation available")
                    win.surrender.reject()
                    report["checks"].append("surrender cancellation leaves break running")
                    phase = "full" if args.full_break else "emergency"
            elif phase == "emergency":
                win.tray.emergency_action.trigger()
                assert win.emergency_dialog.isVisible()
                assert win.emergency_dialog.parentWidget() is None
                win.emergency_dialog.hide()
                win.request_emergency()
                assert win.emergency_dialog.isVisible()
                QTest.mouseClick(win.emergency_dialog.button(QMessageBox.StandardButton.No), Qt.MouseButton.LeftButton)
                assert win.controller.phase == Phase.BREAK_ACTIVE
                assert win.emergency_dialog is None
                win.request_emergency()
                QTest.mouseClick(win.emergency_dialog.button(QMessageBox.StandardButton.Yes), Qt.MouseButton.LeftButton)
                assert win.controller.phase == Phase.IDLE
                assert not win.screens.windows and win.screens.video is None
                assert win.records.all()[0]["event_type"] == "EMERGENCY_EXIT"
                report["checks"].append("emergency cancel and confirm release all resources")
                report["checks"].append("repeated emergency restores hidden independent confirmation")
                finish(0)
            elif phase == "full":
                if win.screens.video is not None:
                    video = win.screens.video
                    assert video.player.audioOutput() is None and not video.fallback_active
                    position = video.player.position()
                    if last_position - position > 1000:
                        report["loops_observed"] += 1
                    last_position = position
                if win.controller.phase == Phase.IDLE:
                    if win.records.all()[0]["event_type"] != "BREAK_COMPLETED":
                        report["interrupted_by"] = win.records.all()[0]["event_type"]
                        report["checks"].append("user stopped supervision before full-break completion")
                        finish(2)
                        return
                    elapsed = time.monotonic() - break_start
                    report["observed_break_elapsed_seconds"] = round(elapsed, 3)
                    assert 299.5 <= elapsed < 303, f"Completion observed after {elapsed:.3f}s; event-loop or system delay"
                    assert win.screens.video is None and not win.screens.windows
                    assert win.records.all()[0]["event_type"] == "BREAK_COMPLETED"
                    assert win.reminder.mode == "completed"
                    report["real_break_elapsed_seconds"] = round(elapsed, 3)
                    report["checks"].append("real 300-second break completed without early release")
                    finish(0)
            if ((break_start is not None and time.monotonic() - break_start > (320 if args.full_break else 35))
                    or (break_start is None and time.monotonic() - start > 90)):
                raise TimeoutError("Native smoke timeout")
        except Exception as error:
            report["error"] = f"{type(error).__name__}: {error}"
            finish(1)

    win.grab().save(str(args.report.parent / "v11-main-native.png"))
    win.start_timer(15)
    QTimer.singleShot(1000, win.showMinimized)
    timer = QTimer()
    timer.setInterval(50)
    timer.timeout.connect(inspect)
    timer.start()
    code = app.exec()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
