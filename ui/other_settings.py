# ui/other_settings.py
import customtkinter as ctk
from ui.config_tab import create_label_with_help
from tkinter import messagebox
from config_manager import load_config, save_config, normalize_quality_policy
import requests
from requests.auth import HTTPBasicAuth
import os
from xml.etree import ElementTree as ET
import shutil
import time


def _safe_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on", "enabled", "t"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "disabled", "f", ""}:
            return False
    return default


def build_other_settings_tab(self):
    self.other_settings_tab = self.tabview.add("Other Settings")
    self.other_settings_tab.rowconfigure(0, weight=1)
    self.other_settings_tab.columnconfigure(0, weight=1)

    # 使用可滚动容器，确保“质量控制配置”等长表单在小屏上也可完整访问。
    settings_scroll = ctk.CTkScrollableFrame(self.other_settings_tab, orientation="vertical")
    settings_scroll.grid(row=0, column=0, sticky="nsew")
    settings_scroll.grid_columnconfigure(0, weight=1)

    if "webdav_config" not in self.loaded_config:
        self.loaded_config["webdav_config"] = {
            "webdav_url": "",
            "webdav_username": "",
            "webdav_password": "",
            "webdav_target_dir": "AI_Novel_Generator"
        }
    if "webdav_target_dir" not in self.loaded_config["webdav_config"]:
        self.loaded_config["webdav_config"]["webdav_target_dir"] = "AI_Novel_Generator"

    self.webdav_url_var.set(self.loaded_config["webdav_config"].get("webdav_url", ""))
    self.webdav_username_var.set(self.loaded_config["webdav_config"].get("webdav_username", ""))
    self.webdav_password_var.set(self.loaded_config["webdav_config"].get("webdav_password", ""))
    if not hasattr(self, "webdav_target_dir_var"):
        self.webdav_target_dir_var = ctk.StringVar()
    self.webdav_target_dir_var.set(
        self.loaded_config["webdav_config"].get("webdav_target_dir", "AI_Novel_Generator")
    )

    def get_webdav_target_dir() -> str:
        target_dir = self.webdav_target_dir_var.get().strip()
        return target_dir if target_dir else "AI_Novel_Generator"


    def save_webdav_settings():
        self.loaded_config["webdav_config"]["webdav_url"] = self.webdav_url_var.get().strip()
        self.loaded_config["webdav_config"]["webdav_username"] = self.webdav_username_var.get().strip()
        self.loaded_config["webdav_config"]["webdav_password"] = self.webdav_password_var.get().strip()
        self.loaded_config["webdav_config"]["webdav_target_dir"] = get_webdav_target_dir()
        save_config(self.loaded_config, self.config_file)


    def test_webdav_connection(test = True):
        try:
            client = WebDAVClient(self.webdav_url_var.get().strip(),self.webdav_username_var.get().strip(),self.webdav_password_var.get().strip())
            client.list_directory()
            if not test:
                save_webdav_settings()
                return True
            messagebox.showinfo("成功", "WebDAV 连接成功！")
            save_webdav_settings()
            return True

        except Exception as e:
            print(e)

            messagebox.showerror("错误", f"发生未知错误: {e}")
            return False

    def backup_to_webdav():
        try:
            target_dir = get_webdav_target_dir()
            client = WebDAVClient(self.webdav_url_var.get().strip(),self.webdav_username_var.get().strip(),self.webdav_password_var.get().strip())
            if not client.ensure_directory_exists(target_dir):
                client.create_directory(target_dir)
            client.upload_file(self.config_file, f"{target_dir}/config.json")
            messagebox.showinfo("成功", "配置备份成功！")
        except Exception as e:
            print(e)
            messagebox.showerror("错误", f"发生未知错误: {e}")
            return False







    def restore_from_webdav():
        try:
            target_dir = get_webdav_target_dir()
            client = WebDAVClient(self.webdav_url_var.get().strip(),self.webdav_username_var.get().strip(),self.webdav_password_var.get().strip())
            client.download_file(f"{target_dir}/config.json", self.config_file)
            self.loaded_config = load_config(self.config_file)
            messagebox.showinfo("成功", "配置恢复成功！")

        except Exception as e:
            print(e)
            messagebox.showerror("错误", f"发生未知错误: {e}")
            return False




    dav_frame = ctk.CTkFrame(settings_scroll)
    dav_frame.pack(padx=20, pady=20, fill="x")

    dav_title = ctk.CTkLabel(dav_frame, text="webdav设置", font=("Microsoft YaHei", 16, "bold"))
    dav_title.pack(anchor="w", padx=5, pady=(0, 5))
    dav_warp_frame = ctk.CTkFrame(dav_frame, corner_radius=10, border_width=2, border_color="gray")
    dav_warp_frame.pack(fill="x", padx=5)
    dav_warp_frame.columnconfigure(1, weight=1)

    

    create_label_with_help(self, parent=dav_warp_frame, label_text="Webdav URL", tooltip_key="webdav_url",row=0, column=0, font=("Microsoft YaHei", 12), sticky="w")
    dav_url_entry = ctk.CTkEntry(dav_warp_frame, textvariable=self.webdav_url_var, font=("Microsoft YaHei", 12))
    dav_url_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

    create_label_with_help(self, parent=dav_warp_frame, label_text="Webdav用户名", tooltip_key="webdav_username",row=1, column=0, font=("Microsoft YaHei", 12), sticky="w")
    dav_username_entry = ctk.CTkEntry(dav_warp_frame, textvariable=self.webdav_username_var, font=("Microsoft YaHei", 12))
    dav_username_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")

    create_label_with_help(self, parent=dav_warp_frame, label_text="Webdav密码", tooltip_key="webdav_password",row=2, column=0, font=("Microsoft YaHei", 12), sticky="w")
    dav_password_entry = ctk.CTkEntry(dav_warp_frame, textvariable=self.webdav_password_var, font=("Microsoft YaHei", 12), show="*")
    dav_password_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")

    create_label_with_help(self, parent=dav_warp_frame, label_text="Webdav目录", tooltip_key="webdav_target_dir",row=3, column=0, font=("Microsoft YaHei", 12), sticky="w")
    dav_target_dir_entry = ctk.CTkEntry(dav_warp_frame, textvariable=self.webdav_target_dir_var, font=("Microsoft YaHei", 12))
    dav_target_dir_entry.grid(row=3, column=1, padx=5, pady=5, sticky="w")

    button_frame = ctk.CTkFrame(dav_warp_frame)
    button_frame.grid(row=4, column=0, columnspan=2, padx=5, pady=10, sticky="w")
    
    # 测试连接按钮
    test_btn = ctk.CTkButton(button_frame, text="测试连接", font=("Microsoft YaHei", 12),
                            command=test_webdav_connection)
    test_btn.pack(side="left", padx=5)
    
    # 保存设置按钮
    save_btn = ctk.CTkButton(button_frame, text="备份", font=("Microsoft YaHei", 12),
                            command=backup_to_webdav)
    save_btn.pack(side="left", padx=5)
    
    # 重置按钮
    reset_btn = ctk.CTkButton(button_frame, text="恢复", font=("Microsoft YaHei", 12),
                             command=restore_from_webdav)
    reset_btn.pack(side="left", padx=5)

    # ==================== 质量控制配置面板 ====================
    quality_frame = ctk.CTkFrame(settings_scroll)
    quality_frame.pack(padx=20, pady=20, fill="x")
    
    quality_title_row = ctk.CTkFrame(quality_frame, fg_color="transparent")
    quality_title_row.pack(fill="x", padx=5, pady=(0, 5))
    quality_title = ctk.CTkLabel(quality_title_row, text="质量控制配置 (P0/P1增强)", font=("Microsoft YaHei", 16, "bold"))
    quality_title.pack(side="left", anchor="w")
    quality_quick_save_btn = ctk.CTkButton(
        quality_title_row,
        text="保存质量配置",
        width=130,
        font=("Microsoft YaHei", 12),
        state="disabled",
    )
    quality_quick_save_btn.pack(side="right")
    quality_stage_legend = ctk.CTkLabel(
        quality_frame,
        text="图例：🔵 S1架构 | 🟣 S2章节目录 | 🟢 S3章节生成/批量",
        font=("Microsoft YaHei", 11),
        text_color="gray",
    )
    quality_stage_legend.pack(fill="x", padx=8, pady=(0, 4), anchor="w")
    
    quality_warp_frame = ctk.CTkFrame(quality_frame, corner_radius=10, border_width=2, border_color="gray")
    quality_warp_frame.pack(fill="x", padx=5)
    quality_warp_frame.columnconfigure(1, weight=1)
    
    # 初始化质量控制变量
    quality_params = self.loaded_config.get("other_params", {})
    if not isinstance(quality_params, dict):
        quality_params = {}
    quality_loop_llm_name = self.quality_loop_llm_var.get() if hasattr(self, "quality_loop_llm_var") else ""
    quality_loop_cfg = self.loaded_config.get("llm_configs", {}).get(quality_loop_llm_name, {})
    if not isinstance(quality_loop_cfg, dict):
        quality_loop_cfg = {}
    quality_policy = quality_loop_cfg.get("quality_policy", {})
    if not isinstance(quality_policy, dict):
        quality_policy = {}
    if not hasattr(self, 'enable_iterative_gen_var'):
        self.enable_iterative_gen_var = ctk.BooleanVar()
    self.enable_iterative_gen_var.set(
        _safe_bool(quality_params.get("enable_iterative_generation"), default=True)
    )

    if not hasattr(self, 'max_iterations_var'):
        self.max_iterations_var = ctk.StringVar()
    self.max_iterations_var.set(str(quality_params.get("max_iterations", 3)))

    if not hasattr(self, 'quality_threshold_var'):
        self.quality_threshold_var = ctk.StringVar()
    self.quality_threshold_var.set(str(quality_params.get("quality_threshold", 7.5)))

    if not hasattr(self, 'force_critic_logging_each_iteration_var'):
        self.force_critic_logging_each_iteration_var = ctk.BooleanVar()
    self.force_critic_logging_each_iteration_var.set(
        _safe_bool(
            quality_policy.get(
                "force_critic_logging_each_iteration",
                quality_params.get("force_critic_logging_each_iteration", False),
            ),
            default=False,
        )
    )

    if not hasattr(self, 'enable_llm_consistency_var'):
        self.enable_llm_consistency_var = ctk.BooleanVar()
    self.enable_llm_consistency_var.set(
        _safe_bool(quality_params.get("enable_llm_consistency_check"), default=True)
    )

    if not hasattr(self, 'consistency_hard_gate_var'):
        self.consistency_hard_gate_var = ctk.BooleanVar()
    self.consistency_hard_gate_var.set(
        _safe_bool(quality_params.get("consistency_hard_gate"), default=True)
    )

    if not hasattr(self, 'enable_timeline_check_var'):
        self.enable_timeline_check_var = ctk.BooleanVar()
    self.enable_timeline_check_var.set(
        _safe_bool(quality_params.get("enable_timeline_check"), default=True)
    )

    if not hasattr(self, 'timeline_hard_gate_var'):
        self.timeline_hard_gate_var = ctk.BooleanVar()
    self.timeline_hard_gate_var.set(
        _safe_bool(quality_params.get("timeline_hard_gate"), default=True)
    )

    if not hasattr(self, 'stop_batch_on_hard_gate_var'):
        self.stop_batch_on_hard_gate_var = ctk.BooleanVar()
    self.stop_batch_on_hard_gate_var.set(
        _safe_bool(quality_params.get("stop_batch_on_hard_gate"), default=True)
    )

    if not hasattr(self, 'post_batch_runtime_audit_enabled_var'):
        self.post_batch_runtime_audit_enabled_var = ctk.BooleanVar()
    self.post_batch_runtime_audit_enabled_var.set(
        _safe_bool(quality_params.get("post_batch_runtime_audit_enabled"), default=False)
    )

    if not hasattr(self, 'post_batch_runtime_audit_sample_size_var'):
        self.post_batch_runtime_audit_sample_size_var = ctk.StringVar()
    self.post_batch_runtime_audit_sample_size_var.set(
        str(quality_params.get("post_batch_runtime_audit_sample_size", 20))
    )

    if not hasattr(self, 'blueprint_full_auto_mode_var'):
        self.blueprint_full_auto_mode_var = ctk.BooleanVar()
    self.blueprint_full_auto_mode_var.set(
        _safe_bool(quality_params.get("blueprint_full_auto_mode"), default=True)
    )

    if not hasattr(self, 'blueprint_auto_restart_on_arch_change_var'):
        self.blueprint_auto_restart_on_arch_change_var = ctk.BooleanVar()
    self.blueprint_auto_restart_on_arch_change_var.set(
        _safe_bool(quality_params.get("blueprint_auto_restart_on_arch_change"), default=True)
    )

    if not hasattr(self, 'blueprint_resume_auto_repair_existing_var'):
        self.blueprint_resume_auto_repair_existing_var = ctk.BooleanVar()
    self.blueprint_resume_auto_repair_existing_var.set(
        _safe_bool(quality_params.get("blueprint_resume_auto_repair_existing"), default=True)
    )

    if not hasattr(self, 'blueprint_force_resume_skip_history_validation_var'):
        self.blueprint_force_resume_skip_history_validation_var = ctk.BooleanVar()
    self.blueprint_force_resume_skip_history_validation_var.set(
        _safe_bool(quality_params.get("blueprint_force_resume_skip_history_validation"), default=False)
    )

    if not hasattr(self, 'batch_partial_resume_allow_fallback_var'):
        self.batch_partial_resume_allow_fallback_var = ctk.BooleanVar()
    self.batch_partial_resume_allow_fallback_var.set(
        _safe_bool(quality_params.get("batch_partial_resume_allow_fallback"), default=True)
    )

    if not hasattr(self, 'batch_precheck_deep_scan_var'):
        self.batch_precheck_deep_scan_var = ctk.BooleanVar()
    self.batch_precheck_deep_scan_var.set(
        _safe_bool(quality_params.get("batch_precheck_deep_scan"), default=True)
    )

    if not hasattr(self, 'batch_precheck_auto_continue_on_warning_var'):
        self.batch_precheck_auto_continue_on_warning_var = ctk.BooleanVar()
    self.batch_precheck_auto_continue_on_warning_var.set(
        _safe_bool(quality_params.get("batch_precheck_auto_continue_on_warning"), default=True)
    )

    if not hasattr(self, 'architecture_context_ignore_budget_var'):
        self.architecture_context_ignore_budget_var = ctk.BooleanVar()
    self.architecture_context_ignore_budget_var.set(
        _safe_bool(quality_params.get("architecture_context_ignore_budget"), default=True)
    )

    if not hasattr(self, 'architecture_context_budget_chapter_prompt_var'):
        self.architecture_context_budget_chapter_prompt_var = ctk.StringVar()
    self.architecture_context_budget_chapter_prompt_var.set(
        str(quality_params.get("architecture_context_budget_chapter_prompt", 18000))
    )

    if not hasattr(self, 'architecture_context_budget_consistency_var'):
        self.architecture_context_budget_consistency_var = ctk.StringVar()
    self.architecture_context_budget_consistency_var.set(
        str(quality_params.get("architecture_context_budget_consistency", 22000))
    )

    if not hasattr(self, 'architecture_context_budget_quality_loop_var'):
        self.architecture_context_budget_quality_loop_var = ctk.StringVar()
    self.architecture_context_budget_quality_loop_var.set(
        str(quality_params.get("architecture_context_budget_quality_loop", 16000))
    )

    if not hasattr(self, 'enable_knowledge_extraction_var'):
        self.enable_knowledge_extraction_var = ctk.BooleanVar()
    self.enable_knowledge_extraction_var.set(
        _safe_bool(quality_params.get("enable_post_generation_extraction"), default=True)
    )
    
    # 迭代生成开关
    iter_check = ctk.CTkCheckBox(quality_warp_frame, text="🟢 [S3章节] 启用迭代质量生成 (生成→评估→修正循环)",
                                  variable=self.enable_iterative_gen_var, font=("Microsoft YaHei", 12))
    iter_check.grid(row=0, column=0, columnspan=2, padx=10, pady=5, sticky="w")
    
    # 最大迭代次数
    ctk.CTkLabel(quality_warp_frame, text="🟢 [S3] 最大迭代次数:", font=("Microsoft YaHei", 12)).grid(row=1, column=0, padx=10, pady=5, sticky="w")
    iter_entry = ctk.CTkEntry(quality_warp_frame, textvariable=self.max_iterations_var, width=80, font=("Microsoft YaHei", 12))
    iter_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
    
    # 质量阈值
    ctk.CTkLabel(quality_warp_frame, text="🟢 [S3] 质量阈值 (7.0-9.0):", font=("Microsoft YaHei", 12)).grid(row=2, column=0, padx=10, pady=5, sticky="w")
    threshold_entry = ctk.CTkEntry(quality_warp_frame, textvariable=self.quality_threshold_var, width=80, font=("Microsoft YaHei", 12))
    threshold_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")

    force_critic_log_check = ctk.CTkCheckBox(
        quality_warp_frame,
        text="🟢 [S3章节] 低分轮次也输出毒舌对话日志（仅记录，不参与门控）",
        variable=self.force_critic_logging_each_iteration_var,
        font=("Microsoft YaHei", 12),
    )
    force_critic_log_check.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="w")
    
    # LLM一致性检查
    consistency_check = ctk.CTkCheckBox(quality_warp_frame, text="🟢 [S3章节] 启用LLM深度一致性检查",
                                         variable=self.enable_llm_consistency_var, font=("Microsoft YaHei", 12))
    consistency_check.grid(row=4, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    hard_gate_check = ctk.CTkCheckBox(
        quality_warp_frame,
        text="🟢 [S3章节] 启用高危一致性阻断（推荐）",
        variable=self.consistency_hard_gate_var,
        font=("Microsoft YaHei", 12),
    )
    hard_gate_check.grid(row=5, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    timeline_check = ctk.CTkCheckBox(
        quality_warp_frame,
        text="🟢 [S3章节] 启用时间线一致性检查",
        variable=self.enable_timeline_check_var,
        font=("Microsoft YaHei", 12),
    )
    timeline_check.grid(row=6, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    timeline_hard_gate_check = ctk.CTkCheckBox(
        quality_warp_frame,
        text="🟢 [S3章节] 启用时间线硬阻断（推荐）",
        variable=self.timeline_hard_gate_var,
        font=("Microsoft YaHei", 12),
    )
    timeline_hard_gate_check.grid(row=7, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    stop_batch_check = ctk.CTkCheckBox(
        quality_warp_frame,
        text="🟢 [S3批量] 硬阻断失败时停止整批任务",
        variable=self.stop_batch_on_hard_gate_var,
        font=("Microsoft YaHei", 12),
    )
    stop_batch_check.grid(row=8, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    post_batch_audit_check = ctk.CTkCheckBox(
        quality_warp_frame,
        text="🟢 [S3批量] 批量完成后执行运行时Prompt审计（后台非阻塞）",
        variable=self.post_batch_runtime_audit_enabled_var,
        font=("Microsoft YaHei", 12),
    )
    post_batch_audit_check.grid(row=9, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    ctk.CTkLabel(
        quality_warp_frame,
        text="🟢 [S3批量] 运行时Prompt审计采样数(0=全量):",
        font=("Microsoft YaHei", 12),
    ).grid(row=10, column=0, padx=10, pady=5, sticky="w")

    s2_header_label = ctk.CTkLabel(
        quality_warp_frame,
        text="🟣 [S2目录] 目录生成 / 续传策略",
        font=("Microsoft YaHei", 12, "bold"),
        text_color="#B084F5",
    )
    s2_header_label.grid(row=11, column=0, columnspan=2, padx=10, pady=(8, 4), sticky="w")
    post_batch_audit_sample_entry = ctk.CTkEntry(
        quality_warp_frame,
        textvariable=self.post_batch_runtime_audit_sample_size_var,
        width=80,
        font=("Microsoft YaHei", 12),
    )
    post_batch_audit_sample_entry.grid(row=10, column=1, padx=5, pady=5, sticky="w")

    blueprint_full_auto_mode_check = ctk.CTkCheckBox(
        quality_warp_frame,
        text="🟣 [S2目录] 启用全自动模式（默认推荐）",
        variable=self.blueprint_full_auto_mode_var,
        font=("Microsoft YaHei", 12),
    )
    blueprint_full_auto_mode_check.grid(row=12, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    blueprint_auto_restart_check = ctk.CTkCheckBox(
        quality_warp_frame,
        text="🟣 [S2目录] 检测架构变更时自动从头开始（推荐）",
        variable=self.blueprint_auto_restart_on_arch_change_var,
        font=("Microsoft YaHei", 12),
    )
    blueprint_auto_restart_check.grid(row=13, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    blueprint_resume_auto_repair_check = ctk.CTkCheckBox(
        quality_warp_frame,
        text="🟣 [S2目录] 断点续传时自动修复已有目录问题（推荐）",
        variable=self.blueprint_resume_auto_repair_existing_var,
        font=("Microsoft YaHei", 12),
    )
    blueprint_resume_auto_repair_check.grid(row=14, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    blueprint_force_resume_skip_history_check = ctk.CTkCheckBox(
        quality_warp_frame,
        text="⚠️ 🟣 [S2目录] 高风险强制续传（跳过历史目录校验）",
        variable=self.blueprint_force_resume_skip_history_validation_var,
        font=("Microsoft YaHei", 12),
    )
    blueprint_force_resume_skip_history_check.grid(row=15, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    s3_batch_header_label = ctk.CTkLabel(
        quality_warp_frame,
        text="🟢 [S3章节/批量] 批量续跑与上下文策略",
        font=("Microsoft YaHei", 12, "bold"),
        text_color="#53B36B",
    )
    s3_batch_header_label.grid(row=16, column=0, columnspan=2, padx=10, pady=(8, 4), sticky="w")

    partial_resume_fallback_check = ctk.CTkCheckBox(
        quality_warp_frame,
        text="🟢 [S3批量] 中途重跑缺快照时自动降级回滚（推荐）",
        variable=self.batch_partial_resume_allow_fallback_var,
        font=("Microsoft YaHei", 12),
    )
    partial_resume_fallback_check.grid(row=17, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    ignore_budget_check = ctk.CTkCheckBox(
        quality_warp_frame,
        text="🟢 [S3] 质量优先：架构上下文不做预算裁剪（推荐）",
        variable=self.architecture_context_ignore_budget_var,
        font=("Microsoft YaHei", 12),
    )
    ignore_budget_check.grid(row=18, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    ctk.CTkLabel(
        quality_warp_frame,
        text="🟢 [S3] 架构上下文预算-章节生成(字符):",
        font=("Microsoft YaHei", 12),
    ).grid(row=19, column=0, padx=10, pady=5, sticky="w")
    architecture_budget_chapter_entry = ctk.CTkEntry(
        quality_warp_frame,
        textvariable=self.architecture_context_budget_chapter_prompt_var,
        width=100,
        font=("Microsoft YaHei", 12),
    )
    architecture_budget_chapter_entry.grid(row=19, column=1, padx=5, pady=5, sticky="w")

    ctk.CTkLabel(
        quality_warp_frame,
        text="🟢 [S3] 架构上下文预算-一致性审校(字符):",
        font=("Microsoft YaHei", 12),
    ).grid(row=20, column=0, padx=10, pady=5, sticky="w")
    architecture_budget_consistency_entry = ctk.CTkEntry(
        quality_warp_frame,
        textvariable=self.architecture_context_budget_consistency_var,
        width=100,
        font=("Microsoft YaHei", 12),
    )
    architecture_budget_consistency_entry.grid(row=20, column=1, padx=5, pady=5, sticky="w")

    ctk.CTkLabel(
        quality_warp_frame,
        text="🟢 [S3] 架构上下文预算-质量闭环(字符):",
        font=("Microsoft YaHei", 12),
    ).grid(row=21, column=0, padx=10, pady=5, sticky="w")
    architecture_budget_loop_entry = ctk.CTkEntry(
        quality_warp_frame,
        textvariable=self.architecture_context_budget_quality_loop_var,
        width=100,
        font=("Microsoft YaHei", 12),
    )
    architecture_budget_loop_entry.grid(row=21, column=1, padx=5, pady=5, sticky="w")

    precheck_deep_scan_check = ctk.CTkCheckBox(
        quality_warp_frame,
        text="🟢 [S3批量] 生成前执行深度预检扫描（占位符/结构/重复）",
        variable=self.batch_precheck_deep_scan_var,
        font=("Microsoft YaHei", 12),
    )
    precheck_deep_scan_check.grid(row=22, column=0, columnspan=2, padx=10, pady=5, sticky="w")

    precheck_auto_continue_check = ctk.CTkCheckBox(
        quality_warp_frame,
        text="🟢 [S3批量] 预检告警自动放行（全自动模式推荐）",
        variable=self.batch_precheck_auto_continue_on_warning_var,
        font=("Microsoft YaHei", 12),
    )
    precheck_auto_continue_check.grid(row=23, column=0, columnspan=2, padx=10, pady=5, sticky="w")
    
    # 知识提取
    knowledge_check = ctk.CTkCheckBox(quality_warp_frame, text="🟢 [S3章节] 启用结构化知识提取",
                                       variable=self.enable_knowledge_extraction_var, font=("Microsoft YaHei", 12))
    knowledge_check.grid(row=24, column=0, columnspan=2, padx=10, pady=5, sticky="w")
    
    # 应用配置按钮
    def apply_quality_config(show_success_message: bool = True, show_error_message: bool = True):
        if getattr(self, "_quality_config_applying", False):
            return False
        self._quality_config_applying = True
        try:
            max_iter = int(self.max_iterations_var.get())
            threshold = float(self.quality_threshold_var.get())
            post_batch_audit_sample_size = int(self.post_batch_runtime_audit_sample_size_var.get())
            architecture_context_budget_chapter_prompt = int(self.architecture_context_budget_chapter_prompt_var.get())
            architecture_context_budget_consistency = int(self.architecture_context_budget_consistency_var.get())
            architecture_context_budget_quality_loop = int(self.architecture_context_budget_quality_loop_var.get())
        except ValueError:
            if show_error_message:
                messagebox.showerror("错误", "请输入有效的数值")
            self._quality_config_applying = False
            return False

        try:
            max_iter = max(1, min(50, max_iter))
            threshold = min(10.0, max(1.0, threshold))
            if post_batch_audit_sample_size < 0:
                post_batch_audit_sample_size = 0
            architecture_context_budget_chapter_prompt = max(4000, min(120000, architecture_context_budget_chapter_prompt))
            architecture_context_budget_consistency = max(4000, min(120000, architecture_context_budget_consistency))
            architecture_context_budget_quality_loop = max(4000, min(120000, architecture_context_budget_quality_loop))

            def _set_str_if_changed(var_obj, value) -> None:
                desired = str(value)
                if str(var_obj.get()) != desired:
                    var_obj.set(desired)

            _set_str_if_changed(self.max_iterations_var, max_iter)
            _set_str_if_changed(self.quality_threshold_var, threshold)
            _set_str_if_changed(self.post_batch_runtime_audit_sample_size_var, post_batch_audit_sample_size)
            _set_str_if_changed(self.architecture_context_budget_chapter_prompt_var, architecture_context_budget_chapter_prompt)
            _set_str_if_changed(self.architecture_context_budget_consistency_var, architecture_context_budget_consistency)
            _set_str_if_changed(self.architecture_context_budget_quality_loop_var, architecture_context_budget_quality_loop)

            if hasattr(self, 'optimized_handler') and self.optimized_handler:
                self.optimized_handler.update_quality_config({
                    'enable_iterative_generation': self.enable_iterative_gen_var.get(),
                    'max_iterations': max_iter,
                    'quality_threshold': threshold,
                    'force_critic_logging_each_iteration': self.force_critic_logging_each_iteration_var.get(),
                    'enable_llm_consistency_check': self.enable_llm_consistency_var.get(),
                    'consistency_hard_gate': self.consistency_hard_gate_var.get(),
                    'enable_timeline_check': self.enable_timeline_check_var.get(),
                    'timeline_hard_gate': self.timeline_hard_gate_var.get(),
                    'stop_batch_on_hard_gate': self.stop_batch_on_hard_gate_var.get(),
                    'post_batch_runtime_audit_enabled': self.post_batch_runtime_audit_enabled_var.get(),
                    'post_batch_runtime_audit_sample_size': post_batch_audit_sample_size,
                    'blueprint_full_auto_mode': self.blueprint_full_auto_mode_var.get(),
                    'blueprint_auto_restart_on_arch_change': self.blueprint_auto_restart_on_arch_change_var.get(),
                    'blueprint_resume_auto_repair_existing': self.blueprint_resume_auto_repair_existing_var.get(),
                    'blueprint_force_resume_skip_history_validation': self.blueprint_force_resume_skip_history_validation_var.get(),
                    'batch_partial_resume_allow_fallback': self.batch_partial_resume_allow_fallback_var.get(),
                    'batch_precheck_deep_scan': self.batch_precheck_deep_scan_var.get(),
                    'batch_precheck_auto_continue_on_warning': self.batch_precheck_auto_continue_on_warning_var.get(),
                    'architecture_context_ignore_budget': self.architecture_context_ignore_budget_var.get(),
                    'architecture_context_budget_chapter_prompt': architecture_context_budget_chapter_prompt,
                    'architecture_context_budget_consistency': architecture_context_budget_consistency,
                    'architecture_context_budget_quality_loop': architecture_context_budget_quality_loop,
                    'enable_post_generation_extraction': self.enable_knowledge_extraction_var.get()
                })

            if "other_params" not in self.loaded_config:
                self.loaded_config["other_params"] = {}
            self.loaded_config["other_params"].update({
                'enable_iterative_generation': self.enable_iterative_gen_var.get(),
                'max_iterations': max_iter,
                'quality_threshold': threshold,
                'force_critic_logging_each_iteration': self.force_critic_logging_each_iteration_var.get(),
                'enable_llm_consistency_check': self.enable_llm_consistency_var.get(),
                'consistency_hard_gate': self.consistency_hard_gate_var.get(),
                'enable_timeline_check': self.enable_timeline_check_var.get(),
                'timeline_hard_gate': self.timeline_hard_gate_var.get(),
                'stop_batch_on_hard_gate': self.stop_batch_on_hard_gate_var.get(),
                'post_batch_runtime_audit_enabled': self.post_batch_runtime_audit_enabled_var.get(),
                'post_batch_runtime_audit_sample_size': post_batch_audit_sample_size,
                'blueprint_full_auto_mode': self.blueprint_full_auto_mode_var.get(),
                'blueprint_auto_restart_on_arch_change': self.blueprint_auto_restart_on_arch_change_var.get(),
                'blueprint_resume_auto_repair_existing': self.blueprint_resume_auto_repair_existing_var.get(),
                'blueprint_force_resume_skip_history_validation': self.blueprint_force_resume_skip_history_validation_var.get(),
                'batch_partial_resume_allow_fallback': self.batch_partial_resume_allow_fallback_var.get(),
                'batch_precheck_deep_scan': self.batch_precheck_deep_scan_var.get(),
                'batch_precheck_auto_continue_on_warning': self.batch_precheck_auto_continue_on_warning_var.get(),
                'architecture_context_ignore_budget': self.architecture_context_ignore_budget_var.get(),
                'architecture_context_budget_chapter_prompt': architecture_context_budget_chapter_prompt,
                'architecture_context_budget_consistency': architecture_context_budget_consistency,
                'architecture_context_budget_quality_loop': architecture_context_budget_quality_loop,
                'enable_post_generation_extraction': self.enable_knowledge_extraction_var.get()
            })
            selected_quality_loop_llm_name = (
                self.quality_loop_llm_var.get() if hasattr(self, "quality_loop_llm_var") else ""
            )
            llm_configs = self.loaded_config.get("llm_configs", {})
            if isinstance(llm_configs, dict) and selected_quality_loop_llm_name in llm_configs:
                selected_llm_cfg = llm_configs.get(selected_quality_loop_llm_name, {})
                if isinstance(selected_llm_cfg, dict):
                    selected_policy = normalize_quality_policy(
                        selected_llm_cfg.get("quality_policy"),
                        fallback_threshold=threshold,
                    )
                    selected_policy["default_quality_threshold"] = threshold
                    selected_policy["max_iterations"] = max_iter
                    selected_policy["force_critic_logging_each_iteration"] = (
                        bool(self.force_critic_logging_each_iteration_var.get())
                    )
                    selected_policy["enable_llm_consistency_check"] = bool(self.enable_llm_consistency_var.get())
                    selected_policy["consistency_hard_gate"] = bool(self.consistency_hard_gate_var.get())
                    selected_policy["enable_timeline_check"] = bool(self.enable_timeline_check_var.get())
                    selected_policy["timeline_hard_gate"] = bool(self.timeline_hard_gate_var.get())
                    selected_llm_cfg["quality_policy"] = selected_policy

            save_ok = save_config(self.loaded_config, self.config_file)
            if show_success_message:
                if save_ok:
                    messagebox.showinfo("成功", "质量控制配置已应用并保存到 config.json")
                else:
                    messagebox.showerror("错误", "保存质量控制配置失败，请检查日志")
            return bool(save_ok)
        finally:
            self._quality_config_applying = False

    self.apply_quality_config = apply_quality_config
    
    quality_button_frame = ctk.CTkFrame(quality_warp_frame)
    quality_button_frame.grid(row=25, column=0, columnspan=2, padx=5, pady=10, sticky="w")
    
    apply_btn = ctk.CTkButton(quality_button_frame, text="应用并保存", font=("Microsoft YaHei", 12),
                              command=apply_quality_config)
    apply_btn.pack(side="left", padx=5)
    quality_quick_save_btn.configure(state="normal", command=apply_quality_config)

    def _schedule_quality_auto_save(*_args):
        if getattr(self, "_quality_config_applying", False):
            return
        if hasattr(self, "_quality_config_auto_save_timer"):
            try:
                self.master.after_cancel(self._quality_config_auto_save_timer)
            except Exception:
                pass
        self._quality_config_auto_save_timer = self.master.after(
            900,
            lambda: apply_quality_config(show_success_message=False, show_error_message=False),
        )

    if not getattr(self, "_quality_auto_save_bound", False):
        quality_vars_for_auto_save = [
            self.enable_iterative_gen_var,
            self.max_iterations_var,
            self.quality_threshold_var,
            self.force_critic_logging_each_iteration_var,
            self.enable_llm_consistency_var,
            self.consistency_hard_gate_var,
            self.enable_timeline_check_var,
            self.timeline_hard_gate_var,
            self.stop_batch_on_hard_gate_var,
            self.post_batch_runtime_audit_enabled_var,
            self.post_batch_runtime_audit_sample_size_var,
            self.blueprint_full_auto_mode_var,
            self.blueprint_auto_restart_on_arch_change_var,
            self.blueprint_resume_auto_repair_existing_var,
            self.blueprint_force_resume_skip_history_validation_var,
            self.batch_partial_resume_allow_fallback_var,
            self.batch_precheck_deep_scan_var,
            self.batch_precheck_auto_continue_on_warning_var,
            self.architecture_context_ignore_budget_var,
            self.architecture_context_budget_chapter_prompt_var,
            self.architecture_context_budget_consistency_var,
            self.architecture_context_budget_quality_loop_var,
            self.enable_knowledge_extraction_var,
        ]
        for config_var in quality_vars_for_auto_save:
            try:
                config_var.trace_add("write", _schedule_quality_auto_save)
            except Exception:
                pass
        self._quality_auto_save_bound = True
    
    # 提示标签
    tip_label = ctk.CTkLabel(quality_warp_frame, 
                             text="💡 本页参数支持自动保存（输入稳定约1秒后写入config.json）",
                             font=("Microsoft YaHei", 10), text_color="gray")
    tip_label.grid(row=26, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="w")





class WebDAVClient:
    def __init__(self, base_url, username, password):
        """初始化WebDAV客户端"""
        self.base_url = base_url.rstrip('/') + '/'
        self.auth = HTTPBasicAuth(username, password)
        self.headers = {
            'User-Agent': 'Python WebDAV Client',
            'Accept': '*/*'
        }
        # WebDAV命名空间
        self.ns = {'d': 'DAV:'}

    def _get_url(self, path):
        """获取完整的资源URL"""
        return self.base_url + path.lstrip('/')

    def directory_exists(self, path):
        """
        检查目录是否存在
        :param path: 目录路径
        :return: 布尔值，表示目录是否存在
        """
        url = self._get_url(path)
        headers = self.headers.copy()
        headers['Depth'] = '0'  # 只检查当前资源
        
        try:
            # 发送PROPFIND请求检查资源是否存在
            response = requests.request('PROPFIND', url, headers=headers, auth=self.auth)
            
            # 207 Multi-Status表示成功，说明资源存在
            if response.status_code == 207:
                # 解析XML响应，确认是目录
                root = ET.fromstring(response.content)
                # 查找资源类型属性
                res_type = root.find('.//d:resourcetype', namespaces=self.ns)
                # 如果包含collection元素，则是目录
                if res_type is not None and res_type.find('d:collection', namespaces=self.ns) is not None:
                    return True
            return False
        except requests.exceptions.RequestException as e:
            print(f"检查目录存在性时出错: {e}")
            return False

    def create_directory(self, path):
        """
        创建远程目录
        :param path: 要创建的目录路径
        :return: 是否创建成功
        """
        url = self._get_url(path)
        
        try:
            response = requests.request('MKCOL', url, auth=self.auth, headers=self.headers)
            response.raise_for_status()
            
            print(f"目录创建成功: {path}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"目录创建失败: {e}")
            return False

    def ensure_directory_exists(self, path):
        """
        确保目录存在，如果不存在则创建
        :param path: 目录路径
        :return: 布尔值，表示最终目录是否存在
        """
        # 移除末尾的斜杠（如果有）
        path = path.rstrip('/')
        
        # 如果目录已经存在，直接返回True
        if self.directory_exists(path):
            print(f"目录已存在: {path}")
            return True
            
        # 递归创建父目录
        parent_dir = os.path.dirname(path)
        if parent_dir and not self.directory_exists(parent_dir):
            # 如果父目录不存在，则先创建父目录
            if not self.ensure_directory_exists(parent_dir):
                print(f"创建父目录失败: {parent_dir}")
                return False
                
        # 创建当前目录
        return self.create_directory(path)
    def upload_file(self, local_path, remote_path):
        """
        上传文件到WebDAV服务器
        :param local_path: 本地文件路径
        :param remote_path: 远程文件路径
        :return: 是否上传成功
        """
        if not os.path.isfile(local_path):
            print(f"本地文件不存在: {local_path}")
            return False

        url = self._get_url(remote_path)
        
        try:
            with open(local_path, 'rb') as f:
                response = requests.put(url, data=f, auth=self.auth, headers=self.headers)
                response.raise_for_status()
            
            print(f"文件上传成功: {local_path} -> {remote_path}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"文件上传失败: {e}")
            return False
    def download_file(self, remote_path, local_path):
        """
        从WebDAV服务器下载文件
        :param remote_path: 远程文件路径
        :param local_path: 本地保存路径
        :return: 是否下载成功
        """
        url = self._get_url(remote_path)
        local_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), local_path)
        self.backup(local_path)
        try:
            response = requests.get(url, auth=self.auth, headers=self.headers, stream=True)
            response.raise_for_status()
            
            # 创建本地目录（如果需要）
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"文件下载成功: {remote_path} -> {local_path}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"文件下载失败: {e}")
            return False
    def backup(self, local_path):
        name_parts = os.path.basename(local_path).rsplit('.', 1)  # 只分割最后一个点
        base_name = name_parts[0]
        extension = name_parts[1]
        timestamp = time.strftime("%Y%m%d%H%M%S")
        if not os.path.exists(os.path.join(os.path.dirname(local_path), "backup")):
            os.makedirs(os.path.join(os.path.dirname(local_path), "backup"))
        backup_file_name = f"{base_name}_{timestamp}_bak.{extension}"
        shutil.copy2(os.path.basename(local_path), os.path.join(os.path.dirname(local_path), "backup", backup_file_name))
