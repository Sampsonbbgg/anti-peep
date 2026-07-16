"""Windows 会话状态检测。"""

import ctypes
import sys
import time
from ctypes import wintypes
from typing import Callable, Optional


DESKTOP_SWITCHDESKTOP = 0x0100
WTS_CURRENT_SESSION = 0xFFFFFFFF
WTS_SESSION_INFO_EX = 25
WTS_SESSIONSTATE_LOCK = 0
WTS_SESSIONSTATE_UNLOCK = 1


class _WTSINFOEX_LEVEL1(ctypes.Structure):
    _fields_ = [
        ("SessionId", wintypes.DWORD),
        ("SessionState", ctypes.c_int),
        ("SessionFlags", wintypes.LONG),
        ("WinStationName", wintypes.WCHAR * 33),
        ("UserName", wintypes.WCHAR * 21),
        ("DomainName", wintypes.WCHAR * 18),
        ("LogonTime", ctypes.c_longlong),
        ("ConnectTime", ctypes.c_longlong),
        ("DisconnectTime", ctypes.c_longlong),
        ("LastInputTime", ctypes.c_longlong),
        ("CurrentTime", ctypes.c_longlong),
        ("IncomingBytes", wintypes.DWORD),
        ("OutgoingBytes", wintypes.DWORD),
        ("IncomingFrames", wintypes.DWORD),
        ("OutgoingFrames", wintypes.DWORD),
        ("IncomingCompressedBytes", wintypes.DWORD),
        ("OutgoingCompressedBytes", wintypes.DWORD),
    ]


class _WTSINFOEX_DATA(ctypes.Union):
    _fields_ = [("WTSInfoExLevel1", _WTSINFOEX_LEVEL1)]


class _WTSINFOEX(ctypes.Structure):
    _fields_ = [("Level", wintypes.DWORD), ("Data", _WTSINFOEX_DATA)]


def _query_wts_lock_state() -> Optional[bool]:
    """从当前 WTS 会话读取明确的锁定/解锁标记。"""
    try:
        wtsapi32 = ctypes.WinDLL("Wtsapi32", use_last_error=True)
        wtsapi32.WTSQuerySessionInformationW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.DWORD),
        ]
        wtsapi32.WTSQuerySessionInformationW.restype = wintypes.BOOL
        wtsapi32.WTSFreeMemory.argtypes = [ctypes.c_void_p]

        buffer = ctypes.c_void_p()
        size = wintypes.DWORD()
        if not wtsapi32.WTSQuerySessionInformationW(
            0,
            WTS_CURRENT_SESSION,
            WTS_SESSION_INFO_EX,
            ctypes.byref(buffer),
            ctypes.byref(size),
        ):
            return None

        try:
            if size.value < ctypes.sizeof(_WTSINFOEX):
                return None
            info = ctypes.cast(buffer, ctypes.POINTER(_WTSINFOEX)).contents
            if info.Level != 1:
                return None
            flags = info.Data.WTSInfoExLevel1.SessionFlags
            if flags == WTS_SESSIONSTATE_LOCK:
                return True
            if flags == WTS_SESSIONSTATE_UNLOCK:
                return False
            return None
        finally:
            wtsapi32.WTSFreeMemory(buffer)
    except Exception:
        return None


def _probe_workstation_locked() -> bool:
    """判断 Windows 当前会话是否锁屏。"""
    if not sys.platform.startswith("win"):
        return False

    wts_state = _query_wts_lock_state()
    if wts_state is not None:
        return wts_state

    # 旧系统无法读取 WTSInfoEx 时，回退到输入桌面检测。
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.OpenInputDesktop.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        user32.OpenInputDesktop.restype = wintypes.HANDLE
        user32.SwitchDesktop.argtypes = [wintypes.HANDLE]
        user32.SwitchDesktop.restype = wintypes.BOOL
        user32.CloseDesktop.argtypes = [wintypes.HANDLE]
        user32.CloseDesktop.restype = wintypes.BOOL

        desktop = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
        if not desktop:
            # 安全桌面通常不允许普通桌面进程取得可切换句柄。
            return True
        try:
            return not bool(user32.SwitchDesktop(desktop))
        finally:
            user32.CloseDesktop(desktop)
    except Exception:
        # 检测 API 异常时不把系统误判为锁屏。
        return False


class WindowsSessionState:
    """带短时缓存的 Windows 锁屏状态读取器。"""

    def __init__(
        self,
        probe: Optional[Callable[[], bool]] = None,
        cache_seconds: float = 0.5,
    ):
        self._probe = probe or _probe_workstation_locked
        self._cache_seconds = cache_seconds
        self._last_check_time: Optional[float] = None
        self._locked = False

    def is_locked(self) -> bool:
        now = time.monotonic()
        if (
            self._last_check_time is None
            or now - self._last_check_time >= self._cache_seconds
        ):
            self._locked = bool(self._probe())
            self._last_check_time = now
        return self._locked
