# ui/prompts_tab.py
# -*- coding: utf-8 -*-
import customtkinter as ctk
from tkinter import messagebox
from prompt_definitions import (
    first_chapter_draft_prompt as default_first_chapter_draft_prompt,
    next_chapter_draft_prompt as default_next_chapter_draft_prompt
    # Import other default prompts if they become customizable
)
from ui.context_menu import TextWidgetContextMenu

# Define which prompts are customizable and their default values / placeholder info
EDITABLE_PROMPTS_CONFIG = {
    "first_chapter_draft": {
        "display_name": "第一章草稿提示词",
        "default_prompt": default_first_chapter_draft_prompt,
        "placeholders": [
            "{novel_number}", "{chapter_title}", "{chapter_role}", "{chapter_purpose}",
            "{suspense_level}", "{foreshadowing}", "{plot_twist_level}", "{chapter_summary}",
            "{characters_involved}", "{key_items}", "{scene_location}", "{time_constraint}",
            "{user_guidance}", "{novel_setting}", "{writing_style_instructions}"
        ]
    },
    "next_chapter_draft": {
        "display_name": "后续章节草稿提示词",
        "default_prompt": default_next_chapter_draft_prompt,
        "placeholders": [
            "{global_summary}", "{previous_chapter_excerpt}", "{user_guidance}",
            "{character_state}", "{short_summary}", "{novel_number}", "{chapter_title}",
            "{chapter_role}", "{chapter_purpose}", "{suspense_level}", "{foreshadowing}",
            "{plot_twist_level}", "{chapter_summary}", "{word_number}", "{characters_involved}",
            "{key_items}", "{scene_location}", "{time_constraint}",
            "{next_chapter_number}", "{next_chapter_title}", "{next_chapter_role}",
            "{next_chapter_purpose}", "{next_chapter_suspense_level}",
            "{next_chapter_foreshadowing}", "{next_chapter_plot_twist_level}",
            "{next_chapter_summary}", "{filtered_context}", "{writing_style_instructions}"
        ]
    }
    # Add other prompts here
}

def build_prompts_tab(self):
    self.prompts_tab = self.tabview.add("自定义提示词")
    self.prompts_tab.grid_columnconfigure(0, weight=1)
    self.prompts_tab.grid_rowconfigure(2, weight=1) # Textbox row

    # --- Top Frame for selection and buttons ---
    top_frame = ctk.CTkFrame(self.prompts_tab)
    top_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
    top_frame.grid_columnconfigure(1, weight=1) # Allow prompt_selector to expand if needed

    prompt_select_label = ctk.CTkLabel(top_frame, text="选择提示词:", font=("Microsoft YaHei", 12))
    prompt_select_label.grid(row=0, column=0, padx=(0,5), pady=5, sticky="w")

    self.selected_prompt_key = ctk.StringVar()
    prompt_display_names = [config["display_name"] for config in EDITABLE_PROMPTS_CONFIG.values()]

    prompt_selector = ctk.CTkOptionMenu(
        top_frame,
        values=prompt_display_names,
        variable=self.selected_prompt_key,
        command=lambda choice: load_selected_prompt_to_editor(self, choice),
        font=("Microsoft YaHei", 12)
    )
    prompt_selector.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

    buttons_frame = ctk.CTkFrame(top_frame) # Frame for buttons to group them
    buttons_frame.grid(row=0, column=2, padx=(10,0), pady=5, sticky="e")

    load_default_btn = ctk.CTkButton(
        buttons_frame,
        text="加载默认",
        command=lambda: load_default_for_selected_prompt(self),
        font=("Microsoft YaHei", 12)
    )
    load_default_btn.pack(side="left", padx=(0,5))

    save_prompt_btn = ctk.CTkButton(
        buttons_frame,
        text="保存当前提示词",
        command=lambda: save_current_prompt_from_editor(self),
        font=("Microsoft YaHei", 12)
    )
    save_prompt_btn.pack(side="left")

    # --- Placeholder Info Label ---
    self.prompt_placeholders_label = ctk.CTkLabel(
        self.prompts_tab,
        text="请先选择一个提示词进行编辑。\n提示：占位符 (例如 {variable}) 是必需的，请勿删除或修改其名称，它们将被程序自动替换。",
        font=("Microsoft YaHei", 10),
        wraplength=self.prompts_tab.winfo_width() - 20, # Adjust wraplength
        justify="left"
    )
    self.prompt_placeholders_label.grid(row=1, column=0, padx=10, pady=5, sticky="w")
    self.prompts_tab.bind("<Configure>", lambda event: self.prompt_placeholders_label.configure(wraplength=event.width - 30))


    # --- Textbox for prompt editing ---
    self.prompt_editor_text = ctk.CTkTextbox(
        self.prompts_tab,
        wrap="word",
        font=("Microsoft YaHei", 12)
    )
    TextWidgetContextMenu(self.prompt_editor_text)
    self.prompt_editor_text.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")

    # Initialize with the first prompt if available
    if prompt_display_names:
        self.selected_prompt_key.set(prompt_display_names[0])
        load_selected_prompt_to_editor(self, prompt_display_names[0])
    else:
        self.prompt_editor_text.insert("0.0", "没有可配置的提示词。")
        self.prompt_editor_text.configure(state="disabled")
        prompt_selector.configure(state="disabled")
        load_default_btn.configure(state="disabled")
        save_prompt_btn.configure(state="disabled")

    self.log("自定义提示词界面已构建。")

def get_prompt_key_by_display_name(display_name):
    for key, config in EDITABLE_PROMPTS_CONFIG.items():
        if config["display_name"] == display_name:
            return key
    return None

def load_selected_prompt_to_editor(self, selected_display_name):
    prompt_key = get_prompt_key_by_display_name(selected_display_name)
    if not prompt_key:
        self.log(f"错误：未找到与显示名称 '{selected_display_name}' 匹配的提示词键。")
        self.prompt_editor_text.delete("0.0", "end")
        self.prompt_editor_text.insert("0.0", "错误：无法加载此提示词。")
        self.prompt_placeholders_label.configure(text="错误：无法加载此提示词的占位符信息。")
        return

    # Load custom prompt if available, otherwise default
    prompt_content = self.custom_prompts.get(prompt_key, "").strip()
    if not prompt_content:
        prompt_content = EDITABLE_PROMPTS_CONFIG[prompt_key]["default_prompt"]
        self.log(f"为 '{selected_display_name}' 加载了默认提示词。")
    else:
        self.log(f"为 '{selected_display_name}' 加载了自定义提示词。")

    self.prompt_editor_text.delete("0.0", "end")
    self.prompt_editor_text.insert("0.0", prompt_content)

    # Update placeholder info
    placeholders = EDITABLE_PROMPTS_CONFIG[prompt_key]["placeholders"]
    placeholder_text = "此提示词的关键占位符 (请勿修改或删除):\n" + "\n".join(placeholders)
    self.prompt_placeholders_label.configure(text=placeholder_text)


def load_default_for_selected_prompt(self):
    selected_display_name = self.selected_prompt_key.get()
    prompt_key = get_prompt_key_by_display_name(selected_display_name)
    if not prompt_key:
        messagebox.showerror("错误", f"无法加载默认提示词，因为选择的提示词 '{selected_display_name}' 无效。")
        return

    default_prompt = EDITABLE_PROMPTS_CONFIG[prompt_key]["default_prompt"]
    self.prompt_editor_text.delete("0.0", "end")
    self.prompt_editor_text.insert("0.0", default_prompt)
    self.log(f"已为 '{selected_display_name}' 加载默认提示词到编辑框。")

def save_current_prompt_from_editor(self):
    selected_display_name = self.selected_prompt_key.get()
    prompt_key = get_prompt_key_by_display_name(selected_display_name)
    if not prompt_key:
        messagebox.showerror("错误", f"无法保存提示词，因为选择的提示词 '{selected_display_name}' 无效。")
        return

    current_prompt_content = self.prompt_editor_text.get("0.0", "end-1c").strip()
    if not current_prompt_content:
        messagebox.showwarning("警告", "提示词内容不能为空。如果想恢复默认，请使用“加载默认”并保存。")
        return

    # Validate if all required placeholders are present (simple check)
    missing_placeholders = []
    required_placeholders = EDITABLE_PROMPTS_CONFIG[prompt_key]["placeholders"]
    for ph in required_placeholders:
        if ph not in current_prompt_content:
            missing_placeholders.append(ph)

    if missing_placeholders:
        msg = f"警告：当前编辑的提示词似乎缺少以下必需的占位符：\n{', '.join(missing_placeholders)}\n\n这可能导致程序在生成内容时出错。是否仍要保存？"
        if not messagebox.askyesno("缺少占位符", msg):
            return

    self.custom_prompts[prompt_key] = current_prompt_content
    self.save_config_btn() # This will save the entire config, including all custom_prompts
    # self.log(f"自定义提示词 '{selected_display_name}' 已更新。") # save_config_btn logs "配置已保存。"
    # messagebox.showinfo("成功", f"提示词 '{selected_display_name}' 已保存。") # save_config_btn shows its own success message
