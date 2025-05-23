# ui/main_tab.py
# -*- coding: utf-8 -*-
"""Main tab layout for the Novel Generator GUI.

此版本集成了批量章节生成与章节范围配置：
1. 批量生成按钮 (Step1‑4 自动串联)。
2. 起始/结束章节输入框，供批量模式使用。
3. 自动处理所有确认对话框，无需手动点击。
"""

import customtkinter as ctk
from tkinter import messagebox

from ui.context_menu import TextWidgetContextMenu

__all__ = [
    "build_main_tab",
    "build_left_layout",
    "build_right_layout",
]


def build_main_tab(self):
    """构建主 Tab ―― 左侧编辑区 & 右侧参数区。"""
    self.main_tab = self.tabview.add("Main Functions")
    self.main_tab.rowconfigure(0, weight=1)
    self.main_tab.columnconfigure(0, weight=1)  # left
    self.main_tab.columnconfigure(1, weight=0)  # right

    # 左右两侧 Frame
    self.left_frame = ctk.CTkFrame(self.main_tab)
    self.left_frame.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

    self.right_frame = ctk.CTkFrame(self.main_tab)
    self.right_frame.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)

    build_left_layout(self)
    build_right_layout(self)


# ---------------------------------------------------------------------------
# Left‑hand layout
# ---------------------------------------------------------------------------

def build_left_layout(self):
    """左侧：章节内容编辑 → Step 按钮 → 章节范围 → 输出日志。"""

    # Grid skeleton
    self.left_frame.grid_rowconfigure(0, weight=0)  # label
    self.left_frame.grid_rowconfigure(1, weight=2)  # text body
    self.left_frame.grid_rowconfigure(2, weight=0)  # step buttons
    self.left_frame.grid_rowconfigure(3, weight=0)  # chapter range
    self.left_frame.grid_rowconfigure(4, weight=0)  # log label
    self.left_frame.grid_rowconfigure(5, weight=1)  # log output
    self.left_frame.columnconfigure(0, weight=1)

    # --- 本章内容（可编辑）
    self.chapter_label = ctk.CTkLabel(
        self.left_frame,
        text="本章内容（可编辑）  字数：0",
        font=("Microsoft YaHei", 12),
    )
    self.chapter_label.grid(row=0, column=0, padx=5, pady=(5, 0), sticky="w")

    # 章节文本框
    self.chapter_result = ctk.CTkTextbox(
        self.left_frame, wrap="word", font=("Microsoft YaHei", 14)
    )
    TextWidgetContextMenu(self.chapter_result)
    self.chapter_result.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 5))

    # 实时字数统计
    def _update_word_count(event=None):
        text = self.chapter_result.get("0.0", "end")
        self.chapter_label.configure(text=f"本章内容（可编辑）  字数：{max(len(text) - 1, 0)}")

    self.chapter_result.bind("<KeyRelease>", _update_word_count)
    self.chapter_result.bind("<ButtonRelease>", _update_word_count)

    # --- Step 按钮区
    self.step_buttons_frame = ctk.CTkFrame(self.left_frame)
    self.step_buttons_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
    self.step_buttons_frame.columnconfigure((0, 1, 2, 3), weight=1)

    # Step‑1‑4 原有按钮
    self.btn_generate_architecture = ctk.CTkButton(
        self.step_buttons_frame,
        text="Step1. 生成架构",
        command=self.generate_novel_architecture_ui,
        font=("Microsoft YaHei", 12),
    )
    self.btn_generate_architecture.grid(row=0, column=0, padx=5, pady=2, sticky="ew")

    self.btn_generate_directory = ctk.CTkButton(
        self.step_buttons_frame,
        text="Step2. 生成目录",
        command=self.generate_chapter_blueprint_ui,
        font=("Microsoft YaHei", 12),
    )
    self.btn_generate_directory.grid(row=0, column=1, padx=5, pady=2, sticky="ew")

    self.btn_generate_chapter = ctk.CTkButton(
        self.step_buttons_frame,
        text="Step3. 生成草稿",
        command=self.generate_chapter_draft_ui,
        font=("Microsoft YaHei", 12),
    )
    self.btn_generate_chapter.grid(row=0, column=2, padx=5, pady=2, sticky="ew")

    self.btn_finalize_chapter = ctk.CTkButton(
        self.step_buttons_frame,
        text="Step4. 定稿章节",
        command=self.finalize_chapter_ui,
        font=("Microsoft YaHei", 12),
    )
    self.btn_finalize_chapter.grid(row=0, column=3, padx=5, pady=2, sticky="ew")

    # 批量按钮（横跨 4 列）
    self.btn_batch_process = ctk.CTkButton(
        self.step_buttons_frame,
        text="🔁 批量生成章节",
        command=self.batch_generate_chapters_ui,
        font=("Microsoft YaHei", 12, "bold"),
    )
    self.btn_batch_process.grid(row=1, column=0, columnspan=4, padx=5, pady=(6, 2), sticky="ew")

    # --- 章节范围输入区
    self.chapter_range_frame = ctk.CTkFrame(self.left_frame)
    self.chapter_range_frame.grid(row=3, column=0, sticky="ew", padx=5, pady=(0, 5))
    self.chapter_range_frame.columnconfigure((0, 1), weight=1)

    # 起始/结束章节变量
    self.start_chap_var = getattr(self, "start_chap_var", ctk.StringVar(value="1"))
    self.end_chap_var = getattr(self, "end_chap_var", ctk.StringVar(value="10"))

    self.start_chap_entry = ctk.CTkEntry(
        self.chapter_range_frame,
        textvariable=self.start_chap_var,
        placeholder_text="起始章节",
        font=("Microsoft YaHei", 12),
    )
    self.start_chap_entry.grid(row=0, column=0, padx=5, pady=2, sticky="ew")

    self.end_chap_entry = ctk.CTkEntry(
        self.chapter_range_frame,
        textvariable=self.end_chap_var,
        placeholder_text="结束章节",
        font=("Microsoft YaHei", 12),
    )
    self.end_chap_entry.grid(row=0, column=1, padx=5, pady=2, sticky="ew")

    # --- 日志区
    log_label = ctk.CTkLabel(
        self.left_frame, text="输出日志 (只读)", font=("Microsoft YaHei", 12)
    )
    log_label.grid(row=4, column=0, padx=5, pady=(5, 0), sticky="w")

    self.log_text = ctk.CTkTextbox(
        self.left_frame, wrap="word", font=("Microsoft YaHei", 12)
    )
    TextWidgetContextMenu(self.log_text)
    self.log_text.grid(row=5, column=0, sticky="nsew", padx=5, pady=(0, 5))
    self.log_text.configure(state="disabled")


# ---------------------------------------------------------------------------
# Right‑hand layout
# ---------------------------------------------------------------------------

def build_right_layout(self):
    """右侧：模型 / Embedding 配置、小说参数与可选工具按钮。"""

    # 基础网格
    self.right_frame.grid_rowconfigure(0, weight=0)
    self.right_frame.grid_rowconfigure(1, weight=1)
    self.right_frame.grid_rowconfigure(2, weight=0)
    self.right_frame.columnconfigure(0, weight=1)

    # 配置区外框（在其它模块里继续细分）
    self.config_frame = ctk.CTkFrame(
        self.right_frame, corner_radius=10, border_width=2, border_color="gray"
    )
    self.config_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
    self.config_frame.columnconfigure(0, weight=1)

    # 其余详细布局由其他模块（config_tab.py / novel_params_tab.py 等）构建。
