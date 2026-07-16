# -*- coding: utf-8 -*-
"""
设置对话框 - 运行时修改配置的图形界面。
"""

import os
import copy
from typing import Callable, Optional, Dict, Any

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    tk = None
    ttk = None
    filedialog = None
    messagebox = None

# 导入 DPI 工具
from .dpi_utils import enable_dpi_awareness, enable_dark_title_bar, scaled_size, extract_app_name


# 复用主题配色
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
    SUCCESS = "#2ecc71"
    TAB_ACTIVE = "#1e3a5f"
    TAB_INACTIVE = "#16213e"


class SettingsDialog:
    """设置对话框"""

    def __init__(
        self,
        config: Dict[str, Any],
        on_save: Optional[Callable[[Dict[str, Any]], None]] = None,
        parent: Optional[tk.Tk] = None
    ):
        if tk is None:
            raise RuntimeError("tkinter 不可用")

        # 启用高 DPI 感知
        enable_dpi_awareness()

        self.config = copy.deepcopy(config)
        self.on_save = on_save
        self.saved = False

        # 预先从配置读取所有值，避免未访问标签页时出错
        work_cfg = self.config.get("work_app", {})
        self.current_active = work_cfg.get("active", "")
        self.work_targets = dict(work_cfg.get("targets", {}))
        
        snapshot_cfg = self.config.get("snapshot", {})
        self._snapshot_enabled = snapshot_cfg.get("enabled", True)
        self._snapshot_directory = snapshot_cfg.get("directory", "")

        lock_cfg = self.config.get("lock_screen", {})
        self._lock_screen_enabled = lock_cfg.get("enabled", True)
        self._lock_screen_directory = lock_cfg.get("directory", "lock_screen_people")
        self._lock_screen_min_faces = lock_cfg.get("min_faces", 1)
        self._lock_screen_cooldown = lock_cfg.get("cooldown_seconds", 10)
        
        camera_cfg = self.config.get("camera", {})
        self._camera_index = self.config.get("camera_index", 0)
        self._min_faces = self.config.get("min_faces_for_alert", 2)
        self._cooldown = self.config.get("alert_cooldown_seconds", 15)
        self._debug_draw = camera_cfg.get("debug_draw", False)
        
        ui_cfg = self.config.get("ui", {})
        self._message = ui_cfg.get("message", "")
        self._enable_tray = ui_cfg.get("enable_system_tray", True)
        self._minimize_to_tray = ui_cfg.get("minimize_to_tray", True)
        self._start_minimized = ui_cfg.get("start_minimized", False)

        # 创建窗口
        if parent:
            self.root = tk.Toplevel(parent)
        else:
            self.root = tk.Tk()

        self._setup_ui()

    def _setup_ui(self):
        """构建设置 UI"""
        self.root.title("设置")
        self.root.configure(bg=Theme.BG_DARK)
        self.root.resizable(False, False)
        
        # 设置窗口图标
        from moyu.core.paths import get_asset_path
        icon_path = get_asset_path("moyu.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass
        
        # 先更新一次以获取正确的 DPI
        self.root.update_idletasks()
        
        # 基础尺寸 (100% DPI 下的尺寸)
        base_width = 500
        base_height = 700
        
        # 根据 DPI 缩放窗口大小
        window_width, window_height = scaled_size(base_width, base_height, self.root)

        # 居中显示
        x = (self.root.winfo_screenwidth() - window_width) // 2
        y = (self.root.winfo_screenheight() - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # 启用暗色标题栏
        enable_dark_title_bar(self.root)

        # 主容器
        main_frame = tk.Frame(self.root, bg=Theme.BG_DARK)
        main_frame.pack(fill="both", expand=True, padx=20, pady=15)

        # 标题
        title_frame = tk.Frame(main_frame, bg=Theme.BG_DARK)
        title_frame.pack(fill="x", pady=(0, 15))

        tk.Label(
            title_frame,
            text="⚙️ 设置",
            font=("Microsoft YaHei", 16, "bold"),
            fg=Theme.TEXT,
            bg=Theme.BG_DARK
        ).pack(side="left")

        # 标签页容器
        self.tab_frame = tk.Frame(main_frame, bg=Theme.BG_DARK)
        self.tab_frame.pack(fill="x")

        self.content_frame = tk.Frame(main_frame, bg=Theme.BG_CARD, highlightbackground=Theme.BORDER, highlightthickness=1)
        self.content_frame.pack(fill="both", expand=True, pady=(0, 15))

        # 创建标签页
        self.tabs = {}
        self.current_tab = None
        self._create_tabs()

        # 按钮区域
        self._create_buttons(main_frame)

        # 显示第一个标签页
        self._show_tab("work_app")

    def _create_tab_button(self, parent, tab_id: str, text: str):
        """创建标签页按钮"""
        btn = tk.Button(
            parent,
            text=text,
            font=("Microsoft YaHei", 10),
            bg=Theme.TAB_INACTIVE,
            fg=Theme.TEXT_SECONDARY,
            relief="flat",
            cursor="hand2",
            command=lambda: self._show_tab(tab_id)
        )
        btn.pack(side="left", ipadx=15, ipady=6)
        self.tabs[tab_id] = {"button": btn, "frame": None}
        return btn

    def _create_tabs(self):
        """创建所有标签页"""
        self._create_tab_button(self.tab_frame, "work_app", "📁 工作应用")
        self._create_tab_button(self.tab_frame, "snapshot", "📷 截图")
        self._create_tab_button(self.tab_frame, "camera", "🎥 摄像头")
        self._create_tab_button(self.tab_frame, "ui", "🎨 界面")

    def _show_tab(self, tab_id: str):
        """显示指定标签页"""
        # 更新按钮状态
        for tid, tab in self.tabs.items():
            if tid == tab_id:
                tab["button"].configure(bg=Theme.TAB_ACTIVE, fg=Theme.TEXT)
            else:
                tab["button"].configure(bg=Theme.TAB_INACTIVE, fg=Theme.TEXT_SECONDARY)

        # 在切换标签页前，保存当前标签页的值到实例变量
        self._save_current_tab_values()

        # 清空内容区域
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        # 显示对应内容
        self.current_tab = tab_id
        if tab_id == "work_app":
            self._create_work_app_content()
        elif tab_id == "snapshot":
            self._create_snapshot_content()
        elif tab_id == "camera":
            self._create_camera_content()
        elif tab_id == "ui":
            self._create_ui_content()

    def _create_section_title(self, parent, text: str):
        """创建区块标题"""
        tk.Label(
            parent,
            text=text,
            font=("Microsoft YaHei", 11, "bold"),
            fg=Theme.PRIMARY,
            bg=Theme.BG_CARD
        ).pack(anchor="w", pady=(0, 10))

    def _create_input_row(self, parent, label: str, var, browse_command=None):
        """创建输入行"""
        row = tk.Frame(parent, bg=Theme.BG_CARD)
        row.pack(fill="x", pady=5)

        tk.Label(
            row,
            text=label,
            font=("Microsoft YaHei", 10),
            fg=Theme.TEXT,
            bg=Theme.BG_CARD,
            width=12,
            anchor="w"
        ).pack(side="left")

        entry = tk.Entry(
            row,
            textvariable=var,
            font=("Consolas", 10),
            bg=Theme.BG_INPUT,
            fg=Theme.TEXT,
            insertbackground=Theme.TEXT,
            relief="flat",
            highlightbackground=Theme.BORDER,
            highlightthickness=1
        )
        entry.pack(side="left", fill="x", expand=True, ipady=5)
        
        # 强制设置初始值（修复 tkinter StringVar 在某些情况下不显示的问题）
        initial_value = var.get()
        if initial_value:
            entry.delete(0, tk.END)
            entry.insert(0, initial_value)

        if browse_command:
            btn = tk.Button(
                row,
                text="...",
                font=("Microsoft YaHei", 9),
                bg=Theme.PRIMARY,
                fg="white",
                relief="flat",
                cursor="hand2",
                command=browse_command
            )
            btn.pack(side="left", padx=(8, 0), ipadx=8, ipady=2)

        return entry

    def _create_checkbox_row(self, parent, label: str, var):
        """创建复选框行"""
        row = tk.Frame(parent, bg=Theme.BG_CARD)
        row.pack(fill="x", pady=5)

        cb = tk.Checkbutton(
            row,
            text=label,
            variable=var,
            font=("Microsoft YaHei", 10),
            fg=Theme.TEXT,
            bg=Theme.BG_CARD,
            selectcolor=Theme.BG_INPUT,
            activebackground=Theme.BG_CARD,
            activeforeground=Theme.TEXT
        )
        cb.pack(anchor="w")
        return cb

    def _save_current_tab_values(self):
        """保存当前标签页的值到实例变量"""
        if not self.current_tab:
            return

        try:
            if self.current_tab == "snapshot":
                # 保存启用状态
                if hasattr(self, 'snapshot_enabled_var'):
                    try:
                        self._snapshot_enabled = self.snapshot_enabled_var.get()
                    except tk.TclError:
                        pass
                
                # 保存目录：优先从 Entry 获取
                if hasattr(self, 'snapshot_path_entry'):
                    try:
                        if self.snapshot_path_entry.winfo_exists():
                            self._snapshot_directory = self.snapshot_path_entry.get()
                    except tk.TclError:
                        pass

                if hasattr(self, 'lock_screen_enabled_var'):
                    try:
                        self._lock_screen_enabled = self.lock_screen_enabled_var.get()
                    except tk.TclError:
                        pass

                if hasattr(self, 'lock_screen_path_entry'):
                    try:
                        if self.lock_screen_path_entry.winfo_exists():
                            self._lock_screen_directory = self.lock_screen_path_entry.get()
                    except tk.TclError:
                        pass

                if hasattr(self, 'lock_screen_min_faces_entry'):
                    try:
                        if self.lock_screen_min_faces_entry.winfo_exists():
                            self._lock_screen_min_faces = int(self.lock_screen_min_faces_entry.get())
                    except (tk.TclError, ValueError):
                        pass

                if hasattr(self, 'lock_screen_cooldown_entry'):
                    try:
                        if self.lock_screen_cooldown_entry.winfo_exists():
                            self._lock_screen_cooldown = int(self.lock_screen_cooldown_entry.get())
                    except (tk.TclError, ValueError):
                        pass
                     
            elif self.current_tab == "camera":
                # 保存摄像头索引
                if hasattr(self, 'camera_index_entry'):
                    try:
                        if self.camera_index_entry.winfo_exists():
                            self._camera_index = int(self.camera_index_entry.get())
                    except (tk.TclError, ValueError):
                        pass
                
                # 保存最小人脸数
                if hasattr(self, 'min_faces_entry'):
                    try:
                        if self.min_faces_entry.winfo_exists():
                            self._min_faces = int(self.min_faces_entry.get())
                    except (tk.TclError, ValueError):
                        pass
                
                # 保存冷却时间
                if hasattr(self, 'cooldown_entry'):
                    try:
                        if self.cooldown_entry.winfo_exists():
                            self._cooldown = int(self.cooldown_entry.get())
                    except (tk.TclError, ValueError):
                        pass
                
                # 保存调试模式
                if hasattr(self, 'debug_draw_var'):
                    try:
                        self._debug_draw = self.debug_draw_var.get()
                    except tk.TclError:
                        pass

            elif self.current_tab == "ui":
                # 保存提示信息
                if hasattr(self, 'message_entry'):
                    try:
                        if self.message_entry.winfo_exists():
                            self._message = self.message_entry.get()
                    except tk.TclError:
                        pass

                # 保存托盘设置
                if hasattr(self, 'enable_tray_var'):
                    try:
                        self._enable_tray = self.enable_tray_var.get()
                    except tk.TclError:
                        pass
                if hasattr(self, 'minimize_to_tray_var'):
                    try:
                        self._minimize_to_tray = self.minimize_to_tray_var.get()
                    except tk.TclError:
                        pass
                if hasattr(self, 'start_minimized_var'):
                    try:
                        self._start_minimized = self.start_minimized_var.get()
                    except tk.TclError:
                        pass
        except Exception:
            # 忽略任何异常，保持已有的值
            pass

    def _create_work_app_content(self):
        """工作应用配置内容"""
        content = tk.Frame(self.content_frame, bg=Theme.BG_CARD)
        content.pack(fill="both", expand=True, padx=20, pady=15)

        self._create_section_title(content, "工作应用管理")

        # 使用 __init__ 中已读取的实例变量，避免覆盖用户的更改

        # 现有应用列表
        list_frame = tk.Frame(content, bg=Theme.BG_CARD)
        list_frame.pack(fill="x", pady=5)

        tk.Label(
            list_frame,
            text="已配置的应用：",
            font=("Microsoft YaHei", 10),
            fg=Theme.TEXT,
            bg=Theme.BG_CARD
        ).pack(anchor="w")

        # 应用选择下拉框
        select_frame = tk.Frame(content, bg=Theme.BG_CARD)
        select_frame.pack(fill="x", pady=5)

        self.selected_app_var = tk.StringVar(value=self.current_active)
        
        # 获取应用显示名称列表
        app_display_names = []
        self.app_key_map = {}  # 显示名 -> key
        for key, cfg in self.work_targets.items():
            display = cfg.get("display_name", key)
            app_display_names.append(display)
            self.app_key_map[display] = key
        
        if not app_display_names:
            app_display_names = ["(无)"]

        # 当前激活的显示名
        current_target = self.work_targets.get(self.current_active, {})
        current_display = current_target.get("display_name", self.current_active)
        
        self.selected_display_var = tk.StringVar(value=current_display)

        self.app_combo = ttk.Combobox(
            select_frame,
            textvariable=self.selected_display_var,
            values=app_display_names,
            state="readonly",
            width=25
        )
        self.app_combo.pack(side="left")
        
        # 确保 combobox 选中正确的值
        if current_display in app_display_names:
            self.app_combo.set(current_display)
        elif app_display_names and app_display_names[0] != "(无)":
            self.app_combo.set(app_display_names[0])
            self.selected_display_var.set(app_display_names[0])
        
        self.app_combo.bind("<<ComboboxSelected>>", self._on_app_selected)

        # 设为当前按钮
        set_active_btn = tk.Button(
            select_frame,
            text="✓ 设为当前",
            font=("Microsoft YaHei", 9),
            bg=Theme.ACCENT,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._set_as_active
        )
        set_active_btn.pack(side="left", padx=(10, 0), ipadx=8, ipady=2)

        # 删除按钮
        del_btn = tk.Button(
            select_frame,
            text="🗑 删除",
            font=("Microsoft YaHei", 9),
            bg=Theme.ERROR,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._delete_app
        )
        del_btn.pack(side="left", padx=(5, 0), ipadx=8, ipady=2)

        # 分隔线
        tk.Frame(content, bg=Theme.BORDER, height=1).pack(fill="x", pady=15)

        # 添加/编辑应用区域
        self._create_section_title(content, "添加新应用")

        # 获取当前激活应用的配置用于初始化表单
        current_target = self.work_targets.get(self.current_active, {})
        current_display_name = current_target.get("display_name", self.current_active)
        current_path = current_target.get("windows_command", "")
        current_keywords = current_target.get("window_keywords", [])
        
        # 应用名称
        self.app_display_name_var = tk.StringVar(value=current_display_name)
        self.app_display_name_entry = self._create_input_row(content, "应用名称：", self.app_display_name_var)

        # 应用路径
        self.app_path_var = tk.StringVar(value=current_path)
        self.app_path_entry = self._create_input_row(
            content,
            "程序路径：",
            self.app_path_var,
            browse_command=self._browse_work_app
        )

        # 窗口关键字
        self.window_keywords_var = tk.StringVar(value=", ".join(current_keywords))
        self.window_keywords_entry = self._create_input_row(content, "窗口关键字：", self.window_keywords_var)

        # 提示标签
        hint_label = tk.Label(
            content,
            text="💡 选择程序后将自动识别名称和关键字，可手动修改",
            font=("Microsoft YaHei", 9),
            fg=Theme.TEXT_SECONDARY,
            bg=Theme.BG_CARD
        )
        hint_label.pack(anchor="w", pady=(5, 0))

        # 应用数量限制提示
        limit_label = tk.Label(
            content,
            text="💡 最多可添加 5 个工作应用",
            font=("Microsoft YaHei", 9),
            fg=Theme.TEXT_SECONDARY,
            bg=Theme.BG_CARD
        )
        limit_label.pack(anchor="w", pady=(2, 0))

        # 添加按钮
        add_frame = tk.Frame(content, bg=Theme.BG_CARD)
        add_frame.pack(fill="x", pady=(10, 0))

        add_btn = tk.Button(
            add_frame,
            text="➕ 添加此应用",
            font=("Microsoft YaHei", 10),
            bg=Theme.PRIMARY,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._add_app
        )
        add_btn.pack(side="right", ipadx=15, ipady=4)
        
        # 初始化表单 - 显示当前激活应用的配置
        if self.current_active and self.current_active in self.work_targets:
            self._on_app_selected()

    def _on_app_selected(self, event=None):
        """当选择应用时更新表单并设为当前激活"""
        # 使用 Combobox.get() 直接获取当前选中值（StringVar.get() 可能返回旧值）
        display_name = self.app_combo.get() if hasattr(self, 'app_combo') else self.selected_display_var.get()
        key = self.app_key_map.get(display_name, "")
        target = self.work_targets.get(key, {})
        
        # 自动将选中的应用设为当前激活应用
        if key:
            self.current_active = key
        
        # 更新表单字段
        new_display_name = target.get("display_name", display_name)
        new_path = target.get("windows_command", "")
        new_keywords = ", ".join(target.get("window_keywords", []))
        
        # 更新 StringVar
        self.app_display_name_var.set(new_display_name)
        self.app_path_var.set(new_path)
        self.window_keywords_var.set(new_keywords)
        
        # 直接更新 Entry 控件（修复 tkinter 同步问题）
        if hasattr(self, 'app_display_name_entry'):
            self.app_display_name_entry.delete(0, tk.END)
            self.app_display_name_entry.insert(0, new_display_name)
        if hasattr(self, 'app_path_entry'):
            self.app_path_entry.delete(0, tk.END)
            self.app_path_entry.insert(0, new_path)
        if hasattr(self, 'window_keywords_entry'):
            self.window_keywords_entry.delete(0, tk.END)
            self.window_keywords_entry.insert(0, new_keywords)

    def _set_as_active(self):
        """设置选中的应用为当前激活"""
        display_name = self.selected_display_var.get()
        key = self.app_key_map.get(display_name, "")
        if key:
            self.current_active = key
            messagebox.showinfo("成功", f"已将「{display_name}」设为当前工作应用")

    def _delete_app(self):
        """删除选中的应用"""
        display_name = self.selected_display_var.get()
        key = self.app_key_map.get(display_name, "")
        if not key:
            return
        
        if len(self.work_targets) <= 1:
            messagebox.showwarning("提示", "至少需要保留一个工作应用")
            return
        
        if messagebox.askyesno("确认", f"确定要删除「{display_name}」吗？"):
            del self.work_targets[key]
            del self.app_key_map[display_name]
            
            # 更新下拉框
            new_values = list(self.app_key_map.keys())
            self.app_combo["values"] = new_values
            if new_values:
                self.selected_display_var.set(new_values[0])
                # 如果删除的是当前激活的，切换到第一个
                if self.current_active == key:
                    self.current_active = self.app_key_map.get(new_values[0], "")
                self._on_app_selected()

    def _add_app(self):
        """添加新应用"""
        # 检查应用数量限制
        if len(self.work_targets) >= 5:
            messagebox.showwarning("提示", "最多只能添加 5 个工作应用")
            return
        
        app_name = self.app_display_name_var.get().strip()
        app_path = self.app_path_var.get().strip()
        
        if not app_name:
            messagebox.showwarning("提示", "请输入应用名称")
            return
        if not app_path:
            messagebox.showwarning("提示", "请选择程序路径")
            return
        
        # 生成 key
        app_key = app_name.lower().replace(" ", "_").replace("/", "_")
        
        keywords_str = self.window_keywords_var.get()
        keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
        if not keywords:
            keywords = [app_name]
        
        # 添加到目标列表
        self.work_targets[app_key] = {
            "windows_command": app_path,
            "window_keywords": keywords,
            "display_name": app_name
        }
        self.app_key_map[app_name] = app_key
        
        # 如果是第一个应用，设为激活
        if not self.current_active:
            self.current_active = app_key
        
        # 更新下拉框
        self.app_combo["values"] = list(self.app_key_map.keys())
        self.selected_display_var.set(app_name)
        
        # 清空输入框
        self.app_display_name_var.set("")
        self.app_path_var.set("")
        self.window_keywords_var.set("")
        
        messagebox.showinfo("成功", f"已添加应用「{app_name}」")

    def _create_snapshot_content(self):
        """截图配置内容"""
        content = tk.Frame(self.content_frame, bg=Theme.BG_CARD)
        content.pack(fill="both", expand=True, padx=20, pady=15)

        self._create_section_title(content, "截图设置")

        # 启用开关
        self.snapshot_enabled_var = tk.BooleanVar(value=self._snapshot_enabled)
        self._create_checkbox_row(content, "启用人脸检测时自动截图", self.snapshot_enabled_var)
        # 添加变化监听器
        self.snapshot_enabled_var.trace_add("write", lambda *args: self._on_snapshot_enabled_change())

        # 保存路径
        self.snapshot_path_var = tk.StringVar(value=self._snapshot_directory)
        self.snapshot_path_entry = self._create_input_row(
            content,
            "保存目录：",
            self.snapshot_path_var,
            browse_command=self._browse_snapshot_dir
        )
        # 绑定 Entry 变化事件
        self.snapshot_path_entry.bind("<KeyRelease>", lambda e: self._on_snapshot_path_change())
        self.snapshot_path_entry.bind("<FocusOut>", lambda e: self._on_snapshot_path_change())

        self._create_section_title(content, "Windows 锁屏抓拍")
        self.lock_screen_enabled_var = tk.BooleanVar(value=self._lock_screen_enabled)
        self._create_checkbox_row(
            content,
            "锁屏时检测到人脸自动截图",
            self.lock_screen_enabled_var,
        )

        self.lock_screen_path_var = tk.StringVar(value=self._lock_screen_directory)
        self.lock_screen_path_entry = self._create_input_row(
            content,
            "锁屏目录：",
            self.lock_screen_path_var,
            browse_command=self._browse_lock_screen_dir,
        )

        self.lock_screen_min_faces_var = tk.StringVar(value=str(self._lock_screen_min_faces))
        self.lock_screen_min_faces_entry = self._create_input_row(
            content,
            "触发人脸数：",
            self.lock_screen_min_faces_var,
        )

        self.lock_screen_cooldown_var = tk.StringVar(value=str(self._lock_screen_cooldown))
        self.lock_screen_cooldown_entry = self._create_input_row(
            content,
            "抓拍间隔(秒)：",
            self.lock_screen_cooldown_var,
        )

    def _on_snapshot_enabled_change(self):
        """截图启用状态变化时更新实例变量"""
        try:
            self._snapshot_enabled = self.snapshot_enabled_var.get()
        except tk.TclError:
            pass

    def _on_snapshot_path_change(self):
        """截图路径变化时更新实例变量"""
        try:
            if hasattr(self, 'snapshot_path_entry') and self.snapshot_path_entry.winfo_exists():
                self._snapshot_directory = self.snapshot_path_entry.get()
        except tk.TclError:
            pass

    def _create_camera_content(self):
        """摄像头配置内容"""
        content = tk.Frame(self.content_frame, bg=Theme.BG_CARD)
        content.pack(fill="both", expand=True, padx=20, pady=15)

        self._create_section_title(content, "摄像头设置")

        # 摄像头索引
        self.camera_index_var = tk.StringVar(value=str(self._camera_index))
        self.camera_index_entry = self._create_input_row(content, "摄像头编号：", self.camera_index_var)
        self.camera_index_entry.bind("<KeyRelease>", lambda e: self._on_camera_index_change())
        self.camera_index_entry.bind("<FocusOut>", lambda e: self._on_camera_index_change())

        # 最小人脸数
        self.min_faces_var = tk.StringVar(value=str(self._min_faces))
        self.min_faces_entry = self._create_input_row(content, "触发人脸数：", self.min_faces_var)
        self.min_faces_entry.bind("<KeyRelease>", lambda e: self._on_min_faces_change())
        self.min_faces_entry.bind("<FocusOut>", lambda e: self._on_min_faces_change())

        # 冷却时间
        self.cooldown_var = tk.StringVar(value=str(self._cooldown))
        self.cooldown_entry = self._create_input_row(content, "冷却时间(秒)：", self.cooldown_var)
        self.cooldown_entry.bind("<KeyRelease>", lambda e: self._on_cooldown_change())
        self.cooldown_entry.bind("<FocusOut>", lambda e: self._on_cooldown_change())

        # 调试模式
        self.debug_draw_var = tk.BooleanVar(value=self._debug_draw)
        self._create_checkbox_row(content, "显示调试框（在画面上绘制人脸框）", self.debug_draw_var)
        self.debug_draw_var.trace_add("write", lambda *args: self._on_debug_draw_change())

    def _on_camera_index_change(self):
        """摄像头索引变化时更新实例变量"""
        try:
            if hasattr(self, 'camera_index_entry') and self.camera_index_entry.winfo_exists():
                val = self.camera_index_entry.get().strip()
                if val.isdigit():
                    self._camera_index = int(val)
        except tk.TclError:
            pass

    def _on_min_faces_change(self):
        """最小人脸数变化时更新实例变量"""
        try:
            if hasattr(self, 'min_faces_entry') and self.min_faces_entry.winfo_exists():
                val = self.min_faces_entry.get().strip()
                if val.isdigit():
                    self._min_faces = int(val)
        except tk.TclError:
            pass

    def _on_cooldown_change(self):
        """冷却时间变化时更新实例变量"""
        try:
            if hasattr(self, 'cooldown_entry') and self.cooldown_entry.winfo_exists():
                val = self.cooldown_entry.get().strip()
                if val.isdigit():
                    self._cooldown = int(val)
        except tk.TclError:
            pass

    def _on_debug_draw_change(self):
        """调试模式变化时更新实例变量"""
        try:
            self._debug_draw = self.debug_draw_var.get()
        except tk.TclError:
            pass

    def _create_ui_content(self):
        """界面配置内容"""
        content = tk.Frame(self.content_frame, bg=Theme.BG_CARD)
        content.pack(fill="both", expand=True, padx=20, pady=15)

        self._create_section_title(content, "界面设置")

        # 提示文字
        self.message_var = tk.StringVar(value=self._message)
        self.message_entry = self._create_input_row(content, "提示文字：", self.message_var)
        self.message_entry.bind("<KeyRelease>", lambda e: self._on_message_change())
        self.message_entry.bind("<FocusOut>", lambda e: self._on_message_change())

        # 托盘设置
        self.enable_tray_var = tk.BooleanVar(value=self._enable_tray)
        self._create_checkbox_row(content, "启用系统托盘图标", self.enable_tray_var)
        self.enable_tray_var.trace_add("write", lambda *args: self._on_enable_tray_change())

        self.minimize_to_tray_var = tk.BooleanVar(value=self._minimize_to_tray)
        self._create_checkbox_row(content, "关闭窗口时最小化到托盘", self.minimize_to_tray_var)
        self.minimize_to_tray_var.trace_add("write", lambda *args: self._on_minimize_to_tray_change())

        self.start_minimized_var = tk.BooleanVar(value=self._start_minimized)
        self._create_checkbox_row(content, "启动时自动最小化到托盘", self.start_minimized_var)
        self.start_minimized_var.trace_add("write", lambda *args: self._on_start_minimized_change())

    def _on_message_change(self):
        """提示文字变化时更新实例变量"""
        try:
            if hasattr(self, 'message_entry') and self.message_entry.winfo_exists():
                self._message = self.message_entry.get()
        except tk.TclError:
            pass

    def _on_enable_tray_change(self):
        """启用托盘变化时更新实例变量"""
        try:
            self._enable_tray = self.enable_tray_var.get()
        except tk.TclError:
            pass

    def _on_minimize_to_tray_change(self):
        """最小化到托盘变化时更新实例变量"""
        try:
            self._minimize_to_tray = self.minimize_to_tray_var.get()
        except tk.TclError:
            pass

    def _on_start_minimized_change(self):
        """启动时最小化变化时更新实例变量"""
        try:
            self._start_minimized = self.start_minimized_var.get()
        except tk.TclError:
            pass

    def _create_buttons(self, parent):
        """底部按钮"""
        btn_frame = tk.Frame(parent, bg=Theme.BG_DARK)
        btn_frame.pack(fill="x")

        # 取消按钮
        cancel_btn = tk.Button(
            btn_frame,
            text="取消",
            font=("Microsoft YaHei", 10),
            bg=Theme.BG_CARD,
            fg=Theme.TEXT_SECONDARY,
            relief="flat",
            cursor="hand2",
            command=self._on_cancel
        )
        cancel_btn.pack(side="left", ipadx=20, ipady=6)

        # 保存按钮
        save_btn = tk.Button(
            btn_frame,
            text="保存 ✓",
            font=("Microsoft YaHei", 10, "bold"),
            bg=Theme.ACCENT,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._on_save
        )
        save_btn.pack(side="right", ipadx=20, ipady=6)

    def _browse_work_app(self):
        """浏览工作应用程序，并自动识别应用名称"""
        path = filedialog.askopenfilename(
            title="选择工作应用程序",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")]
        )
        if path:
            # 自动识别应用名称
            app_name = extract_app_name(path) or ""
            
            # 更新 StringVar
            self.app_path_var.set(path)
            self.app_display_name_var.set(app_name)
            self.window_keywords_var.set(app_name)
            
            # 直接更新 Entry 控件（修复 tkinter 同步问题）
            if hasattr(self, 'app_path_entry'):
                self.app_path_entry.delete(0, tk.END)
                self.app_path_entry.insert(0, path)
            if hasattr(self, 'app_display_name_entry'):
                self.app_display_name_entry.delete(0, tk.END)
                self.app_display_name_entry.insert(0, app_name)
            if hasattr(self, 'window_keywords_entry'):
                self.window_keywords_entry.delete(0, tk.END)
                self.window_keywords_entry.insert(0, app_name)

    def _browse_snapshot_dir(self):
        """浏览截图目录"""
        path = filedialog.askdirectory(title="选择截图保存目录")
        if path:
            # 同时更新实例变量、StringVar 和 Entry 控件
            self._snapshot_directory = path
            self.snapshot_path_var.set(path)
            # 直接更新 Entry 控件
            if hasattr(self, 'snapshot_path_entry'):
                self.snapshot_path_entry.delete(0, tk.END)
                self.snapshot_path_entry.insert(0, path)

    def _browse_lock_screen_dir(self):
        """浏览 Windows 锁屏截图目录。"""
        path = filedialog.askdirectory(title="选择锁屏截图保存目录")
        if path:
            self._lock_screen_directory = path
            self.lock_screen_path_var.set(path)
            if hasattr(self, 'lock_screen_path_entry'):
                self.lock_screen_path_entry.delete(0, tk.END)
                self.lock_screen_path_entry.insert(0, path)

    def _on_cancel(self):
        """取消"""
        self.root.destroy()

    def _on_save(self):
        """保存配置"""
        try:
            # 保存当前标签页的最新值
            self._save_current_tab_values()
            
            # 使用多应用管理数据
            if not hasattr(self, 'work_targets') or not self.work_targets:
                messagebox.showwarning("提示", "请至少添加一个工作应用")
                return
            
            self.config["work_app"] = {
                "active": self.current_active,
                "targets": self.work_targets
            }

            # 截图配置
            self.config["snapshot"] = {
                "enabled": self._snapshot_enabled,
                "directory": self._snapshot_directory
            }
            self.config["lock_screen"] = {
                "enabled": self._lock_screen_enabled,
                "directory": self._lock_screen_directory,
                "min_faces": self._lock_screen_min_faces,
                "cooldown_seconds": self._lock_screen_cooldown,
            }

            # 摄像头配置
            self.config["camera_index"] = self._camera_index
            self.config["min_faces_for_alert"] = self._min_faces
            self.config["alert_cooldown_seconds"] = self._cooldown

            if "camera" not in self.config:
                self.config["camera"] = {}
            self.config["camera"]["debug_draw"] = self._debug_draw

            # UI 配置
            if "ui" not in self.config:
                self.config["ui"] = {}
            self.config["ui"]["message"] = self._message
            self.config["ui"]["enable_system_tray"] = self._enable_tray
            self.config["ui"]["minimize_to_tray"] = self._minimize_to_tray
            self.config["ui"]["start_minimized"] = self._start_minimized

            self.saved = True
            if self.on_save:
                self.on_save(self.config)

            messagebox.showinfo("成功", "配置已保存，部分设置将在重启后生效")
            self.root.destroy()

        except Exception as e:
            messagebox.showerror("错误", f"保存配置失败: {e}")

    def run(self):
        """运行设置对话框"""
        self.root.grab_set()  # 模态窗口
        self.root.wait_window()
        return self.saved

    def get_config(self) -> Dict[str, Any]:
        """获取配置"""
        return self.config


if __name__ == "__main__":
    # 测试设置对话框
    test_config = {
        "camera_index": 0,
        "min_faces_for_alert": 2,
        "alert_cooldown_seconds": 15,
        "work_app": {
            "active": "idea",
            "targets": {
                "idea": {
                    "windows_command": "C:/app/idea64.exe",
                    "window_keywords": ["IntelliJ IDEA"]
                }
            }
        },
        "snapshot": {
            "enabled": True,
            "directory": "C:/Users/test/Pictures"
        },
        "ui": {
            "message": "有人在看屏幕！",
            "enable_system_tray": True,
            "minimize_to_tray": True,
            "start_minimized": False
        },
        "camera": {
            "debug_draw": False
        }
    }

    def on_save(cfg):
        print("保存配置：", cfg)

    dialog = SettingsDialog(test_config, on_save=on_save)
    dialog.run()
