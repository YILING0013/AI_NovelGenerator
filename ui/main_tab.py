# ui/main_tab.py
# -*- coding: utf-8 -*-
import customtkinter as ctk
from tkinter import messagebox
from ui.context_menu import TextWidgetContextMenu

def build_main_tab(self):
    """
    The main tab contains the chapter editor and logs on the left,
    and controls/parameters on the right.
    """
    self.main_tab = self.tabview.add("Main Functions")
    self.main_tab.rowconfigure(0, weight=1)
    self.main_tab.columnconfigure(0, weight=1)
    self.main_tab.columnconfigure(1, weight=0)

    self.left_frame = ctk.CTkFrame(self.main_tab)
    self.left_frame.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

    self.right_frame = ctk.CTkFrame(self.main_tab)
    self.right_frame.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)

    build_left_layout(self)
    build_right_layout(self)

def build_left_layout(self):
    """
    Left Layout: Chapter Editor + Step Buttons + Read-only Log.
    """
    self.left_frame.grid_rowconfigure(0, weight=0)
    self.left_frame.grid_rowconfigure(1, weight=2)
    self.left_frame.grid_rowconfigure(2, weight=0)
    self.left_frame.grid_rowconfigure(3, weight=0)
    self.left_frame.grid_rowconfigure(4, weight=1)
    self.left_frame.columnconfigure(0, weight=1)

    self.chapter_label = ctk.CTkLabel(self.left_frame, text="Current Chapter Content (Editable)  Words: 0", font=("Arial", 12))
    self.chapter_label.grid(row=0, column=0, padx=5, pady=(5, 0), sticky="w")

    # Chapter editor
    self.chapter_result = ctk.CTkTextbox(self.left_frame, wrap="word", font=("Arial", 14))
    TextWidgetContextMenu(self.chapter_result)
    self.chapter_result.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 5))

    def update_word_count(event=None):
        text = self.chapter_result.get("0.0", "end")
        count = len(text) - 1
        self.chapter_label.configure(text=f"Current Chapter Content (Editable)  Words: {count}")

    self.chapter_result.bind("<KeyRelease>", update_word_count)
    self.chapter_result.bind("<ButtonRelease>", update_word_count)

    # Step buttons
    self.step_buttons_frame = ctk.CTkFrame(self.left_frame)
    self.step_buttons_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
    self.step_buttons_frame.columnconfigure((0, 1, 2, 3, 4), weight=1)

    self.btn_generate_architecture = ctk.CTkButton(
        self.step_buttons_frame,
        text="Step 1. Generate Settings",
        command=self.generate_novel_architecture_ui,
        font=("Arial", 12)
    )
    self.btn_generate_architecture.grid(row=0, column=0, padx=5, pady=2, sticky="ew")

    self.btn_generate_directory = ctk.CTkButton(
        self.step_buttons_frame,
        text="Step 2. Generate Directory",
        command=self.generate_chapter_blueprint_ui,
        font=("Arial", 12)
    )
    self.btn_generate_directory.grid(row=0, column=1, padx=5, pady=2, sticky="ew")

    self.btn_generate_chapter = ctk.CTkButton(
        self.step_buttons_frame,
        text="Step 3. Generate Draft",
        command=self.generate_chapter_draft_ui,
        font=("Arial", 12)
    )
    self.btn_generate_chapter.grid(row=0, column=2, padx=5, pady=2, sticky="ew")

    self.btn_finalize_chapter = ctk.CTkButton(
        self.step_buttons_frame,
        text="Step 4. Finalize Chapter",
        command=self.finalize_chapter_ui,
        font=("Arial", 12)
    )
    self.btn_finalize_chapter.grid(row=0, column=3, padx=5, pady=2, sticky="ew")

    self.btn_batch_generate = ctk.CTkButton(
        self.step_buttons_frame,
        text="Batch Generate",
        command=self.generate_batch_ui,
        font=("Arial", 12)
    )
    self.btn_batch_generate.grid(row=0, column=4, padx=5, pady=2, sticky="ew")

    # Output log
    log_label = ctk.CTkLabel(self.left_frame, text="Output Log (Read-only)", font=("Arial", 12))
    log_label.grid(row=3, column=0, padx=5, pady=(5, 0), sticky="w")

    self.log_text = ctk.CTkTextbox(self.left_frame, wrap="word", font=("Arial", 12))
    TextWidgetContextMenu(self.log_text)
    self.log_text.grid(row=4, column=0, sticky="nsew", padx=5, pady=(0, 5))
    self.log_text.configure(state="disabled")

def build_right_layout(self):
    """
    Right Layout: Configuration (tabview) + Parameters + Optional Buttons.
    """
    self.right_frame.grid_rowconfigure(0, weight=0)
    self.right_frame.grid_rowconfigure(1, weight=1)
    self.right_frame.grid_rowconfigure(2, weight=0)
    self.right_frame.columnconfigure(0, weight=1)

    # Configuration area
    self.config_frame = ctk.CTkFrame(self.right_frame, corner_radius=10, border_width=2, border_color="gray")
    self.config_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
    self.config_frame.columnconfigure(0, weight=1)
