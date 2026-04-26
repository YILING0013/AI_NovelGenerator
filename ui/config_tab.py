# ui/config_tab.py
# -*- coding: utf-8 -*-
from tkinter import messagebox
import uuid
import datetime

import customtkinter as ctk

from config_manager import load_config, save_config
from tooltips import tooltips

import os


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
    self.config_choose = self.config_tabview.add("Config choose")

    # PenBo 增加代理功能支持
    self.proxy_setting_tab = self.config_tabview.add("Proxy setting")


    build_ai_config_tab(self)
    build_embeddings_config_tab(self)
    build_config_choose_tab(self)

    # PenBo 增加代理功能支持
    build_proxy_setting_tab(self)

def build_ai_config_tab(self):
    def refresh_config_dropdown():
        """刷新配置下拉菜单"""
        config_names = list(self.loaded_config.get("llm_configs", {}).keys())
        interface_config_dropdown.configure(values=config_names)
        if config_names and self.interface_config_var.get() not in config_names:
            self.interface_config_var.set(config_names[0])

    def on_config_selected(new_value):
        """当选择不同配置时的回调"""
        if new_value in self.loaded_config.get("llm_configs", {}):
            config = self.loaded_config["llm_configs"][new_value]
            # 更新所有UI变量
            self.api_key_var.set(config.get("api_key", ""))
            self.base_url_var.set(config.get("base_url", ""))
            self.model_name_var.set(config.get("model_name", ""))
            self.temperature_var.set(float(config.get("temperature", 0.7)))
            self.max_tokens_var.set(int(config.get("max_tokens", 8192)))
            self.timeout_var.set(int(config.get("timeout", 600)))
            self.interface_format_var.set(config.get("interface_format", "OpenAI"))
            
            # 更新显示标签
            self.temp_value_label.configure(text=f"{float(config.get('temperature', 0.7)):.2f}")
            self.max_tokens_value_label.configure(text=str(int(config.get('max_tokens', 8192))))
            self.timeout_value_label.configure(text=str(int(config.get('timeout', 600))))

    def add_new_config():
        """添加新配置 - 弹出对话框让用户输入名称"""
        dialog = ctk.CTkInputDialog(
            text="请输入新配置名称:",
            title="新增配置"
        )
        new_name = dialog.get_input()
        
        if not new_name:
            return
            
        new_name = new_name.strip()
        
        if new_name in self.loaded_config.get("llm_configs", {}):
            messagebox.showerror("错误", f"配置名称 '{new_name}' 已存在!")
            return
            
        if "llm_configs" not in self.loaded_config:
            self.loaded_config["llm_configs"] = {}
            
        self.loaded_config["llm_configs"][new_name] = {
            "id": str(uuid.uuid4()),
            "api_key": "",
            "base_url": "",
            "model_name": "",
            "temperature": 0.7,
            "max_tokens": 8192,
            "timeout": 600,
            "interface_format": "OpenAI",
            "created_at": datetime.datetime.now().isoformat()
        }
        
        refresh_config_dropdown()
        self.interface_config_var.set(new_name)
        messagebox.showinfo("提示", f"已成功创建新配置: {new_name}")

    def delete_current_config():
        """删除当前选中的配置并保存到JSON文件"""
        selected_config = self.interface_config_var.get()
        if selected_config in self.loaded_config.get("llm_configs", {}):
            if len(self.loaded_config["llm_configs"]) <= 1:
                messagebox.showerror("错误", "至少需要保留一个配置!")
                return
                
            confirm = messagebox.askyesno(
            "确认删除",
            f"确定要删除配置 '{selected_config}' 吗?\n此操作不可撤销!"
        )
        if not confirm:
            return
            
        del self.loaded_config["llm_configs"][selected_config]
        refresh_config_dropdown()
        
        # 保存到JSON文件
        try:
            save_config(self.loaded_config, self.config_file)
            messagebox.showinfo("提示", f"已删除配置: {selected_config}，并已更新配置文件")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置文件失败: {str(e)}")
        else:
            messagebox.showerror("错误", "未找到选中的配置!")

    def save_current_config():
        """保存当前配置的修改到JSON文件"""
        config_name = self.interface_config_var.get()
        if config_name not in self.loaded_config.get("llm_configs", {}):
            messagebox.showerror("错误", "配置不存在!")
            return
            
        config = self.loaded_config["llm_configs"][config_name]
        config.update({
            "api_key": self.api_key_var.get(),
            "base_url": self.base_url_var.get(),
            "model_name": self.model_name_var.get(),
            "temperature": float(self.temperature_var.get()),
            "max_tokens": int(self.max_tokens_var.get()),
            "timeout": int(self.timeout_var.get()),
            "interface_format": self.interface_format_var.get(),
            "updated_at": datetime.datetime.now().isoformat()
        })
        
        # 如果修改了配置名称
        new_name = self.interface_config_var.get()
        if new_name != config_name:
            self.loaded_config["llm_configs"][new_name] = self.loaded_config["llm_configs"].pop(config_name)
            refresh_config_dropdown()
        embedding_config = {
        "api_key": self.embedding_api_key_var.get(),
        "base_url": self.embedding_url_var.get(),
        "model_name": self.embedding_model_name_var.get(),
        "retrieval_k": self.safe_get_int(self.embedding_retrieval_k_var, 4),
        "interface_format": self.embedding_interface_format_var.get().strip()

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
        self.loaded_config["embedding_configs"][self.embedding_interface_format_var.get().strip()] = embedding_config
        self.loaded_config["other_params"] = other_params


        # 保存到JSON文件
        try:
            save_config(self.loaded_config, self.config_file)
            messagebox.showinfo("提示", f"配置 {new_name} 已保存并持久化到文件")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置文件失败: {str(e)}")

    def rename_current_config():
        """重命名当前配置"""
        old_name = self.interface_config_var.get()
        if old_name not in self.loaded_config.get("llm_configs", {}):
            messagebox.showerror("错误", "当前配置不存在!")
            return
            
        dialog = ctk.CTkInputDialog(
            text=f"请输入新的配置名称 (原名称: {old_name}):",
            title="重命名配置"
        )
        new_name = dialog.get_input()
        
        if not new_name:
            return
            
        new_name = new_name.strip()
        
        if new_name == old_name:
            return
            
        if new_name in self.loaded_config.get("llm_configs", {}):
            messagebox.showerror("错误", f"配置名称 '{new_name}' 已存在!")
            return
            
        # 更新配置名称
        self.loaded_config["llm_configs"][new_name] = self.loaded_config["llm_configs"].pop(old_name)
        self.interface_config_var.set(new_name)
        refresh_config_dropdown()

        messagebox.showinfo("提示", f"配置已从 '{old_name}' 重命名为 '{new_name}'")

    # 初始化UI布局
    for i in range(10):
        self.ai_config_tab.grid_rowconfigure(i, weight=0)
    self.ai_config_tab.grid_columnconfigure(0, weight=0)
    self.ai_config_tab.grid_columnconfigure(1, weight=1)
    self.ai_config_tab.grid_columnconfigure(2, weight=0)

    # 配置选择控件
    create_label_with_help(self, self.ai_config_tab, "当前配置", "interface_config", 0, 0)
    config_names = list(self.loaded_config.get("llm_configs", {}).keys())
    if not config_names:
        self.loaded_config["llm_configs"] = {
            "默认配置": {
                "id": str(uuid.uuid4()),
                "api_key": "",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-4",
                "temperature": 0.7,
                "max_tokens": 8192,
                "timeout": 600,
                "interface_format": "OpenAI",
                "created_at": datetime.datetime.now().isoformat()
            }
        }
        config_names = ["默认配置"]
    
    self.interface_config_var = ctk.StringVar(value=config_names[0])

    interface_config_dropdown = ctk.CTkOptionMenu(
        self.ai_config_tab, 
        values=config_names,
        variable=self.interface_config_var,
        command=on_config_selected,
        font=("Microsoft YaHei", 12)
    )
    interface_config_dropdown.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky="nsew")

    # 配置管理按钮组
    btn_frame = ctk.CTkFrame(self.ai_config_tab)
    btn_frame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
    btn_frame.columnconfigure(0, weight=1)
    btn_frame.columnconfigure(1, weight=1)
    btn_frame.columnconfigure(2, weight=1)
    btn_frame.columnconfigure(3, weight=1)

    add_btn = ctk.CTkButton(
        btn_frame, 
        text="➕ 新增", 
        command=add_new_config,
        font=("Microsoft YaHei", 12),
        fg_color="#2E8B57",
        width=80
    )
    add_btn.grid(row=0, column=0, padx=2, pady=2, sticky="ew")

    rename_btn = ctk.CTkButton(
        btn_frame, 
        text="✏️ 重命名", 
        command=rename_current_config,
        font=("Microsoft YaHei", 12),
        fg_color="#DAA520",
        width=80
    )
    rename_btn.grid(row=0, column=1, padx=2, pady=2, sticky="ew")

    del_btn = ctk.CTkButton(
        btn_frame, 
        text="🗑️ 删除", 
        command=delete_current_config,
        font=("Microsoft YaHei", 12),
        fg_color="#8B0000",
        width=80
    )
    del_btn.grid(row=0, column=2, padx=2, pady=2, sticky="ew")

    save_btn = ctk.CTkButton(
        btn_frame, 
        text="💾 保存", 
        command=save_current_config,
        font=("Microsoft YaHei", 12),
        fg_color="#1E90FF",
        width=80
    )
    save_btn.grid(row=0, column=3, padx=2, pady=2, sticky="ew")

    # 配置参数控件
    row_start = 2
    # 1) API Key
    create_label_with_help(self, self.ai_config_tab, "API Key:", "api_key", row_start, 0)
    self.api_key_var = ctk.StringVar(value="")
    api_key_entry = ctk.CTkEntry(
        self.ai_config_tab, 
        textvariable=self.api_key_var,
        font=("Microsoft YaHei", 12),
        show="*"
    )
    api_key_entry.grid(row=row_start, column=1, columnspan=2, padx=5, pady=5, sticky="nsew")
    
    # 2) Base URL
    create_label_with_help(self, self.ai_config_tab, "Base URL:", "base_url", row_start+1, 0)
    self.base_url_var = ctk.StringVar(value="")
    base_url_entry = ctk.CTkEntry(
        self.ai_config_tab, 
        textvariable=self.base_url_var,
        font=("Microsoft YaHei", 12)
    )
    base_url_entry.grid(row=row_start+1, column=1, columnspan=2, padx=5, pady=5, sticky="nsew")
    
    # 3) 接口格式
    create_label_with_help(self, self.ai_config_tab, "接口格式:", "interface_format", row_start+2, 0)
    self.interface_format_var = ctk.StringVar(value="OpenAI")
    interface_options = ["OpenAI", "Azure OpenAI", "Ollama", "DeepSeek", "Gemini", "ML Studio"]
    interface_dropdown = ctk.CTkOptionMenu(
        self.ai_config_tab,
        values=interface_options,
        variable=self.interface_format_var,
        font=("Microsoft YaHei", 12)
    )
    interface_dropdown.grid(row=row_start+2, column=1, columnspan=2, padx=5, pady=5, sticky="nsew")
    
    # 4) Model Name
    create_label_with_help(self, self.ai_config_tab, "模型名称:", "model_name", row_start+3, 0)
    self.model_name_var = ctk.StringVar(value="")
    model_name_entry = ctk.CTkEntry(
        self.ai_config_tab, 
        textvariable=self.model_name_var,
        font=("Microsoft YaHei", 12)
    )
    model_name_entry.grid(row=row_start+3, column=1, columnspan=2, padx=5, pady=5, sticky="nsew")
    
    # 5) Temperature
    create_label_with_help(self, self.ai_config_tab, "Temperature:", "temperature", row_start+4, 0)
    self.temperature_var = ctk.DoubleVar(value=0.7)
    def update_temp_label(value):
        self.temp_value_label.configure(text=f"{float(value):.2f}")
    temp_scale = ctk.CTkSlider(
        self.ai_config_tab, 
        from_=0.0, 
        to=2.0, 
        number_of_steps=200, 
        command=update_temp_label,
        variable=self.temperature_var
    )
    temp_scale.grid(row=row_start+4, column=1, padx=5, pady=5, sticky="we")
    self.temp_value_label = ctk.CTkLabel(
        self.ai_config_tab, 
        text=f"{self.temperature_var.get():.2f}",
        font=("Microsoft YaHei", 12)
    )
    self.temp_value_label.grid(row=row_start+4, column=2, padx=5, pady=5, sticky="w")
    
    # 6) Max Tokens
    create_label_with_help(self, self.ai_config_tab, "Max Tokens:", "max_tokens", row_start+5, 0)
    self.max_tokens_var = ctk.IntVar(value=8192)
    def update_max_tokens_label(value):
        self.max_tokens_value_label.configure(text=str(int(float(value))))
    max_tokens_slider = ctk.CTkSlider(
        self.ai_config_tab, 
        from_=0, 
        to=102400, 
        number_of_steps=100, 
        command=update_max_tokens_label,
        variable=self.max_tokens_var
    )
    max_tokens_slider.grid(row=row_start+5, column=1, padx=5, pady=5, sticky="we")
    self.max_tokens_value_label = ctk.CTkLabel(
        self.ai_config_tab, 
        text=str(self.max_tokens_var.get()),
        font=("Microsoft YaHei", 12)
    )
    self.max_tokens_value_label.grid(row=row_start+5, column=2, padx=5, pady=5, sticky="w")
    
    # 7) Timeout
    create_label_with_help(self, self.ai_config_tab, "Timeout (sec):", "timeout", row_start+6, 0)
    self.timeout_var = ctk.IntVar(value=600)
    def update_timeout_label(value):
        self.timeout_value_label.configure(text=str(int(float(value))))
    timeout_slider = ctk.CTkSlider(
        self.ai_config_tab, 
        from_=0, 
        to=3600, 
        number_of_steps=3600, 
        command=update_timeout_label,
        variable=self.timeout_var
    )
    timeout_slider.grid(row=row_start+6, column=1, padx=5, pady=5, sticky="we")
    self.timeout_value_label = ctk.CTkLabel(
        self.ai_config_tab, 
        text=str(self.timeout_var.get()),
        font=("Microsoft YaHei", 12)
    )
    self.timeout_value_label.grid(row=row_start+6, column=2, padx=5, pady=5, sticky="w")
    
    # 测试按钮
    test_btn = ctk.CTkButton(
        self.ai_config_tab, 
        text="测试配置", 
        command=self.test_llm_config,
        font=("Microsoft YaHei", 12)
    )
    test_btn.grid(row=row_start+7, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

    # 初始化当前配置
    on_config_selected(config_names[0])


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
    emb_api_key_entry = ctk.CTkEntry(self.embeddings_config_tab, textvariable=self.embedding_api_key_var, font=("Microsoft YaHei", 12), show="*")
    emb_api_key_entry.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

    # 2) Embedding 接口格式
    create_label_with_help(self, parent=self.embeddings_config_tab, label_text="Embedding 接口格式:", tooltip_key="embedding_intexrface_format", row=1, column=0, font=("Microsoft YaHei", 12))

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

def build_config_choose_tab(self):


    self.config_choose.grid_rowconfigure(0, weight=0)
    self.config_choose.grid_columnconfigure(0, weight=0)
    self.config_choose.grid_columnconfigure(1, weight=1)
    config_choose_options = list(self.loaded_config.get("llm_configs", {}).keys())
    create_label_with_help(self, parent=self.config_choose, label_text="生成架构所用大模型", tooltip_key="architecture_llm_config", row=0, column=0, font=("Microsoft YaHei", 12))
    architecture_dropdown = ctk.CTkOptionMenu(self.config_choose, values=config_choose_options, variable=self.architecture_llm_var, font=("Microsoft YaHei", 12))
    architecture_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

    create_label_with_help(self, parent=self.config_choose, label_text="生成大目录所用大模型", tooltip_key="chapter_outline_llm_config", row=1, column=0, font=("Microsoft YaHei", 12))
    chapter_outline_dropdown = ctk.CTkOptionMenu(self.config_choose, values=config_choose_options, variable=self.chapter_outline_llm_var, font=("Microsoft YaHei", 12))
    chapter_outline_dropdown.grid(row=1, column=1, padx=5, pady=5, sticky="nsew")

    create_label_with_help(self, parent=self.config_choose, label_text="生成草稿所用大模型", tooltip_key="prompt_draft_llm_config", row=2, column=0, font=("Microsoft YaHei", 12))
    prompt_draft_dropdown = ctk.CTkOptionMenu(self.config_choose, values=config_choose_options, variable=self.prompt_draft_llm_var, font=("Microsoft YaHei", 12))
    prompt_draft_dropdown.grid(row=2, column=1, padx=5, pady=5, sticky="nsew")

    create_label_with_help(self, parent=self.config_choose, label_text="定稿章节所用大模型", tooltip_key="final_chapter_llm_config", row=3, column=0, font=("Microsoft YaHei", 12))
    final_chapter_dropdown = ctk.CTkOptionMenu(self.config_choose, values=config_choose_options, variable=self.final_chapter_llm_var, font=("Microsoft YaHei", 12))
    final_chapter_dropdown.grid(row=3, column=1, padx=5, pady=5, sticky="nsew")

    create_label_with_help(self, parent=self.config_choose, label_text="一致性审校所用大模型", tooltip_key="consistency_review_llm_config", row=4, column=0, font=("Microsoft YaHei", 12))
    consistency_review_dropdown = ctk.CTkOptionMenu(self.config_choose, values=config_choose_options, variable=self.consistency_review_llm_var, font=("Microsoft YaHei", 12))
    consistency_review_dropdown.grid(row=4, column=1, padx=5, pady=5, sticky="nsew")

    def save_config_choose():
        config_data = load_config(self.config_file)["choose_configs"]
        if not config_data:
            config_data = {}
        config_data["architecture_llm"] = self.architecture_llm_var.get()
        config_data["chapter_outline_llm"] = self.chapter_outline_llm_var.get()
        config_data["prompt_draft_llm"] = self.prompt_draft_llm_var.get()
        config_data["final_chapter_llm"] = self.final_chapter_llm_var.get()
        config_data["consistency_review_llm"] = self.consistency_review_llm_var.get()


        config_data_full = load_config(self.config_file)
        config_data_full["choose_configs"] = config_data
        save_config(config_data_full, self.config_file)
        messagebox.showinfo("提示", "配置已保存。")

    def refresh_config_dropdowns():
        """刷新所有配置下拉菜单"""
        config_names = list(self.loaded_config.get("llm_configs", {}).keys())
        for dropdown in [architecture_dropdown, chapter_outline_dropdown, prompt_draft_dropdown, final_chapter_dropdown, consistency_review_dropdown]:
            dropdown.configure(values=config_names)
            if config_names and dropdown.cget("variable").get() not in config_names:
                dropdown.cget("variable").set(config_names[0])

    save_btn = ctk.CTkButton(
        self.config_choose, 
        text="保存配置", 
        command=save_config_choose,
        font=("Microsoft YaHei", 12)
    )
    save_btn.grid(row=10, column=0,padx=2, pady=2, sticky="ew")

    refresh_btn = ctk.CTkButton(
        self.config_choose, 
        text="刷新配置", 
        command=refresh_config_dropdowns,
        font=("Microsoft YaHei", 12)
    )
    refresh_btn.grid(row=10, column=1, padx=2, pady=2, sticky="ew")



# PenBo 增加代理功能支持
def build_proxy_setting_tab(self):
    # 代理设置标签页布局
    for i in range(5):
        self.proxy_setting_tab.grid_rowconfigure(i, weight=0)
    self.proxy_setting_tab.grid_columnconfigure(0, weight=0)
    self.proxy_setting_tab.grid_columnconfigure(1, weight=1)

    # 从配置文件加载代理设置
    config_data = load_config(self.config_file)
    proxy_setting = config_data.get("proxy_setting", {})
    
    # 代理启用开关
    create_label_with_help(self, self.proxy_setting_tab, "启用代理:", "proxy_enabled", 0, 0)
    self.proxy_enabled_var = ctk.BooleanVar(value=proxy_setting.get("enabled", False))
    proxy_enabled_switch = ctk.CTkSwitch(
        self.proxy_setting_tab,
        text="",
        variable=self.proxy_enabled_var,
        onvalue=True,
        offvalue=False,
        font=("Microsoft YaHei", 12)
    )
    proxy_enabled_switch.grid(row=0, column=1, padx=5, pady=5, sticky="w")

    # 地址输入框
    create_label_with_help(self, self.proxy_setting_tab, "地址:", "proxy_address", 1, 0)
    self.proxy_address_var = ctk.StringVar(value=proxy_setting.get("proxy_url", "127.0.0.1"))
    proxy_address_entry = ctk.CTkEntry(
        self.proxy_setting_tab,
        textvariable=self.proxy_address_var,
        font=("Microsoft YaHei", 12)
    )
    proxy_address_entry.grid(row=1, column=1, padx=5, pady=5, sticky="nsew")

    # 端口输入框
    create_label_with_help(self, self.proxy_setting_tab, "端口:", "proxy_port", 2, 0)
    self.proxy_port_var = ctk.StringVar(value=proxy_setting.get("proxy_port", "10809"))
    proxy_port_entry = ctk.CTkEntry(
        self.proxy_setting_tab,
        textvariable=self.proxy_port_var,
        font=("Microsoft YaHei", 12)
    )
    proxy_port_entry.grid(row=2, column=1, padx=5, pady=5, sticky="nsew")


    def open_proxy(address, port):
        """启动代理"""
        # 设置环境变量
        os.environ['HTTP_PROXY'] = f"http://{address}:{port}"
        os.environ['HTTPS_PROXY'] = f"http://{address}:{port}"

    def save_proxy_setting():
        config_data = load_config(self.config_file)
        if "proxy_setting" not in config_data:
            config_data["proxy_setting"] = {}
            
        config_data["proxy_setting"]["enabled"] = self.proxy_enabled_var.get()
        config_data["proxy_setting"]["proxy_url"] = self.proxy_address_var.get()
        config_data["proxy_setting"]["proxy_port"] = self.proxy_port_var.get()

        save_config(config_data, self.config_file)
        messagebox.showinfo("提示", "代理配置已保存。")

        if self.proxy_enabled_var.get():
            open_proxy(self.proxy_address_var.get(), self.proxy_port_var.get())
        else:
            os.environ.pop('HTTP_PROXY', None)
            os.environ.pop('HTTPS_PROXY', None)

    # 添加保存按钮
    save_btn = ctk.CTkButton(
        self.proxy_setting_tab,
        text="保存代理设置",
        command=save_proxy_setting,
        font=("Microsoft YaHei", 12)
    )
    save_btn.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="ew")


    

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
            self.interface_format_var.set(llm_conf.get("interface_format", "OpenAI"))
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
        "timeout": self.safe_get_int(self.timeout_var, 600),
        "interface_format": current_llm_interface
    }
    embedding_config = {
        "api_key": self.embedding_api_key_var.get(),
        "base_url": self.embedding_url_var.get(),
        "model_name": self.embedding_model_name_var.get(),
        "retrieval_k": self.safe_get_int(self.embedding_retrieval_k_var, 4),
        "interface_format": current_embedding_interface

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
    llm_config_name = self.base_url_var.get().split("/")[2] + " " + self.model_name_var.get()

    existing_config = load_config(self.config_file)
    if not existing_config:
        existing_config = {}
    existing_config["last_interface_format"] = current_llm_interface
    existing_config["last_embedding_interface_format"] = current_embedding_interface
    if "llm_configs" not in existing_config:
        existing_config["llm_configs"] = {}
    llm_config["config_name"] = llm_config_name

    existing_config["llm_configs"][llm_config_name] = llm_config

    if "embedding_configs" not in existing_config:
        existing_config["embedding_configs"] = {}
    existing_config["embedding_configs"][current_embedding_interface] = embedding_config

    existing_config["other_params"] = other_params

    if save_config(existing_config, self.config_file):
        messagebox.showinfo("提示", "配置已保存至 config.json")
        self.log("配置已保存。")
    else:
        messagebox.showerror("错误", "保存配置失败。")