# -*- coding: utf-8 -*-
"""
启动画面 (Splash Screen) - 程序加载时显示
"""

try:
    import tkinter as tk
except ImportError:
    tk = None

from .dpi_utils import enable_dpi_awareness


class SplashScreen:
    """启动画面类 - 使用 Toplevel 避免影响主窗口"""
    
    def __init__(self):
        if tk is None:
            self.splash = None
            return
        
        enable_dpi_awareness()
        
        # 创建隐藏的根窗口（保持 tkinter 运行）
        self._hidden_root = tk.Tk()
        self._hidden_root.withdraw()  # 隐藏
        
        # 创建启动画面作为 Toplevel
        self.splash = tk.Toplevel(self._hidden_root)
        self.splash.overrideredirect(True)  # 无边框
        self.splash.attributes("-topmost", True)
        
        # 窗口尺寸
        width = 300
        height = 150
        
        # 居中显示
        x = (self.splash.winfo_screenwidth() - width) // 2
        y = (self.splash.winfo_screenheight() - height) // 2
        self.splash.geometry(f"{width}x{height}+{x}+{y}")
        
        # 背景色
        bg_color = "#1a1a2e"
        self.splash.configure(bg=bg_color)
        
        # 主框架
        frame = tk.Frame(self.splash, bg=bg_color)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 应用图标/表情
        icon_label = tk.Label(
            frame,
            text="🍠",
            font=("Segoe UI Emoji", 36),
            bg=bg_color,
            fg="white"
        )
        icon_label.pack(pady=(10, 5))
        
        # 应用名称
        title_label = tk.Label(
            frame,
            text="Anti-Peep",
            font=("Microsoft YaHei", 18, "bold"),
            bg=bg_color,
            fg="white"
        )
        title_label.pack()
        
        # 加载状态
        self.status_label = tk.Label(
            frame,
            text="正在加载...",
            font=("Microsoft YaHei", 10),
            bg=bg_color,
            fg="#888888"
        )
        self.status_label.pack(pady=(10, 0))
        
        # 刷新显示
        self.splash.update()
    
    def update_status(self, text: str):
        """更新加载状态文字"""
        if self.splash and self.status_label:
            self.status_label.config(text=text)
            self.splash.update()
    
    def close(self):
        """关闭启动画面和隐藏的根窗口"""
        if self.splash:
            try:
                self.splash.destroy()
            except Exception:
                pass
            self.splash = None
        if hasattr(self, '_hidden_root') and self._hidden_root:
            try:
                self._hidden_root.destroy()
            except Exception:
                pass
            self._hidden_root = None
