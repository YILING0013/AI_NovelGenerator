# ui/main_window.py
# -*- coding: utf-8 -*-
import os
import threading
import logging
import traceback
from typing import Any
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from .role_library import RoleLibrary
from llm_adapters import create_llm_adapter
from config_manager import create_config, load_config, save_config, test_llm_config, test_embedding_config
from utils import read_file, save_string_to_txt, clear_file_content
from tooltips import tooltips
from ui.proxy_utils import build_proxy_url, clear_proxy_env, apply_proxy_env

from ui.context_menu import TextWidgetContextMenu
from ui.main_tab import build_main_tab, build_left_layout, build_right_layout
from ui.config_tab import build_config_tabview, load_config_btn, save_config_btn
from ui.novel_params_tab import build_novel_params_area, build_optional_buttons_area, add_save_button_to_params, save_novel_params_config
from ui.generation_handlers import (
    generate_novel_architecture_ui,
    generate_chapter_blueprint_ui,
    generate_chapter_draft_ui,
    finalize_chapter_ui,
    do_consistency_check,
    import_knowledge_handler,
    clear_vectorstore_handler,
    show_plot_arcs_ui,
    generate_batch_ui,
    _start_blueprint_repair,
    _start_coherence_repair
)
from ui.setting_tab import build_setting_tab, load_novel_architecture, save_novel_architecture
from ui.directory_tab import build_directory_tab, load_chapter_blueprint, save_chapter_blueprint
from ui.character_tab import build_character_tab, load_character_state, save_character_state
from ui.summary_tab import build_summary_tab, load_global_summary, save_global_summary
from ui.chapters_tab import build_chapters_tab, refresh_chapters_list, on_chapter_selected, load_chapter_content, save_current_chapter, prev_chapter, next_chapter
from ui.other_settings import build_other_settings_tab
from ui.quality_logs_tab import build_quality_logs_tab


class NovelGeneratorGUI:
    """
    小说生成器的主GUI类，包含所有的界面布局、事件处理、与后端逻辑的交互等。
    """
    def __init__(self, master):


        self.master = master
        self.master.title("Novel Generator GUI")
        try:
            if os.path.exists("icon.ico"):
                self.master.iconbitmap("icon.ico")
        except Exception:
            pass
        self.master.geometry("1350x840")

        # --------------- 配置文件路径 ---------------
        self.config_file = "config.json"
        self.loaded_config = load_config(self.config_file)
        if (
            not isinstance(self.loaded_config, dict)
            or not isinstance(self.loaded_config.get("llm_configs"), dict)
            or not self.loaded_config.get("llm_configs")
        ):
            logging.warning("配置文件缺失或结构损坏，已自动重建默认配置。")
            self.loaded_config = create_config(self.config_file)

        llm_configs = self.loaded_config.get("llm_configs", {})
        first_llm_conf = next(iter(llm_configs.values()), {})
        last_llm = first_llm_conf.get("interface_format", "OpenAI")
        last_embedding = self.loaded_config.get("last_embedding_interface_format", "OpenAI")

        # if self.loaded_config and "llm_configs" in self.loaded_config and last_llm in self.loaded_config["llm_configs"]:
        #     llm_conf = next(iter(self.loaded_config["llm_configs"]))
        # else:
        #     llm_conf = {
        #         "api_key": "",
        #         "base_url": "https://api.openai.com/v1",
        #         "model_name": "gpt-4o-mini",
        #         "temperature": 0.7,
        #         "max_tokens": 8192,
        #         "timeout": 600
        #     }
        llm_conf = next(iter(llm_configs.values()), {})
        choose_configs = self.loaded_config.get("choose_configs", {})


        embedding_configs = self.loaded_config.get("embedding_configs", {})
        if isinstance(embedding_configs, dict) and last_embedding in embedding_configs:
            emb_conf = embedding_configs[last_embedding]
        else:
            emb_conf = {
                "api_key": "",
                "base_url": "https://api.openai.com/v1",
                "model_name": "text-embedding-ada-002",
                "retrieval_k": 4
            }

        # PenBo 增加代理功能支持
        proxy_setting = self.loaded_config.get("proxy_setting", {})
        if not isinstance(proxy_setting, dict):
            proxy_setting = {}
        proxy_url_raw = proxy_setting.get("proxy_url", "")
        proxy_port = str(proxy_setting.get("proxy_port", "")).strip()
        proxy_url = build_proxy_url(proxy_url_raw, proxy_port)
        if proxy_setting.get("enabled", False) and proxy_url:
            apply_proxy_env(proxy_url)
        else:
            clear_proxy_env()



        # -- LLM通用参数 --
        # self.llm_conf_name = next(iter(self.loaded_config["llm_configs"]))
        self.api_key_var = ctk.StringVar(value=llm_conf.get("api_key", ""))
        self.base_url_var = ctk.StringVar(value=llm_conf.get("base_url", "https://api.openai.com/v1"))
        self.interface_format_var = ctk.StringVar(value=llm_conf.get("interface_format", "OpenAI"))
        self.model_name_var = ctk.StringVar(value=llm_conf.get("model_name", "gpt-4o-mini"))
        self.temperature_var = ctk.DoubleVar(value=llm_conf.get("temperature", 0.7))
        self.max_tokens_var = ctk.IntVar(value=llm_conf.get("max_tokens", 8192))
        self.timeout_var = ctk.IntVar(value=llm_conf.get("timeout", 600))
        self.interface_config_var = ctk.StringVar(value=next(iter(llm_configs), ""))



        # -- Embedding相关 --
        self.embedding_interface_format_var = ctk.StringVar(value=last_embedding)
        self.embedding_api_key_var = ctk.StringVar(value=emb_conf.get("api_key", ""))
        self.embedding_url_var = ctk.StringVar(value=emb_conf.get("base_url", "https://api.openai.com/v1"))
        self.embedding_model_name_var = ctk.StringVar(value=emb_conf.get("model_name", "text-embedding-ada-002"))
        self.embedding_retrieval_k_var = ctk.StringVar(value=str(emb_conf.get("retrieval_k", 4)))


        # -- 生成配置相关 (验证配置名称有效性) --
        available_llm_configs = list(self.loaded_config.get("llm_configs", {}).keys())
        default_llm = available_llm_configs[0] if available_llm_configs else "DeepSeek"
        
        def get_valid_config(key):
            """获取有效的配置名称，如果旧配置不存在则回落到默认值"""
            saved_value = choose_configs.get(key, default_llm)
            if saved_value in available_llm_configs:
                return saved_value
            return default_llm
        
        self.architecture_llm_var = ctk.StringVar(value=get_valid_config("architecture_llm"))
        self.chapter_outline_llm_var = ctk.StringVar(value=get_valid_config("chapter_outline_llm"))
        self.final_chapter_llm_var = ctk.StringVar(value=get_valid_config("final_chapter_llm"))
        self.consistency_review_llm_var = ctk.StringVar(value=get_valid_config("consistency_review_llm"))
        self.prompt_draft_llm_var = ctk.StringVar(value=get_valid_config("prompt_draft_llm"))
        self.quality_loop_llm_var = ctk.StringVar(value=get_valid_config("quality_loop_llm"))  # 🆕 质量闭环LLM





        # -- 小说参数相关 --
        if self.loaded_config and "other_params" in self.loaded_config:
            op = self.loaded_config["other_params"]
            self.topic_default = op.get("topic", "")
            self.genre_var = ctk.StringVar(value=op.get("genre", ""))
            self.num_chapters_var = ctk.StringVar(value=str(op.get("num_chapters", 10)))
            self.word_number_var = ctk.StringVar(value=str(op.get("word_number", 3000)))
            self.filepath_var = ctk.StringVar(value=op.get("filepath", ""))
            self.chapter_num_var = ctk.StringVar(value=str(op.get("chapter_num", "1")))
            self.characters_involved_var = ctk.StringVar(value=op.get("characters_involved", ""))
            self.key_items_var = ctk.StringVar(value=op.get("key_items", ""))
            self.scene_location_var = ctk.StringVar(value=op.get("scene_location", ""))
            self.time_constraint_var = ctk.StringVar(value=op.get("time_constraint", ""))
            self.user_guidance_default = op.get("user_guidance", "")
            self.webdav_url_var = ctk.StringVar(value=op.get("webdav_url", ""))
            self.webdav_username_var = ctk.StringVar(value=op.get("webdav_username", ""))
            self.webdav_password_var = ctk.StringVar(value=op.get("webdav_password", ""))

        else:
            self.topic_default = ""
            self.genre_var = ctk.StringVar(value="")
            self.num_chapters_var = ctk.StringVar(value="10")
            self.word_number_var = ctk.StringVar(value="3000")
            self.filepath_var = ctk.StringVar(value="")
            self.chapter_num_var = ctk.StringVar(value="1")
            self.characters_involved_var = ctk.StringVar(value="")
            self.key_items_var = ctk.StringVar(value="")
            self.scene_location_var = ctk.StringVar(value="")
            self.time_constraint_var = ctk.StringVar(value="")
            self.user_guidance_default = ""

        # --------------- 整体Tab布局 ---------------
        self.tabview = ctk.CTkTabview(self.master)
        self.tabview.pack(fill="both", expand=True)

        # 绑定小说参数保存函数（在创建GUI组件之前）
        self.add_save_button_to_params = lambda: add_save_button_to_params(self)

        # 创建一个保存函数，包含防抖机制
        def save_novel_params_config_with_debounce():
            """带防抖机制的保存函数"""
            # 防抖机制：如果已经有一个保存计划，先取消它
            if hasattr(self, '_save_pending_timer'):
                self.master.after_cancel(self._save_pending_timer)
            # 计划新的保存操作
            self._save_pending_timer = self.master.after(500, self._do_save_novel_params_config)

        def do_save_novel_params_config():
            """实际执行保存操作"""
            save_novel_params_config(self)
            # 清除待保存标记
            if hasattr(self, '_save_pending_timer'):
                delattr(self, '_save_pending_timer')

        self.save_novel_params_config = save_novel_params_config_with_debounce
        self._do_save_novel_params_config = do_save_novel_params_config

        # 创建各个标签页
        build_main_tab(self)
        build_config_tabview(self)
        build_novel_params_area(self, start_row=1)
        build_optional_buttons_area(self, start_row=2)
        build_setting_tab(self)
        build_directory_tab(self)
        build_character_tab(self)
        build_summary_tab(self)
        build_chapters_tab(self)
        build_other_settings_tab(self)
        build_quality_logs_tab(self)

        # 设置窗口关闭时的自动保存
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        """窗口关闭时的处理函数"""
        try:
            # 保存小说参数配置
            if hasattr(self, 'save_novel_params_config'):
                self.save_novel_params_config()

            # 保存Embedding配置
            if hasattr(self, 'auto_save_embedding_config'):
                # 立即执行保存，不使用防抖
                if hasattr(self, '_embedding_save_timer'):
                    self.master.after_cancel(self._embedding_save_timer)
                    delattr(self, '_embedding_save_timer')
                self._do_save_embedding_config()

            # 可以在这里添加其他保存逻辑
        except Exception as e:
            print(f"关闭时保存配置出错: {e}")
        finally:
            self.master.destroy()


    # ----------------- 通用辅助函数 -----------------
    def show_tooltip(self, key: str):
        info_text = tooltips.get(key, "暂无说明")
        messagebox.showinfo("参数说明", info_text)

    def safe_get_int(self, var, default=1):
        try:
            val_str = str(var.get()).strip()
            return int(val_str)
        except:
            var.set(str(default))
            return default

    def log(self, message: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def safe_log(self, message: str):
        self.master.after(0, lambda: self.log(message))

    def update_step2_repair_status(self, text: str, progress: float | None = None, text_color: str = "gray") -> None:
        """更新 Step2 目录自动修复/续写状态条。"""
        if hasattr(self, "step2_repair_status_label"):
            self.step2_repair_status_label.configure(text=text, text_color=text_color)
        if progress is not None and hasattr(self, "step2_repair_progressbar"):
            try:
                value = float(progress)
            except (TypeError, ValueError):
                value = 0.0
            value = max(0.0, min(1.0, value))
            self.step2_repair_progressbar.set(value)

    def safe_update_step2_repair_status(self, text: str, progress: float | None = None, text_color: str = "gray") -> None:
        self.master.after(
            0,
            lambda: self.update_step2_repair_status(text=text, progress=progress, text_color=text_color),
        )
    
    def _refresh_quality_reason_stats(self):
        if not hasattr(self, "quality_reason_stats_text"):
            return
        if not hasattr(self, "_quality_reason_counts"):
            self._quality_reason_counts = {}

        items = sorted(self._quality_reason_counts.items(), key=lambda x: x[1], reverse=True)
        total = sum(v for _, v in items)
        lines = [f"总事件数: {total}"]
        if not items:
            lines.append("暂无统计数据")
        else:
            top_items = items[:8]
            for reason, count in top_items:
                ratio = (count / total * 100.0) if total > 0 else 0.0
                lines.append(f"- {reason}: {count} ({ratio:.1f}%)")

        self.quality_reason_stats_text.configure(state="normal")
        self.quality_reason_stats_text.delete("0.0", "end")
        self.quality_reason_stats_text.insert("0.0", "\n".join(lines))
        self.quality_reason_stats_text.configure(state="disabled")
    
    def log_quality_score_event(self, event: dict):
        """在评分日志面板中追加一条评分事件。"""
        if not hasattr(self, "quality_log_text"):
            return
        if not isinstance(event, dict):
            return

        chapter = event.get("chapter", "?")
        iteration = int(event.get("iteration", 0)) + 1
        raw_score = event.get("raw_score")
        critic_score = event.get("critic_score")
        final_score = event.get("final_score")
        reasons = event.get("trigger_reasons", []) or []
        pass_reasons = event.get("pass_reasons", []) or []
        critic_feedback = event.get("critic_feedback", "")
        guard_feedback = event.get("guard_feedback", "")

        # 去重：回调实时写入 + 闭环结束兜底回放时避免重复。
        if not hasattr(self, "_quality_event_keys"):
            self._quality_event_keys = set()
        dedupe_key = (chapter, iteration, raw_score, critic_score, final_score, tuple(reasons))
        if dedupe_key in self._quality_event_keys:
            return
        self._quality_event_keys.add(dedupe_key)

        reason_alias = {
            "score_below_threshold": "分数低于阈值",
            "critic_reject": "毒舌拒收",
            "pass": "通过",
            "critic_agent_unavailable": "毒舌未启用/不可用",
        }
        normalized_reasons = []
        for item in reasons:
            text = str(item)
            if text.startswith("unresolved_conflicts:"):
                normalized_reasons.append(f"一致性问题残留({text.split(':', 1)[1]})")
            elif text.startswith("critic_skipped_below_threshold("):
                normalized_reasons.append(f"毒舌未触发(分数未达阈值)")
            elif text.startswith("safety_issues:"):
                normalized_reasons.append(f"敏感风险({text.split(':', 1)[1]})")
            elif text.startswith("pattern_issues:"):
                normalized_reasons.append(f"模式重复({text.split(':', 1)[1]})")
            else:
                normalized_reasons.append(reason_alias.get(text, text))

        reason_text = ", ".join(normalized_reasons) if normalized_reasons else "通过"
        if not hasattr(self, "_quality_reason_counts"):
            self._quality_reason_counts = {}
        for reason in (normalized_reasons or ["通过"]):
            self._quality_reason_counts[reason] = self._quality_reason_counts.get(reason, 0) + 1
        self._refresh_quality_reason_stats()

        raw_text = f"{float(raw_score):.2f}" if isinstance(raw_score, (int, float)) else "-"
        critic_text = f"{float(critic_score):.2f}" if isinstance(critic_score, (int, float)) else "-"
        final_text = f"{float(final_score):.2f}" if isinstance(final_score, (int, float)) else "-"

        lines = [
            f"[Ch{chapter}][Iter{iteration}] raw={raw_text} | critic={critic_text} | final={final_text}",
            f"  reasons: {reason_text}",
        ]
        if ("通过" in reason_text or "pass" in [str(x).lower() for x in reasons]) and pass_reasons:
            lines.append(f"  pass_feedback: {' | '.join([str(x) for x in pass_reasons[:6]])}")
        if guard_feedback:
            lines.append(f"  guard_feedback: {guard_feedback}")
        if critic_feedback:
            lines.append(f"  critic_feedback: {critic_feedback}")
        log_line = "\n".join(lines) + "\n"

        self.quality_log_text.configure(state="normal")
        self.quality_log_text.insert("end", log_line)
        self.quality_log_text.see("end")
        self.quality_log_text.configure(state="disabled")
    
    def safe_log_quality_score_event(self, event: dict):
        self.master.after(0, lambda: self.log_quality_score_event(event))

    def _refresh_precheck_risk_stats(self) -> None:
        if not hasattr(self, "precheck_risk_text"):
            return

        history = getattr(self, "_precheck_risk_history", [])
        if not history:
            lines = ["暂无预检风险数据"]
        else:
            latest = history[-1] if isinstance(history[-1], dict) else {}
            metrics = latest.get("metrics", {}) if isinstance(latest.get("metrics"), dict) else {}
            warnings = latest.get("warnings", []) if isinstance(latest.get("warnings"), list) else []
            risk_label = str(latest.get("risk_label", "未知"))
            risk_score = int(latest.get("risk_score", 0) or 0)
            chapter_range = str(latest.get("chapter_range", "-")).strip() or "-"
            timestamp = str(latest.get("timestamp", "-")).strip() or "-"

            lines = [
                f"最新等级: {risk_label} (score={risk_score})",
                f"扫描范围: {chapter_range}",
                f"扫描时间: {timestamp}",
                (
                    "指标: "
                    f"占位符{int(metrics.get('placeholder_count', 0) or 0)} | "
                    f"结构异常章{int(metrics.get('structure_chapters', 0) or 0)} | "
                    f"重复对{int(metrics.get('duplicate_pairs', 0) or 0)} | "
                    f"一致性提示章{int(metrics.get('consistency_chapters', 0) or 0)} | "
                    f"警告{int(metrics.get('warnings_count', 0) or 0)}"
                ),
            ]

            if warnings:
                lines.append("警告摘要:")
                for warning in warnings[:4]:
                    lines.append(f"- {warning}")

            recent_items = history[-5:]
            lines.append("最近记录:")
            for item in reversed(recent_items):
                if not isinstance(item, dict):
                    continue
                item_time = str(item.get("timestamp", "--:--:--"))[-8:]
                item_label = str(item.get("risk_label", "未知"))
                item_range = str(item.get("chapter_range", "-"))
                item_score = int(item.get("risk_score", 0) or 0)
                lines.append(f"- {item_time} | {item_label} | 范围{item_range} | score={item_score}")

        self.precheck_risk_text.configure(state="normal")
        self.precheck_risk_text.delete("0.0", "end")
        self.precheck_risk_text.insert("0.0", "\n".join(lines))
        self.precheck_risk_text.configure(state="disabled")

    def log_precheck_risk_event(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        if not hasattr(self, "_precheck_risk_history"):
            self._precheck_risk_history = []
        self._precheck_risk_history.append(dict(event))
        if len(self._precheck_risk_history) > 20:
            self._precheck_risk_history = self._precheck_risk_history[-20:]
        self._refresh_precheck_risk_stats()

    def safe_log_precheck_risk_event(self, event: dict[str, Any]) -> None:
        self.master.after(0, lambda: self.log_precheck_risk_event(event))

    def disable_button_safe(self, btn):
        self.master.after(0, lambda: btn.configure(state="disabled"))

    def enable_button_safe(self, btn):
        self.master.after(0, lambda: btn.configure(state="normal"))

    def handle_exception(self, context: str):
        full_message = f"{context}\n{traceback.format_exc()}"
        logging.error(full_message)
        self.safe_log(full_message)

    def show_chapter_in_textbox(self, text: str):
        self.chapter_result.delete("0.0", "end")
        self.chapter_result.insert("0.0", text)
        self.chapter_result.see("end")
    
    def test_llm_config(self):
        """
        测试当前的LLM配置是否可用
        """
        interface_format = self.interface_format_var.get().strip()
        api_key = self.api_key_var.get().strip()
        base_url = self.base_url_var.get().strip()
        model_name = self.model_name_var.get().strip()
        temperature = self.temperature_var.get()
        max_tokens = self.max_tokens_var.get()
        timeout = self.timeout_var.get()

        test_llm_config(
            interface_format=interface_format,
            api_key=api_key,
            base_url=base_url,
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            log_func=self.safe_log,
            handle_exception_func=self.handle_exception
        )

    def test_embedding_config(self):
        """
        测试当前的Embedding配置是否可用
        """
        api_key = self.embedding_api_key_var.get().strip()
        base_url = self.embedding_url_var.get().strip()
        interface_format = self.embedding_interface_format_var.get().strip()
        model_name = self.embedding_model_name_var.get().strip()

        test_embedding_config(
            api_key=api_key,
            base_url=base_url,
            interface_format=interface_format,
            model_name=model_name,
            log_func=self.safe_log,
            handle_exception_func=self.handle_exception
        )
    
    def browse_folder(self):
        selected_dir = filedialog.askdirectory()
        if selected_dir:
            self.filepath_var.set(selected_dir)

    def show_character_import_window(self):
        """显示角色导入窗口"""
        import_window = ctk.CTkToplevel(self.master)
        import_window.title("导入角色信息")
        import_window.geometry("600x500")
        import_window.transient(self.master)  # 设置为父窗口的临时窗口
        import_window.grab_set()  # 保持窗口在顶层
        
        # 主容器
        main_frame = ctk.CTkFrame(import_window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 滚动容器
        scroll_frame = ctk.CTkScrollableFrame(main_frame)
        scroll_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 获取角色库路径
        role_lib_path = os.path.join(self.filepath_var.get().strip(), "角色库")
        self.selected_roles = []  # 存储选中的角色名称
        
        # 动态加载角色分类
        if os.path.exists(role_lib_path):
            # 配置网格布局参数
            scroll_frame.columnconfigure(0, weight=1)
            max_roles_per_row = 4
            current_row = 0
            
            for category in os.listdir(role_lib_path):
                category_path = os.path.join(role_lib_path, category)
                if os.path.isdir(category_path):
                    # 创建分类容器
                    category_frame = ctk.CTkFrame(scroll_frame)
                    category_frame.grid(row=current_row, column=0, sticky="w", pady=(10,5), padx=5)
                    
                    # 添加分类标签
                    category_label = ctk.CTkLabel(category_frame, text=f"【{category}】", 
                                                font=("Microsoft YaHei", 12, "bold"))
                    category_label.grid(row=0, column=0, padx=(0,10), sticky="w")
                    
                    # 初始化角色排列参数
                    role_count = 0
                    row_num = 0
                    col_num = 1  # 从第1列开始（第0列是分类标签）
                    
                    # 添加角色复选框
                    for role_file in os.listdir(category_path):
                        if role_file.endswith(".txt"):
                            role_name = os.path.splitext(role_file)[0]
                            if not any(name == role_name for _, name in self.selected_roles):
                                chk = ctk.CTkCheckBox(category_frame, text=role_name)
                                chk.grid(row=row_num, column=col_num, padx=5, pady=2, sticky="w")
                                self.selected_roles.append((chk, role_name))
                                
                                # 更新行列位置
                                role_count += 1
                                col_num += 1
                                if col_num > max_roles_per_row:
                                    col_num = 1
                                    row_num += 1
                    
                    # 如果没有角色，调整分类标签占满整行
                    if role_count == 0:
                        category_label.grid(columnspan=max_roles_per_row+1, sticky="w")
                    
                    # 更新主布局的行号
                    current_row += 1
                    
                    # 添加分隔线
                    separator = ctk.CTkFrame(scroll_frame, height=1, fg_color="gray")
                    separator.grid(row=current_row, column=0, sticky="ew", pady=5)
                    current_row += 1
        
        # 底部按钮框架
        btn_frame = ctk.CTkFrame(main_frame)
        btn_frame.pack(fill="x", pady=10)
        
        # 选择按钮
        def confirm_selection():
            selected = [name for chk, name in self.selected_roles if chk.get() == 1]
            self.char_inv_text.delete("0.0", "end")
            self.char_inv_text.insert("0.0", ", ".join(selected))
            import_window.destroy()
            
        btn_confirm = ctk.CTkButton(btn_frame, text="选择", command=confirm_selection)
        btn_confirm.pack(side="left", padx=20)
        
        # 取消按钮
        btn_cancel = ctk.CTkButton(btn_frame, text="取消", command=import_window.destroy)
        btn_cancel.pack(side="right", padx=20)

    def show_role_library(self):
        save_path = self.filepath_var.get().strip()
        if not save_path:
            messagebox.showwarning("警告", "请先设置保存路径")
            return
        
        # 初始化LLM适配器
        llm_adapter = create_llm_adapter(
            interface_format=self.interface_format_var.get(),
            base_url=self.base_url_var.get(),
            model_name=self.model_name_var.get(),
            api_key=self.api_key_var.get(),
            temperature=self.temperature_var.get(),
            max_tokens=self.max_tokens_var.get(),
            timeout=self.timeout_var.get()
        )
        
        # 传递LLM适配器实例到角色库
        if hasattr(self, '_role_lib'):
            if self._role_lib.window and self._role_lib.window.winfo_exists():
                self._role_lib.window.destroy()
        
        self._role_lib = RoleLibrary(self.master, save_path, llm_adapter)  # 新增参数

    # ----------------- 将导入的各模块函数直接赋给类方法 -----------------
    generate_novel_architecture_ui = generate_novel_architecture_ui
    generate_chapter_blueprint_ui = generate_chapter_blueprint_ui
    generate_chapter_draft_ui = generate_chapter_draft_ui
    finalize_chapter_ui = finalize_chapter_ui
    do_consistency_check = do_consistency_check
    generate_batch_ui = generate_batch_ui
    _start_blueprint_repair = _start_blueprint_repair
    _start_coherence_repair = _start_coherence_repair
    import_knowledge_handler = import_knowledge_handler
    clear_vectorstore_handler = clear_vectorstore_handler
    show_plot_arcs_ui = show_plot_arcs_ui
    load_config_btn = load_config_btn
    save_config_btn = save_config_btn
    load_novel_architecture = load_novel_architecture
    save_novel_architecture = save_novel_architecture
    load_chapter_blueprint = load_chapter_blueprint
    save_chapter_blueprint = save_chapter_blueprint
    load_character_state = load_character_state
    save_character_state = save_character_state
    load_global_summary = load_global_summary
    save_global_summary = save_global_summary
    refresh_chapters_list = refresh_chapters_list
    on_chapter_selected = on_chapter_selected
    save_current_chapter = save_current_chapter
    prev_chapter = prev_chapter
    next_chapter = next_chapter
    test_llm_config = test_llm_config
    test_embedding_config = test_embedding_config
    browse_folder = browse_folder
