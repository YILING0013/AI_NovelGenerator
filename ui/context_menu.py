# ui/context_menu.py
# -*- coding: utf-8 -*-
import tkinter as tk
import customtkinter as ctk

class TextWidgetContextMenu:
    """
    Provides right-click copy/cut/paste/select-all functionality for CTkTextbox or tk.Text.
    """
    def __init__(self, widget):
        self.widget = widget
        self.menu = tk.Menu(widget, tearoff=0)
        self.menu.add_command(label="Copy", command=self.copy)
        self.menu.add_command(label="Paste", command=self.paste)
        self.menu.add_command(label="Cut", command=self.cut)
        self.menu.add_separator()
        self.menu.add_command(label="Select All", command=self.select_all)
        
        # Bind right-click event
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
            pass

    def paste(self):
        try:
            text = self.widget.clipboard_get()
            self.widget.insert("insert", text)
        except tk.TclError:
            pass

    def cut(self):
        try:
            text = self.widget.get("sel.first", "sel.last")
            self.widget.delete("sel.first", "sel.last")
            self.widget.clipboard_clear()
            self.widget.clipboard_append(text)
        except tk.TclError:
            pass

    def select_all(self):
        self.widget.tag_add("sel", "1.0", "end")
