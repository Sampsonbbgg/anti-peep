"""全局热键（Windows）：用于紧急暂停/恢复防护。"""
import ctypes
import sys
import threading
from ctypes import wintypes

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
VK_P = 0x50


class GlobalHotkey(threading.Thread):
    """在独立线程里注册一个系统级热键，触发时调用 callback。"""

    def __init__(self, callback, vk: int = VK_P, mods: int = MOD_CONTROL | MOD_ALT, hotkey_id: int = 1):
        super().__init__(daemon=True)
        self.callback = callback
        self.vk = vk
        self.mods = mods
        self.hotkey_id = hotkey_id
        self._stop = threading.Event()
        self._thread_id = None
        self.registered = False

    def run(self):
        if not sys.platform.startswith("win"):
            return
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        self.registered = bool(user32.RegisterHotKey(None, self.hotkey_id, self.mods | MOD_NOREPEAT, self.vk))
        if not self.registered:
            return
        msg = wintypes.MSG()
        while not self._stop.is_set():
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r == 0 or r == -1:
                break
            if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                try:
                    self.callback()
                except Exception:
                    pass
        try:
            user32.UnregisterHotKey(None, self.hotkey_id)
        except Exception:
            pass

    def stop(self):
        self._stop.set()
        if self._thread_id and sys.platform.startswith("win"):
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
