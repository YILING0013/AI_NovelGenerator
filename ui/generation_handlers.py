# ui/generation_handlers.py
# -*- coding: utf-8 -*-
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import traceback
import glob
from utils import read_file, save_string_to_txt, clear_file_content
from novel_generator import (
    Novel_architecture_generate,
    Chapter_blueprint_generate,
    generate_chapter_draft,
    finalize_chapter,
    import_knowledge_file,
    clear_vector_store,
    enrich_chapter_text,
    build_chapter_prompt
)
from consistency_checker import check_consistency

def generate_novel_architecture_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("Warning", "Please select a save path first.")
        return

    def task():
        confirm = messagebox.askyesno("Confirm", "Are you sure you want to generate the novel architecture?")
        if not confirm:
            self.enable_button_safe(self.btn_generate_architecture)
            return

        self.disable_button_safe(self.btn_generate_architecture)
        try:
            llm_cfg = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]
            interface_format = llm_cfg["interface_format"]
            api_key = llm_cfg["api_key"]
            base_url = llm_cfg["base_url"]
            model_name = llm_cfg["model_name"]
            temperature = llm_cfg["temperature"]
            max_tokens = llm_cfg["max_tokens"]
            timeout_val = llm_cfg["timeout"]

            topic = self.topic_text.get("0.0", "end").strip()
            genre = self.genre_var.get().strip()
            num_chapters = self.safe_get_int(self.num_chapters_var, 10)
            word_number = self.safe_get_int(self.word_number_var, 3000)
            user_guidance = self.user_guide_text.get("0.0", "end").strip()

            self.safe_log("Starting novel architecture generation...")
            Novel_architecture_generate(
                interface_format=interface_format,
                api_key=api_key,
                base_url=base_url,
                llm_model=model_name,
                topic=topic,
                genre=genre,
                number_of_chapters=num_chapters,
                word_number=word_number,
                filepath=filepath,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout_val,
                user_guidance=user_guidance
            )
            self.safe_log("Novel architecture generation complete. Check 'Novel Settings' tab.")
        except Exception:
            self.handle_exception("Error generating novel architecture")
        finally:
            self.enable_button_safe(self.btn_generate_architecture)
    threading.Thread(target=task, daemon=True).start()

def generate_chapter_blueprint_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("Warning", "Please select a save path first.")
        return

    def task():
        if not messagebox.askyesno("Confirm", "Are you sure you want to generate the chapter directory?"):
            self.enable_button_safe(self.btn_generate_chapter)
            return
        self.disable_button_safe(self.btn_generate_directory)
        try:
            number_of_chapters = self.safe_get_int(self.num_chapters_var, 10)
            llm_cfg = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]

            interface_format = llm_cfg["interface_format"]
            api_key = llm_cfg["api_key"]
            base_url = llm_cfg["base_url"]
            model_name = llm_cfg["model_name"]
            temperature = llm_cfg["temperature"]
            max_tokens = llm_cfg["max_tokens"]
            timeout_val = llm_cfg["timeout"]

            user_guidance = self.user_guide_text.get("0.0", "end").strip()

            self.safe_log("Starting chapter blueprint generation...")
            Chapter_blueprint_generate(
                interface_format=interface_format,
                api_key=api_key,
                base_url=base_url,
                llm_model=model_name,
                number_of_chapters=number_of_chapters,
                filepath=filepath,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout_val,
                user_guidance=user_guidance
            )
            self.safe_log("Chapter blueprint generation complete. Check 'Chapter Blueprint' tab.")
        except Exception:
            self.handle_exception("Error generating chapter blueprint")
        finally:
            self.enable_button_safe(self.btn_generate_directory)
    threading.Thread(target=task, daemon=True).start()

def generate_chapter_draft_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("Warning", "Please configure the save path first.")
        return

    def task():
        self.disable_button_safe(self.btn_generate_chapter)
        try:
            llm_cfg = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]
            interface_format = llm_cfg["interface_format"]
            api_key = llm_cfg["api_key"]
            base_url = llm_cfg["base_url"]
            model_name = llm_cfg["model_name"]
            temperature = llm_cfg["temperature"]
            max_tokens = llm_cfg["max_tokens"]
            timeout_val = llm_cfg["timeout"]

            chap_num = self.safe_get_int(self.chapter_num_var, 1)
            word_number = self.safe_get_int(self.word_number_var, 3000)
            user_guidance = self.user_guide_text.get("0.0", "end").strip()

            char_inv = self.characters_involved_var.get().strip()
            key_items = self.key_items_var.get().strip()
            scene_loc = self.scene_location_var.get().strip()
            time_constr = self.time_constraint_var.get().strip()

            embedding_api_key = self.embedding_api_key_var.get().strip()
            embedding_url = self.embedding_url_var.get().strip()
            embedding_interface_format = self.embedding_interface_format_var.get().strip()
            embedding_model_name = self.embedding_model_name_var.get().strip()
            embedding_k = self.safe_get_int(self.embedding_retrieval_k_var, 4)

            self.safe_log(f"Preparing prompt for Chapter {chap_num} draft...")

            prompt_text = build_chapter_prompt(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                filepath=filepath,
                novel_number=chap_num,
                word_number=word_number,
                temperature=temperature,
                user_guidance=user_guidance,
                characters_involved=char_inv,
                key_items=key_items,
                scene_location=scene_loc,
                time_constraint=time_constr,
                embedding_api_key=embedding_api_key,
                embedding_url=embedding_url,
                embedding_interface_format=embedding_interface_format,
                embedding_model_name=embedding_model_name,
                embedding_retrieval_k=embedding_k,
                interface_format=interface_format,
                max_tokens=max_tokens,
                timeout=timeout_val
            )

            result = {"prompt": None}
            event = threading.Event()

            def create_dialog():
                dialog = ctk.CTkToplevel(self.master)
                dialog.title("Chapter Request Prompt (Editable)")
                dialog.geometry("600x400")
                text_box = ctk.CTkTextbox(dialog, wrap="word", font=("Arial", 12))
                text_box.pack(fill="both", expand=True, padx=10, pady=10)

                wordcount_label = ctk.CTkLabel(dialog, text="Words: 0", font=("Arial", 12))
                wordcount_label.pack(side="left", padx=(10,0), pady=5)
                
                final_prompt = prompt_text
                role_names = [name.strip() for name in self.char_inv_text.get("0.0", "end").strip().split(',') if name.strip()]
                role_lib_path = os.path.join(filepath, "CharacterLibrary")
                role_contents = []
                
                if os.path.exists(role_lib_path):
                    for root, dirs, files in os.walk(role_lib_path):
                        for file in files:
                            if file.endswith(".txt") and os.path.splitext(file)[0] in role_names:
                                file_path = os.path.join(root, file)
                                try:
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        role_contents.append(f.read().strip())
                                except Exception as e:
                                    self.safe_log(f"Failed to read character file {file}: {str(e)}")
                
                if role_contents:
                    role_content_str = "\n".join(role_contents)
                    placeholder_variations = [
                        "- Major Characters: {characters_involved}",
                        "├── Characters: {characters_involved}",
                        "- Major Characters (if any): {characters_involved}",
                        "Major Characters: {characters_involved}"
                    ]
                    
                    for placeholder in placeholder_variations:
                        if placeholder in final_prompt:
                            final_prompt = final_prompt.replace(
                                placeholder,
                                f"Major Characters:\n{role_content_str}"
                            )
                            break

                text_box.insert("0.0", final_prompt)
                def update_word_count(event=None):
                    text = text_box.get("0.0", "end-1c")
                    text_length = len(text)
                    wordcount_label.configure(text=f"Words: {text_length}")

                text_box.bind("<KeyRelease>", update_word_count)
                text_box.bind("<ButtonRelease>", update_word_count)
                update_word_count()

                button_frame = ctk.CTkFrame(dialog)
                button_frame.pack(pady=10)
                def on_confirm():
                    result["prompt"] = text_box.get("1.0", "end").strip()
                    dialog.destroy()
                    event.set()
                def on_cancel():
                    result["prompt"] = None
                    dialog.destroy()
                    event.set()
                ctk.CTkButton(button_frame, text="Confirm", font=("Arial", 12), command=on_confirm).pack(side="left", padx=10)
                ctk.CTkButton(button_frame, text="Cancel", font=("Arial", 12), command=on_cancel).pack(side="left", padx=10)
                dialog.protocol("WM_DELETE_WINDOW", on_cancel)
                dialog.grab_set()

            self.master.after(0, create_dialog)
            event.wait()
            edited_prompt = result["prompt"]
            if edited_prompt is None:
                self.safe_log("User cancelled draft generation.")
                return

            self.safe_log("Generating chapter draft...")
            draft_text = generate_chapter_draft(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                filepath=filepath,
                novel_number=chap_num,
                word_number=word_number,
                temperature=temperature,
                user_guidance=user_guidance,
                characters_involved=char_inv,
                key_items=key_items,
                scene_location=scene_loc,
                time_constraint=time_constr,
                embedding_api_key=embedding_api_key,
                embedding_url=embedding_url,
                embedding_interface_format=embedding_interface_format,
                embedding_model_name=embedding_model_name,
                embedding_retrieval_k=embedding_k,
                interface_format=interface_format,
                max_tokens=max_tokens,
                timeout=timeout_val,
                custom_prompt_text=edited_prompt
            )
            if draft_text:
                self.safe_log(f"Chapter {chap_num} draft generated.")
                self.master.after(0, lambda: self.show_chapter_in_textbox(draft_text))
            else:
                self.safe_log("Draft generation failed or empty.")
        except Exception:
            self.handle_exception("Error generating chapter draft")
        finally:
            self.enable_button_safe(self.btn_generate_chapter)
    threading.Thread(target=task, daemon=True).start()

def finalize_chapter_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("Warning", "Please configure the save path first.")
        return

    def task():
        if not messagebox.askyesno("Confirm", "Are you sure you want to finalize the current chapter?"):
            self.enable_button_safe(self.btn_finalize_chapter)
            return

        self.disable_button_safe(self.btn_finalize_chapter)
        try:
            llm_cfg = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]
            interface_format = llm_cfg["interface_format"]
            api_key = llm_cfg["api_key"]
            base_url = llm_cfg["base_url"]
            model_name = llm_cfg["model_name"]
            temperature = llm_cfg["temperature"]
            max_tokens = llm_cfg["max_tokens"]
            timeout_val = llm_cfg["timeout"]

            embedding_api_key = self.embedding_api_key_var.get().strip()
            embedding_url = self.embedding_url_var.get().strip()
            embedding_interface_format = self.embedding_interface_format_var.get().strip()
            embedding_model_name = self.embedding_model_name_var.get().strip()

            chap_num = self.safe_get_int(self.chapter_num_var, 1)
            word_number = self.safe_get_int(self.word_number_var, 3000)

            self.safe_log(f"Finalizing Chapter {chap_num}...")

            chapters_dir = os.path.join(filepath, "chapters")
            os.makedirs(chapters_dir, exist_ok=True)
            chapter_file = os.path.join(chapters_dir, f"chapter_{chap_num}.txt")

            edited_text = self.chapter_result.get("0.0", "end").strip()

            if len(edited_text) < 0.7 * word_number:
                ask = messagebox.askyesno("Short Content", f"Current word count ({len(edited_text)}) is below 70% of target ({word_number}). Try to expand?")
                if ask:
                    self.safe_log("Expanding chapter content...")
                    enriched = enrich_chapter_text(
                        chapter_text=edited_text,
                        word_number=word_number,
                        api_key=api_key,
                        base_url=base_url,
                        model_name=model_name,
                        temperature=temperature,
                        interface_format=interface_format,
                        max_tokens=max_tokens,
                        timeout=timeout_val
                    )
                    edited_text = enriched
                    self.master.after(0, lambda: self.chapter_result.delete("0.0", "end"))
                    self.master.after(0, lambda: self.chapter_result.insert("0.0", edited_text))
            clear_file_content(chapter_file)
            save_string_to_txt(edited_text, chapter_file)

            finalize_chapter(
                novel_number=chap_num,
                word_number=word_number,
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                temperature=temperature,
                filepath=filepath,
                embedding_api_key=embedding_api_key,
                embedding_url=embedding_url,
                embedding_interface_format=embedding_interface_format,
                embedding_model_name=embedding_model_name,
                interface_format=interface_format,
                max_tokens=max_tokens,
                timeout=timeout_val
            )
            self.safe_log(f"Chapter {chap_num} finalized (Summary, Character State, and Vector Store updated).")

            final_text = read_file(chapter_file)
            self.master.after(0, lambda: self.show_chapter_in_textbox(final_text))
        except Exception:
            self.handle_exception("Error finalizing chapter")
        finally:
            self.enable_button_safe(self.btn_finalize_chapter)
    threading.Thread(target=task, daemon=True).start()

def do_consistency_check(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("Warning", "Please configure the save path first.")
        return

    def task():
        self.disable_button_safe(self.btn_check_consistency)
        try:
            llm_cfg = self.loaded_config["llm_configs"][self.consistency_review_llm_var.get()]
            interface_format = llm_cfg["interface_format"]
            api_key = llm_cfg["api_key"]
            base_url = llm_cfg["base_url"]
            model_name = llm_cfg["model_name"]
            temperature = llm_cfg["temperature"]
            max_tokens = llm_cfg["max_tokens"]
            timeout = llm_cfg["timeout"]

            chap_num = self.safe_get_int(self.chapter_num_var, 1)
            chap_file = os.path.join(filepath, "chapters", f"chapter_{chap_num}.txt")
            chapter_text = read_file(chap_file)

            if not chapter_text.strip():
                self.safe_log("Chapter file is empty or missing, cannot check consistency.")
                return

            self.safe_log("Starting consistency check...")
            result = check_consistency(
                novel_setting="",
                character_state=read_file(os.path.join(filepath, "character_state.txt")),
                global_summary=read_file(os.path.join(filepath, "global_summary.txt")),
                chapter_text=chapter_text,
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                temperature=temperature,
                interface_format=interface_format,
                max_tokens=max_tokens,
                timeout=timeout,
                plot_arcs=""
            )
            self.safe_log("Consistency Check Results:")
            self.safe_log(result)
        except Exception:
            self.handle_exception("Error during consistency check")
        finally:
            self.enable_button_safe(self.btn_check_consistency)
    threading.Thread(target=task, daemon=True).start()

def generate_batch_ui(self):
    def open_batch_dialog():
        dialog = ctk.CTkToplevel()
        dialog.title("Batch Generate Chapters")
        
        chapter_dir = os.path.join(self.filepath_var.get().strip(), "chapters")
        files = glob.glob(os.path.join(chapter_dir, "chapter_*.txt"))
        num = max([int(os.path.basename(f).split('_')[1].split('.')[0]) for f in files] + [0]) + 1
            
        dialog.geometry("400x250")
        dialog.resizable(False, False)
        dialog.grid_columnconfigure((1, 3), weight=1)
        
        ctk.CTkLabel(dialog, text="Start Chap:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        entry_start = ctk.CTkEntry(dialog)
        entry_start.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        entry_start.insert(0, str(num))
        
        ctk.CTkLabel(dialog, text="End Chap:").grid(row=0, column=2, padx=10, pady=10, sticky="w")
        entry_end = ctk.CTkEntry(dialog)
        entry_end.grid(row=0, column=3, padx=10, pady=10, sticky="ew")
        
        ctk.CTkLabel(dialog, text="Target Words:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        entry_word = ctk.CTkEntry(dialog)
        entry_word.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        entry_word.insert(0, self.word_number_var.get())
        
        ctk.CTkLabel(dialog, text="Min Words:").grid(row=1, column=2, padx=10, pady=10, sticky="w")
        entry_min = ctk.CTkEntry(dialog)
        entry_min.grid(row=1, column=3, padx=10, pady=10, sticky="ew")
        entry_min.insert(0, self.word_number_var.get())

        auto_enrich_bool = ctk.BooleanVar()
        ctk.CTkCheckBox(dialog, text="Auto-expand if below minimum", variable=auto_enrich_bool).grid(row=2, column=0, columnspan=4, padx=10, pady=10, sticky="w")

        result = {"start": None, "end": None, "word": None, "min": None, "auto_enrich": None, "close": False}

        def on_confirm():
            nonlocal result
            if not all([entry_start.get(), entry_end.get(), entry_word.get(), entry_min.get()]):
                messagebox.showwarning("Warning", "Please fill in all fields.")
                return

            result = {
                "start": entry_start.get(),
                "end": entry_end.get(),
                "word": entry_word.get(),
                "min": entry_min.get(),
                "auto_enrich": auto_enrich_bool.get(),
                "close": False
            }
            dialog.destroy()

        def on_cancel():
            nonlocal result
            result["close"] = True
            dialog.destroy()
            
        button_frame = ctk.CTkFrame(dialog)
        button_frame.grid(row=3, column=0, columnspan=4, padx=10, pady=10, sticky="ew")
        button_frame.grid_columnconfigure((0, 1), weight=1)
        
        ctk.CTkButton(button_frame, text="Confirm", command=on_confirm).grid(row=0, column=0, padx=10, pady=10, sticky="e")
        ctk.CTkButton(button_frame, text="Cancel", command=on_cancel).grid(row=0, column=1, padx=10, pady=10, sticky="w")
        
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        dialog.transient(self.master)
        dialog.grab_set()
        dialog.wait_window(dialog)
        return result
    
    def generate_chapter_batch(self ,i ,word, min, auto_enrich):
        llm_cfg = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]
        interface_format = llm_cfg["interface_format"]
        api_key = llm_cfg["api_key"]
        base_url = llm_cfg["base_url"]
        model_name = llm_cfg["model_name"]
        temperature = llm_cfg["temperature"]
        max_tokens = llm_cfg["max_tokens"]
        timeout = llm_cfg["timeout"]

        user_guidance = self.user_guide_text.get("0.0", "end").strip()  
        char_inv = self.characters_involved_var.get().strip()
        key_items = self.key_items_var.get().strip()
        scene_loc = self.scene_location_var.get().strip()
        time_constr = self.time_constraint_var.get().strip()

        embedding_api_key = self.embedding_api_key_var.get().strip()
        embedding_url = self.embedding_url_var.get().strip()
        embedding_interface_format = self.embedding_interface_format_var.get().strip()
        embedding_model_name = self.embedding_model_name_var.get().strip()
        embedding_k = self.safe_get_int(self.embedding_retrieval_k_var, 4)

        prompt_text = build_chapter_prompt(
            api_key=api_key, base_url=base_url, model_name=model_name,
            filepath=self.filepath_var.get().strip(), novel_number=i, word_number=word,
            temperature=temperature, user_guidance=user_guidance, characters_involved=char_inv,
            key_items=key_items, scene_location=scene_loc, time_constraint=time_constr,
            embedding_api_key=embedding_api_key, embedding_url=embedding_url,
            embedding_interface_format=embedding_interface_format,
            embedding_model_name=embedding_model_name, embedding_retrieval_k=embedding_k,
            interface_format=interface_format, max_tokens=max_tokens, timeout=timeout
        )

        final_prompt = prompt_text
        role_names = [name.strip() for name in self.char_inv_text.get("0.0", "end").split("\n")]
        role_lib_path = os.path.join(self.filepath_var.get().strip(), "CharacterLibrary")
        role_contents = []
        if os.path.exists(role_lib_path):
            for root, dirs, files in os.walk(role_lib_path):
                for file in files:
                    if file.endswith(".txt") and os.path.splitext(file)[0] in role_names:
                        try:
                            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                                role_contents.append(f.read().strip())
                        except Exception as e:
                            self.safe_log(f"Failed to read character file {file}: {str(e)}")
        if role_contents:
            role_content_str = "\n".join(role_contents)
            placeholder_variations = [
                "- Major Characters: {characters_involved}",
                "├── Characters: {characters_involved}",
                "- Major Characters (if any): {characters_involved}",
                "Major Characters: {characters_involved}",
            ]
            for placeholder in placeholder_variations:
                if placeholder in final_prompt:
                    final_prompt = final_prompt.replace(placeholder, f"Major Characters:\n{role_content_str}")
                    break

        draft_text = generate_chapter_draft(
            api_key=api_key, base_url=base_url, model_name=model_name,
            filepath=self.filepath_var.get().strip(), novel_number=i, word_number=word,
            temperature=temperature, user_guidance=user_guidance, characters_involved=char_inv,
            key_items=key_items, scene_location=scene_loc, time_constraint=time_constr,
            embedding_api_key=embedding_api_key, embedding_url=embedding_url,
            embedding_interface_format=embedding_interface_format,
            embedding_model_name=embedding_model_name, embedding_retrieval_k=embedding_k,
            interface_format=interface_format, max_tokens=max_tokens, timeout=timeout,
            custom_prompt_text=final_prompt  
        )

        finalize_cfg = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]

        chapter_dir = os.path.join(self.filepath_var.get().strip(), "chapters")
        os.makedirs(chapter_dir, exist_ok=True)
        chapter_path = os.path.join(chapter_dir, f"chapter_{i}.txt")

        if len(draft_text) < 0.7 * min and auto_enrich:
            self.safe_log(f"Chapter {i} draft is short ({len(draft_text)} words). Expanding...")
            draft_text = enrich_chapter_text(
                chapter_text=draft_text, word_number=word, api_key=api_key,
                base_url=base_url, model_name=model_name, temperature=temperature,
                interface_format=interface_format, max_tokens=max_tokens, timeout=timeout
            )

        clear_file_content(chapter_path)
        save_string_to_txt(draft_text, chapter_path)
        finalize_chapter(
            novel_number=i, word_number=word,
            api_key=finalize_cfg["api_key"], base_url=finalize_cfg["base_url"],
            model_name=finalize_cfg["model_name"], temperature=finalize_cfg["temperature"],
            filepath=self.filepath_var.get().strip(), embedding_api_key=embedding_api_key,
            embedding_url=embedding_url, embedding_interface_format=embedding_interface_format,
            embedding_model_name=embedding_model_name, interface_format=finalize_cfg["interface_format"],
            max_tokens=finalize_cfg["max_tokens"], timeout=finalize_cfg["timeout"]
        )

    batch_result = open_batch_dialog()
    if batch_result["close"]:
        return

    for i in range(int(batch_result["start"]), int(batch_result["end"]) + 1):
        generate_chapter_batch(self, i, int(batch_result["word"]), int(batch_result["min"]), batch_result["auto_enrich"])

def import_knowledge_handler(self):
    selected_file = tk.filedialog.askopenfilename(
        title="Select Knowledge Base File",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
    )
    if selected_file:
        def task():
            self.disable_button_safe(self.btn_import_knowledge)
            try:
                emb_api_key = self.embedding_api_key_var.get().strip()
                emb_url = self.embedding_url_var.get().strip()
                emb_format = self.embedding_interface_format_var.get().strip()
                emb_model = self.embedding_model_name_var.get().strip()

                content = None
                encodings = ['utf-8', 'gbk', 'gb2312', 'ansi']
                for encoding in encodings:
                    try:
                        with open(selected_file, 'r', encoding=encoding) as f:
                            content = f.read()
                            break
                    except UnicodeDecodeError:
                        continue

                if content is None:
                    raise Exception("Could not read file with any supported encoding.")

                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as temp:
                    temp.write(content)
                    temp_path = temp.name

                try:
                    self.safe_log(f"Starting import of: {selected_file}")
                    import_knowledge_file(
                        embedding_api_key=emb_api_key,
                        embedding_url=emb_url,
                        embedding_interface_format=emb_format,
                        embedding_model_name=emb_model,
                        file_path=temp_path,
                        filepath=self.filepath_var.get().strip()
                    )
                    self.safe_log("Knowledge base file imported.")
                finally:
                    try: os.unlink(temp_path)
                    except: pass

            except Exception:
                self.handle_exception("Error importing knowledge base")
            finally:
                self.enable_button_safe(self.btn_import_knowledge)

        threading.Thread(target=task, daemon=True).start()

def clear_vectorstore_handler(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("Warning", "Please configure the save path first.")
        return

    if messagebox.askyesno("Warning", "Are you sure you want to clear the local vector store? This cannot be undone!"):
        if messagebox.askyesno("Confirm Again", "Confirm deletion of all vector data?"):
            if clear_vector_store(filepath):
                self.log("Vector store cleared.")
            else:
                self.log(f"Failed to clear vector store. Please delete the 'vectorstore' folder in {filepath} manually.")

def show_plot_arcs_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("Warning", "Please set the save path first.")
        return

    plot_arcs_file = os.path.join(filepath, "plot_arcs.txt")
    if not os.path.exists(plot_arcs_file):
        messagebox.showinfo("Plot Points", "No plot points or conflict records generated yet.")
        return

    arcs_text = read_file(plot_arcs_file).strip() or "No plot points recorded."

    top = ctk.CTkToplevel(self.master)
    top.title("Plot Points / Unresolved Conflicts")
    top.geometry("600x400")
    text_area = ctk.CTkTextbox(top, wrap="word", font=("Arial", 12))
    text_area.pack(fill="both", expand=True, padx=10, pady=10)
    text_area.insert("0.0", arcs_text)
    text_area.configure(state="disabled")
