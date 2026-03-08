# gui_integration_patch.py
# -*- coding: utf-8 -*-
"""
GUI 集成补丁
将新架构功能集成到现有 GUI
"""

import os
import re

# ======== 集成 1: Schema 验证到蓝图生成后 ========

def add_schema_validation_to_blueprint_generation():
    """
    在 ui/generation_handlers.py 中添加 Schema 验证

    在 generate_chapter_blueprint_ui 函数的质量检查部分之后添加以下代码
    """

    patch_code = '''
            # 🆕 Schema 验证（新架构集成）
            try:
                self.safe_log("")
                self.safe_log("🔬 正在进行 Schema 验证（Pydantic 类型安全）...")

                from novel_generator import schema_validator
                from utils import read_file

                blueprint_file = f"{filepath}/Novel_directory.txt"
                if os.path.exists(blueprint_file):
                    blueprint_content = read_file(blueprint_file).strip()

                    # 提取章节范围
                    chapter_numbers = re.findall(r'第(\\d+)章', blueprint_content)
                    if chapter_numbers:
                        start_chapter = int(min(chapter_numbers))
                        end_chapter = int(max(chapter_numbers))
                    else:
                        start_chapter = 1
                        end_chapter = 100

                    # 创建 Schema 验证器
                    validator = schema_validator.BlueprintValidator()

                    # 执行验证
                    schema_validation = validator.validate_blueprint_format(
                        blueprint_content, start_chapter, end_chapter
                    )

                    # 显示结果
                    if schema_validation["is_valid"]:
                        self.safe_log("  ✅ Schema 验证通过")

                        # 显示警告
                        if schema_validation.get("warnings"):
                            self.safe_log("  ⚠️ Schema 警告:")
                            for warning in schema_validation["warnings"]:
                                self.safe_log(f"    - {warning}")

                        # 显示建议
                        if schema_validation.get("suggestions"):
                            self.safe_log("  💡 Schema 建议:")
                            for suggestion in schema_validation["suggestions"]:
                                self.safe_log(f"    - {suggestion}")
                    else:
                        self.safe_log("  ❌ Schema 验证失败:")
                        for error in schema_validation["errors"]:
                            self.safe_log(f"    - {error}")

                        # 询问是否继续
                        if messagebox.askyesno(
                            "Schema 验证失败",
                            "Schema 验证发现问题，是否继续？\\n\\n"
                            "建议先修复问题再继续生成。\\n"
                            "强行继续可能导致后续问题。"
                        ):
                            self.safe_log("  ⚠️ 用户选择忽略 Schema 验证错误")
                        else:
                            raise Exception("用户取消：Schema 验证失败")
                else:
                    self.safe_log("  ⚠️ Schema 验证跳过：蓝图文件不存在")

            except ImportError as ie:
                self.safe_log(f"  ⚠️ Schema 验证模块未找到(跳过): {ie}")
            except Exception as se:
                self.safe_log(f"  ⚠️ Schema 验证异常: {se}")

    '''

    return patch_code


# ======== 集成 2: 智能重试状态显示 ========

def add_retry_status_display():
    """
    在 GUI 中显示智能重试状态
    """

    patch_code = '''
    # 在 generate_chapter_draft_ui 函数中添加重试状态监控
    def generate_chapter_draft_ui_with_retry_status(self):
        """生成章节草稿（带重试状态显示）"""

        # ... 现有代码 ...

        self.safe_log("🔄 智能重试已启用 (指数退避 + 50%抖动)")
        self.safe_log("  - 最大重试次数: 3")
        self.safe_log("  - 退避策略: 指数退避")

        # ... 继续现有代码 ...

    '''

    return patch_code


# ======== 集成 3: 错误统计显示 ========

def add_error_statistics_button():
    """
    在 GUI 中添加错误统计按钮
    """

    patch_code = '''
    # 在 build_main_tab 的按钮区域添加错误统计按钮

    self.btn_error_stats = ctk.CTkButton(
        self.step_buttons_frame,
        text="📊 错误统计",
        command=self.show_error_statistics_ui,
        font=("Microsoft YaHei", 12)
    )
    self.btn_error_stats.grid(row=1, column=0, padx=5, pady=2, sticky="ew")

    # 添加错误统计处理函数
    def show_error_statistics_ui(self):
        """显示错误统计信息"""
        try:
            from novel_generator import error_handler

            handler = error_handler.ErrorHandler()
            stats = handler.get_statistics()

            self.safe_log("")
            self.safe_log("=" * 50)
            self.safe_log("📊 错误统计信息")
            self.safe_log("=" * 50)
            self.safe_log(f"总错误数: {stats['total_errors']}")
            self.safe_log(f"唯一错误类型: {stats['unique_errors']}")
            self.safe_log(f"错误分布:")

            if stats['error_distribution']:
                for error_type, count in stats['error_distribution'].items():
                    self.safe_log(f"  - {error_type}: {count}次")
            else:
                self.safe_log("  (无错误记录)")

            self.safe_log("=" * 50)

            # 询问是否重置
            if stats['total_errors'] > 0:
                if messagebox.askyesno(
                    "重置错误统计",
                    f"当前共有 {stats['total_errors']} 条错误记录。\\n\\n是否重置统计？"
                ):
                    handler.reset_statistics()
                    self.safe_log("✅ 错误统计已重置")
                else:
                    self.safe_log("ℹ️ 错误统计保持不变")
            else:
                self.safe_log("ℹ️ 无错误记录需要重置")

        except ImportError as ie:
            self.safe_log(f"⚠️ 错误处理模块未找到: {ie}")
        except Exception as e:
            self.safe_log(f"⚠️ 显示错误统计时出错: {e}")

    '''

    return patch_code


# ======== 集成 4: 新架构选项开关 ========

def add_new_architecture_switch():
    """
    在 GUI 中添加新架构选项开关
    """

    patch_code = '''
    # 在 build_right_layout 的配置区域添加新架构选项

    # 创建高级选项 Frame
    self.advanced_options_frame = ctk.CTkFrame(self.right_frame)
    self.advanced_options_frame.grid(row=4, column=0, sticky="ew", padx=5, pady=5)

    self.advanced_options_label = ctk.CTkLabel(
        self.advanced_options_frame,
        text="🚀 高级架构选项",
        font=("Microsoft YaHei", 11, "bold")
    )
    self.advanced_options_label.pack(fill="x", padx=5, pady=(5, 2))

    # Schema 验证开关
    self.enable_schema_validation_var = ctk.BooleanVar(value=True)

    self.schema_validation_switch_frame = ctk.CTkFrame(self.advanced_options_frame)
    self.schema_validation_switch_frame.pack(fill="x", padx=5, pady=2)

    ctk.CTkLabel(
        self.schema_validation_switch_frame,
        text="启用 Schema 验证",
        font=("Microsoft YaHei", 10)
    ).pack(side="left", padx=5)

    ctk.CTkSwitch(
        self.schema_validation_switch_frame,
        variable=self.enable_schema_validation_var,
        onvalue=True,
        offvalue=False,
        width=40
    ).pack(side="right", padx=5)

    # 智能重试开关
    self.enable_intelligent_retry_var = ctk.BooleanVar(value=True)

    self.intelligent_retry_switch_frame = ctk.CTkFrame(self.advanced_options_frame)
    self.intelligent_retry_switch_frame.pack(fill="x", padx=5, pady=2)

    ctk.CTkLabel(
        self.intelligent_retry_switch_frame,
        text="启用智能重试",
        font=("Microsoft YaHei", 10)
    ).pack(side="left", padx=5)

    ctk.CTkSwitch(
        self.intelligent_retry_switch_frame,
        variable=self.enable_intelligent_retry_var,
        onvalue=True,
        offvalue=False,
        width=40
    ).pack(side="right", padx=5)

    '''

    return patch_code


# ======== 应用补丁说明 ========

INSTRUCTIONS = """
GUI 集成补丁使用说明
====================

本文件包含了将新架构集成到现有 GUI 的补丁代码。

应用步骤：
1. 打开 ui/generation_handlers.py
2. 在 generate_chapter_blueprint_ui 函数中找到质量检查结束的位置（约在第 329 行）
3. 在质量检查 except 块之后添加 "集成 1" 的代码

4. 打开 ui/main_tab.py
5. 在 build_main_tab 的按钮区域添加 "集成 3" 的按钮代码

6. 在 build_right_layout 函数中添加 "集成 4" 的高级选项 Frame

注意事项：
- 确保所有导入语句正确
- 测试每个集成点是否正常工作
- 智能重试已通过装饰器自动集成，无需额外 GUI 修改
- Schema 验证和错误统计需要手动添加 GUI 显示

测试验证：
1. 启动 GUI
2. 生成章节蓝图，检查 Schema 验证是否执行
3. 点击"错误统计"按钮，检查统计信息是否显示
4. 验证高级选项开关是否正常工作
"""

if __name__ == "__main__":
    print(INSTRUCTIONS)
