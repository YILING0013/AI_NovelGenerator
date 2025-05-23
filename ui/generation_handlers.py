# ui/generation_handlers.py
# -*- coding: utf-8 -*-
import os
import threading
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from utils import read_file, save_string_to_txt, clear_file_content
from novel_generator import (
    Novel_architecture_generate,
    Chapter_blueprint_generate,
    finalize_chapter,
    import_knowledge_file,
    clear_vector_store,
    enrich_chapter_text
)
from consistency_checker import check_consistency
from novel_generator.finalization import enrich_chapter_text

def generate_novel_architecture_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先选择保存文件路径")
        return

    def task():
        confirm = messagebox.askyesno("确认", "确定要生成小说架构吗？")
        if not confirm:
            self.enable_button_safe(self.btn_generate_architecture)
            return

        self.disable_button_safe(self.btn_generate_architecture)
        try:
            interface_format = self.interface_format_var.get().strip()
            api_key = self.api_key_var.get().strip()
            base_url = self.base_url_var.get().strip()
            model_name = self.model_name_var.get().strip()
            temperature = self.temperature_var.get()
            max_tokens = self.max_tokens_var.get()
            timeout_val = self.safe_get_int(self.timeout_var, 600)

            topic = self.topic_text.get("0.0", "end").strip()
            genre = self.genre_var.get().strip()
            num_chapters = self.safe_get_int(self.num_chapters_var, 10)
            word_number = self.safe_get_int(self.word_number_var, 3000)
            # 获取内容指导
            user_guidance = self.user_guide_text.get("0.0", "end").strip()

            self.safe_log("开始生成小说架构...")
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
                user_guidance=user_guidance  # 添加内容指导参数
            )
            self.safe_log("✅ 小说架构生成完成。请在 'Novel Architecture' 标签页查看或编辑。")
        except Exception:
            self.handle_exception("生成小说架构时出错")
        finally:
            self.enable_button_safe(self.btn_generate_architecture)
    threading.Thread(target=task, daemon=True).start()

def generate_chapter_blueprint_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先选择保存文件路径")
        return

    def task():
        if not messagebox.askyesno("确认", "确定要生成章节目录吗？"):
            self.enable_button_safe(self.btn_generate_chapter)
            return
        self.disable_button_safe(self.btn_generate_directory)
        try:
            interface_format = self.interface_format_var.get().strip()
            api_key = self.api_key_var.get().strip()
            base_url = self.base_url_var.get().strip()
            model_name = self.model_name_var.get().strip()
            number_of_chapters = self.safe_get_int(self.num_chapters_var, 10)
            temperature = self.temperature_var.get()
            max_tokens = self.max_tokens_var.get()
            timeout_val = self.safe_get_int(self.timeout_var, 600)
            user_guidance = self.user_guide_text.get("0.0", "end").strip()  # 新增获取用户指导

            self.safe_log("开始生成章节蓝图...")
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
                user_guidance=user_guidance  # 新增参数
            )
            self.safe_log("✅ 章节蓝图生成完成。请在 'Chapter Blueprint' 标签页查看或编辑。")
        except Exception:
            self.handle_exception("生成章节蓝图时出错")
        finally:
            self.enable_button_safe(self.btn_generate_directory)
    threading.Thread(target=task, daemon=True).start()


def generate_chapter_draft_ui(self, *, auto_confirm: bool = False) -> "threading.Event":
    done_evt = threading.Event()

    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        done_evt.set()
        return done_evt

    def task():
        try:
            # === 读取参数 ===
            interface_format = self.interface_format_var.get().strip()
            api_key      = self.api_key_var.get().strip()
            base_url     = self.base_url_var.get().strip()
            model_name   = self.model_name_var.get().strip()
            temperature  = self.temperature_var.get()
            max_tokens   = self.max_tokens_var.get()
            timeout_val  = self.safe_get_int(self.timeout_var, 600)

            chap_num     = self.safe_get_int(self.chapter_num_var, 1)
            word_number  = self.safe_get_int(self.word_number_var, 3000)
            user_guidance= self.user_guide_text.get("0.0", "end").strip()

            char_inv     = self.characters_involved_var.get().strip()
            key_items    = self.key_items_var.get().strip()
            scene_loc    = self.scene_location_var.get().strip()
            time_constr  = self.time_constraint_var.get().strip()

            emb_api_key  = self.embedding_api_key_var.get().strip()
            emb_url      = self.embedding_url_var.get().strip()
            emb_format   = self.embedding_interface_format_var.get().strip()
            emb_model    = self.embedding_model_name_var.get().strip()
            emb_k        = self.safe_get_int(self.embedding_retrieval_k_var, 4)

            # === 构造 prompt ===
            from novel_generator.chapter import build_chapter_prompt
            prompt_text = build_chapter_prompt(
                api_key=api_key, base_url=base_url, model_name=model_name,
                filepath=filepath, novel_number=chap_num, word_number=word_number,
                temperature=temperature, user_guidance=user_guidance,
                characters_involved=char_inv, key_items=key_items,
                scene_location=scene_loc, time_constraint=time_constr,
                embedding_api_key=emb_api_key, embedding_url=emb_url,
                embedding_interface_format=emb_format, embedding_model_name=emb_model,
                embedding_retrieval_k=emb_k,
                interface_format=interface_format, max_tokens=max_tokens,
                timeout=timeout_val
            )

            # === 获取最终 prompt ===
            if auto_confirm:
                edited_prompt = prompt_text
            else:
                result = {"prompt": None}
                wait_evt = threading.Event()

                def create_dialog():
                    dlg = ctk.CTkToplevel(self.master)
                    dlg.title("当前章节请求提示词（可编辑）")
                    dlg.geometry("650x450")

                    txt = ctk.CTkTextbox(dlg, wrap="word",
                                         font=("Microsoft YaHei", 12))
                    txt.pack(fill="both", expand=True, padx=10, pady=10)
                    txt.insert("0.0", prompt_text)

                    wc = ctk.CTkLabel(dlg, font=("Microsoft YaHei", 12))
                    wc.pack(side="left", padx=(10, 0), pady=5)
                    txt.bind("<KeyRelease>", lambda e=None:
                             wc.configure(text=f"字数：{len(txt.get('0.0','end-1c'))}"))
                    txt.event_generate("<<KeyRelease>>")

                    def _ok():
                        result["prompt"] = txt.get("1.0", "end").strip()
                        dlg.destroy(); wait_evt.set()
                    def _cancel():
                        result["prompt"] = None
                        dlg.destroy(); wait_evt.set()

                    frm = ctk.CTkFrame(dlg); frm.pack(pady=10)
                    ctk.CTkButton(frm, text="确认使用", command=_ok).pack(side="left", padx=10)
                    ctk.CTkButton(frm, text="取消请求", command=_cancel).pack(side="left", padx=10)
                    dlg.protocol("WM_DELETE_WINDOW", _cancel)
                    dlg.grab_set()

                self.master.after(0, create_dialog)
                wait_evt.wait()
                edited_prompt = result["prompt"]
                if edited_prompt is None:
                    self.safe_log("❌ 用户取消了草稿生成请求。")
                    return

            # === 调用 LLM ===
            self.safe_log(f"开始生成第 {chap_num} 章草稿…")
            from novel_generator.chapter import generate_chapter_draft
            draft_text = generate_chapter_draft(
                api_key=api_key, base_url=base_url, model_name=model_name,
                filepath=filepath, novel_number=chap_num, word_number=word_number,
                temperature=temperature, user_guidance=user_guidance,
                characters_involved=char_inv, key_items=key_items,
                scene_location=scene_loc, time_constraint=time_constr,
                embedding_api_key=emb_api_key, embedding_url=emb_url,
                embedding_interface_format=emb_format, embedding_model_name=emb_model,
                embedding_retrieval_k=emb_k,
                interface_format=interface_format, max_tokens=max_tokens,
                timeout=timeout_val, custom_prompt_text=edited_prompt
            )

            if draft_text:
                self.safe_log(f"✅ 第 {chap_num} 章草稿生成完成。")
                self.master.after(0,
                    lambda: self.show_chapter_in_textbox(draft_text))
            else:
                self.safe_log("⚠️ 草稿生成失败或返回空内容。")

        except Exception:
            self.handle_exception("生成章节草稿时出错")
        finally:
            self.enable_button_safe(self.btn_generate_chapter)
            done_evt.set()

    self.disable_button_safe(self.btn_generate_chapter)
    threading.Thread(target=task, daemon=True).start()
    return done_evt

def finalize_chapter_ui(self) -> "threading.Event":
    done_evt = threading.Event()
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        done_evt.set(); return done_evt

    def task():
        try:
            api_key = self.api_key_var.get().strip()
            base_url = self.base_url_var.get().strip()
            model_name = self.model_name_var.get().strip()
            temperature = self.temperature_var.get()
            interface_format = self.interface_format_var.get()
            max_tokens = self.max_tokens_var.get()
            timeout_val = self.safe_get_int(self.timeout_var, 600)

            emb_api_key  = self.embedding_api_key_var.get().strip()
            emb_url      = self.embedding_url_var.get().strip()
            emb_format   = self.embedding_interface_format_var.get().strip()
            emb_model    = self.embedding_model_name_var.get().strip()

            chap_num = self.safe_get_int(self.chapter_num_var, 1)
            word_number = self.safe_get_int(self.word_number_var, 3000)

            self.safe_log(f"开始定稿第{chap_num}章...")

            chapters_dir = os.path.join(filepath, "chapters")
            os.makedirs(chapters_dir, exist_ok=True)
            chapter_file = os.path.join(chapters_dir, f"chapter_{chap_num}.txt")

            edited_text = self.chapter_result.get("0.0", "end").strip()

            if len(edited_text) < 0.7 * word_number:
                from tkinter import messagebox
                if messagebox.askyesno("字数不足", f"当前章节字数 ({len(edited_text)}) 低于目标字数({word_number})的70%，是否扩写？"):
                    self.safe_log("正在扩写章节内容...")
                    
                    edited_text = enrich_chapter_text(
                        chapter_text=edited_text, word_number=word_number,
                        api_key=api_key, base_url=base_url, model_name=model_name,
                        temperature=temperature, interface_format=interface_format,
                        max_tokens=max_tokens, timeout=timeout_val
                    )
                    self.master.after(0, lambda: self.chapter_result.delete("0.0", "end"))
                    self.master.after(0, lambda: self.chapter_result.insert("0.0", edited_text))

            from utils import clear_file_content, save_string_to_txt, read_file
            clear_file_content(chapter_file)
            save_string_to_txt(edited_text, chapter_file)

            from novel_generator import finalize_chapter
            finalize_chapter(
                novel_number=chap_num, word_number=word_number,
                api_key=api_key, base_url=base_url, model_name=model_name,
                temperature=temperature, filepath=filepath,
                embedding_api_key=emb_api_key, embedding_url=emb_url,
                embedding_interface_format=emb_format, embedding_model_name=emb_model,
                interface_format=interface_format, max_tokens=max_tokens,
                timeout=timeout_val
            )

            self.safe_log(f"✅ 第 {chap_num} 章定稿完成。")
            final_text = read_file(chapter_file)
            self.master.after(0, lambda: self.show_chapter_in_textbox(final_text))

        except Exception:
            self.handle_exception("定稿章节时出错")
        finally:
            self.enable_button_safe(self.btn_finalize_chapter)
            done_evt.set()

    self.disable_button_safe(self.btn_finalize_chapter)
    threading.Thread(target=task, daemon=True).start()
    return done_evt


def do_consistency_check(self) -> "threading.Event":
    done_evt = threading.Event()
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        done_evt.set(); return done_evt

    def task():
        try:
            api_key = self.api_key_var.get().strip()
            base_url = self.base_url_var.get().strip()
            model_name = self.model_name_var.get().strip()
            temperature = self.temperature_var.get()
            interface_format = self.interface_format_var.get()
            max_tokens = self.max_tokens_var.get()
            timeout = self.timeout_var.get()

            chap_num = self.safe_get_int(self.chapter_num_var, 1)
            chap_file = os.path.join(filepath, "chapters", f"chapter_{chap_num}.txt")
            from utils import read_file
            chapter_text = read_file(chap_file)

            if not chapter_text.strip():
                self.safe_log("⚠️ 当前章节文件为空或不存在，无法审校。")
                return

            self.safe_log("开始一致性审校...")
            from consistency_checker import check_consistency
            result = check_consistency(
                novel_setting="",
                character_state=read_file(os.path.join(filepath, "character_state.txt")),
                global_summary=read_file(os.path.join(filepath, "global_summary.txt")),
                chapter_text=chapter_text,
                api_key=api_key, base_url=base_url, model_name=model_name,
                temperature=temperature, interface_format=interface_format,
                max_tokens=max_tokens, timeout=timeout, plot_arcs=""
            )
            self.safe_log("审校结果：")
            self.safe_log(result)
        except Exception:
            self.handle_exception("审校时出错")
        finally:
            self.enable_button_safe(self.btn_check_consistency)
            done_evt.set()

    self.disable_button_safe(self.btn_check_consistency)
    threading.Thread(target=task, daemon=True).start()
    return done_evt

def import_knowledge_handler(self):
    selected_file = tk.filedialog.askopenfilename(
        title="选择要导入的知识库文件",
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

                # 尝试不同编码读取文件
                content = None
                encodings = ['utf-8', 'gbk', 'gb2312', 'ansi']
                for encoding in encodings:
                    try:
                        with open(selected_file, 'r', encoding=encoding) as f:
                            content = f.read()
                            break
                    except UnicodeDecodeError:
                        continue
                    except Exception as e:
                        self.safe_log(f"读取文件时发生错误: {str(e)}")
                        raise

                if content is None:
                    raise Exception("无法以任何已知编码格式读取文件")

                # 创建临时UTF-8文件
                import tempfile
                import os
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as temp:
                    temp.write(content)
                    temp_path = temp.name

                try:
                    self.safe_log(f"开始导入知识库文件: {selected_file}")
                    import_knowledge_file(
                        embedding_api_key=emb_api_key,
                        embedding_url=emb_url,
                        embedding_interface_format=emb_format,
                        embedding_model_name=emb_model,
                        file_path=temp_path,
                        filepath=self.filepath_var.get().strip()
                    )
                    self.safe_log("✅ 知识库文件导入完成。")
                finally:
                    # 清理临时文件
                    try:
                        os.unlink(temp_path)
                    except:
                        pass

            except Exception:
                self.handle_exception("导入知识库时出错")
            finally:
                self.enable_button_safe(self.btn_import_knowledge)

        try:
            thread = threading.Thread(target=task, daemon=True)
            thread.start()
        except Exception as e:
            self.enable_button_safe(self.btn_import_knowledge)
            messagebox.showerror("错误", f"线程启动失败: {str(e)}")

def clear_vectorstore_handler(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        return

    first_confirm = messagebox.askyesno("警告", "确定要清空本地向量库吗？此操作不可恢复！")
    if first_confirm:
        second_confirm = messagebox.askyesno("二次确认", "你确定真的要删除所有向量数据吗？此操作不可恢复！")
        if second_confirm:
            if clear_vector_store(filepath):
                self.log("已清空向量库。")
            else:
                self.log(f"未能清空向量库，请关闭程序后手动删除 {filepath} 下的 vectorstore 文件夹。")

def show_plot_arcs_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先在主Tab中设置保存文件路径")
        return

    plot_arcs_file = os.path.join(filepath, "plot_arcs.txt")
    if not os.path.exists(plot_arcs_file):
        messagebox.showinfo("剧情要点", "当前还未生成任何剧情要点或冲突记录。")
        return

    arcs_text = read_file(plot_arcs_file).strip()
    if not arcs_text:
        arcs_text = "当前没有记录的剧情要点或冲突。"

    top = ctk.CTkToplevel(self.master)
    top.title("剧情要点/未解决冲突")
    top.geometry("600x400")
    text_area = ctk.CTkTextbox(top, wrap="word", font=("Microsoft YaHei", 12))
    text_area.pack(fill="both", expand=True, padx=10, pady=10)
    text_area.insert("0.0", arcs_text)
    text_area.configure(state="disabled")

def batch_generate_chapters_ui(self):

    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        return

    # 读取范围
    start_chap = self.safe_get_int(self.start_chap_var, 1)
    total_chapters = self.safe_get_int(self.num_chapters_var, 10)
    end_chap = self.safe_get_int(self.end_chap_var, total_chapters)

    if start_chap < 1 or end_chap > total_chapters or start_chap > end_chap:
        messagebox.showerror("范围错误", f"请输入 1–{total_chapters} 且起始≤结束")
        return

    # 所有确认框自动点“是”
    orig_yesno = messagebox.askyesno
    messagebox.askyesno = lambda *a, **k: True

    def task():
        self.disable_button_safe(self.btn_batch_process)
        try:
            for chap in range(start_chap, end_chap + 1):
                self.chapter_num_var.set(str(chap))
                self.safe_log(f"🔹 [{chap}] 生成草稿…")
                self.generate_chapter_draft_ui(auto_confirm=True).wait()

                self.safe_log(f"🔹 [{chap}] 一致性审校…")
                self.do_consistency_check().wait()

                self.safe_log(f"🔹 [{chap}] 定稿…")
                self.finalize_chapter_ui().wait()

                self.safe_log(f"✅ 第 {chap} 章完成")
            self.safe_log("🎉 批量处理全部章节完成！")
        except Exception:
            self.handle_exception("批量处理章节时出错")
        finally:
            messagebox.askyesno = orig_yesno
            self.enable_button_safe(self.btn_batch_process)

    threading.Thread(target=task, daemon=True).start()
