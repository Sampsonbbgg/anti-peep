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
WM_APP = 0x8000
WM_ENABLE = WM_APP + 1
WM_DISABLE = WM_APP + 2
VK_P = 0x50
VK_ESCAPE = 0x1B


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


class EscListener(threading.Thread):
    """监听无修饰键 Esc：按需启用/停用，仅在防护层显示时消费 Esc。

    与 GlobalHotkey 不同：Esc 会被系统独占消费，因此不能在常态下一直注册，
    否则会吞掉其它程序的 Esc。这里用一个常驻消息线程，通过 set_enabled()
    动态注册/注销，确保只有模糊或遮屏显示期间 Esc 才被接管。
    """

    def __init__(self, callback, vk: int = VK_ESCAPE, hotkey_id: int = 2):
        super().__init__(daemon=True)
        self.callback = callback
        self.vk = vk
        self.hotkey_id = hotkey_id
        self._stop = threading.Event()
        self._thread_id = None
        self._enabled = False
        self._ready = threading.Event()

    def run(self):
        if not sys.platform.startswith("win"):
            return
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        self._ready.set()
        msg = wintypes.MSG()
        while not self._stop.is_set():
            r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r == 0 or r == -1:
                break
            m = msg.message
            if m == WM_HOTKEY and msg.wParam == self.hotkey_id:
                try:
                    self.callback()
                except Exception:
                    pass
            elif m == WM_ENABLE:
                self._apply(True)
            elif m == WM_DISABLE:
                self._apply(False)
        self._apply(False)

    def _apply(self, enable: bool) -> None:
        if not sys.platform.startswith("win"):
            return
        user32 = ctypes.windll.user32
        if enable and not self._enabled:
            try:
                if user32.RegisterHotKey(None, self.hotkey_id, MOD_NOREPEAT, self.vk):
                    self._enabled = True
            except Exception:
                pass
        elif not enable and self._enabled:
            try:
                user32.UnregisterHotKey(None, self.hotkey_id)
            except Exception:
                pass
            self._enabled = False

    def set_enabled(self, enable: bool) -> None:
        """线程安全地请求启用/停用（从任意线程调用）。"""
        if not sys.platform.startswith("win"):
            return
        self._ready.wait(timeout=1.0)
        if not self._thread_id:
            return
        wm = WM_ENABLE if enable else WM_DISABLE
        try:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, wm, 0, 0)
        except Exception:
            pass

    def stop(self) -> None:
        self._stop.set()
        if self._thread_id and sys.platform.startswith("win"):
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
