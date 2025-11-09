# -*- coding: utf-8 -*-
"""
用户体验优化模块
"""
import tkinter as tk
from tkinter import messagebox
import threading
import time
from typing import Callable, Any, List
from dataclasses import dataclass

@dataclass
class UXImprovement:
    """UX改进数据类"""
    component: str
    improvement: str
    description: str
    impact: str

class UXOptimizer:
    """用户体验优化器"""

    def __init__(self):
        self.loading_indicators = {}
        self.async_operations = {}

    def add_loading_indicator(self, parent: tk.Widget, operation_id: str):
        """添加加载指示器"""
        if operation_id in self.loading_indicators:
            return

        indicator = tk.Label(parent, text="⏳ 处理中...", fg="blue")
        indicator.grid(pady=5)
        self.loading_indicators[operation_id] = indicator

    def remove_loading_indicator(self, operation_id: str):
        """移除加载指示器"""
        if operation_id in self.loading_indicators:
            self.loading_indicators[operation_id].destroy()
            del self.loading_indicators[operation_id]

    def run_async_operation(self, operation_id: str, func: Callable, *args, **kwargs):
        """异步执行操作"""
        def async_wrapper():
            try:
                self.add_loading_indicator(None, operation_id)
                result = func(*args, **kwargs)
                self.async_operations[operation_id] = {"success": True, "result": result}
            except Exception as e:
                self.async_operations[operation_id] = {"success": False, "error": str(e)}
            finally:
                self.remove_loading_indicator(operation_id)

        thread = threading.Thread(target=async_wrapper, daemon=True)
        thread.start()
        return thread

    def show_friendly_error(self, title: str, error: str, suggestions: List[str] = None):
        """显示友好的错误提示"""
        message = f"发生错误：{error}"

        if suggestions:
            message += "\n\n建议解决方案：\n"
            for i, suggestion in enumerate(suggestions, 1):
                message += f"{i}. {suggestion}\n"

        messagebox.showerror(title, message)

    def show_success_message(self, title: str, message: str):
        """显示成功消息"""
        messagebox.showinfo(title, message)

    def create_progress_bar(self, parent: tk.Widget, operation_id: str) -> tk.Widget:
        """创建进度条"""
        from tkinter import ttk

        progress_frame = tk.Frame(parent)
        progress_frame.pack(fill=tk.X, pady=5)

        progress_bar = ttk.Progressbar(
            progress_frame,
            mode='indeterminate',
            length=200
        )
        progress_bar.pack(side=tk.LEFT, padx=5)

        label = tk.Label(progress_frame, text="处理中...")
        label.pack(side=tk.LEFT)

        progress_bar.start(10)

        return progress_frame

    def optimize_button_feedback(self, button: tk.Button):
        """优化按钮反馈"""
        original_config = button.cget("text")

        def on_click():
            button.config(text="✓ 已点击", state="disabled")
            button.after(500, lambda: button.config(text=original_config, state="normal"))

        button.config(command=on_click)

    def add_tooltip(self, widget: tk.Widget, text: str):
        """添加工具提示"""
        def on_enter(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")

            label = tk.Label(tooltip, text=text, background="lightyellow",
                           relief="solid", borderwidth=1)
            label.pack()

            widget.tooltip = tooltip

        def on_leave(event):
            if hasattr(widget, 'tooltip'):
                widget.tooltip.destroy()
                del widget.tooltip

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

# 全局UX优化器实例
ux_optimizer = UXOptimizer()
