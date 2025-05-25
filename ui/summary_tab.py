# ui/summary_tab.py
# -*- coding: utf-8 -*-
import os
import customtkinter as ctk
from tkinter import messagebox
from utils import read_file, save_string_to_txt, clear_file_content
from ui.context_menu import TextWidgetContextMenu

def build_summary_tab(self):
    self.summary_tab = self.tabview.add("全局摘要")
    self.summary_tab.rowconfigure(0, weight=0)
    self.summary_tab.rowconfigure(1, weight=1)
    self.summary_tab.columnconfigure(0, weight=1)
    self.summary_tab.columnconfigure(1, weight=0)
    self.summary_tab.columnconfigure(2, weight=0)

    load_btn = ctk.CTkButton(self.summary_tab, text="加载 global_summary.txt", command=self.load_global_summary, font=("Microsoft YaHei", 12))
    load_btn.grid(row=0, column=0, padx=5, pady=5, sticky="w")

    self.word_count_label = ctk.CTkLabel(self.summary_tab, text="字数：0", font=("Microsoft YaHei", 12))
    self.word_count_label.grid(row=0, column=1, padx=5, pady=5, sticky="w")

    save_btn = ctk.CTkButton(self.summary_tab, text="保存修改", command=self.save_global_summary, font=("Microsoft YaHei", 12))
    save_btn.grid(row=0, column=2, padx=5, pady=5, sticky="e")

    self.summary_text = ctk.CTkTextbox(self.summary_tab, wrap="word", font=("Microsoft YaHei", 12))
    TextWidgetContextMenu(self.summary_text)
    self.summary_text.grid(row=1, column=0, sticky="nsew", padx=5, pady=5, columnspan=3)

    def update_word_count(event=None):
        text = self.summary_text.get("0.0", "end")
        count = len(text) - 1
        self.word_count_label.configure(text=f"字数：{count}")

    self.summary_text.bind("<KeyRelease>", update_word_count)
    self.summary_text.bind("<ButtonRelease>", update_word_count)
def load_global_summary(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先设置保存文件路径")
        return
    filename = os.path.join(filepath, "global_summary.txt")
    content = read_file(filename)
    self.summary_text.delete("0.0", "end")
    self.summary_text.insert("0.0", content)
    self.log("已加载 global_summary.txt 到编辑区。")

def save_global_summary(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先设置保存文件路径")
        return
    content = self.summary_text.get("0.0", "end").strip()
    filename = os.path.join(filepath, "global_summary.txt")
    clear_file_content(filename)
    save_string_to_txt(content, filename)
    self.log("已保存对 global_summary.txt 的修改。")
