"""摄像头与无声录像自检（V2.0，复用 app.camera_recorder 正式实现）。

用法（在项目根目录、正常桌面的 PowerShell 里运行）：

    .venv\\Scripts\\python.exe tools\\camera_check.py
    .venv\\Scripts\\python.exe tools\\camera_check.py --seconds 6 --keep
    .venv\\Scripts\\python.exe tools\\camera_check.py --devices-only
    .venv\\Scripts\\python.exe tools\\camera_check.py --gui      # 打开预览窗口，能看见自己

检查项：
  1. Windows/Qt 是否枚举到摄像头
  2. 是否收到预览帧
  3. 无声录像是否落盘（MP4 头、字节数、帧数、时长）
  4. 取消录制后临时文件是否被删除
  5. 重新录制（第二次）是否正常
  6. 摄像头是否释放（停止后能再次打开）

默认录制的两段视频在检查结束后删除；加 --keep 会保留并打印路径。
不会上传任何画面，也不会调用任何视觉 API。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtMultimedia import QMediaDevices  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from app.camera_recorder import DEFAULT_CLIP_MS, CameraRecorder, clip_directory  # noqa: E402


class Check:
    def __init__(self, name):
        self.name = name
        self.ok = False
        self.detail = ""
        self.data = {}

    def pass_(self, detail, **data):
        self.ok = True
        self.detail = detail
        self.data.update(data)
        return self

    def fail(self, detail, **data):
        self.ok = False
        self.detail = detail
        self.data.update(data)
        return self

    def as_dict(self):
        return {"name": self.name, "ok": self.ok, "detail": self.detail, **self.data}


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def pump(ms):
    end = time.monotonic() + ms / 1000.0
    app = QApplication.instance()
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


class RecorderRun:
    """驱动一次 CameraRecorder（与投降对话框里的用法一致）。"""

    def __init__(self, parent, clip_ms):
        self.recorder = CameraRecorder(parent, clip_ms=clip_ms)
        self.preview_frames = 0
        self.progress_calls = 0
        self.path = None
        self.frames = 0
        self.span_ms = 0
        self.error = None
        self.started = False
        self.finished = False
        self.recorder.started.connect(self._started)
        self.recorder.progress.connect(self._progress)
        self.recorder.preview.connect(self._preview)
        self.recorder.finished.connect(self._finished)
        self.recorder.failed.connect(self._failed)

    def _started(self):
        self.started = True

    def _progress(self, elapsed, total):
        self.progress_calls += 1

    def _preview(self, image):
        if not image.isNull():
            self.preview_frames += 1

    def _finished(self, path, frames, span_ms):
        self.path = str(path)
        self.frames = len(frames) if not isinstance(frames, int) else frames
        self.span_ms = span_ms
        self.finished = True

    def _failed(self, message):
        self.error = message

    def start(self):
        self.recorder.start()

    def wait_started(self, timeout_ms=6000):
        end = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() < end:
            QApplication.instance().processEvents()
            if self.started or self.error:
                return self.started
            time.sleep(0.02)
        return False

    def wait_finished(self, timeout_ms):
        end = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() < end:
            QApplication.instance().processEvents()
            if self.finished or self.error:
                return self.finished
            time.sleep(0.02)
        return False

    def shutdown(self, delete=True):
        try:
            if delete:
                self.recorder.stop()
            else:
                self.recorder.release()
        except Exception:
            pass
        self.recorder.deleteLater()
        pump(150)


def inspect_clip(path):
    info = {"path": path, "exists": False, "bytes": 0, "ftyp": "", "playable": False}
    p = Path(path)
    if not p.exists():
        return info
    info["exists"] = True
    info["bytes"] = p.stat().st_size
    with p.open("rb") as fh:
        head = fh.read(16)
    info["ftyp"] = head[4:8].decode("latin-1", "replace")
    info["playable"] = info["ftyp"] == "ftyp" and info["bytes"] > 10000
    return info


def main():
    parser = argparse.ArgumentParser(description="奶龙劝学 V2.0 摄像头与无声录像自检")
    parser.add_argument("--seconds", type=float, default=8.0, help="每段录像秒数（>=6）")
    parser.add_argument("--keep", action="store_true", help="保留录像文件用于人工查看")
    parser.add_argument("--devices-only", action="store_true", help="只枚举摄像头")
    parser.add_argument("--gui", action="store_true", help="打开一个预览窗口")
    parser.add_argument("--report", default=str(ROOT / "build" / "camera-check.json"))
    args = parser.parse_args()

    clip_ms = int(max(6000, min(60000, args.seconds * 1000)))
    app = QApplication.instance() or QApplication(sys.argv)
    checks = []

    devices = QMediaDevices.videoInputs()
    device_report = {
        "count": len(devices),
        "devices": [{"description": d.description(),
                     "id": bytes(d.id()).decode("utf-8", "replace")} for d in devices],
        "audio_inputs": len(QMediaDevices.audioInputs()),
        "clip_directory": str(clip_directory()),
    }
    check = Check("摄像头枚举")
    if devices:
        check.pass_("枚举到 %d 个摄像头：%s" % (len(devices), "、".join(d.description() for d in devices)))
    else:
        check.fail(
            "没有枚举到摄像头。请依次检查：Windows 设置 → 隐私和安全性 → 摄像头 → "
            "“摄像头访问”和“允许桌面应用访问你的摄像头”都为开，并在同一页的应用列表里把本程序打开；"
            "也检查笔记本的摄像头物理开关/热键（如 Fn+F10）与 MyASUS 的摄像头开关。")
    checks.append(check)

    print("摄像头：", check.detail)
    if args.devices_only or not devices or not check.ok:
        _write_report(args.report, device_report, checks, keep=args.keep, files=[])
        return 0 if check.ok else 2

    preview_label = None
    if args.gui:
        preview_label = QLabel("等待摄像头画面")
        preview_label.resize(560, 420)
        preview_label.show()

    # 1) 正常录像一段
    run = RecorderRun(None, clip_ms)
    if preview_label is not None:
        from PySide6.QtGui import QPixmap

        run.recorder.preview.connect(
            lambda img: preview_label.setPixmap(QPixmap.fromImage(img)) if not img.isNull() else None)
    run.start()
    started = run.wait_started()
    check = Check("摄像头启动")
    checks.append(check.pass_("摄像头已激活") if started else check.fail(run.error or "6 秒内没有激活"))

    check = Check("预览画面")
    pump(1200)
    checks.append(check.pass_("收到 %d 帧预览" % run.preview_frames, frames=run.preview_frames)
                  if run.preview_frames > 0 else check.fail("没有收到任何预览帧"))

    if started:
        pump(int(clip_ms) + 3000)
        run.wait_finished(6000)
    check = Check("无声录像落盘")
    if run.finished and run.path:
        info = inspect_clip(run.path)
        good = info["playable"] and run.frames >= 6
        detail = "路径=%s 字节=%d 头=%s 采样帧=%d 跨度=%dms" % (
            info["path"], info["bytes"], info["ftyp"], run.frames, run.span_ms)
        checks.append(check.pass_(detail, **info, sampled_frames=run.frames, span_ms=run.span_ms)
                      if good else check.fail("文件不完整：" + detail, **info))
    else:
        checks.append(check.fail(run.error or "录像没有结束（超时）"))
    first_clip = run.path
    run.shutdown(delete=not args.keep)
    pump(400)

    # 2) 取消录制后清理（只比较取消前后的差异，旧文件不算）
    before = {p.name for p in clip_directory().glob("clip-*.mp4")} if clip_directory().exists() else set()
    run2 = RecorderRun(None, max(6000, clip_ms))
    run2.start()
    run2.wait_started()
    pump(1500)
    temp_path = None
    run2_pending = getattr(run2.recorder, "path", None)
    if run2_pending:
        temp_path = str(run2_pending)
    run2.shutdown(delete=True)
    pump(1500)
    check = Check("取消后清理临时文件")
    leftover = [p for p in clip_directory().glob("clip-*.mp4") if p.name not in before] \
        if clip_directory().exists() else []
    if temp_path and Path(temp_path).exists():
        check.fail("取消后临时文件仍在：%s" % temp_path)
    elif leftover:
        check.fail("临时目录仍有未清理文件：%s" % "、".join(p.name for p in leftover))
    else:
        check.pass_("取消后没有残留临时录像")
    checks.append(check)

    # 3) 重新录制
    run3 = RecorderRun(None, clip_ms)
    run3.start()
    started3 = run3.wait_started()
    pump(int(clip_ms) + 3000)
    run3.wait_finished(6000)
    check = Check("重新录制")
    if run3.finished and run3.path and run3.path != first_clip:
        info = inspect_clip(run3.path)
        checks.append(check.pass_("第二段录像 %s（%d 字节，%d 帧）" % (
            Path(run3.path).name, info["bytes"], run3.frames), **info)
            if info["playable"] else check.fail("第二段录像不完整"))
    else:
        checks.append(check.fail(run3.error or ("摄像头没有重新激活" if not started3 else "没有生成新的录像")))
    second_clip = run3.path
    run3.shutdown(delete=not args.keep)
    pump(500)

    # 4) 释放检查：停止后能再次打开
    run4 = RecorderRun(None, max(6000, clip_ms))
    run4.start()
    released = run4.wait_started(5000)
    run4.shutdown(delete=True)
    check = Check("摄像头释放")
    checks.append(check.pass_("停止后可以再次打开摄像头") if released
                  else check.fail(run4.error or "停止后无法再次打开摄像头，可能没有释放"))

    files = []
    if args.keep:
        files = [p for p in (first_clip, second_clip) if p and Path(p).exists()]

    ok = all(c.ok for c in checks)
    _write_report(args.report, device_report, checks, keep=args.keep, files=files)
    print()
    for c in checks:
        print(("[通过] " if c.ok else "[失败] ") + c.name + "：" + c.detail)
    print()
    if files:
        print("已保留录像（本机文件，请自行确认后再删除）：")
        for f in files:
            print("  " + f)
    print("报告：%s" % args.report)
    print("结论：" + ("摄像头与无声录像自检全部通过。" if ok else "存在失败项，请看上面的明细。"))
    return 0 if ok else 1


def _write_report(path, devices, checks, keep, files):
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python": sys.executable,
        "qt_platform": os.environ.get("QT_QPA_PLATFORM", ""),
        "devices": devices,
        "kept_files": files if keep else [],
        "kept": bool(keep),
        "checks": [c.as_dict() for c in checks],
        "ok": all(c.ok for c in checks) and bool(checks),
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
