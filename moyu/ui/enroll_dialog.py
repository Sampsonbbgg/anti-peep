# -*- coding: utf-8 -*-
"""主人人脸录入对话框：采集多张样本写入主人特征库。"""

import tkinter as tk
from typing import Optional

from moyu.core.deps import cv2, Image, ImageTk
from moyu.core.face_engine import FaceEngine, LABEL_OWNER
from moyu.core.owner_store import OwnerStore


class Theme:
    BG_DARK = "#1a1a2e"
    BG_CARD = "#16213e"
    BG_INPUT = "#0f3460"
    PRIMARY = "#4a90d9"
    ACCENT = "#00d4aa"
    TEXT = "#e8e8e8"
    TEXT_SECONDARY = "#888888"
    BORDER = "#2a4a7a"
    ERROR = "#e74c3c"


class EnrollDialog:
    """打开摄像头，采集 samples 张主人人脸特征并保存。"""

    def __init__(
        self,
        parent: tk.Tk,
        engine: FaceEngine,
        owner_store: OwnerStore,
        samples: int = 9,
        camera_index: int = 0,
    ):
        self.engine = engine
        self.owner_store = owner_store
        self.samples = max(1, int(samples))
        self.camera_index = int(camera_index)
        self.captured = 0
        self.saved = False
        self._cap = None
        self._running = False
        self._photo = None
        self._last_feature_sim = 0.0

        self.root = tk.Toplevel(parent)
        self.root.title("录入主人人脸")
        self.root.configure(bg=Theme.BG_DARK)
        self.root.resizable(False, False)
        self.root.geometry("420x420")
        self.root.transient(parent)
        self._build_ui()

    def _build_ui(self):
        tk.Label(
            self.root, text="录入主人人脸", font=("Microsoft YaHei", 15, "bold"),
            fg=Theme.TEXT, bg=Theme.BG_DARK,
        ).pack(pady=(14, 4))
        tk.Label(
            self.root,
            text="正对摄像头，按提示缓慢左右转头，采集过程中保持画面中只有你一人。",
            font=("Microsoft YaHei", 9), fg=Theme.TEXT_SECONDARY, bg=Theme.BG_DARK,
            wraplength=380, justify="center",
        ).pack()

        self.video_label = tk.Label(self.root, bg="black", width=360, height=240)
        self.video_label.pack(pady=10)

        self.status_label = tk.Label(
            self.root, text="点击「开始录入」", font=("Microsoft YaHei", 10),
            fg=Theme.TEXT, bg=Theme.BG_DARK,
        )
        self.status_label.pack()

        btn_row = tk.Frame(self.root, bg=Theme.BG_DARK)
        btn_row.pack(pady=12)
        self.start_btn = tk.Button(
            btn_row, text="开始录入", font=("Microsoft YaHei", 10, "bold"),
            bg=Theme.ACCENT, fg="white", relief="flat", cursor="hand2",
            command=self._start, ipadx=16, ipady=5,
        )
        self.start_btn.pack(side="left", padx=6)
        tk.Button(
            btn_row, text="取消", font=("Microsoft YaHei", 10),
            bg=Theme.BG_CARD, fg=Theme.TEXT_SECONDARY, relief="flat", cursor="hand2",
            command=self._cancel, ipadx=16, ipady=5,
        ).pack(side="left", padx=6)
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)

    # ---------- 录入流程 ----------

    def _start(self):
        if self._running:
            return
        self._running = True
        self.start_btn.configure(state="disabled")
        self.owner_store.clear()
        self._cap = cv2.VideoCapture(self.camera_index)
        if not self._cap.isOpened():
            self.status_label.configure(text="无法打开摄像头，请检查设备。", fg=Theme.ERROR)
            self._running = False
            self.start_btn.configure(state="normal")
            return
        self.root.after(100, self._loop)

    def _loop(self):
        if not self._running or self._cap is None:
            return
        ok, frame = self._cap.read()
        if not ok:
            self.root.after(60, self._loop)
            return
        frame = cv2.flip(frame, 1)
        rows = self.engine.detect(frame)
        faces = list(rows) if rows is not None else []

        # 预览
        if cv2 is not None and Image is not None:
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w = rgb.shape[:2]
                scale = min(360 / w, 240 / h)
                nw, nh = max(int(w * scale), 1), max(int(h * scale), 1)
                resized = cv2.resize(rgb, (nw, nh))
                img = Image.fromarray(resized)
                self._photo = ImageTk.PhotoImage(img)
                self.video_label.configure(image=self._photo)
            except Exception:
                pass

        if len(faces) == 1:
            row = max(faces, key=lambda r: float(r[2]) * float(r[3]))
            try:
                emb = self.engine.feature(frame, row)
                self.owner_store.add(emb)
                self.captured += 1
                self.status_label.configure(
                    text=f"采集中… 已采集 {self.captured}/{self.samples} 张",
                    fg=Theme.TEXT,
                )
            except Exception:
                pass
        elif len(faces) == 0:
            self.status_label.configure(text="未检测到人脸，请正对摄像头。", fg=Theme.TEXT_SECONDARY)
        else:
            self.status_label.configure(text="画面中有多人，请确保只有你一人。", fg=Theme.ERROR)

        if self.captured >= self.samples:
            self._finish()
            return
        self.root.after(200, self._loop)

    def _release_camera(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _finish(self):
        self._release_camera()
        self._running = False
        try:
            self.owner_store.save()
            self.saved = True
            self.status_label.configure(text="录入完成，已保存主人人脸。", fg=Theme.ACCENT)
            self.root.after(800, self.root.destroy)
        except Exception as e:
            self.status_label.configure(text=f"保存失败：{e}", fg=Theme.ERROR)

    def _cancel(self):
        self._running = False
        self._release_camera()
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self) -> bool:
        self.root.grab_set()
        self.root.wait_window()
        return self.saved
