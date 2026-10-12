# ui/context_menu.py
# -*- coding: utf-8 -*-
import tkinter as tk
import customtkinter as ctk

class TextWidgetContextMenu:
    """
    为 customtkinter.TextBox 或 tkinter.Text 提供右键复制/剪切/粘贴/全选的功能。
    """
    def __init__(self, widget):
        self.widget = widget
        self.menu = tk.Menu(widget, tearoff=0)
        self.menu.add_command(label="复制", command=self.copy)
        self.menu.add_command(label="粘贴", command=self.paste)
        self.menu.add_command(label="剪切", command=self.cut)
        self.menu.add_separator()
        self.menu.add_command(label="全选", command=self.select_all)
        
        # 绑定右键事件
        self.widget.bind("<Button-3>", self.show_menu)
        
    def show_menu(self, event):
        if isinstance(self.widget, ctk.CTkTextbox):
            try:
                self.menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.menu.grab_release()
            
    def copy(self):
        try:
            text = self.widget.get("sel.first", "sel.last")
            self.widget.clipboard_clear()
            self.widget.clipboard_append(text)
        except tk.TclError:
            pass  # 没有选中文本时忽略错误

    def paste(self):
        try:
            text = self.widget.clipboard_get()
            self.widget.insert("insert", text)
        except tk.TclError:
            pass  # 剪贴板为空时忽略错误

    def cut(self):
        try:
            text = self.widget.get("sel.first", "sel.last")
            self.widget.delete("sel.first", "sel.last")
            self.widget.clipboard_clear()
            self.widget.clipboard_append(text)
        except tk.TclError:
            pass  # 没有选中文本时忽略错误

    def select_all(self):
        self.widget.tag_add("sel", "1.0", "end")
