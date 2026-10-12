import time
import os
import sys as _sys
from typing import Optional

# Windows 任务栏图标修复：设置 AppUserModelID 让 Windows 识别这是独立应用
if _sys.platform.startswith('win'):
    try:
        import ctypes
        # 设置应用 ID，让 Windows 任务栏正确显示图标而不是 Python 图标
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('anti_peep.app.v1')
    except Exception:
        pass

from anti_peep.core.constants import APP_NAME
from anti_peep.core.config_store import save_user_config
from anti_peep.core.deps import sys, tk, Image, ImageTk, cv2
from anti_peep.core.analysis_worker import FaceAnalysisWorker
from anti_peep.core.paths import get_asset_path
from anti_peep.services.snapshot import save_snapshot
from anti_peep.services.lock_screen_capture import LockScreenCaptureService
from .tray import get_tray_manager
from anti_peep.services.work_app import switch_to_work_app
from anti_peep.services.esc_dismiss import next_override, effective_mode
from .settings_dialog import SettingsDialog
from .dpi_utils import enable_dpi_awareness, enable_dark_title_bar


class CameraPreviewApp:
    """
    带摄像头预览的小窗口：
      - 窗口在屏幕上可自由拖动、缩放（默认 100x100，黑色背景）
      - 实时显示摄像头画面（镜像）和可选调试框
      - 通过独立的人脸检测线程读取 is_face_present 状态：
        - 从"无人"→"有人"时：显示提示文字 + 抓拍 + 切换到工作应用 + 托盘气泡
    """

    def __init__(self, config: dict):
        if tk is None:
            raise RuntimeError("当前环境不支持 tkinter。")
        if Image is None or ImageTk is None:
            raise RuntimeError(
                "当前环境未安装 Pillow。请先运行 pip install -r requirements.txt"
            )

        # 启用高 DPI 感知
        enable_dpi_awareness()

        self.config = config
        ui_cfg = config.get("ui", {})

        # 提示文字内容与显示时长
        self.message_text = ui_cfg.get("message", "有人在看屏幕，请注意隐私。")
        self.display_ms = int(ui_cfg.get("display_milliseconds", 3000))

        # 冷却时间：避免频繁切换应用
        self.cooldown_seconds = float(config.get("alert_cooldown_seconds", 15))
        self._last_action_time = 0.0
        self._prev_is_face_present = False

        TrayManager = get_tray_manager()
        self.enable_tray = (
            bool(ui_cfg.get("enable_system_tray", True))
            and TrayManager is not None
        )
        self.minimize_to_tray = bool(ui_cfg.get("minimize_to_tray", True))
        self.start_minimized = bool(ui_cfg.get("start_minimized", False))
        tray_seconds = int(ui_cfg.get("tray_notification_seconds", 8))
        self.tray_notification_seconds = max(5, min(tray_seconds, 10))
        self.tray: Optional[TrayManager] = None  # type: ignore[assignment]
        self._hidden_to_tray = False
        self._tray_hint_shown = False
        self._config_path = None  # 用户配置文件路径

        # 定义主题颜色
        self.theme_bg = "#1a1a2e"
        self.theme_card = "#16213e"
        self.theme_accent = "#4a90d9"
        self.theme_text = "#e8e8e8"

        # 初始化 Tk 小窗口
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} - 预览")
        self.root.attributes("-topmost", True)
        self.root.resizable(True, True)  # 允许水平和垂直调整大小
        self.root.geometry("300x130")  # 加宽预览窗口
        self.root.configure(bg=self.theme_bg)
        
        # 设置窗口图标（修复任务栏显示 Python 图标的问题）
        icon_path = get_asset_path("anti-peep.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass  # 忽略图标加载失败

        # 顶部工具栏
        toolbar = tk.Frame(self.root, bg=self.theme_card, height=24)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        # 状态指示器
        self.status_label = tk.Label(
            toolbar,
            text="● 运行中",
            font=("Microsoft YaHei", 8),
            fg="#00d4aa",
            bg=self.theme_card,
        )
        self.status_label.pack(side="left", padx=6)

        # 设置按钮
        settings_btn = tk.Button(
            toolbar,
            text="⚙",
            font=("Segoe UI Symbol", 10),
            fg=self.theme_text,
            bg=self.theme_card,
            relief="flat",
            cursor="hand2",
            command=self._open_settings,
        )
        settings_btn.pack(side="right", padx=4)

        # 视频显示区域
        self.video_label = tk.Label(self.root, bg=self.theme_bg)
        self.video_label.pack(fill="both", expand=True)

        # 左上角小号提示文字
        self.text_label = tk.Label(
            self.root,
            text="",
            bg=self.theme_bg,
            fg="#CCCCCC",
            font=("Microsoft YaHei", 8),
            anchor="w",
        )
        self.text_label.place(x=6, y=28)
        self.text_visible = False

        # 启用暗色标题栏
        enable_dark_title_bar(self.root)

        self._photo = None

        # 身份识别 + 视觉防护
        self._init_privacy(config)

        # 启动人脸分析线程
        self.detector = FaceAnalysisWorker(config, self.face_engine)
        self.detector.start()
        self.lock_screen_capture = LockScreenCaptureService(config)

        if self.enable_tray:
            self.tray = TrayManager(
                APP_NAME,
                on_restore=lambda: self.root.after(0, self._restore_from_tray),
                on_exit=lambda: self.root.after(
                    0, lambda: self._on_close(force_exit=True)
                ),
                on_settings=lambda: self.root.after(0, self._open_settings),
            )
            try:
                self.tray.start()
            except Exception:
                self.tray = None
                self.enable_tray = False

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Unmap>", self._on_window_state_change)
        self.root.after(0, self._update_frame)
        if self.enable_tray and self.start_minimized:
            self.root.after(150, self._hide_to_tray)

    # ---------- 身份识别与防护 ----------

    def _init_privacy(self, config):
        """构建主人特征库、人脸引擎、防护状态机与遮罩层。"""
        from anti_peep.core.face_engine import FaceEngine
        from anti_peep.core.owner_store import OwnerStore
        from anti_peep.core.paths import get_models_dir, get_owner_file_path
        from anti_peep.services.privacy_guard import PrivacyGuard
        from anti_peep.services.screen_shield import ScreenShield
        from anti_peep.platforms.windows_session import WindowsSessionState
        from anti_peep.services.hotkey import GlobalHotkey, EscListener

        identity_cfg = config.get("identity", {})
        self.owner_store = OwnerStore(
            get_owner_file_path(),
            threshold=float(identity_cfg.get("match_threshold", 0.363)),
        )
        self.owner_store.load()
        self.face_engine = FaceEngine(get_models_dir(), self.owner_store)
        self.identity_enabled = bool(identity_cfg.get("enabled", True))
        try:
            self.face_engine.load()
        except Exception as e:
            print(f"人脸模型加载失败，降级为仅多人检测：{e}")
            self.identity_enabled = False
        if not self.identity_enabled:
            self.owner_store.clear()

        pg_cfg = config.get("privacy_guard", {})
        self.guard = PrivacyGuard(
            config,
            owner_enrolled=self.identity_enabled and not self.owner_store.is_empty,
        )
        self.shield = ScreenShield(self.root, config)
        self.session_state = WindowsSessionState()
        self._snapshot_cooldown = float(
            pg_cfg.get("snapshot", {}).get("cooldown_seconds", 15)
        )
        self._last_snapshot_time = 0.0
        self._prev_shield_mode = "none"
        self.paused = False
        # Esc 退出：覆盖生效时强制清晰，待场景回到安全后自动重新武装
        self._esc_override = False
        self.legacy_switch_work_app = bool(
            pg_cfg.get("legacy_switch_work_app", False)
        )

        # 全局热键 Ctrl+Alt+P：紧急暂停/恢复防护
        self._hotkey = GlobalHotkey(
            lambda: self.root.after(0, self._toggle_pause)
        )
        try:
            self._hotkey.start()
        except Exception:
            self._hotkey = None

        # 全局 Esc：仅在防护层（模糊/遮屏）显示期间接管，用于立即退出
        self._esc_hotkey = EscListener(
            lambda: self.root.after(0, self._on_esc_dismiss)
        )
        try:
            self._esc_hotkey.start()
        except Exception:
            self._esc_hotkey = None

    def _set_esc_active(self, active: bool) -> None:
        if self._esc_hotkey is None:
            return
        try:
            self._esc_hotkey.set_enabled(active)
        except Exception:
            pass

    def _on_esc_dismiss(self):
        """Esc 按下：撤除当前模糊/遮屏，并在本触发条件结束前不再弹出。"""
        mode = getattr(self.shield, "_mode", "none")
        if mode not in ("blur", "cover"):
            return
        self._esc_override = True
        self.shield.set_mode("none")
        self._set_esc_active(False)
        self._prev_shield_mode = "none"
        self._update_message_visibility()
        print("[Anti-Peep] 已按 Esc 退出防护层")
        if self.tray:
            self.tray.show_notification(
                APP_NAME, "已按 Esc 退出模糊/遮屏", self.tray_notification_seconds
            )


    def _toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self._esc_override = False
            self._set_esc_active(False)
            self.shield.set_mode("none")
        state = "已暂停防护" if self.paused else "已恢复防护"
        print(f"[Anti-Peep] {state}（Ctrl+Alt+P）")
        if self.tray:
            self.tray.show_notification(APP_NAME, state, self.tray_notification_seconds)

    # ---------- Tk 回调 ----------

    def _on_close(self, force_exit: bool = False):
        """关闭窗口时最小化到托盘或退出程序。"""
        if self.enable_tray and self.minimize_to_tray and not force_exit:
            self._hide_to_tray()
            return
        self._shutdown()

    def _on_window_state_change(self, event):
        if (
            event.widget == self.root
            and self.enable_tray
            and self.minimize_to_tray
            and not self._hidden_to_tray
            and str(self.root.state()) == "iconic"
        ):
            self._hide_to_tray()

    def _hide_to_tray(self):
        self._hidden_to_tray = True
        self.root.withdraw()
        if self.tray and not self._tray_hint_shown:
            # self.tray.show_notification(
            #     APP_NAME,
            #     "Anti-Peep 已最小化到托盘，双击图标可恢复。",
            #     self.tray_notification_seconds,
            # )
            self._tray_hint_shown = True

    def _restore_from_tray(self):
        self._hidden_to_tray = False
        self.root.deiconify()
        try:
            self.root.state("normal")
        except Exception:
            pass
        self.root.lift()
        try:
            self.root.focus_force()
        except Exception:
            pass

    def _shutdown(self):
        try:
            if self.detector:
                self.detector.stop()
        except Exception:
            pass
        try:
            if getattr(self, "shield", None):
                self.shield.close()
        except Exception:
            pass
        try:
            if getattr(self, "_hotkey", None):
                self._hotkey.stop()
        except Exception:
            pass
        try:
            if getattr(self, "_esc_hotkey", None):
                self._esc_hotkey.stop()
        except Exception:
            pass
        if self.tray:
            self.tray.stop()
            self.tray = None
        self.root.destroy()

    def _open_settings(self):
        """打开设置对话框"""
        import os
        # 隐藏预览窗口
        self.root.withdraw()

        def on_save(new_config):
            # 保存配置到用户配置文件
            save_user_config(new_config, self._config_path)
            
            # 立即应用新配置（不需要重启）
            self.config.update(new_config)
            self.lock_screen_capture.update_config(self.config)
            # 更新消息显示配置
            ui_cfg = new_config.get("ui", {})
            self.message_text = ui_cfg.get("message", self.message_text)

        def on_enrolled():
            # 录入主人人脸后立即重载特征库，使视线/陌生人判定即时生效。
            try:
                self.owner_store.load()
                self.guard.owner_enrolled = (
                    self.identity_enabled and not self.owner_store.is_empty
                )
            except Exception:
                pass

        try:
            # 传递 self.root 作为父窗口，避免创建多个 Tk() 实例导致卡死
            dialog = SettingsDialog(
                self.config,
                on_save=on_save,
                on_enrolled=on_enrolled,
                frame_provider=lambda: (
                    self.detector.get_latest()[0] if self.detector else None
                ),
                parent=self.root,
            )
            dialog.run()
        finally:
            # 恢复预览窗口
            self.root.deiconify()
            self.root.lift()

    def _show_message(self):
        """在左上角显示提示文字。"""
        self.text_label.config(text=self.message_text)
        self.text_visible = True
        self._message_hide_at = time.time() + self.display_ms / 1000.0

    def _update_message_visibility(self):
        """根据时间自动隐藏提示文字。"""
        if not self.text_visible:
            return
        if time.time() >= getattr(self, "_message_hide_at", 0):
            self.text_label.config(text="")
            self.text_visible = False

    def _handle_alert(self, frame_bgr):
        """统一处理报警后的动作：提示、抓拍、切换应用、托盘提醒。"""
        self._show_message()
        save_snapshot(self.config, frame_bgr)
        switch_to_work_app(self.config)
        if self.tray:
            self.tray.show_notification(
                APP_NAME,
                self.message_text,
                self.tray_notification_seconds,
            )

    # ---------- 主 UI 循环 ----------

    def _update_frame(self):
        """从分析线程读取最新结果并驱动视觉防护。"""
        frame_bgr, analysis = self.detector.get_latest()

        if frame_bgr is not None and cv2 is not None:
            draw = frame_bgr.copy()
            for (x, y, bw, bh, score, label, sim) in analysis.faces:
                color = (0, 200, 0) if label == "owner" else (0, 0, 255)
                cv2.rectangle(draw, (x, y), (x + bw, y + bh), color, 1)
            frame_rgb = cv2.cvtColor(draw, cv2.COLOR_BGR2RGB)
            h, w = frame_rgb.shape[:2]

            label_width = max(self.video_label.winfo_width(), 1)
            label_height = max(self.video_label.winfo_height(), 1)

            scale = min(label_width / w, label_height / h)
            new_w = max(int(w * scale), 1)
            new_h = max(int(h * scale), 1)

            frame_resized = cv2.resize(frame_rgb, (new_w, new_h))

            from PIL import Image as PILImage  # type: ignore

            canvas = PILImage.new("RGB", (label_width, label_height), (0, 0, 0))
            x_offset = (label_width - new_w) // 2
            y_offset = (label_height - new_h) // 2
            canvas.paste(PILImage.fromarray(frame_resized), (x_offset, y_offset))

            self._photo = ImageTk.PhotoImage(image=canvas)
            self.video_label.config(image=self._photo)

        now = time.time()
        lock_face_present = bool(getattr(analysis, "face_count", 0) > 0)
        self.lock_screen_capture.process(frame_bgr, lock_face_present)

        if self.paused:
            self.shield.set_mode("none")
            decision_mode = "none"
        else:
            decision = self.guard.update(analysis, now, self.session_state.is_locked())
            # Esc 覆盖：撤除后保持清晰，直到决策自然回到 none 再重新武装
            if self._esc_override:
                self._esc_override = next_override(True, decision.mode)
            decision_mode = effective_mode(decision.mode, self._esc_override)
            self.shield.set_mode(decision_mode)
            if decision_mode in ("blur", "cover") and decision_mode != self._prev_shield_mode:
                if now - self._last_snapshot_time >= self._snapshot_cooldown:
                    self._last_snapshot_time = now
                    try:
                        save_snapshot(
                            self.config, frame_bgr,
                            filename_prefix=f"shield_{decision.reason}",
                        )
                    except Exception:
                        pass
            if self.legacy_switch_work_app and analysis.face_count >= 2:
                if now - self._last_action_time >= self.cooldown_seconds:
                    self._last_action_time = now
                    self._handle_alert(frame_bgr)

        # 仅在防护层显示期间接管 Esc，平时不干扰其它程序
        self._set_esc_active(decision_mode in ("blur", "cover"))
        self._prev_shield_mode = decision_mode
        self._update_message_visibility()
        self.root.after(30, self._update_frame)

    def run(self):
        """进入 Tk 主循环。"""
        try:
            # 确保窗口完全渲染后再设置暗色标题栏
            self.root.update_idletasks()
            enable_dark_title_bar(self.root)
            self.root.mainloop()
        finally:
            try:
                if self.detector:
                    self.detector.stop()
            except Exception:
                pass
            try:
                if self.tray:
                    self.tray.stop()
            except Exception:
                pass
