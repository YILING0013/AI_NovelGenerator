# ui/writing_style_tab.py
# -*- coding: utf-8 -*-
import customtkinter as ctk
from tkinter import messagebox
from prompt_definitions import DEFAULT_WRITING_STYLE_PROMPT
from ui.context_menu import TextWidgetContextMenu # Assuming you want context menu for this textbox too

def build_writing_style_tab(self):
    self.writing_style_tab = self.tabview.add("写作风格")
    self.writing_style_tab.grid_columnconfigure(0, weight=1)
    self.writing_style_tab.grid_rowconfigure(1, weight=1)

    # --- Top Frame for buttons ---
    top_frame = ctk.CTkFrame(self.writing_style_tab)
    top_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
    top_frame.grid_columnconfigure(0, weight=0) # Load default button
    top_frame.grid_columnconfigure(1, weight=0) # Save button
    top_frame.grid_columnconfigure(2, weight=1) # Spacer

    # --- Textbox for writing style ---
    self.writing_style_text = ctk.CTkTextbox(
        self.writing_style_tab,
        wrap="word",
        font=("Microsoft YaHei", 12)
    )
    TextWidgetContextMenu(self.writing_style_text)
    self.writing_style_text.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

    # --- Functions for buttons ---
    def load_default_style():
        self.writing_style_text.delete("0.0", "end")
        self.writing_style_text.insert("0.0", DEFAULT_WRITING_STYLE_PROMPT)
        self.log("已加载默认写作风格到编辑框。")

    def save_custom_style():
        style_content = self.writing_style_text.get("0.0", "end-1c").strip()
        if not style_content:
            messagebox.showwarning("警告", "写作风格内容不能为空。如果想使用默认风格，请点击“加载默认风格”并保存，或将默认风格文本粘贴至此。")
            return

        self.user_defined_writing_style_var.set(style_content)
        # Call the main config saving function which now includes writing style
        self.save_config_btn()
        # save_config_btn already shows a messagebox and logs
        # self.log("自定义写作风格已保存到配置。") # No longer needed here

    # --- Buttons ---
    load_default_btn = ctk.CTkButton(
        top_frame,
        text="加载默认风格",
        command=load_default_style,
        font=("Microsoft YaHei", 12)
    )
    load_default_btn.grid(row=0, column=0, padx=(0,5), pady=5, sticky="w")

    save_style_btn = ctk.CTkButton(
        top_frame,
        text="保存写作风格",
        command=save_custom_style,
        font=("Microsoft YaHei", 12)
    )
    save_style_btn.grid(row=0, column=1, padx=(0,5), pady=5, sticky="w")

    # --- Initial population of the textbox ---
    # Load from config var if not empty, else load default
    initial_style = self.user_defined_writing_style_var.get()
    if initial_style and initial_style.strip():
        self.writing_style_text.insert("0.0", initial_style)
    else:
        self.writing_style_text.insert("0.0", DEFAULT_WRITING_STYLE_PROMPT)

    self.log("写作风格界面已构建。")
