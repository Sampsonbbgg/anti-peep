"""多显示器视觉防护层。

- blur：触发瞬间抓取桌面 → 模糊半径由小渐增到目标（渐进模糊动画）→ 冻结显示。
  渐进式而非"淡入模糊层"，避免低透明度时透出清晰画面造成泄露。
- cover：不透明全屏遮罩。
- 解除模糊时按同样时长反向渐变回清晰。
"""
import ctypes
import time
import tkinter as tk
from typing import List, Optional

from PIL import Image, ImageFilter, ImageGrab, ImageTk

from ..core.deps import win32con, win32gui
from .monitors import list_monitors


def ease_in_out(t: float) -> float:
    """smoothstep：把 0..1 的进度映射为 0..1 的缓入缓出曲线（避免生硬起停）。"""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def blur_radius_at(target: int, progress: float) -> int:
    """动画某一进度处的模糊半径：progress=0 为清晰，=1 为达到目标强度。"""
    return int(round(float(target) * ease_in_out(progress)))


class ScreenShield:
    def __init__(self, root: tk.Tk, config: dict):
        self.root = root
        g = (config.get("privacy_guard", {}) or {}).get("shield", {}) or {}
        self.blur_radius = int(g.get("blur_radius", 10))
        self.blur_anim_ms = int(g.get("blur_anim_ms", 350))
        # 0 表示不重抓（推荐）；>0 会周期性重抓，可能造成清晰画面闪现。
        self.blur_refresh_ms = int(g.get("blur_refresh_ms", 0))
        self.cover_text = str(g.get("cover_text", ""))
        self._mode = "none"
        self._windows: List[tk.Toplevel] = []
        self._labels: List[tk.Label] = []
        self._photos: List[Optional[ImageTk.PhotoImage]] = []
        self._timer = None
        # 动画状态
        self._base_crops: List[Image.Image] = []
        self._anim_timer = None
        self._anim_start = 0.0
        self._anim_dur = 0.0
        self._anim_dir: Optional[str] = None  # "in" | "out" | None

    # ---------- public ----------

    def set_mode(self, mode: str) -> None:
        if mode == self._mode:
            return
        self._cancel_anim()
        prev = self._mode
        self._mode = mode

        if mode == "none":
            # 从模糊恢复：反向渐变回清晰后再撤除。
            if prev == "blur" and self._windows and self._base_crops:
                self._start_anim(direction="out")
                return
            self._teardown()
            return

        if mode == "cover":
            self._teardown()
            self._build_windows()
            self._set_click_through(False)
            self._paint_cover()
            return

        # mode == "blur"
        self._teardown()
        self._grab_base()
        self._build_windows()
        self._set_click_through(True)
        if self._base_crops:
            self._start_anim(direction="in")
        else:
            # 抓屏失败则退化为遮屏，避免无保护。
            self._mode = "cover"
            self._set_click_through(False)
            self._paint_cover()

    def refresh(self) -> None:
        """重抓并更新为满强度模糊画面（仅在 blur_refresh_ms>0 时由定时器调用）。"""
        if self._mode != "blur":
            return
        self._grab_base()
        self._render(self.blur_radius)

    def close(self) -> None:
        self._cancel_anim()
        self._teardown()
        self._mode = "none"

    # ---------- animation ----------

    def _start_anim(self, direction: str) -> None:
        # 反向（恢复）时重抓一份当前桌面作为清晰底图，使撤销时与实时画面无缝衔接。
        if direction == "out":
            self._grab_base()
        dur_ms = max(1, self.blur_anim_ms)
        self._anim_dur = dur_ms / 1000.0
        self._anim_start = time.monotonic()
        self._anim_dir = direction
        self._render(self._radius_for(0.0))
        self._anim_timer = self.root.after(16, self._anim_tick)

    def _radius_for(self, progress: float) -> int:
        p = ease_in_out(progress)
        if self._anim_dir == "out":
            p = 1.0 - p
        return int(round(float(self.blur_radius) * p))

    def _anim_tick(self) -> None:
        self._anim_timer = None
        if self._anim_dir is None:
            return
        progress = (time.monotonic() - self._anim_start) / self._anim_dur
        if progress >= 1.0:
            self._render(self._radius_for(1.0))
            self._finish_anim()
            return
        self._render(self._radius_for(progress))
        self._anim_timer = self.root.after(16, self._anim_tick)

    def _finish_anim(self) -> None:
        direction = self._anim_dir
        self._anim_dir = None
        if direction == "out":
            self._teardown()
            return
        # direction == "in"：冻结在满强度
        if self.blur_refresh_ms > 0:
            self._schedule_refresh()

    def _cancel_anim(self) -> None:
        if self._anim_timer:
            try:
                self.root.after_cancel(self._anim_timer)
            except Exception:
                pass
            self._anim_timer = None
        self._anim_dir = None

    # ---------- internals ----------

    def _grab_base(self) -> None:
        """抓取一次桌面并按显示器切成清晰底图（动画时逐帧施加模糊）。"""
        self._base_crops = []
        try:
            shot = ImageGrab.grab(all_screens=True).convert("RGB")
        except Exception:
            return
        ox, oy = self._virtual_origin()
        for (left, top, width, height) in list_monitors():
            x0, y0 = left - ox, top - oy
            self._base_crops.append(shot.crop((x0, y0, x0 + width, y0 + height)))

    def _build_windows(self) -> None:
        for (left, top, width, height) in list_monitors():
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

    def _render(self, radius: int) -> None:
        """按给定半径渲染所有显示器：radius<=0 用清晰底图，否则高斯模糊。"""
        for idx, label in enumerate(self._labels):
            if idx >= len(self._base_crops):
                break
            base = self._base_crops[idx]
            img = base.filter(ImageFilter.GaussianBlur(radius)) if radius > 0 else base
            photo = ImageTk.PhotoImage(img)
            self._photos[idx] = photo
            label.configure(image=photo)

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
        self._cancel_anim()
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
        self._base_crops = []
