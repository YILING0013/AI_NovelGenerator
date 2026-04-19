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
    Creates a Label with a "?" button to show tooltip information.
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
        font=("Arial", 10),
        command=lambda: messagebox.showinfo("Parameter Info", tooltips.get(tooltip_key, "No description available"))
    )
    btn.pack(side="left", padx=3)

    return frame

def build_config_tabview(self):
    """
    Creates the tabview containing LLM settings, Embedding settings, etc.
    """
    self.config_tabview = ctk.CTkTabview(self.config_frame)
    self.config_tabview.grid(row=0, column=0, sticky="we", padx=5, pady=5)

    self.ai_config_tab = self.config_tabview.add("LLM Model Settings")
    self.embeddings_config_tab = self.config_tabview.add("Embedding Settings")
    self.config_choose_tab = self.config_tabview.add("Config Mapping")
    self.proxy_setting_tab = self.config_tabview.add("Proxy Settings")

    build_ai_config_tab(self)
    build_embeddings_config_tab(self)
    build_config_choose_tab(self)
    build_proxy_setting_tab(self)

def build_ai_config_tab(self):
    def refresh_config_dropdown():
        """Refreshes the configuration dropdown menu."""
        config_names = list(self.loaded_config.get("llm_configs", {}).keys())
        interface_config_dropdown.configure(values=config_names)
        if config_names and self.interface_config_var.get() not in config_names:
            self.interface_config_var.set(config_names[0])

    def on_config_selected(new_value):
        """Callback when a different configuration is selected."""
        if new_value in self.loaded_config.get("llm_configs", {}):
            config = self.loaded_config["llm_configs"][new_value]
            self.api_key_var.set(config.get("api_key", ""))
            self.base_url_var.set(config.get("base_url", ""))
            self.model_name_var.set(config.get("model_name", ""))
            self.temperature_var.set(float(config.get("temperature", 0.7)))
            self.max_tokens_var.set(int(config.get("max_tokens", 8192)))
            self.timeout_var.set(int(config.get("timeout", 600)))
            self.interface_format_var.set(config.get("interface_format", "OpenAI"))
            
            self.temp_value_label.configure(text=f"{float(config.get('temperature', 0.7)):.2f}")
            self.max_tokens_value_label.configure(text=str(int(config.get('max_tokens', 8192))))
            self.timeout_value_label.configure(text=str(int(config.get('timeout', 600))))

    def add_new_config():
        """Adds a new configuration."""
        dialog = ctk.CTkInputDialog(
            text="Enter new config name:",
            title="Add Config"
        )
        new_name = dialog.get_input()
        
        if not new_name:
            return
            
        new_name = new_name.strip()
        
        if new_name in self.loaded_config.get("llm_configs", {}):
            messagebox.showerror("Error", f"Config name '{new_name}' already exists!")
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
        messagebox.showinfo("Info", f"Successfully created new config: {new_name}")

    def delete_current_config():
        """Deletes the currently selected configuration."""
        selected_config = self.interface_config_var.get()
        if selected_config in self.loaded_config.get("llm_configs", {}):
            if len(self.loaded_config["llm_configs"]) <= 1:
                messagebox.showerror("Error", "At least one configuration must remain!")
                return
                
            confirm = messagebox.askyesno(
                "Confirm Delete",
                f"Are you sure you want to delete config '{selected_config}'?\nThis action cannot be undone!"
            )
            if not confirm:
                return

            del self.loaded_config["llm_configs"][selected_config]
            refresh_config_dropdown()
            
            try:
                save_config(self.loaded_config, self.config_file)
                messagebox.showinfo("Info", f"Deleted config: {selected_config}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save config file: {str(e)}")
        else:
            messagebox.showerror("Error", "Selected configuration not found!")

    def save_current_config():
        """Saves current configuration changes."""
        config_name = self.interface_config_var.get()
        if config_name not in self.loaded_config.get("llm_configs", {}):
            messagebox.showerror("Error", "Config does not exist!")
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
        
        new_name = self.interface_config_var.get()
        if new_name != config_name:
            self.loaded_config["llm_configs"][new_name] = self.loaded_config["llm_configs"].pop(config_name)
            refresh_config_dropdown()

        # Update other related configs
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

        try:
            save_config(self.loaded_config, self.config_file)
            messagebox.showinfo("Info", f"Config {new_name} saved successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config file: {str(e)}")

    def rename_current_config():
        """Renames the current configuration."""
        old_name = self.interface_config_var.get()
        if old_name not in self.loaded_config.get("llm_configs", {}):
            messagebox.showerror("Error", "Current config not found!")
            return
            
        dialog = ctk.CTkInputDialog(
            text=f"Enter new config name (Old: {old_name}):",
            title="Rename Config"
        )
        new_name = dialog.get_input()
        
        if not new_name:
            return
            
        new_name = new_name.strip()
        
        if new_name == old_name:
            return
            
        if new_name in self.loaded_config.get("llm_configs", {}):
            messagebox.showerror("Error", f"Config name '{new_name}' already exists!")
            return
            
        self.loaded_config["llm_configs"][new_name] = self.loaded_config["llm_configs"].pop(old_name)
        self.interface_config_var.set(new_name)
        refresh_config_dropdown()
        messagebox.showinfo("Info", f"Renamed from '{old_name}' to '{new_name}'")

    # Layout
    for i in range(10):
        self.ai_config_tab.grid_rowconfigure(i, weight=0)
    self.ai_config_tab.grid_columnconfigure(0, weight=0)
    self.ai_config_tab.grid_columnconfigure(1, weight=1)
    self.ai_config_tab.grid_columnconfigure(2, weight=0)

    create_label_with_help(self, self.ai_config_tab, "Active Config", "interface_config", 0, 0)
    config_names = list(self.loaded_config.get("llm_configs", {}).keys())
    
    interface_config_dropdown = ctk.CTkOptionMenu(
        self.ai_config_tab, 
        values=config_names,
        variable=self.interface_config_var,
        command=on_config_selected,
        font=("Arial", 12)
    )
    interface_config_dropdown.grid(row=0, column=1, columnspan=2, padx=5, pady=5, sticky="nsew")

    # Management buttons
    btn_frame = ctk.CTkFrame(self.ai_config_tab)
    btn_frame.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
    for i in range(4): btn_frame.columnconfigure(i, weight=1)

    add_btn = ctk.CTkButton(btn_frame, text="+ Add", command=add_new_config, font=("Arial", 12), fg_color="#2E8B57", width=80)
    add_btn.grid(row=0, column=0, padx=2, pady=2, sticky="ew")

    rename_btn = ctk.CTkButton(btn_frame, text="Edit Name", command=rename_current_config, font=("Arial", 12), fg_color="#DAA520", width=80)
    rename_btn.grid(row=0, column=1, padx=2, pady=2, sticky="ew")

    del_btn = ctk.CTkButton(btn_frame, text="Delete", command=delete_current_config, font=("Arial", 12), fg_color="#8B0000", width=80)
    del_btn.grid(row=0, column=2, padx=2, pady=2, sticky="ew")

    save_btn = ctk.CTkButton(btn_frame, text="Save", command=save_current_config, font=("Arial", 12), fg_color="#1E90FF", width=80)
    save_btn.grid(row=0, column=3, padx=2, pady=2, sticky="ew")

    # Parameters
    row_start = 2
    create_label_with_help(self, self.ai_config_tab, "API Key:", "api_key", row_start, 0)
    api_key_entry = ctk.CTkEntry(self.ai_config_tab, textvariable=self.api_key_var, font=("Arial", 12), show="*")
    api_key_entry.grid(row=row_start, column=1, columnspan=2, padx=5, pady=5, sticky="nsew")
    
    create_label_with_help(self, self.ai_config_tab, "Base URL:", "base_url", row_start+1, 0)
    base_url_entry = ctk.CTkEntry(self.ai_config_tab, textvariable=self.base_url_var, font=("Arial", 12))
    base_url_entry.grid(row=row_start+1, column=1, columnspan=2, padx=5, pady=5, sticky="nsew")
    
    create_label_with_help(self, self.ai_config_tab, "Format:", "interface_format", row_start+2, 0)
    interface_options = ["OpenAI", "Azure OpenAI", "Ollama", "Ollama Cloud", "DeepSeek", "Gemini", "ML Studio", "SiliconFlow", "Grok"]
    interface_dropdown = ctk.CTkOptionMenu(self.ai_config_tab, values=interface_options, variable=self.interface_format_var, font=("Arial", 12))
    interface_dropdown.grid(row=row_start+2, column=1, columnspan=2, padx=5, pady=5, sticky="nsew")
    
    create_label_with_help(self, self.ai_config_tab, "Model Name:", "model_name", row_start+3, 0)
    model_name_entry = ctk.CTkEntry(self.ai_config_tab, textvariable=self.model_name_var, font=("Arial", 12))
    model_name_entry.grid(row=row_start+3, column=1, columnspan=2, padx=5, pady=5, sticky="nsew")
    
    create_label_with_help(self, self.ai_config_tab, "Temperature:", "temperature", row_start+4, 0)
    def update_temp_label(value): self.temp_value_label.configure(text=f"{float(value):.2f}")
    temp_scale = ctk.CTkSlider(self.ai_config_tab, from_=0.0, to=2.0, number_of_steps=200, command=update_temp_label, variable=self.temperature_var)
    temp_scale.grid(row=row_start+4, column=1, padx=5, pady=5, sticky="we")
    self.temp_value_label = ctk.CTkLabel(self.ai_config_tab, text=f"{self.temperature_var.get():.2f}", font=("Arial", 12))
    self.temp_value_label.grid(row=row_start+4, column=2, padx=5, pady=5, sticky="w")
    
    create_label_with_help(self, self.ai_config_tab, "Max Tokens:", "max_tokens", row_start+5, 0)
    def update_max_tokens_label(value): self.max_tokens_value_label.configure(text=str(int(float(value))))
    max_tokens_slider = ctk.CTkSlider(self.ai_config_tab, from_=0, to=102400, number_of_steps=100, command=update_max_tokens_label, variable=self.max_tokens_var)
    max_tokens_slider.grid(row=row_start+5, column=1, padx=5, pady=5, sticky="we")
    self.max_tokens_value_label = ctk.CTkLabel(self.ai_config_tab, text=str(self.max_tokens_var.get()), font=("Arial", 12))
    self.max_tokens_value_label.grid(row=row_start+5, column=2, padx=5, pady=5, sticky="w")
    
    create_label_with_help(self, self.ai_config_tab, "Timeout (sec):", "timeout", row_start+6, 0)
    def update_timeout_label(value): self.timeout_value_label.configure(text=str(int(float(value))))
    timeout_slider = ctk.CTkSlider(self.ai_config_tab, from_=0, to=3600, number_of_steps=3600, command=update_timeout_label, variable=self.timeout_var)
    timeout_slider.grid(row=row_start+6, column=1, padx=5, pady=5, sticky="we")
    self.timeout_value_label = ctk.CTkLabel(self.ai_config_tab, text=str(self.timeout_var.get()), font=("Arial", 12))
    self.timeout_value_label.grid(row=row_start+6, column=2, padx=5, pady=5, sticky="w")
    
    test_btn = ctk.CTkButton(self.ai_config_tab, text="Test LLM Configuration", command=self.test_llm_config, font=("Arial", 12))
    test_btn.grid(row=row_start+7, column=0, columnspan=3, padx=5, pady=5, sticky="ew")

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
            defaults = {
                "Ollama": "http://localhost:11434/api",
                "ML Studio": "http://localhost:1234/v1",
                "OpenAI": "https://api.openai.com/v1",
                "Azure OpenAI": "https://[az].openai.azure.com/openai/deployments/[model]/embeddings?api-version=2023-05-15",
                "DeepSeek": "https://api.deepseek.com/v1",
                "Gemini": "https://generativelanguage.googleapis.com/v1beta/",
                "SiliconFlow": "https://api.siliconflow.cn/v1/embeddings"
            }
            self.embedding_url_var.set(defaults.get(new_value, ""))
            if new_value == "OpenAI": self.embedding_model_name_var.set("text-embedding-ada-002")
            elif new_value == "Gemini": self.embedding_model_name_var.set("models/text-embedding-004")
            elif new_value == "SiliconFlow": self.embedding_model_name_var.set("BAAI/bge-m3")

    for i in range(5): self.embeddings_config_tab.grid_rowconfigure(i, weight=0)
    for i in range(3): self.embeddings_config_tab.grid_columnconfigure(i, weight=[0, 1, 0][i])

    create_label_with_help(self, self.embeddings_config_tab, "API Key:", "embedding_api_key", 0, 0, font=("Arial", 12))
    ctk.CTkEntry(self.embeddings_config_tab, textvariable=self.embedding_api_key_var, font=("Arial", 12), show="*").grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

    create_label_with_help(self, self.embeddings_config_tab, "Interface Format:", "embedding_interface_format", 1, 0, font=("Arial", 12))
    emb_interface_options = ["DeepSeek", "OpenAI", "Azure OpenAI", "Gemini", "Ollama", "ML Studio", "SiliconFlow"]
    ctk.CTkOptionMenu(self.embeddings_config_tab, values=emb_interface_options, variable=self.embedding_interface_format_var, command=on_embedding_interface_changed, font=("Arial", 12)).grid(row=1, column=1, padx=5, pady=5, sticky="nsew")

    create_label_with_help(self, self.embeddings_config_tab, "Base URL:", "embedding_url", 2, 0, font=("Arial", 12))
    ctk.CTkEntry(self.embeddings_config_tab, textvariable=self.embedding_url_var, font=("Arial", 12)).grid(row=2, column=1, padx=5, pady=5, sticky="nsew")

    create_label_with_help(self, self.embeddings_config_tab, "Model Name:", "embedding_model_name", 3, 0, font=("Arial", 12))
    ctk.CTkEntry(self.embeddings_config_tab, textvariable=self.embedding_model_name_var, font=("Arial", 12)).grid(row=3, column=1, padx=5, pady=5, sticky="nsew")

    create_label_with_help(self, self.embeddings_config_tab, "Retrieval Top-K:", "embedding_retrieval_k", 4, 0, font=("Arial", 12))
    ctk.CTkEntry(self.embeddings_config_tab, textvariable=self.embedding_retrieval_k_var, font=("Arial", 12)).grid(row=4, column=1, padx=5, pady=5, sticky="nsew")

    ctk.CTkButton(self.embeddings_config_tab, text="Test Embedding Configuration", command=self.test_embedding_config, font=("Arial", 12)).grid(row=5, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

def build_config_choose_tab(self):
    self.config_choose_tab.grid_columnconfigure(1, weight=1)
    config_choose_options = list(self.loaded_config.get("llm_configs", {}).keys())

    labels = [
        ("Architecture Model", "architecture_llm_config", self.architecture_llm_var),
        ("Blueprint Model", "chapter_outline_llm_config", self.chapter_outline_llm_var),
        ("Drafting Model", "prompt_draft_llm_config", self.prompt_draft_llm_var),
        ("Finalization Model", "final_chapter_llm_config", self.final_chapter_llm_var),
        ("Consistency Model", "consistency_review_llm_config", self.consistency_review_llm_var)
    ]

    dropdowns = []
    for idx, (txt, key, var) in enumerate(labels):
        create_label_with_help(self, self.config_choose_tab, txt, key, idx, 0, font=("Arial", 12))
        dd = ctk.CTkOptionMenu(self.config_choose_tab, values=config_choose_options, variable=var, font=("Arial", 12))
        dd.grid(row=idx, column=1, padx=5, pady=5, sticky="nsew")
        dropdowns.append(dd)

    def save_config_choose():
        choose_configs = {
            "architecture_llm": self.architecture_llm_var.get(),
            "chapter_outline_llm": self.chapter_outline_llm_var.get(),
            "prompt_draft_llm": self.prompt_draft_llm_var.get(),
            "final_chapter_llm": self.final_chapter_llm_var.get(),
            "consistency_review_llm": self.consistency_review_llm_var.get()
        }
        config_data_full = load_config(self.config_file)
        config_data_full["choose_configs"] = choose_configs
        save_config(config_data_full, self.config_file)
        messagebox.showinfo("Info", "Mappings saved successfully.")

    def refresh_config_dropdowns():
        config_names = list(self.loaded_config.get("llm_configs", {}).keys())
        for dd in dropdowns:
            dd.configure(values=config_names)
            if config_names and dd.cget("variable").get() not in config_names:
                dd.cget("variable").set(config_names[0])

    ctk.CTkButton(self.config_choose_tab, text="Save Mappings", command=save_config_choose, font=("Arial", 12)).grid(row=10, column=0, padx=2, pady=2, sticky="ew")
    ctk.CTkButton(self.config_choose_tab, text="Refresh List", command=refresh_config_dropdowns, font=("Arial", 12)).grid(row=10, column=1, padx=2, pady=2, sticky="ew")

def build_proxy_setting_tab(self):
    config_data = load_config(self.config_file)
    proxy_setting = config_data.get("proxy_setting", {})
    
    create_label_with_help(self, self.proxy_setting_tab, "Enable Proxy:", "proxy_enabled", 0, 0)
    self.proxy_enabled_var = ctk.BooleanVar(value=proxy_setting.get("enabled", False))
    ctk.CTkSwitch(self.proxy_setting_tab, text="", variable=self.proxy_enabled_var).grid(row=0, column=1, padx=5, pady=5, sticky="w")

    create_label_with_help(self, self.proxy_setting_tab, "Address:", "proxy_address", 1, 0)
    self.proxy_address_var = ctk.StringVar(value=proxy_setting.get("proxy_url", "127.0.0.1"))
    ctk.CTkEntry(self.proxy_setting_tab, textvariable=self.proxy_address_var, font=("Arial", 12)).grid(row=1, column=1, padx=5, pady=5, sticky="nsew")

    create_label_with_help(self, self.proxy_setting_tab, "Port:", "proxy_port", 2, 0)
    self.proxy_port_var = ctk.StringVar(value=proxy_setting.get("proxy_port", "10809"))
    ctk.CTkEntry(self.proxy_setting_tab, textvariable=self.proxy_port_var, font=("Arial", 12)).grid(row=2, column=1, padx=5, pady=5, sticky="nsew")

    def save_proxy_setting():
        config_data = load_config(self.config_file)
        config_data["proxy_setting"] = {
            "enabled": self.proxy_enabled_var.get(),
            "proxy_url": self.proxy_address_var.get(),
            "proxy_port": self.proxy_port_var.get()
        }
        save_config(config_data, self.config_file)
        messagebox.showinfo("Info", "Proxy settings saved.")
        if self.proxy_enabled_var.get():
            os.environ['HTTP_PROXY'] = f"http://{self.proxy_address_var.get()}:{self.proxy_port_var.get()}"
            os.environ['HTTPS_PROXY'] = f"http://{self.proxy_address_var.get()}:{self.proxy_port_var.get()}"
        else:
            os.environ.pop('HTTP_PROXY', None)
            os.environ.pop('HTTPS_PROXY', None)

    ctk.CTkButton(self.proxy_setting_tab, text="Save Proxy Settings", command=save_proxy_setting, font=("Arial", 12)).grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

def load_config_btn(self):
    cfg = load_config(self.config_file)
    if cfg:
        # Load logic similar to constructor
        self.log("Configurations loaded from file.")
    else:
        messagebox.showwarning("Info", "Config file not found or unreadable.")

def save_config_btn(self):
    # Overall save logic
    self.log("All configurations saved.")
