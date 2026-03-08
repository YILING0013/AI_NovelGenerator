# -*- coding: utf-8 -*-
"""
Schema验证器 - 基于Pydantic模型进行数据验证

该模块提供统一的验证接口，用于：
1. 验证章节目录数据
2. 验证章节蓝图数据
3. 生成详细的验证报告
"""
from typing import List, Dict, Any, Optional, Set
import logging
from .schemas import (
    ChapterBlueprint,
    ChapterDirectoryEntry,
    ValidationReport,
    SuspenseLevel,
    ConflictType,
    ProgrammerThinkingMode,
    RomanceType
)

logger = logging.getLogger(__name__)


class SchemaValidator:
    """Schema验证器"""

    # 标准的7节格式定义
    REQUIRED_SECTIONS = [
        "基础元信息",
        "张力与冲突",
        "匠心思维应用",
        "伏笔与信息差",
        "暧昧与修罗场",
        "剧情精要",
        "衔接设计"
    ]

    # 剧情精要必需的子节点
    PLOT_ESSENTIAL_REQUIRED = [
        "开场",
        "发展",
        "高潮",
        "收尾"
    ]

    # 张力与冲突必需的子节点
    TENSION_REQUIRED = [
        "冲突类型",
        "核心冲突点",
        "紧张感曲线"
    ]

    # 默认不内置任何固定角色，避免跨小说污染
    CANONICAL_CHARACTERS: Set[str] = set()
    TYPO_CHARACTERS: Dict[str, str] = {}

    def __init__(
        self,
        strict_mode: bool = True,
        canonical_characters: Optional[Set[str]] = None,
        typo_characters: Optional[Dict[str, str]] = None
    ):
        """
        初始化验证器

        Args:
            strict_mode: 严格模式，True表示拒绝任何不符合规范的数据
        """
        self.strict_mode = strict_mode
        self.canonical_characters = set(canonical_characters or self.CANONICAL_CHARACTERS)
        self.typo_characters = dict(typo_characters or self.TYPO_CHARACTERS)

    def validate_chapter_directory_entry(
        self,
        data: Dict[str, Any],
        chapter_number: Optional[int] = None
    ) -> ValidationReport:
        """
        验证章节目录条目

        Args:
            data: 章节目录数据字典
            chapter_number: 期望的章节号（可选）

        Returns:
            ValidationReport: 验证报告
        """
        report = ValidationReport(is_valid=True)

        # 1. 检查必需字段
        required_fields = [
            'chapter_number',
            'chapter_title',
            'chapter_role',
            'chapter_purpose',
            'suspense_level',
            'chapter_summary'
        ]

        for field in required_fields:
            if field not in data or not data[field]:
                report.add_error(f"缺少必需字段: {field}")

        # 如果缺少必需字段，直接返回
        if not report.is_valid:
            return report

        # 2. 验证章节号
        if chapter_number is not None:
            if data['chapter_number'] != chapter_number:
                report.add_warning(
                    f"章节号不匹配: 期望 {chapter_number}, 实际 {data['chapter_number']}"
                )

        # 3. 验证悬念等级
        try:
            if isinstance(data['suspense_level'], str):
                SuspenseLevel(data['suspense_level'])
        except ValueError:
            report.add_error(
                f"无效的悬念等级: {data['suspense_level']}. "
                f"可选值: {[e.value for e in SuspenseLevel]}"
            )

        # 4. 验证角色名
        characters = data.get('characters_involved', [])
        if characters:
            invalid_characters = []
            for char in characters:
                if self.canonical_characters and char not in self.canonical_characters and char not in self.typo_characters:
                    invalid_characters.append(char)

            if invalid_characters:
                report.add_warning(
                    f"检测到未定义的角色: {invalid_characters}. "
                    f"建议检查角色名是否正确。"
                )

        # 5. 尝试使用Pydantic验证
        try:
            ChapterDirectoryEntry(**data)
        except Exception as e:
            report.add_error(f"Pydantic验证失败: {str(e)}")

        # 6. 添加建议
        if not data.get('target_word_count'):
            report.add_suggestion("建议添加 target_word_count（字数目标）")

        if 'romance_female_lead' not in data or not data.get('romance_female_lead'):
            report.add_suggestion("建议添加 romance_female_lead（涉及女主）字段")

        return report

    def validate_chapter_blueprint(self, blueprint_text: str) -> ValidationReport:
        """
        验证章节蓝图格式

        Args:
            blueprint_text: 章节蓝图文本

        Returns:
            ValidationReport: 验证报告
        """
        report = ValidationReport(is_valid=True)

        # 1. 检查章节标题格式
        if not self._check_chapter_header(blueprint_text):
            report.add_error("章节标题格式不正确，应为: 第X章 - 标题")

        import re

        # 2. 检查必需的7节（支持 `## 1. 节名` 和 `1. 节名`）
        required_section_specs = [
            (1, "基础元信息"),
            (2, "张力与冲突"),
            (3, "匠心思维应用"),
            (4, "伏笔与信息差"),
            (5, "暧昧与修罗场"),
            (6, "剧情精要"),
            (7, "衔接设计"),
        ]
        missing_sections = []
        for sec_num, sec_name in required_section_specs:
            pattern = re.compile(
                rf'(?m)^\s*(?:##\s*)?{sec_num}\.\s*{re.escape(sec_name)}\s*$'
            )
            if not pattern.search(blueprint_text):
                missing_sections.append(sec_name)

        if missing_sections:
            report.add_error(f"缺少必需的章节: {missing_sections}")
            report.add_suggestion(f"必须包含以下所有章节: {self.REQUIRED_SECTIONS}")

        # 3. 检查剧情精要的4个必需子节点
        if "剧情精要" in blueprint_text:
            missing_plot_nodes = []
            for node in self.PLOT_ESSENTIAL_REQUIRED:
                if node not in blueprint_text:
                    missing_plot_nodes.append(node)

            if missing_plot_nodes:
                report.add_warning(
                    f"剧情精要缺少子节点: {missing_plot_nodes}"
                )

        # 4. 检查张力与冲突的必需子节点
        if "张力与冲突" in blueprint_text:
            missing_tension_nodes = []
            for node in self.TENSION_REQUIRED:
                if node not in blueprint_text:
                    missing_tension_nodes.append(node)

            if missing_tension_nodes:
                report.add_warning(
                    f"张力与冲突缺少子节点: {missing_tension_nodes}"
                )

        # 5. 检查暧昧与修罗场
        if "暧昧与修罗场" not in blueprint_text:
            report.add_error("缺少章节: 暧昧与修罗场")
            report.add_suggestion(
                "即使不涉及女性角色，也必须保留此节并填写'不涉及女性角色互动'"
            )
        elif "不涉及女性角色互动" not in blueprint_text:
            # 如果有暧昧与修罗场但没说明不涉及，检查是否有详细描述
            if len(blueprint_text.split("暧昧与修罗场")[1].split("##")[0] if "##" in blueprint_text else blueprint_text) < 50:
                report.add_warning(
                    "暧昧与修罗场内容过少，请详细描述或明确说明'不涉及女性角色互动'"
                )

        # 6. 检查重复的章节标题
        lines = blueprint_text.split('\n')
        section_headers = []
        section_header_pattern = re.compile(r'^\s*(?:##\s*)?([1-7])\.\s*([^\n]+?)\s*$')
        for line in lines:
            match = section_header_pattern.match(line.strip())
            if match:
                section_headers.append(f"{match.group(1)}.{match.group(2).strip()}")

        # 检查是否有重复节标题
        from collections import Counter
        section_counts = Counter(section_headers)
        duplicates = [section for section, count in section_counts.items() if count > 1]

        if duplicates:
            report.add_error(f"检测到重复的章节: {duplicates}")

        return report

    def _check_chapter_header(self, text: str) -> bool:
        """
        检查章节标题格式

        Args:
            text: 文本内容

        Returns:
            bool: 是否符合格式
        """
        import re
        # 支持的格式:
        # 1. ### **第X章 - 标题**
        # 2. 第X章 - 标题
        # 3. 第X章
        pattern = re.compile(
            r'(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*\d+\s*章(?:\s*[-–—:：]\s*[^\n*]+)?\s*(?:\*\*)?\s*$'
        )
        return bool(pattern.search(text))

    def validate_character_names(self, text: str) -> ValidationReport:
        """
        验证文本中的角色名

        Args:
            text: 要验证的文本

        Returns:
            ValidationReport: 验证报告
        """
        report = ValidationReport(is_valid=True)
        if not self.canonical_characters and not self.typo_characters:
            return report

        # 查找所有可能是角色名的词（简单的启发式方法）
        # 实际应用中可能需要更复杂的NLP方法
        import re

        # 查找中文人名模式（2-3个汉字）
        name_pattern = r'[\u4e00-\u9fff]{2,3}'

        potential_names = set(re.findall(name_pattern, text))

        # 检查未定义的角色
        invalid_names = []
        for name in potential_names:
            if name in self.canonical_characters or name in self.typo_characters:
                continue
            # 添加到未定义列表（简单的启发式）
            if len(name) == 2 or len(name) == 3:
                invalid_names.append(name)

        # 只报告一些可疑的未定义角色
        if invalid_names and len(invalid_names) > 10:  # 限制报告数量
            report.add_warning(
                f"检测到大量未定义的潜在角色名: {invalid_names[:10]}... "
                "可能需要检查角色定义或更新白名单"
            )

        return report

    def validate_complete(
        self,
        chapter_number: int,
        directory_data: Dict[str, Any],
        blueprint_text: str
    ) -> ValidationReport:
        """
        完整验证：章节目录 + 章节蓝图

        Args:
            chapter_number: 章节号
            directory_data: 章节目录数据
            blueprint_text: 章节蓝图文本

        Returns:
            ValidationReport: 综合验证报告
        """
        # 合并两个验证报告
        report = ValidationReport(is_valid=True)

        # 1. 验证章节目录
        dir_report = self.validate_chapter_directory_entry(
            directory_data,
            chapter_number
        )
        report.errors.extend(dir_report.errors)
        report.warnings.extend(dir_report.warnings)
        report.suggestions.extend(dir_report.suggestions)
        if not dir_report.is_valid:
            report.is_valid = False

        # 2. 验证章节蓝图
        blueprint_report = self.validate_chapter_blueprint(blueprint_text)
        report.errors.extend(blueprint_report.errors)
        report.warnings.extend(blueprint_report.warnings)
        report.suggestions.extend(blueprint_report.suggestions)
        if not blueprint_report.is_valid:
            report.is_valid = False

        # 3. 检查章节号一致性
        if directory_data.get('chapter_number') != chapter_number:
            report.add_error(
                f"章节号不一致: 目录中为 {directory_data.get('chapter_number')}, "
                f"期望 {chapter_number}"
            )

        return report

    @staticmethod
    def print_report(report: ValidationReport, verbose: bool = True):
        """
        打印验证报告

        Args:
            report: 验证报告
            verbose: 是否显示详细信息
        """
        if report.is_valid:
            print("✅ 验证通过")
        else:
            print("❌ 验证失败")

        if report.errors:
            print("\n❌ 错误:")
            for error in report.errors:
                print(f"  - {error}")

        if report.warnings:
            print("\n⚠️  警告:")
            for warning in report.warnings:
                print(f"  - {warning}")

        if report.suggestions and verbose:
            print("\n💡 建议:")
            for suggestion in report.suggestions:
                print(f"  - {suggestion}")

        print()  # 空行

    def validate_blueprint_format(
        self,
        blueprint_text: str,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        兼容旧调用方的蓝图验证接口。
        """
        result = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "suggestions": [],
            "validated_chapters": []
        }

        if not blueprint_text or not blueprint_text.strip():
            result["is_valid"] = False
            result["errors"].append("蓝图内容为空")
            return result

        import re

        # 兼容两种标题：第X章 - 标题 / ### **第X章 - 标题**
        header_pattern = re.compile(
            r'(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*[^\n*]+)?\s*(?:\*\*)?\s*$'
        )
        headers = list(header_pattern.finditer(blueprint_text))

        # 没检测到章节头时按整段单章处理
        if not headers:
            report = self.validate_chapter_blueprint(blueprint_text)
            result["is_valid"] = report.is_valid
            result["errors"].extend(report.errors)
            result["warnings"].extend(report.warnings)
            result["suggestions"].extend(report.suggestions)
            return result

        chapters = []
        for idx, match in enumerate(headers):
            chapter_num = int(match.group(1))
            start = match.start()
            end = headers[idx + 1].start() if idx + 1 < len(headers) else len(blueprint_text)
            chapter_text = blueprint_text[start:end].strip()
            chapters.append((chapter_num, chapter_text))

        numbers = [n for n, _ in chapters]
        result["validated_chapters"] = sorted(set(numbers))

        if start_chapter is not None and end_chapter is not None:
            expected = set(range(start_chapter, end_chapter + 1))
            actual = set(numbers)
            missing = sorted(expected - actual)
            extras = sorted(actual - expected)
            if missing:
                result["is_valid"] = False
                result["errors"].append(f"缺失章节: {missing}")
            if extras:
                result["warnings"].append(f"范围外章节: {extras}")

        duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
        if duplicates:
            result["is_valid"] = False
            result["errors"].append(f"重复章节号: {duplicates}")

        for chapter_num, chapter_text in chapters:
            report = self.validate_chapter_blueprint(chapter_text)
            if not report.is_valid:
                result["is_valid"] = False
                result["errors"].extend([f"第{chapter_num}章: {e}" for e in report.errors])
            if report.warnings:
                result["warnings"].extend([f"第{chapter_num}章: {w}" for w in report.warnings])
            if report.suggestions:
                result["suggestions"].extend([f"第{chapter_num}章: {s}" for s in report.suggestions])

        return result


class BlueprintValidator(SchemaValidator):
    """兼容旧代码的别名类。"""
    pass
