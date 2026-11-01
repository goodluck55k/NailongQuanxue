"""Windows DPAPI protection for the API key.

The vision API key is the only secret this application stores. Writing it to
``settings.json`` as plain text would leak it to anyone who can read the profile
directory (backups, sync tools, support bundles), so the key is sealed with
DPAPI under the current Windows user account and only the opaque blob is
persisted.

No new dependencies: ``crypt32``/``kernel32`` are reached through ``ctypes``.
On a platform without DPAPI the helpers report "unavailable" and callers fall
back to plain text, which is the pre-existing behaviour of V1.1/V2.0.
"""
import base64
import ctypes
import sys
from ctypes import wintypes

PREFIX = "dpapi:"
UNPROTECTED = 0x1
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


_crypt32 = None
_kernel32 = None


def _libraries():
    """Return (crypt32, kernel32) with prototypes set, or (None, None)."""
    global _crypt32, _kernel32
    if _crypt32 is not None:
        return (_crypt32, _kernel32) if _crypt32 is not False else (None, None)
    if sys.platform != "win32":
        _crypt32 = False
        return None, None
    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (OSError, AttributeError):
        _crypt32 = False
        return None, None
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_Blob), wintypes.LPCWSTR,
                                         ctypes.POINTER(_Blob), ctypes.c_void_p,
                                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_Blob), ctypes.POINTER(wintypes.LPWSTR),
                                           ctypes.POINTER(_Blob), ctypes.c_void_p,
                                           ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    _crypt32, _kernel32 = crypt32, kernel32
    return crypt32, kernel32


def _input_blob(data):
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def available():
    crypt32, _ = _libraries()
    return crypt32 is not None


def is_sealed(value):
    return isinstance(value, str) and value.startswith(PREFIX)


def protect(text):
    """Seal ``text`` for the current Windows user; returns "" when impossible."""
    if not text or not isinstance(text, str):
        return ""
    crypt32, _ = _libraries()
    if crypt32 is None:
        return ""
    data = text.encode("utf-8")
    source, _keep = _input_blob(data)
    target = _Blob()
    ok = crypt32.CryptProtectData(ctypes.byref(source), None, None, None, None,
                                  _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(target))
    if not ok:
        return ""
    try:
        sealed = ctypes.string_at(target.pbData, target.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(target.pbData, ctypes.c_void_p))
    return PREFIX + base64.b64encode(sealed).decode("ascii")


def unprotect(value):
    """Open a sealed value; plain text is returned unchanged (legacy settings)."""
    if not value or not isinstance(value, str):
        return ""
    if not is_sealed(value):
        return value
    crypt32, _ = _libraries()
    if crypt32 is None:
        return ""
    try:
        raw = base64.b64decode(value[len(PREFIX):], validate=True)
    except (ValueError, TypeError):
        return ""
    if not raw:
        return ""
    source, _keep = _input_blob(raw)
    target = _Blob()
    ok = crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None,
                                    _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(target))
    if not ok:
        return ""
    try:
        opened = ctypes.string_at(target.pbData, target.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(target.pbData, ctypes.c_void_p))
    try:
        return opened.decode("utf-8")
    except UnicodeDecodeError:
        return ""
