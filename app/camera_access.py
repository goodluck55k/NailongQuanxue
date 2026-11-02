"""摄像头可用性诊断：区分「没有摄像头」和「Windows 拒绝了本程序」。

Qt 在 Windows 上遇到隐私授权被拒时，`QMediaDevices.videoInputs()` 只会返回空列表，
和「真的没有摄像头」长得一模一样。这里用 Media Foundation 直接再问一次系统：

* 枚举得到设备名 → 硬件存在；再尝试打开第一个设备，
  拿到 `E_ACCESSDENIED` 就说明是「被 Windows 的摄像头授权拦住了」。
* 枚举为空 → 确实没有设备。

只读诊断，不修改注册表、不改系统设置；引导用户自己去 Windows 设置里授权。
"""
from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass, field

OK = "ok"
BLOCKED = "blocked"
NONE = "none"
UNKNOWN = "unknown"

E_ACCESSDENIED = 0x80070005

_SOURCE_TYPE = "c60ac5fe-252a-478f-a0ef-bc8fa5f7cad3"
_SOURCE_TYPE_VIDCAP = "8ac3587a-4ae7-42d8-99e0-0a6013eef90f"
_FRIENDLY_NAME = "60d0e559-52f8-4fa2-bbce-acdb34a8ec01"

_PRIVACY_URI = "ms-settings:privacy-webcam"


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(text):
    a, b, c, d, e = text.split("-")
    tail = bytes.fromhex(d + e)
    return _GUID(int(a, 16), int(b, 16), int(c, 16), (ctypes.c_ubyte * 8)(*tail))


def _call(obj, index, argtypes, *args):
    """调用 COM 接口的第 index 号虚函数（0 基，含 IUnknown 三个方法）。"""
    table = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, *argtypes)
    return proto(table[index])(obj, *args)


def _probe():
    """返回 {"names": [...], "activation": hr|None, "error": str|None}。"""
    result = {"names": [], "activation": None, "error": None}
    if sys.platform != "win32":
        result["error"] = "not-windows"
        return result
    try:
        mfplat = ctypes.WinDLL("mfplat")
        # MFEnumDeviceSources / MFCreateDeviceSource 在 mf.dll，不在 mfplat.dll
        mf = ctypes.WinDLL("mf")
        ole32 = ctypes.WinDLL("ole32")
    except OSError as exc:  # pragma: no cover - 只可能出现在缺 Media Foundation 的系统
        result["error"] = "mfplat: %s" % exc
        return result

    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    mfplat.MFCreateAttributes.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint32]
    mf.MFEnumDeviceSources.argtypes = [ctypes.c_void_p,
                                           ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
                                           ctypes.POINTER(ctypes.c_uint32)]
    mf.MFCreateDeviceSource.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]

    attributes = ctypes.c_void_p()
    started = False
    try:
        hr = mfplat.MFStartup(0x00020070, 0)
        if hr < 0:
            result["error"] = "MFStartup 0x%08X" % (hr & 0xFFFFFFFF)
            return result
        started = True
        hr = mfplat.MFCreateAttributes(ctypes.byref(attributes), 1)
        if hr < 0:
            result["error"] = "MFCreateAttributes 0x%08X" % (hr & 0xFFFFFFFF)
            return result
        kind = _guid(_SOURCE_TYPE)
        vidcap = _guid(_SOURCE_TYPE_VIDCAP)
        hr = _call(attributes, 24, [ctypes.POINTER(_GUID), ctypes.POINTER(_GUID)],
                   ctypes.byref(kind), ctypes.byref(vidcap))
        if hr < 0:
            result["error"] = "SetGUID 0x%08X" % (hr & 0xFFFFFFFF)
            return result

        array = ctypes.POINTER(ctypes.c_void_p)()
        count = ctypes.c_uint32(0)
        hr = mf.MFEnumDeviceSources(attributes, ctypes.byref(array), ctypes.byref(count))
        if hr < 0:
            result["error"] = "MFEnumDeviceSources 0x%08X" % (hr & 0xFFFFFFFF)
            return result

        friendly = _guid(_FRIENDLY_NAME)
        for index in range(count.value):
            activate = ctypes.cast(array[index], ctypes.c_void_p)
            name_buf = ctypes.c_wchar_p()
            length = ctypes.c_uint32(0)
            name = ""
            read = _call(activate, 13,
                         [ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_wchar_p),
                          ctypes.POINTER(ctypes.c_uint32)],
                         ctypes.byref(friendly), ctypes.byref(name_buf), ctypes.byref(length))
            if read >= 0 and name_buf.value:
                name = name_buf.value
                ole32.CoTaskMemFree(name_buf)
            result["names"].append(name or "摄像头 %d" % (index + 1))
            if result["activation"] is None:
                source = ctypes.c_void_p()
                open_hr = mf.MFCreateDeviceSource(activate, ctypes.byref(source))
                result["activation"] = open_hr & 0xFFFFFFFF
                if open_hr >= 0 and source:
                    _call(ctypes.cast(source, ctypes.c_void_p), 2, [])
            _call(activate, 2, [])
        if array:
            ole32.CoTaskMemFree(array)
    except Exception as exc:  # pragma: no cover - COM 里任何意外都退回"未知"
        result["error"] = "probe: %r" % exc
    finally:
        if attributes:
            _call(attributes, 2, [])
        if started:
            try:
                mfplat.MFShutdown()
            except Exception:
                pass
    return result


@dataclass(frozen=True)
class Diagnosis:
    state: str
    names: list = field(default_factory=list)
    activation: int | None = None
    error: str | None = None

    @property
    def blocked(self):
        return self.state == BLOCKED

    def title(self):
        if self.state == OK:
            return "摄像头可以正常使用"
        if self.state == BLOCKED:
            return "Windows 阻止了摄像头访问"
        if self.state == NONE:
            return "没有找到摄像头"
        return "摄像头状态不明"

    def message(self):
        if self.state == BLOCKED:
            if self.names:
                return ("Windows 拒绝了本程序访问摄像头。摄像头本身是正常的"
                        "（系统里能看到：%s），但需要在设置里给本程序授权。"
                        % "、".join(self.names))
            return "Windows 拒绝了本程序访问摄像头，需要在设置里给本程序授权。"
        if self.state == NONE:
            return ("没有检测到摄像头。请确认摄像头已连接、没有被物理开关或快捷键关闭，"
                    "然后点「重新连接摄像头」。")
        if self.state == OK:
            if self.names:
                return "摄像头可用：%s。" % "、".join(self.names)
            return "摄像头可用。"
        return ("无法确认摄像头状态（%s）。可以点「重新连接摄像头」重试，"
                "或检查 Windows 的摄像头隐私设置。" % (self.error or "未知原因"))

    def guide(self):
        if self.state == BLOCKED:
            return [
                "打开 设置 → 隐私和安全性 → 摄像头",
                "确认「摄像头访问」和「允许桌面应用访问你的摄像头」都打开",
                "在同一页的最近活动列表里，把本程序的开关打开",
                "回到这里点「重新连接摄像头」",
            ]
        return ["确认摄像头已连接、没有被 Fn 快捷键或物理挡板关闭",
                "关闭其他正在使用摄像头的程序后重试"]


def diagnose():
    """先问 Qt，再问 Media Foundation，给出可执行的结论。"""
    try:
        from PySide6.QtMultimedia import QMediaDevices
    except Exception:
        QMediaDevices = None
    if QMediaDevices is not None:
        try:
            devices = QMediaDevices.videoInputs()
            if devices:
                return Diagnosis(OK, [d.description() for d in devices])
        except Exception:
            pass
    probe = _probe()
    names = probe.get("names") or []
    if names:
        if probe.get("activation") == E_ACCESSDENIED:
            return Diagnosis(BLOCKED, names, probe.get("activation"))
        if probe.get("activation") is not None and probe["activation"] >= 0:
            return Diagnosis(OK, names, probe["activation"])
        return Diagnosis(UNKNOWN, names, probe.get("activation"), probe.get("error"))
    if probe.get("error"):
        return Diagnosis(UNKNOWN, [], None, probe.get("error"))
    return Diagnosis(NONE, [], None, None)


def open_privacy_settings():
    """打开 Windows 的摄像头隐私设置页（只打开页面，不改任何设置）。"""
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
    except Exception:
        return False
    try:
        return bool(QDesktopServices.openUrl(QUrl(_PRIVACY_URI)))
    except Exception:
        return False


def guidance_text():
    """给对话框用的一段完整提示。"""
    diagnosis = diagnose()
    lines = ["%s：%s" % (diagnosis.title(), diagnosis.message())]
    if diagnosis.state == BLOCKED:
        lines.append("按下面几步授权后回来点「重新连接摄像头」：")
        for number, step in enumerate(diagnosis.guide(), start=1):
            lines.append("%d. %s" % (number, step))
    return "\n".join(lines), diagnosis
