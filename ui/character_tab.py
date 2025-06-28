# ui/character_tab.py
# -*- coding: utf-8 -*-
import os
import customtkinter as ctk
from tkinter import messagebox
from utils import read_file, save_string_to_txt, clear_file_content
from ui.context_menu import TextWidgetContextMenu

def build_character_tab(self):
    self.character_tab = self.tabview.add("角色状态")
    self.character_tab.rowconfigure(0, weight=0)
    self.character_tab.rowconfigure(1, weight=1)
    self.character_tab.columnconfigure(0, weight=1)

    load_btn = ctk.CTkButton(self.character_tab, text="加载 character_state.txt", command=self.load_character_state, font=("Microsoft YaHei", 12))
    load_btn.grid(row=0, column=0, padx=5, pady=5, sticky="w")

    self.character_wordcount_label = ctk.CTkLabel(self.character_tab, text="字数：0", font=("Microsoft YaHei", 12))
    self.character_wordcount_label.grid(row=0, column=1, padx=5, pady=5, sticky="w")

    save_btn = ctk.CTkButton(self.character_tab, text="保存修改", command=self.save_character_state, font=("Microsoft YaHei", 12))
    save_btn.grid(row=0, column=2, padx=5, pady=5, sticky="e")

    self.character_text = ctk.CTkTextbox(self.character_tab, wrap="word", font=("Microsoft YaHei", 12))
    
    def update_word_count(event=None):
        text = self.character_text.get("0.0", "end-1c")
        text_length = len(text)
        self.character_wordcount_label.configure(text=f"字数：{text_length}")
    
    self.character_text.bind("<KeyRelease>", update_word_count)
    self.character_text.bind("<ButtonRelease>", update_word_count)
    TextWidgetContextMenu(self.character_text)
    self.character_text.grid(row=1, column=0, sticky="nsew", padx=5, pady=5, columnspan=3)

def load_character_state(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先设置保存文件路径")
        return
    filename = os.path.join(filepath, "character_state.txt")
    content = read_file(filename)
    self.character_text.delete("0.0", "end")
    self.character_text.insert("0.0", content)
    self.log("已加载 character_state.txt 到编辑区。")

def save_character_state(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先设置保存文件路径")
        return
    content = self.character_text.get("0.0", "end").strip()
    filename = os.path.join(filepath, "character_state.txt")
    clear_file_content(filename)
    save_string_to_txt(content, filename)
    self.log("已保存对 character_state.txt 的修改。")
