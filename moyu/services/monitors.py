import ctypes
import sys
from ctypes import wintypes
from typing import List, Tuple


def _normalize(rects, primary=None):
    out = [tuple(int(v) for v in r) for r in rects if r[2] > 0 and r[3] > 0]
    if out:
        return out
    if primary:
        return [(0, 0, int(primary[0]), int(primary[1]))]
    return [(0, 0, 1920, 1080)]


def list_monitors() -> List[Tuple[int, int, int, int]]:
    """返回每台显示器的 (left, top, width, height)。"""
    if not sys.platform.startswith("win"):
        return _normalize([])
    try:
        user32 = ctypes.windll.user32
        rects = []

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.POINTER(wintypes.RECT),
            ctypes.c_double,
        )

        def cb(_hmon, _hdc, lprect, _data):
            r = lprect.contents
            rects.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
            return 1

        user32.EnumDisplayMonitors(0, None, MonitorEnumProc(cb), 0)
        primary = (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
        return _normalize(rects, primary=primary)
    except Exception:
        return _normalize(
            [],
            primary=(
                ctypes.windll.user32.GetSystemMetrics(0),
                ctypes.windll.user32.GetSystemMetrics(1),
            ),
        )
