# ui/config_tab.py
# -*- coding: utf-8 -*-
from tkinter import messagebox

import customtkinter as ctk

from config_manager import load_config, save_config
from tooltips import tooltips


def create_label_with_help(self, parent, label_text, tooltip_key, row, column,
                           font=None, sticky="e", padx=5, pady=5):
    """
    封装一个带"?"按钮的Label，用于展示提示信息。
    """
    frame = ctk.CTkFrame(parent)
    frame.grid(row=row, column=column, padx=padx, pady=pady, sticky=sticky)
    frame.columnconfigure(0, weight=0)

    label = ctk.CTkLabel(frame, text=label_text, font=font)
    label.pack(side="left")

    btn = ctk.CTkButton(
        frame,
        text="?",
        width=22,
        height=22,
        font=("Microsoft YaHei", 10),
        command=lambda: messagebox.showinfo("参数说明", tooltips.get(tooltip_key, "暂无说明"))
    )
    btn.pack(side="left", padx=3)

    return frame

def build_config_tabview(self):
    """
    创建包含 LLM Model settings 和 Embedding settings 的选项卡。
    """
    self.config_tabview = ctk.CTkTabview(self.config_frame)
    self.config_tabview.grid(row=0, column=0, sticky="we", padx=5, pady=5)

    self.ai_config_tab = self.config_tabview.add("LLM Model settings")
    self.embeddings_config_tab = self.config_tabview.add("Embedding settings")

    build_ai_config_tab(self)
    build_embeddings_config_tab(self)

    # 底部的"保存配置"和"加载配置"按钮
    self.btn_frame_config = ctk.CTkFrame(self.config_frame)
    self.btn_frame_config.grid(row=1, column=0, padx=5, pady=5, sticky="ew")
    self.btn_frame_config.columnconfigure(0, weight=1)
    self.btn_frame_config.columnconfigure(1, weight=1)

    save_config_btn = ctk.CTkButton(self.btn_frame_config, text="保存当前选择接口配置到文件", command=self.save_config_btn, font=("Microsoft YaHei", 12))
    save_config_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

    load_config_btn = ctk.CTkButton(self.btn_frame_config, text="加载当前选择接口配置到程序", command=self.load_config_btn, font=("Microsoft YaHei", 12))
    load_config_btn.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

def build_ai_config_tab(self):
    def on_interface_format_changed(new_value):
        self.interface_format_var.set(new_value)
        config_data = load_config(self.config_file)
        if config_data:
            config_data["last_interface_format"] = new_value
            save_config(config_data, self.config_file)
        if self.loaded_config and "llm_configs" in self.loaded_config and new_value in self.loaded_config["llm_configs"]:
            llm_conf = self.loaded_config["llm_configs"][new_value]
            self.api_key_var.set(llm_conf.get("api_key", ""))
            self.base_url_var.set(llm_conf.get("base_url", self.base_url_var.get()))
            self.model_name_var.set(llm_conf.get("model_name", ""))
            self.temperature_var.set(llm_conf.get("temperature", 0.7))
            self.max_tokens_var.set(llm_conf.get("max_tokens", 8192))
            self.timeout_var.set(llm_conf.get("timeout", 600))
        else:
            if new_value == "Ollama":
                self.base_url_var.set("http://localhost:11434/v1")
            elif new_value == "ML Studio":
                self.base_url_var.set("http://localhost:1234/v1")
            elif new_value == "OpenAI":
                self.base_url_var.set("https://api.openai.com/v1")
                self.model_name_var.set("gpt-4o-mini")
            elif new_value == "Azure OpenAI":
                self.base_url_var.set("https://[az].openai.azure.com/openai/deployments/[model]/chat/completions?api-version=2024-08-01-preview")
            elif new_value == "DeepSeek":
                self.base_url_var.set("https://api.deepseek.com/v1")
                self.model_name_var.set("deepseek-chat")
            elif new_value == "Gemini":
                self.base_url_var.set("")
            elif new_value == "Azure AI":
                self.base_url_var.set("https://<your-endpoint>.services.ai.azure.com/models/chat/completions?api-version=2024-05-01-preview")
            elif new_value == "阿里云百炼":
                self.base_url_var.set("https://dashscope.aliyuncs.com/compatible-mode/v1")
                self.model_name_var.set("qwen-plus")
            elif new_value == "硅基流动":
                self.base_url_var.set("https://api.siliconflow.cn/v1")
                self.model_name_var.set("deepseek-ai/DeepSeek-V3")
            elif new_value == "Grok":
                self.base_url_var.set("https://api.x.ai/v1")
                self.model_name_var.set("grok-3")

    for i in range(7):
        self.ai_config_tab.grid_rowconfigure(i, weight=0)
    self.ai_config_tab.grid_columnconfigure(0, weight=0)
    self.ai_config_tab.grid_columnconfigure(1, weight=1)
    self.ai_config_tab.grid_columnconfigure(2, weight=0)

    # 1) API Key
    create_label_with_help(self, parent=self.ai_config_tab, label_text="LLM API Key:", tooltip_key="api_key", row=0, column=0, font=("Microsoft YaHei", 12))
    api_key_entry = ctk.CTkEntry(self.ai_config_tab, textvariable=self.api_key_var, font=("Microsoft YaHei", 12),show="*")
    api_key_entry.grid(row=0, column=1, padx=5, pady=5, columnspan=2, sticky="nsew")

    # 2) Base URL
    create_label_with_help(self, parent=self.ai_config_tab, label_text="LLM Base URL:", tooltip_key="base_url", row=1, column=0, font=("Microsoft YaHei", 12))
    base_url_entry = ctk.CTkEntry(self.ai_config_tab, textvariable=self.base_url_var, font=("Microsoft YaHei", 12))
    base_url_entry.grid(row=1, column=1, padx=5, pady=5, columnspan=2, sticky="nsew")

    # 3) 接口格式
    create_label_with_help(self, parent=self.ai_config_tab, label_text="LLM 接口格式:", tooltip_key="interface_format", row=2, column=0, font=("Microsoft YaHei", 12))
    # 在接口选项列表中添加 "Grok"
    interface_options = ["DeepSeek", "阿里云百炼", "OpenAI", "Azure OpenAI", "Azure AI", "Ollama", "ML Studio", "Gemini", "火山引擎", "硅基流动", "Grok"]
    interface_dropdown = ctk.CTkOptionMenu(self.ai_config_tab, values=interface_options, variable=self.interface_format_var, command=on_interface_format_changed, font=("Microsoft YaHei", 12))
    interface_dropdown.grid(row=2, column=1, padx=5, pady=5, columnspan=2, sticky="nsew")

    # 4) Model Name
    create_label_with_help(self, parent=self.ai_config_tab, label_text="Model Name:", tooltip_key="model_name", row=3, column=0, font=("Microsoft YaHei", 12))
    model_name_entry = ctk.CTkEntry(self.ai_config_tab, textvariable=self.model_name_var, font=("Microsoft YaHei", 12))
    model_name_entry.grid(row=3, column=1, padx=5, pady=5, columnspan=2, sticky="nsew")

    # 5) Temperature
    create_label_with_help(self, parent=self.ai_config_tab, label_text="Temperature:", tooltip_key="temperature", row=4, column=0, font=("Microsoft YaHei", 12))
    def update_temp_label(value):
        self.temp_value_label.configure(text=f"{float(value):.2f}")
    temp_scale = ctk.CTkSlider(self.ai_config_tab, from_=0.0, to=2.0, number_of_steps=200, command=update_temp_label, variable=self.temperature_var)
    temp_scale.grid(row=4, column=1, padx=5, pady=5, sticky="we")
    self.temp_value_label = ctk.CTkLabel(self.ai_config_tab, text=f"{self.temperature_var.get():.2f}", font=("Microsoft YaHei", 12))
    self.temp_value_label.grid(row=4, column=2, padx=5, pady=5, sticky="w")

    # 6) Max Tokens
    create_label_with_help(self, parent=self.ai_config_tab, label_text="Max Tokens:", tooltip_key="max_tokens", row=5, column=0, font=("Microsoft YaHei", 12))
    def update_max_tokens_label(value):
        self.max_tokens_value_label.configure(text=str(int(float(value))))
    max_tokens_slider = ctk.CTkSlider(self.ai_config_tab, from_=0, to=102400, number_of_steps=100, command=update_max_tokens_label, variable=self.max_tokens_var)
    max_tokens_slider.grid(row=5, column=1, padx=5, pady=5, sticky="we")
    self.max_tokens_value_label = ctk.CTkLabel(self.ai_config_tab, text=str(self.max_tokens_var.get()), font=("Microsoft YaHei", 12))
    self.max_tokens_value_label.grid(row=5, column=2, padx=5, pady=5, sticky="w")

    # 7) Timeout (sec)
    create_label_with_help(self, parent=self.ai_config_tab, label_text="Timeout (sec):", tooltip_key="timeout", row=6, column=0, font=("Microsoft YaHei", 12))
    def update_timeout_label(value):
        integer_val = int(float(value))
        self.timeout_value_label.configure(text=str(integer_val))
    timeout_slider = ctk.CTkSlider(self.ai_config_tab, from_=0, to=3600, number_of_steps=3600, command=update_timeout_label, variable=self.timeout_var)
    timeout_slider.grid(row=6, column=1, padx=5, pady=5, sticky="we")
    self.timeout_value_label = ctk.CTkLabel(self.ai_config_tab, text=str(self.timeout_var.get()), font=("Microsoft YaHei", 12))
    self.timeout_value_label.grid(row=6, column=2, padx=5, pady=5, sticky="w")

    # 添加测试按钮
    test_btn = ctk.CTkButton(self.ai_config_tab, text="测试配置", command=self.test_llm_config, font=("Microsoft YaHei", 12))
    test_btn.grid(row=7, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

def build_embeddings_config_tab(self):
    def on_embedding_interface_changed(new_value):
        self.embedding_interface_format_var.set(new_value)
        config_data = load_config(self.config_file)
        if config_data:
            config_data["last_embedding_interface_format"] = new_value
            save_config(config_data, self.config_file)
        if self.loaded_config and "embedding_configs" in self.loaded_config and new_value in self.loaded_config["embedding_configs"]:
            emb_conf = self.loaded_config["embedding_configs"][new_value]
            self.embedding_api_key_var.set(emb_conf.get("api_key", ""))
            self.embedding_url_var.set(emb_conf.get("base_url", self.embedding_url_var.get()))
            self.embedding_model_name_var.set(emb_conf.get("model_name", ""))
            self.embedding_retrieval_k_var.set(str(emb_conf.get("retrieval_k", 4)))
        else:
            if new_value == "Ollama":
                self.embedding_url_var.set("http://localhost:11434/api")
            elif new_value == "ML Studio":
                self.embedding_url_var.set("http://localhost:1234/v1")
            elif new_value == "OpenAI":
                self.embedding_url_var.set("https://api.openai.com/v1")
                self.embedding_model_name_var.set("text-embedding-ada-002")
            elif new_value == "Azure OpenAI":
                self.embedding_url_var.set("https://[az].openai.azure.com/openai/deployments/[model]/embeddings?api-version=2023-05-15")
            elif new_value == "DeepSeek":
                self.embedding_url_var.set("https://api.deepseek.com/v1")
            elif new_value == "Gemini":
                self.embedding_url_var.set("https://generativelanguage.googleapis.com/v1beta/")
                self.embedding_model_name_var.set("models/text-embedding-004")
            elif new_value == "SiliconFlow":
                self.embedding_url_var.set("https://api.siliconflow.cn/v1/embeddings")
                self.embedding_model_name_var.set("BAAI/bge-m3")

    for i in range(5):
        self.embeddings_config_tab.grid_rowconfigure(i, weight=0)
    self.embeddings_config_tab.grid_columnconfigure(0, weight=0)
    self.embeddings_config_tab.grid_columnconfigure(1, weight=1)
    self.embeddings_config_tab.grid_columnconfigure(2, weight=0)

    # 1) Embedding API Key
    create_label_with_help(self, parent=self.embeddings_config_tab, label_text="Embedding API Key:", tooltip_key="embedding_api_key", row=0, column=0, font=("Microsoft YaHei", 12))
    emb_api_key_entry = ctk.CTkEntry(self.embeddings_config_tab, textvariable=self.embedding_api_key_var, font=("Microsoft YaHei", 12))
    emb_api_key_entry.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

    # 2) Embedding 接口格式
    create_label_with_help(self, parent=self.embeddings_config_tab, label_text="Embedding 接口格式:", tooltip_key="embedding_interface_format", row=1, column=0, font=("Microsoft YaHei", 12))

    emb_interface_options = ["DeepSeek", "OpenAI", "Azure OpenAI", "Gemini", "Ollama", "ML Studio","SiliconFlow"]

    emb_interface_dropdown = ctk.CTkOptionMenu(self.embeddings_config_tab, values=emb_interface_options, variable=self.embedding_interface_format_var, command=on_embedding_interface_changed, font=("Microsoft YaHei", 12))
    emb_interface_dropdown.grid(row=1, column=1, padx=5, pady=5, sticky="nsew")

    # 3) Embedding Base URL
    create_label_with_help(self, parent=self.embeddings_config_tab, label_text="Embedding Base URL:", tooltip_key="embedding_url", row=2, column=0, font=("Microsoft YaHei", 12))
    emb_url_entry = ctk.CTkEntry(self.embeddings_config_tab, textvariable=self.embedding_url_var, font=("Microsoft YaHei", 12))
    emb_url_entry.grid(row=2, column=1, padx=5, pady=5, sticky="nsew")

    # 4) Embedding Model Name
    create_label_with_help(self, parent=self.embeddings_config_tab, label_text="Embedding Model Name:", tooltip_key="embedding_model_name", row=3, column=0, font=("Microsoft YaHei", 12))
    emb_model_name_entry = ctk.CTkEntry(self.embeddings_config_tab, textvariable=self.embedding_model_name_var, font=("Microsoft YaHei", 12))
    emb_model_name_entry.grid(row=3, column=1, padx=5, pady=5, sticky="nsew")

    # 5) Retrieval Top-K
    create_label_with_help(self, parent=self.embeddings_config_tab, label_text="Retrieval Top-K:", tooltip_key="embedding_retrieval_k", row=4, column=0, font=("Microsoft YaHei", 12))
    emb_retrieval_k_entry = ctk.CTkEntry(self.embeddings_config_tab, textvariable=self.embedding_retrieval_k_var, font=("Microsoft YaHei", 12))
    emb_retrieval_k_entry.grid(row=4, column=1, padx=5, pady=5, sticky="nsew")

    # 添加测试按钮
    test_btn = ctk.CTkButton(self.embeddings_config_tab, text="测试配置", command=self.test_embedding_config, font=("Microsoft YaHei", 12))
    test_btn.grid(row=5, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

def load_config_btn(self):
    cfg = load_config(self.config_file)
    if cfg:
        last_llm = cfg.get("last_interface_format", "OpenAI")
        last_embedding = cfg.get("last_embedding_interface_format", "OpenAI")
        self.interface_format_var.set(last_llm)
        self.embedding_interface_format_var.set(last_embedding)
        llm_configs = cfg.get("llm_configs", {})
        if last_llm in llm_configs:
            llm_conf = llm_configs[last_llm]
            self.api_key_var.set(llm_conf.get("api_key", ""))
            self.base_url_var.set(llm_conf.get("base_url", "https://api.openai.com/v1"))
            self.model_name_var.set(llm_conf.get("model_name", "gpt-4o-mini"))
            self.temperature_var.set(llm_conf.get("temperature", 0.7))
            self.max_tokens_var.set(llm_conf.get("max_tokens", 8192))
            self.timeout_var.set(llm_conf.get("timeout", 600))
        embedding_configs = cfg.get("embedding_configs", {})
        if last_embedding in embedding_configs:
            emb_conf = embedding_configs[last_embedding]
            self.embedding_api_key_var.set(emb_conf.get("api_key", ""))
            self.embedding_url_var.set(emb_conf.get("base_url", "https://api.openai.com/v1"))
            self.embedding_model_name_var.set(emb_conf.get("model_name", "text-embedding-ada-002"))
            self.embedding_retrieval_k_var.set(str(emb_conf.get("retrieval_k", 4)))
        other_params = cfg.get("other_params", {})
        self.topic_text.delete("0.0", "end")
        self.topic_text.insert("0.0", other_params.get("topic", ""))
        self.genre_var.set(other_params.get("genre", "玄幻"))
        self.num_chapters_var.set(str(other_params.get("num_chapters", 10)))
        self.word_number_var.set(str(other_params.get("word_number", 3000)))
        self.filepath_var.set(other_params.get("filepath", ""))
        self.chapter_num_var.set(str(other_params.get("chapter_num", "1")))
        self.user_guide_text.delete("0.0", "end")
        self.user_guide_text.insert("0.0", other_params.get("user_guidance", ""))
        self.characters_involved_var.set(other_params.get("characters_involved", ""))
        self.key_items_var.set(other_params.get("key_items", ""))
        self.scene_location_var.set(other_params.get("scene_location", ""))
        self.time_constraint_var.set(other_params.get("time_constraint", ""))
        self.log("已加载配置。")
    else:
        messagebox.showwarning("提示", "未找到或无法读取配置文件。")

def save_config_btn(self):
    current_llm_interface = self.interface_format_var.get().strip()
    current_embedding_interface = self.embedding_interface_format_var.get().strip()
    llm_config = {
        "api_key": self.api_key_var.get(),
        "base_url": self.base_url_var.get(),
        "model_name": self.model_name_var.get(),
        "temperature": self.temperature_var.get(),
        "max_tokens": self.max_tokens_var.get(),
        "timeout": self.safe_get_int(self.timeout_var, 600)
    }
    embedding_config = {
        "api_key": self.embedding_api_key_var.get(),
        "base_url": self.embedding_url_var.get(),
        "model_name": self.embedding_model_name_var.get(),
        "retrieval_k": self.safe_get_int(self.embedding_retrieval_k_var, 4)
    }
    other_params = {
        "topic": self.topic_text.get("0.0", "end").strip(),
        "genre": self.genre_var.get(),
        "num_chapters": self.safe_get_int(self.num_chapters_var, 10),
        "word_number": self.safe_get_int(self.word_number_var, 3000),
        "filepath": self.filepath_var.get(),
        "chapter_num": self.chapter_num_var.get(),
        "user_guidance": self.user_guide_text.get("0.0", "end").strip(),
        "characters_involved": self.characters_involved_var.get(),
        "key_items": self.key_items_var.get(),
        "scene_location": self.scene_location_var.get(),
        "time_constraint": self.time_constraint_var.get()
    }
    existing_config = load_config(self.config_file)
    if not existing_config:
        existing_config = {}
    existing_config["last_interface_format"] = current_llm_interface
    existing_config["last_embedding_interface_format"] = current_embedding_interface
    if "llm_configs" not in existing_config:
        existing_config["llm_configs"] = {}
    existing_config["llm_configs"][current_llm_interface] = llm_config

    if "embedding_configs" not in existing_config:
        existing_config["embedding_configs"] = {}
    existing_config["embedding_configs"][current_embedding_interface] = embedding_config

    existing_config["other_params"] = other_params

    if save_config(existing_config, self.config_file):
        messagebox.showinfo("提示", "配置已保存至 config.json")
        self.log("配置已保存。")
    else:
        messagebox.showerror("错误", "保存配置失败。")