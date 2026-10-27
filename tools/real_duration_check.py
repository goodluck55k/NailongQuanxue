"""Real 300-second Windows timer/video check without visible blocking windows.

This complements short visible GUI tests; it is not a physical full-screen,
speaker, multi-monitor or sleep/wake manual acceptance test.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "build" / "real-duration-check.json")
    args = parser.parse_args()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from app.supervision import Phase, Supervision
    from app.video_break import VideoBreak

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    core = Supervision()
    video = VideoBreak()
    core.start(1)
    report = {"visible_blocking_windows": False, "break_seconds_required": 300,
              "loops_observed": 0, "actual_clock": "Windows GetTickCount64"}
    started = None
    last_position = 0

    def finish(code):
        timer.stop()
        video.close()
        report["result"] = "PASS" if code == 0 else "FAIL"
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        app.exit(code)

    def check():
        nonlocal started, last_position
        try:
            core.poll()
            if core.phase == Phase.BREAK_ACTIVE:
                if started is None:
                    started = time.monotonic()
                    video.start()
                assert video.player.audioOutput() is None
                assert not video.fallback_active
                position = video.player.position()
                if last_position - position > 1000:
                    report["loops_observed"] += 1
                last_position = position
            elif core.events:
                event = core.events[0]
                report["recorded_break_seconds"] = event.break_seconds
                report["independent_elapsed_seconds"] = round(time.monotonic() - started, 3)
                report["decoded_frames"] = video.frames
                assert event.event_type == "BREAK_COMPLETED"
                assert 300 <= event.break_seconds < 303
                assert 299 <= report["independent_elapsed_seconds"] < 303
                assert report["loops_observed"] >= 30 and video.frames >= 1000
                assert video.player.audioOutput() is None
                finish(0)
        except Exception as error:
            report["error"] = f"{type(error).__name__}: {error}"
            finish(1)

    timer = QTimer()
    timer.setInterval(100)
    timer.timeout.connect(check)
    timer.start()
    code = app.exec()
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
