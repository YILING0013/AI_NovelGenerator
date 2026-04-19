# ui/directory_tab.py
# -*- coding: utf-8 -*-
import os
import customtkinter as ctk
from tkinter import messagebox
from utils import read_file, save_string_to_txt, clear_file_content
from ui.context_menu import TextWidgetContextMenu

def build_directory_tab(self):
    self.directory_tab = self.tabview.add("Chapter Blueprint")
    self.directory_tab.rowconfigure(0, weight=0)
    self.directory_tab.rowconfigure(1, weight=1)
    self.directory_tab.columnconfigure(0, weight=1)

    load_btn = ctk.CTkButton(self.directory_tab, text="Load Novel_directory.txt", command=self.load_chapter_blueprint, font=("Arial", 12))
    load_btn.grid(row=0, column=0, padx=5, pady=5, sticky="w")

    self.directory_word_count_label = ctk.CTkLabel(self.directory_tab, text="Word count: 0", font=("Arial", 12))
    self.directory_word_count_label.grid(row=0, column=1, padx=5, pady=5, sticky="w")

    save_btn = ctk.CTkButton(self.directory_tab, text="Save Changes", command=self.save_chapter_blueprint, font=("Arial", 12))
    save_btn.grid(row=0, column=2, padx=5, pady=5, sticky="e")

    self.directory_text = ctk.CTkTextbox(self.directory_tab, wrap="word", font=("Arial", 12))
    
    def update_word_count(event=None):
        text = self.directory_text.get("0.0", "end")
        count = len(text) - 1
        self.directory_word_count_label.configure(text=f"Word count: {count}")
    
    self.directory_text.bind("<KeyRelease>", update_word_count)
    self.directory_text.bind("<ButtonRelease>", update_word_count)
    TextWidgetContextMenu(self.directory_text)
    self.directory_text.grid(row=1, column=0, sticky="nsew", padx=5, pady=5, columnspan=3)

def load_chapter_blueprint(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("Warning", "Please set the save path first.")
        return
    filename = os.path.join(filepath, "Novel_directory.txt")
    content = read_file(filename)
    self.directory_text.delete("0.0", "end")
    self.directory_text.insert("0.0", content)
    self.log("Loaded Novel_directory.txt into the editor.")

def save_chapter_blueprint(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("Warning", "Please set the save path first.")
        return
    content = self.directory_text.get("0.0", "end").strip()
    filename = os.path.join(filepath, "Novel_directory.txt")
    clear_file_content(filename)
    save_string_to_txt(content, filename)
    self.log("Saved changes to Novel_directory.txt.")
