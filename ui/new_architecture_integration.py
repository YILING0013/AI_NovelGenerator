# ui/new_architecture_integration.py
# -*- coding: utf-8 -*-
"""
新架构 GUI 集成模块
集成 P0 和 P1 优化到现有 GUI
"""

import os
import customtkinter as ctk
from tkinter import messagebox
from novel_generator import schema_validator, error_handler
from novel_generator.pipeline import PipelineFactory


class NewArchitectureIntegration:
    """新架构集成管理器"""

    def __init__(self, gui_instance):
        """
        初始化新架构集成

        Args:
            gui_instance: NovelGeneratorGUI 实例
        """
        self.gui = gui_instance

    def build_advanced_options_frame(self, parent_frame):
        """
        在 GUI 中构建高级选项面板

        Args:
            parent_frame: 父级 Frame

        Returns:
            高级选项 Frame
        """
        # 创建高级选项 Frame
        advanced_frame = ctk.CTkFrame(parent_frame, fg_color="transparent")
        advanced_frame.pack(fill="x", padx=5, pady=(10, 5))

        # 标题
        title_label = ctk.CTkLabel(
            advanced_frame,
            text="🚀 高级架构选项 (P0+P1 优化)",
            font=("Microsoft YaHei", 11, "bold"),
            anchor="w"
        )
        title_label.pack(fill="x", padx=5, pady=(0, 5))

        # Schema 验证选项
        self.enable_schema_validation_var = ctk.BooleanVar(value=True)

        schema_validation_frame = ctk.CTkFrame(advanced_frame)
        schema_validation_frame.pack(fill="x", padx=5, pady=2)

        schema_validation_label = ctk.CTkLabel(
            schema_validation_frame,
            text="启用 Schema 验证 (Pydantic 类型安全)",
            font=("Microsoft YaHei", 10)
        )
        schema_validation_label.pack(side="left", padx=5)

        schema_validation_switch = ctk.CTkSwitch(
            schema_validation_frame,
            variable=self.enable_schema_validation_var,
            onvalue=True,
            offvalue=False,
            width=40
        )
        schema_validation_switch.pack(side="right", padx=5)

        # 智能重试选项
        self.enable_intelligent_retry_var = ctk.BooleanVar(value=True)

        intelligent_retry_frame = ctk.CTkFrame(advanced_frame)
        intelligent_retry_frame.pack(fill="x", padx=5, pady=2)

        intelligent_retry_label = ctk.CTkLabel(
            intelligent_retry_frame,
            text="启用智能重试 (指数退避 + 抖动)",
            font=("Microsoft YaHei", 10)
        )
        intelligent_retry_label.pack(side="left", padx=5)

        intelligent_retry_switch = ctk.CTkSwitch(
            intelligent_retry_frame,
            variable=self.enable_intelligent_retry_var,
            onvalue=True,
            offvalue=False,
            width=40
        )
        intelligent_retry_switch.pack(side="right", padx=5)

        # 管道架构选项
        self.use_pipeline_architecture_var = ctk.BooleanVar(value=False)

        pipeline_frame = ctk.CTkFrame(advanced_frame)
        pipeline_frame.pack(fill="x", padx=5, pady=2)

        pipeline_label = ctk.CTkLabel(
            pipeline_frame,
            text="使用新管道架构 (实验性)",
            font=("Microsoft YaHei", 10)
        )
        pipeline_label.pack(side="left", padx=5)

        pipeline_switch = ctk.CTkSwitch(
            pipeline_frame,
            variable=self.use_pipeline_architecture_var,
            onvalue=True,
            offvalue=False,
            width=40,
            command=self.on_pipeline_switch_changed
        )
        pipeline_switch.pack(side="right", padx=5)

        return advanced_frame

    def on_pipeline_switch_changed(self):
        """管道架构开关变化处理"""
        if self.use_pipeline_architecture_var.get():
            messagebox.showinfo(
                "新管道架构",
                "已启用新管道架构（实验性）\n\n"
                "特性:\n"
                "• 模块化设计，易于扩展\n"
                "• 清晰的数据流\n"
                "• 统一的错误处理\n"
                "• 完整的测试覆盖\n\n"
                "注意：新架构仍在测试中，可能出现不稳定情况"
            )

    def validate_blueprint_with_schema(self, filepath):
        """
        使用 Schema 验证章节蓝图

        Args:
            filepath: 小说文件路径

        Returns:
            验证结果字典
        """
        if not self.enable_schema_validation_var.get():
            return {"is_valid": True, "skipped": True, "reason": "Schema 验证未启用"}

        try:
            from utils import read_file

            blueprint_file = f"{filepath}/Novel_directory.txt"
            if not os.path.exists(blueprint_file):
                return {
                    "is_valid": False,
                    "errors": ["蓝图文件不存在"],
                    "skipped": False
                }

            blueprint_content = read_file(blueprint_file).strip()
            if not blueprint_content:
                return {
                    "is_valid": False,
                    "errors": ["蓝图文件为空"],
                    "skipped": False
                }

            # 创建 Schema 验证器
            validator = schema_validator.SchemaValidator()

            # 提取章节范围
            import re
            chapter_numbers = re.findall(r'第(\d+)章', blueprint_content)
            if chapter_numbers:
                start_chapter = int(min(chapter_numbers))
                end_chapter = int(max(chapter_numbers))
            else:
                start_chapter = 1
                end_chapter = 100  # 默认值

            # 执行验证
            validation_result = validator.validate_blueprint_format(
                blueprint_content, start_chapter, end_chapter
            )

            return {
                "is_valid": validation_result["is_valid"],
                "errors": validation_result.get("errors", []),
                "warnings": validation_result.get("warnings", []),
                "suggestions": validation_result.get("suggestions", []),
                "skipped": False
            }

        except Exception as e:
            return {
                "is_valid": False,
                "errors": [f"Schema 验证异常: {str(e)}"],
                "skipped": False
            }

    def show_schema_validation_results(self, validation_result):
        """
        在 GUI 中显示 Schema 验证结果

        Args:
            validation_result: 验证结果字典
        """
        if validation_result.get("skipped"):
            self.gui.safe_log("ℹ️ Schema 验证：已跳过（未启用）")
            return

        if validation_result["is_valid"]:
            self.gui.safe_log("✅ Schema 验证：通过")

            # 显示警告
            if validation_result.get("warnings"):
                self.gui.safe_log("⚠️ Schema 验证警告：")
                for warning in validation_result["warnings"]:
                    self.gui.safe_log(f"  - {warning}")

            # 显示建议
            if validation_result.get("suggestions"):
                self.gui.safe_log("💡 Schema 验证建议：")
                for suggestion in validation_result["suggestions"]:
                    self.gui.safe_log(f"  - {suggestion}")
        else:
            self.gui.safe_log("❌ Schema 验证：失败")
            self.gui.safe_log("错误详情：")
            for error in validation_result["errors"]:
                self.gui.safe_log(f"  - {error}")

            # 询问是否继续
            if messagebox.askyesno(
                "Schema 验证失败",
                "Schema 验证发现问题，是否继续？\n\n"
                "建议先修复问题再继续生成。\n"
                "强行继续可能导致后续问题。"
            ):
                self.gui.safe_log("⚠️ 用户选择忽略 Schema 验证错误继续执行")
            else:
                raise Exception("用户取消：Schema 验证失败")

    def get_error_statistics(self):
        """
        获取错误统计信息

        Returns:
            错误统计字典
        """
        handler = error_handler.get_global_error_handler()
        raw_stats = handler.get_error_statistics()
        return {
            "total_errors": raw_stats.get("total_errors", 0),
            "unique_errors": raw_stats.get("unique_error_types", 0),
            "error_distribution": raw_stats.get("error_counts", {}),
            "recent_errors_count": raw_stats.get("recent_errors_count", 0),
        }

    def reset_error_statistics(self):
        """重置错误统计"""
        handler = error_handler.get_global_error_handler()
        handler.reset_statistics()
        self.gui.safe_log("✅ 错误统计已重置")

    def show_error_statistics(self):
        """在 GUI 中显示错误统计"""
        stats = self.get_error_statistics()

        self.gui.safe_log("=" * 50)
        self.gui.safe_log("📊 错误统计信息")
        self.gui.safe_log("=" * 50)
        self.gui.safe_log(f"总错误数: {stats['total_errors']}")
        self.gui.safe_log(f"唯一错误类型: {stats['unique_errors']}")
        self.gui.safe_log(f"错误分布:")

        if stats['error_distribution']:
            for error_type, count in stats['error_distribution'].items():
                self.gui.safe_log(f"  - {error_type}: {count}次")
        else:
            self.gui.safe_log("  (无错误记录)")

        self.gui.safe_log("=" * 50)

    def use_new_pipeline_for_generation(self, config):
        """
        使用新管道架构生成内容

        Args:
            config: 生成配置字典

        Returns:
            生成结果
        """
        if not self.use_pipeline_architecture_var.get():
            return {"success": False, "reason": "管道架构未启用"}

        try:
            pipeline_config = dict(config or {})
            project_path = (
                pipeline_config.get("project_path")
                or pipeline_config.get("filepath")
                or ""
            )
            pipeline_config["project_path"] = project_path
            chapter_number = int(pipeline_config.get("chapter_number", 1) or 1)

            # 创建管道实例
            pipeline = PipelineFactory.create_default_pipeline(config=pipeline_config)

            # 执行管道
            self.gui.safe_log("🚀 使用新管道架构生成...")
            result = pipeline.execute_single_chapter(
                chapter_number=chapter_number,
                config=pipeline_config,
            )

            if result.success:
                self.gui.safe_log("✅ 新管道架构生成成功")
                return {
                    "success": True,
                    "data": result.data,
                    "stage": result.stage.value if hasattr(result.stage, "value") else result.stage,
                }
            else:
                self.gui.safe_log(f"❌ 新管道架构生成失败: {result.error}")
                return {
                    "success": False,
                    "reason": result.error
                }

        except Exception as e:
            self.gui.safe_log(f"❌ 新管道架构异常: {str(e)}")
            return {
                "success": False,
                "reason": str(e)
            }


# ======== 导出函数 ========

def add_new_architecture_options(gui_instance):
    """
    将新架构选项添加到 GUI

    Args:
        gui_instance: NovelGeneratorGUI 实例
    """
    # 创建集成管理器
    integration = NewArchitectureIntegration(gui_instance)
    gui_instance.new_arch_integration = integration

    # 在右侧参数区域添加高级选项（尽力挂载，避免静默失效）
    parent_frame = (
        getattr(gui_instance, "right_frame", None)
        or getattr(gui_instance, "params_frame", None)
        or getattr(gui_instance, "main_frame", None)
    )

    if parent_frame is None:
        if hasattr(gui_instance, "safe_log"):
            gui_instance.safe_log("⚠️ 未找到可挂载的新架构选项容器，已跳过。")
        return None

    options_frame = integration.build_advanced_options_frame(parent_frame)
    gui_instance.new_arch_options_frame = options_frame
    return options_frame


def validate_after_blueprint_generation(gui_instance):
    """
    在蓝图生成后执行 Schema 验证

    Args:
        gui_instance: NovelGeneratorGUI 实例
    """
    if not hasattr(gui_instance, "new_arch_integration"):
        return

    filepath = gui_instance.filepath_var.get().strip()
    if not filepath:
        return

    # 执行 Schema 验证
    validation_result = gui_instance.new_arch_integration.validate_blueprint_with_schema(filepath)

    # 显示结果
    gui_instance.new_arch_integration.show_schema_validation_results(validation_result)


def show_error_stats_handler(gui_instance):
    """
    显示错误统计的处理函数

    Args:
        gui_instance: NovelGeneratorGUI 实例
    """
    if hasattr(gui_instance, "new_arch_integration"):
        gui_instance.new_arch_integration.show_error_statistics()
    else:
        gui_instance.safe_log("⚠️ 新架构集成未初始化")
