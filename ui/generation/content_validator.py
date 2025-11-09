"""
Content Validator
内容验证器类

负责内容质量检查、语言纯度验证、一致性检查等功能。
确保生成的内容符合质量标准和一致性要求。

主要功能:
- 内容完整性验证
- 语言纯度检查
- 逻辑一致性验证
- 自动问题修复
- 质量评分
"""

import re
import logging
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

from .error_handler import ErrorHandler

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """验证级别"""
    BASIC = "basic"           # 基础验证
    STANDARD = "standard"     # 标准验证
    STRICT = "strict"         # 严格验证
    COMPREHENSIVE = "comprehensive"  # 综合验证


class ValidationIssueType(Enum):
    """验证问题类型"""
    EMPTY_CONTENT = "empty_content"
    INSUFFICIENT_LENGTH = "insufficient_length"
    MISSING_PUNCTUATION = "missing_punctuation"
    LANGUAGE_MIX = "language_mix"
    REPETITIVE_CONTENT = "repetitive_content"
    INCONSISTENT_STYLE = "inconsistent_style"
    LOGIC_INCONSISTENCY = "logic_inconsistency"
    OMITTED_CONTENT = "omitted_content"
    FORMAT_ERROR = "format_error"


@dataclass
class ValidationIssue:
    """验证问题"""
    issue_type: ValidationIssueType
    severity: str  # "low", "medium", "high", "critical"
    message: str
    position: Optional[int] = None  # 问题位置
    suggestion: Optional[str] = None  # 修复建议
    auto_fixable: bool = False  # 是否可自动修复


@dataclass
class ValidationReport:
    """验证报告"""
    is_valid: bool
    overall_score: float  # 0-100
    issues: List[ValidationIssue]
    word_count: int
    paragraph_count: int
    sentence_count: int
    validation_time: float = 0.0

    @property
    def critical_issues(self) -> List[ValidationIssue]:
        """获取严重问题"""
        return [issue for issue in self.issues if issue.severity == "critical"]

    @property
    def high_issues(self) -> List[ValidationIssue]:
        """获取高优先级问题"""
        return [issue for issue in self.issues if issue.severity == "high"]

    @property
    def auto_fixable_issues(self) -> List[ValidationIssue]:
        """获取可自动修复的问题"""
        return [issue for issue in self.issues if issue.auto_fixable]


class ContentValidator:
    """内容验证器类"""

    def __init__(self, error_handler: ErrorHandler):
        """
        初始化内容验证器

        Args:
            error_handler: 错误处理器
        """
        self.error_handler = error_handler
        self.validation_stats = {
            'total_validations': 0,
            'passed': 0,
            'failed': 0,
            'auto_fixed': 0
        }

        # 省略号模式（零容忍）
        self.omission_patterns = [
            r'\.\.\.',
            r'……',
            r'\.\s*\.\s*\.',
            r'省略',
            r'略写',
            r'待补充',
            r'TODO',
            r'TBD',
            r'此处省略',
            r'内容省略'
        ]

        # 语言混合检测模式
        self.language_mix_patterns = [
            r'[a-zA-Z]{2,}',  # 英文单词
            r'[がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽまみむめもやゆよらりるれろわをん]',  # 日文
        ]

        # 重复内容检测
        self.repetition_threshold = 3  # 同样句子重复3次认为有问题

        logger.info("ContentValidator 初始化完成")

    def validate_content(
        self,
        content: str,
        chapter_id: int = 0,
        validation_level: ValidationLevel = ValidationLevel.STANDARD,
        auto_fix: bool = True
    ) -> Tuple[ValidationReport, str]:
        """
        验证内容质量

        Args:
            content: 待验证的内容
            chapter_id: 章节ID
            validation_level: 验证级别
            auto_fix: 是否自动修复问题

        Returns:
            Tuple[ValidationReport, str]: 验证报告和修复后的内容
        """
        import time
        start_time = time.time()

        self.validation_stats['total_validations'] += 1
        logger.info(f"开始验证第{chapter_id}章内容，级别: {validation_level.value}")

        try:
            # 基础分析
            content_analysis = self._analyze_content(content)

            # 收集问题
            issues = []

            # 基础验证（所有级别都执行）
            issues.extend(self._validate_basic_content(content, content_analysis))

            # 标准验证
            if validation_level in [ValidationLevel.STANDARD, ValidationLevel.STRICT, ValidationLevel.COMPREHENSIVE]:
                issues.extend(self._validate_standard_content(content, content_analysis))

            # 严格验证
            if validation_level in [ValidationLevel.STRICT, ValidationLevel.COMPREHENSIVE]:
                issues.extend(self._validate_strict_content(content, content_analysis))

            # 综合验证
            if validation_level == ValidationLevel.COMPREHENSIVE:
                issues.extend(self._validate_comprehensive_content(content, content_analysis, chapter_id))

            # 计算总体评分
            overall_score = self._calculate_score(content_analysis, issues)

            # 创建验证报告
            report = ValidationReport(
                is_valid=len([i for i in issues if i.severity in ["critical", "high"]]) == 0,
                overall_score=overall_score,
                issues=issues,
                word_count=len(content),
                paragraph_count=content_analysis['paragraph_count'],
                sentence_count=content_analysis['sentence_count'],
                validation_time=time.time() - start_time
            )

            # 自动修复
            fixed_content = content
            if auto_fix and report.auto_fixable_issues:
                fixed_content = self._auto_fix_issues(content, report.auto_fixable_issues)
                self.validation_stats['auto_fixed'] += 1
                logger.info(f"自动修复了{len(report.auto_fixable_issues)}个问题")

            # 更新统计
            if report.is_valid:
                self.validation_stats['passed'] += 1
            else:
                self.validation_stats['failed'] += 1

            logger.info(f"第{chapter_id}章验证完成，评分: {overall_score:.1f}")

            return report, fixed_content

        except Exception as e:
            logger.error(f"内容验证失败: {e}")
            # 创建错误报告
            error_report = ValidationReport(
                is_valid=False,
                overall_score=0.0,
                issues=[ValidationIssue(
                    issue_type=ValidationIssueType.FORMAT_ERROR,
                    severity="critical",
                    message=f"验证过程出错: {e}"
                )],
                word_count=len(content),
                paragraph_count=0,
                sentence_count=0,
                validation_time=time.time() - start_time
            )
            return error_report, content

    def _analyze_content(self, content: str) -> Dict[str, Any]:
        """分析内容结构"""
        # 基础统计
        analysis = {
            'length': len(content),
            'word_count': len(content),
            'paragraph_count': len([p for p in content.split('\n\n') if p.strip()]),
            'sentence_count': len(re.findall(r'[。！？.!?]', content)),
            'has_chinese': bool(re.search(r'[\u4e00-\u9fff]', content)),
            'has_english': bool(re.search(r'[a-zA-Z]', content)),
            'has_numbers': bool(re.search(r'[0-9]', content)),
        }

        # 段落分析
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
        analysis['paragraph_lengths'] = [len(p) for p in paragraphs]
        analysis['avg_paragraph_length'] = sum(analysis['paragraph_lengths']) / len(analysis['paragraph_lengths']) if paragraphs else 0

        # 句子分析
        sentences = re.split(r'[。！？.!?]', content)
        sentences = [s.strip() for s in sentences if s.strip()]
        analysis['sentence_lengths'] = [len(s) for s in sentences]
        analysis['avg_sentence_length'] = sum(analysis['sentence_lengths']) / len(analysis['sentence_lengths']) if sentences else 0

        # 重复检测
        analysis['repeated_sentences'] = self._detect_repetition(sentences)

        return analysis

    def _validate_basic_content(self, content: str, analysis: Dict[str, Any]) -> List[ValidationIssue]:
        """基础内容验证"""
        issues = []

        # 空内容检查
        if not content or not content.strip():
            issues.append(ValidationIssue(
                issue_type=ValidationIssueType.EMPTY_CONTENT,
                severity="critical",
                message="内容为空",
                auto_fixable=False
            ))

        # 内容过短检查
        if len(content) < 100:
            issues.append(ValidationIssue(
                issue_type=ValidationIssueType.INSUFFICIENT_LENGTH,
                severity="high",
                message=f"内容过短: {len(content)} 字符",
                suggestion="增加更多细节和描述",
                auto_fixable=False
            ))

        # 省略号检查（零容忍）
        for pattern in self.omission_patterns:
            matches = re.findall(pattern, content)
            if matches:
                issues.append(ValidationIssue(
                    issue_type=ValidationIssueType.OMITTED_CONTENT,
                    severity="critical",
                    message=f"发现省略内容: {matches[0]}",
                    suggestion="完整表达内容，避免使用省略号",
                    auto_fixable=True
                ))

        return issues

    def _validate_standard_content(self, content: str, analysis: Dict[str, Any]) -> List[ValidationIssue]:
        """标准内容验证"""
        issues = []

        # 段落结构检查
        if analysis['paragraph_count'] < 3:
            issues.append(ValidationIssue(
                issue_type=ValidationIssueType.FORMAT_ERROR,
                severity="medium",
                message=f"段落数量过少: {analysis['paragraph_count']}段",
                suggestion="增加段落划分，提高可读性",
                auto_fixable=False
            ))

        # 段落长度检查
        if analysis['avg_paragraph_length'] > 1000:
            issues.append(ValidationIssue(
                issue_type=ValidationIssueType.FORMAT_ERROR,
                severity="medium",
                message=f"段落过长: 平均{analysis['avg_paragraph_length']:.0f}字符",
                suggestion="拆分过长段落",
                auto_fixable=True
            ))

        # 标点符号检查
        if analysis['sentence_count'] == 0:
            issues.append(ValidationIssue(
                issue_type=ValidationIssueType.MISSING_PUNCTUATION,
                severity="high",
                message="缺少标点符号",
                suggestion="添加适当的标点符号",
                auto_fixable=True
            ))

        return issues

    def _validate_strict_content(self, content: str, analysis: Dict[str, Any]) -> List[ValidationIssue]:
        """严格内容验证"""
        issues = []

        # 语言混合检查
        if analysis['has_chinese'] and analysis['has_english']:
            english_count = len(re.findall(r'[a-zA-Z]{2,}', content))
            if english_count > len(content) * 0.05:  # 超过5%英文
                issues.append(ValidationIssue(
                    issue_type=ValidationIssueType.LANGUAGE_MIX,
                    severity="medium",
                    message=f"语言混合: 发现{english_count}个英文单词",
                    suggestion="考虑翻译或统一语言",
                    auto_fixable=True
                ))

        # 重复内容检查
        if analysis['repeated_sentences']:
            issues.append(ValidationIssue(
                issue_type=ValidationIssueType.REPETITIVE_CONTENT,
                severity="medium",
                message=f"发现重复内容: {len(analysis['repeated_sentences'])}处",
                suggestion="修改重复的表达",
                auto_fixable=True
            ))

        # 句子长度检查
        too_long_sentences = [s for s in analysis['sentence_lengths'] if s > 200]
        if too_long_sentences:
            issues.append(ValidationIssue(
                issue_type=ValidationIssueType.FORMAT_ERROR,
                severity="low",
                message=f"过长句子: {len(too_long_sentences)}句",
                suggestion="拆分过长的句子",
                auto_fixable=True
            ))

        return issues

    def _validate_comprehensive_content(
        self,
        content: str,
        analysis: Dict[str, Any],
        chapter_id: int
    ) -> List[ValidationIssue]:
        """综合内容验证"""
        issues = []

        # 这里可以集成更复杂的验证逻辑
        # 比如：情节一致性检查、角色状态验证、世界观一致性等

        # 风格一致性检查
        if self._check_style_inconsistency(content):
            issues.append(ValidationIssue(
                issue_type=ValidationIssueType.INCONSISTENT_STYLE,
                severity="low",
                message="写作风格不一致",
                suggestion="统一写作风格和表达方式",
                auto_fixable=False
            ))

        return issues

    def _detect_repetition(self, sentences: List[str]) -> List[str]:
        """检测重复的句子"""
        repeated = []
        sentence_counts = {}

        for sentence in sentences:
            sentence = sentence.lower().strip()
            if len(sentence) > 10:  # 忽略太短的句子
                sentence_counts[sentence] = sentence_counts.get(sentence, 0) + 1
                if sentence_counts[sentence] >= self.repetition_threshold:
                    repeated.append(sentence)

        return repeated

    def _check_style_inconsistency(self, content: str) -> bool:
        """检查风格一致性"""
        # 简单的风格检查：人称一致性
        first_person = len(re.findall(r'我[们]?是|我[们]?在|我[们]?的', content))
        third_person = len(re.findall(r'[他她它]们?是|[他她它]们?在|[他她它]们的', content))

        # 如果同时使用较多的一人称和三人称，可能存在风格不一致
        return first_person > 5 and third_person > 5

    def _calculate_score(self, analysis: Dict[str, Any], issues: List[ValidationIssue]) -> float:
        """计算内容质量评分"""
        base_score = 100.0

        # 根据问题扣分
        for issue in issues:
            if issue.severity == "critical":
                base_score -= 20
            elif issue.severity == "high":
                base_score -= 10
            elif issue.severity == "medium":
                base_score -= 5
            elif issue.severity == "low":
                base_score -= 2

        # 基础分数调整
        if analysis['word_count'] < 500:
            base_score -= 10
        elif analysis['word_count'] < 1000:
            base_score -= 5

        if analysis['paragraph_count'] < 3:
            base_score -= 5

        # 确保分数在0-100范围内
        return max(0.0, min(100.0, base_score))

    def _auto_fix_issues(self, content: str, issues: List[ValidationIssue]) -> str:
        """自动修复问题"""
        fixed_content = content

        for issue in issues:
            try:
                if issue.issue_type == ValidationIssueType.OMITTED_CONTENT:
                    fixed_content = self._fix_omissions(fixed_content)
                elif issue.issue_type == ValidationIssueType.LANGUAGE_MIX:
                    fixed_content = self._fix_language_mix(fixed_content)
                elif issue.issue_type == ValidationIssueType.REPETITIVE_CONTENT:
                    fixed_content = self._fix_repetition(fixed_content)
                elif issue.issue_type == ValidationIssueType.FORMAT_ERROR:
                    fixed_content = self._fix_format_issues(fixed_content)
            except Exception as e:
                logger.warning(f"自动修复问题失败: {e}")

        return fixed_content

    def _fix_omissions(self, content: str) -> str:
        """修复省略内容"""
        # 移除省略号模式
        for pattern in self.omission_patterns:
            content = re.sub(pattern, '', content)
        return content

    def _fix_language_mix(self, content: str) -> str:
        """修复语言混合"""
        # 简单的英文单词移除
        content = re.sub(r'\b[a-zA-Z]{2,}\b', '', content)
        return content

    def _fix_repetition(self, content: str) -> str:
        """修复重复内容"""
        # 简单的重复内容合并
        sentences = re.split(r'([。！？.!?])', content)
        seen_sentences = set()
        result = []

        for i in range(0, len(sentences), 2):
            if i + 1 < len(sentences):
                sentence = sentences[i]
                punctuation = sentences[i + 1]
                full_sentence = sentence + punctuation

                if sentence.strip() and sentence.strip().lower() not in seen_sentences:
                    seen_sentences.add(sentence.strip().lower())
                    result.append(full_sentence)
                elif not sentence.strip():
                    result.append(full_sentence)
            else:
                result.append(sentences[i])

        return ''.join(result)

    def _fix_format_issues(self, content: str) -> str:
        """修复格式问题"""
        # 添加标点符号
        content = re.sub(r'([^\s。！？.!?])(\n|$)', r'\1。\2', content)

        # 段落格式化
        paragraphs = content.split('\n\n')
        formatted_paragraphs = [p.strip() for p in paragraphs if p.strip()]
        return '\n\n'.join(formatted_paragraphs)

    def get_validation_stats(self) -> Dict[str, Any]:
        """获取验证统计"""
        total = self.validation_stats['total_validations']
        if total == 0:
            return {
                **self.validation_stats,
                'pass_rate': 0.0,
                'auto_fix_rate': 0.0
            }

        return {
            **self.validation_stats,
            'pass_rate': round(self.validation_stats['passed'] / total * 100, 2),
            'auto_fix_rate': round(self.validation_stats['auto_fixed'] / total * 100, 2)
        }

    def reset_stats(self) -> None:
        """重置验证统计"""
        self.validation_stats = {
            'total_validations': 0,
            'passed': 0,
            'failed': 0,
            'auto_fixed': 0
        }
        logger.info("验证统计已重置")