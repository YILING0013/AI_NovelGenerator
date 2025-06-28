# ui/knowledge_base_tab.py
# -*- coding: utf-8 -*-
import customtkinter as ctk
from tkinter import filedialog, messagebox
import tempfile
import os
from ui.context_menu import TextWidgetContextMenu
# We need access to self.import_knowledge_handler and self.clear_vectorstore_handler
# These are methods of NovelGeneratorGUI. The build_knowledge_base_tab will be called with `self`.

def build_knowledge_base_tab(self):
    self.knowledge_base_tab = self.tabview.add("知识库管理")
    self.knowledge_base_tab.grid_columnconfigure(0, weight=1)
    self.knowledge_base_tab.grid_rowconfigure(1, weight=1) # Textbox for adding new knowledge

    # --- Top Action Frame ---
    action_frame = ctk.CTkFrame(self.knowledge_base_tab)
    action_frame.grid(row=0, column=0, padx=10, pady=(10,5), sticky="ew")
    # Configure columns for button alignment if needed. Example:
    action_frame.grid_columnconfigure(0, weight=0) # Add text button
    action_frame.grid_columnconfigure(1, weight=0) # Import file button
    action_frame.grid_columnconfigure(2, weight=1) # Spacer
    action_frame.grid_columnconfigure(3, weight=0) # Clear DB button

    # --- Textbox for new knowledge ---
    input_frame = ctk.CTkFrame(self.knowledge_base_tab)
    input_frame.grid(row=1, column=0, padx=10, pady=(5,5), sticky="nsew")
    input_frame.grid_columnconfigure(0, weight=1)
    input_frame.grid_rowconfigure(1, weight=1)

    input_label = ctk.CTkLabel(input_frame, text="在此处粘贴或输入新的知识内容:", font=("Microsoft YaHei", 12))
    input_label.grid(row=0, column=0, padx=5, pady=(5,0), sticky="w")

    self.new_knowledge_text = ctk.CTkTextbox(
        input_frame,
        wrap="word",
        height=200, # Default height, can be adjusted
        font=("Microsoft YaHei", 12)
    )
    TextWidgetContextMenu(self.new_knowledge_text)
    self.new_knowledge_text.grid(row=1, column=0, padx=5, pady=(0,5), sticky="nsew")

    # --- Handler for adding text ---
    def add_text_to_kb():
        text_content = self.new_knowledge_text.get("0.0", "end-1c").strip()
        if not text_content:
            messagebox.showwarning("输入为空", "请输入有效的知识内容。")
            return

        if not self.filepath_var.get().strip():
            messagebox.showwarning("路径未设置", "请先在“主要功能”标签页中设置项目保存路径。知识库将存储在该路径下。")
            return

        # Use a temporary file to pass content to existing import_knowledge_file function
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as temp_file:
                temp_file.write(text_content)
                temp_file_path = temp_file.name

            self.log(f"准备将文本内容导入知识库...")
            # Call the existing import_knowledge_file via the handler in NovelGeneratorGUI
            # This handler already manages threading and UI updates (disable/enable buttons)

            # We need to simulate the file selection part for import_knowledge_handler
            # or refactor import_knowledge_handler to accept text or filepath
            # For now, let's call the core import_knowledge_file logic directly but ensure it's threaded
            # and UI is updated.

            # Simplified: Directly use the core logic in a thread like import_knowledge_handler does
            def task():
                self.disable_button_safe(add_text_btn)
                try:
                    from novel_generator import import_knowledge_file # Ensure it's available

                    emb_api_key = self.embedding_api_key_var.get().strip()
                    emb_url = self.embedding_url_var.get().strip()
                    emb_format = self.embedding_interface_format_var.get().strip()
                    emb_model = self.embedding_model_name_var.get().strip()
                    project_filepath = self.filepath_var.get().strip()

                    import_knowledge_file(
                        embedding_api_key=emb_api_key,
                        embedding_url=emb_url,
                        embedding_interface_format=emb_format,
                        embedding_model_name=emb_model,
                        file_path=temp_file_path, # Pass the temp file
                        filepath=project_filepath
                    )
                    self.safe_log("✅ 文本内容已成功添加至知识库。")
                    self.new_knowledge_text.delete("0.0", "end") # Clear textbox on success
                except Exception as e:
                    self.handle_exception(f"通过文本框添加知识到知识库时出错: {e}")
                finally:
                    try:
                        os.unlink(temp_file_path) # Clean up the temporary file
                    except Exception as e:
                        self.safe_log(f"警告：未能删除临时知识文件 {temp_file_path}: {e}")
                    self.enable_button_safe(add_text_btn)

            threading.Thread(target=task, daemon=True).start()

        except Exception as e:
            self.handle_exception(f"创建临时文件以添加知识时出错: {e}")
            messagebox.showerror("错误", f"创建临时文件失败: {e}")


    # --- Buttons in Action Frame ---
    add_text_btn = ctk.CTkButton(
        action_frame,
        text="添加当前文本到知识库",
        command=add_text_to_kb,
        font=("Microsoft YaHei", 12)
    )
    add_text_btn.grid(row=0, column=0, padx=(0,10), pady=5, sticky="w")

    import_file_btn = ctk.CTkButton(
        action_frame,
        text="从文件导入知识",
        command=self.import_knowledge_handler, # Uses the existing handler from NovelGeneratorGUI
        font=("Microsoft YaHei", 12)
    )
    import_file_btn.grid(row=0, column=1, padx=(0,10), pady=5, sticky="w")

    clear_db_btn = ctk.CTkButton(
        action_frame,
        text="清空知识库 (向量)",
        command=self.clear_vectorstore_handler, # Uses the existing handler
        fg_color="red",
        font=("Microsoft YaHei", 12)
    )
    clear_db_btn.grid(row=0, column=3, padx=5, pady=5, sticky="e")

    self.log("知识库管理界面已构建。")
