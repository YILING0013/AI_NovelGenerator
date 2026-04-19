# ui/setting_tab.py
# -*- coding: utf-8 -*-
import os
import customtkinter as ctk
from tkinter import messagebox
from utils import read_file, save_string_to_txt, clear_file_content
from ui.context_menu import TextWidgetContextMenu

def build_setting_tab(self):
    self.setting_tab = self.tabview.add("Novel Settings")
    self.setting_tab.rowconfigure(0, weight=0)
    self.setting_tab.rowconfigure(1, weight=1)
    self.setting_tab.columnconfigure(0, weight=1)

    load_btn = ctk.CTkButton(self.setting_tab, text="Load Novel_architecture.txt", command=self.load_novel_architecture, font=("Arial", 12))
    load_btn.grid(row=0, column=0, padx=5, pady=5, sticky="w")

    self.setting_word_count_label = ctk.CTkLabel(self.setting_tab, text="Word count: 0", font=("Arial", 12))
    self.setting_word_count_label.grid(row=0, column=1, padx=5, pady=5, sticky="w")

    save_btn = ctk.CTkButton(self.setting_tab, text="Save Changes", command=self.save_novel_architecture, font=("Arial", 12))
    save_btn.grid(row=0, column=2, padx=5, pady=5, sticky="e")

    self.setting_text = ctk.CTkTextbox(self.setting_tab, wrap="word", font=("Arial", 12))
    TextWidgetContextMenu(self.setting_text)
    self.setting_text.grid(row=1, column=0, sticky="nsew", padx=5, pady=5, columnspan=3)

    def update_word_count(event=None):
        text = self.setting_text.get("0.0", "end")
        count = len(text) - 1
        self.setting_word_count_label.configure(text=f"Word count: {count}")

    self.setting_text.bind("<KeyRelease>", update_word_count)
    self.setting_text.bind("<ButtonRelease>", update_word_count)

def load_novel_architecture(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("Warning", "Please set the save path first.")
        return
    filename = os.path.join(filepath, "Novel_architecture.txt")
    content = read_file(filename)
    self.setting_text.delete("0.0", "end")
    self.setting_text.insert("0.0", content)
    self.log("Loaded Novel_architecture.txt into the editor.")

def save_novel_architecture(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("Warning", "Please set the save path first.")
        return
    content = self.setting_text.get("0.0", "end").strip()
    filename = os.path.join(filepath, "Novel_architecture.txt")
    clear_file_content(filename)
    save_string_to_txt(content, filename)
    self.log("Saved changes to Novel_architecture.txt.")
