"""多显示器视觉防护层。

- blur：触发瞬间抓取桌面 → 高斯模糊 → 冻结显示（不重抓，避免瞬间泄露清晰画面）。
- cover：不透明全屏遮罩。
"""
import ctypes
import tkinter as tk
from typing import List, Optional

from PIL import Image, ImageFilter, ImageGrab, ImageTk

from ..core.deps import win32con, win32gui
from .monitors import list_monitors


class ScreenShield:
    def __init__(self, root: tk.Tk, config: dict):
        self.root = root
        g = (config.get("privacy_guard", {}) or {}).get("shield", {}) or {}
        self.blur_radius = int(g.get("blur_radius", 28))
        # 0 表示不重抓（推荐）；>0 会周期性重抓，可能造成清晰画面闪现。
        self.blur_refresh_ms = int(g.get("blur_refresh_ms", 0))
        self.cover_text = str(g.get("cover_text", ""))
        self._mode = "none"
        self._windows: List[tk.Toplevel] = []
        self._labels: List[tk.Label] = []
        self._photos: List[Optional[ImageTk.PhotoImage]] = []
        self._timer = None

    # ---------- public ----------

    def set_mode(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._teardown()
        self._mode = mode
        if mode == "none":
            return

        monitors = list_monitors()
        # 模糊模式：先抓取真实桌面，再铺遮罩（顺序很重要）。
        if mode == "blur":
            crops = self._grab_blurred(monitors)
            if crops is None:
                # 抓屏失败则退化为遮屏，避免无保护。
                mode = self._mode = "cover"

        for idx, (left, top, width, height) in enumerate(monitors):
            win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            win.geometry(f"{width}x{height}+{left}+{top}")
            win.attributes("-topmost", True)
            win.configure(bg="black")
            label = tk.Label(win, bg="black", bd=0, highlightthickness=0)
            label.pack(fill="both", expand=True)
            self._windows.append(win)
            self._labels.append(label)
            self._photos.append(None)
            if mode == "blur" and crops is not None and idx < len(crops):
                photo = ImageTk.PhotoImage(crops[idx])
                self._photos[idx] = photo
                label.configure(image=photo)

        if mode == "cover":
            self._set_click_through(False)
            self._paint_cover()
        else:
            self._set_click_through(True)
            if self.blur_refresh_ms > 0:
                self._schedule_refresh()

    def refresh(self) -> None:
        """重抓并更新模糊画面（仅在 blur_refresh_ms>0 时由定时器调用）。"""
        if self._mode != "blur":
            return
        crops = self._grab_blurred(list_monitors())
        if crops is None:
            return
        for idx, crop in enumerate(crops):
            if idx >= len(self._labels):
                break
            photo = ImageTk.PhotoImage(crop)
            self._photos[idx] = photo
            self._labels[idx].configure(image=photo)

    def close(self) -> None:
        self._teardown()
        self._mode = "none"

    # ---------- internals ----------

    def _grab_blurred(self, monitors):
        try:
            shot = ImageGrab.grab(all_screens=True).convert("RGB")
        except Exception:
            return None
        blurred = shot.filter(ImageFilter.GaussianBlur(self.blur_radius))
        ox, oy = self._virtual_origin()
        crops = []
        for (left, top, width, height) in monitors:
            x0, y0 = left - ox, top - oy
            crops.append(blurred.crop((x0, y0, x0 + width, y0 + height)))
        return crops

    @staticmethod
    def _virtual_origin():
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)

    def _paint_cover(self):
        for label in self._labels:
            if self.cover_text:
                label.configure(
                    text=self.cover_text,
                    fg="#888888",
                    bg="black",
                    font=("Microsoft YaHei", 20),
                )
            else:
                label.configure(bg="black")

    def _schedule_refresh(self):
        self._timer = self.root.after(self.blur_refresh_ms, self._on_tick)

    def _on_tick(self):
        if self._mode != "blur":
            return
        self.refresh()
        self._schedule_refresh()

    def _set_click_through(self, enabled: bool):
        if win32gui is None or win32con is None:
            return
        for win in self._windows:
            try:
                hwnd = win.winfo_id()
                ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                if enabled:
                    ex |= win32con.WS_EX_TRANSPARENT | win32con.WS_EX_LAYERED
                else:
                    ex &= ~win32con.WS_EX_TRANSPARENT
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex)
            except Exception:
                pass

    def _teardown(self):
        if self._timer:
            try:
                self.root.after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None
        for win in self._windows:
            try:
                win.destroy()
            except Exception:
                pass
        self._windows = []
        self._labels = []
        self._photos = []
