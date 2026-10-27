"""Windows EXE smoke test using messages targeted only to the launched process.

Launches a visible 15-second timer, minimizes it, checks top-level windows and
opens the release dialog and exercises its sole footer cancel action.
The harness terminates only its own test process after checking the active break;
this does not verify normal application exit. No camera, screenshots or global hooks.
"""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This smoke test requires Windows")
    args.report = args.report.resolve()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.IsIconic.argtypes = [wintypes.HWND]
    report = {"executable": args.executable.name, "checks": []}
    process = None
    start = time.monotonic()

    def windows():
        found = {}

        @callback_type
        def collect(hwnd, _):
            pid = wintypes.DWORD()
            user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == process.pid and user.IsWindowVisible(hwnd):
                title = ctypes.create_unicode_buffer(256)
                user.GetWindowTextW(hwnd, title, 256)
                found[hwnd] = title.value
            return True

        user.EnumWindows(collect, 0)
        return found

    def wait_for(predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Application exited early: {process.returncode}")
            result = predicate()
            if result:
                return result
            time.sleep(0.05)
        raise TimeoutError("Expected application state did not appear")

    def find(title):
        return [hwnd for hwnd, text in windows().items() if text == title]

    def click_button(hwnd, surrender=False):
        rect = wintypes.RECT()
        user.GetClientRect(hwnd, ctypes.byref(rect))
        # Overlay: the sole release button, 150x48 with a 24px margin.
        # Surrender: the sole, full-width cancel action in the footer.
        user.GetDpiForWindow.argtypes = [wintypes.HWND]
        scale = user.GetDpiForWindow(hwnd) / 96
        x = round(rect.right * .5 if surrender else rect.right - 99 * scale)
        y = round(rect.bottom - (43 if surrender else 48) * scale)
        point = (y << 16) | x
        user.PostMessageW(hwnd, 0x201, 1, point)
        user.PostMessageW(hwnd, 0x202, 0, point)

    try:
        working = args.report.parent / "exe-workdir"
        working.mkdir(exist_ok=True)
        env = dict(os.environ)
        env.pop("QT_QPA_PLATFORM", None)
        env["LOCALAPPDATA"] = str(args.report.parent / "exe-localappdata")
        env["NAILONG_DATA_DIR"] = str(args.report.parent / "v11-exe-data")
        process = subprocess.Popen([str(args.executable.resolve()), "--test-seconds", "15"],
                                   cwd=working, env=env)
        main_hwnd = wait_for(lambda: find("奶龙劝学"))[0]
        user.ShowWindow(main_hwnd, 6)
        assert user.IsIconic(main_hwnd)
        report["checks"].append("EXE starts from a different working directory and minimizes")
        wait_for(lambda: find("奶龙劝学 提醒"), timeout=12)
        report["checks"].append("final reminder appears while main window minimized")
        overlays = wait_for(lambda: find("奶龙劝学 — 五分钟休息"), timeout=20)
        report["overlay_count"] = len(overlays)
        report["overlay_observed_seconds"] = round(time.monotonic() - start, 3)
        assert not find("奶龙劝学 提醒")
        for hwnd in overlays:
            assert user.GetWindowLongW(hwnd, -20) & 0x8  # WS_EX_TOPMOST
        report["checks"].append("zero clears reminder and opens topmost overlay windows")
        # The primary overlay is the one whose right-bottom button responds.
        for hwnd in overlays:
            click_button(hwnd)
            # The window becomes visible before FFmpeg initializes. Allow its
            # GUI thread to process the posted click instead of killing it early.
            click_deadline = time.monotonic() + 4
            while time.monotonic() < click_deadline and not find("奶龙投降书"):
                time.sleep(.05)
            if find("奶龙投降书"):
                break
        else:
            raise AssertionError("No clickable release button found")
        surrender = wait_for(lambda: find("奶龙投降书"))[0]
        report["checks"].append("sole overlay release button opens surrender dialog")
        click_button(surrender, surrender=True)
        wait_for(lambda: not find("奶龙投降书"))
        assert not find("紧急退出监督")
        assert len(find("奶龙劝学 — 五分钟休息")) == len(overlays)
        report["checks"].append("sole surrender footer action cancels dialog and preserves active break")
        report["normal_application_exit_verified"] = False
        report["result"] = "PASS"
    except Exception as error:
        report["result"] = "FAIL"
        report["error"] = f"{type(error).__name__}: {error}"
        if process is not None and process.poll() is None:
            report["visible_application_windows"] = list(windows().values())
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
            report["cleanup"] = "harness terminated only its own launched test process"
        report["elapsed_seconds"] = round(time.monotonic() - start, 3)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
