# novel_generator/language_quality.py
# -*- coding: utf-8 -*-
"""
语言质量控制器 - 提升文本的语言表达质量，优化句式结构和文体风格

功能模块：
1. 句式结构优化 - 改善句子长短搭配，增强表达效果
2. 文风一致性控制 - 维持统一的写作风格和语言特色
3. 词汇丰富度提升 - 增加词汇多样性，避免重复表达
4. 表达准确性优化 - 改进措辞选择，提高表达精确度

版本: 1.0
创建时间: 2025-01-07
"""

import re
import json
import logging
import random
from typing import Dict, List, Tuple, Optional, Any, Set
from dataclasses import dataclass
from enum import Enum


class QualityLevel(Enum):
    """语言质量级别"""
    EXCELLENT = "excellent"     # 优秀
    GOOD = "good"             # 良好
    FAIR = "fair"             # 一般
    POOR = "poor"             # 较差


class SuggestionType(Enum):
    """建议类型枚举"""
    SENTENCE_STRUCTURE = "sentence_structure"    # 句式结构建议
    WORD_CHOICE = "word_choice"                 # 词汇选择建议
    STYLE_CONSISTENCY = "style_consistency"     # 文风一致性建议
    EXPRESSION_ACCURACY = "expression_accuracy" # 表达准确性建议
    FLOW_IMPROVEMENT = "flow_improvement"       # 流畅性改进建议


@dataclass
class LanguageQualityIssue:
    """语言质量问题"""
    issue_type: SuggestionType
    severity: QualityLevel
    location: str  # 问题位置描述
    original_text: str  # 原始文本
    suggestion: str  # 改进建议
    explanation: str  # 改进理由
    confidence: float  # 置信度 (0.0 - 1.0)


@dataclass
class StyleProfile:
    """文体风格档案"""
    style_name: str
    sentence_length_range: Tuple[int, int]  # 句子长度范围
    vocabulary_level: str  # 词汇水平：简单/中等/复杂
    formal_level: str  # 正式程度：口语化/半正式/正式
    rhetorical_devices: List[str]  # 修辞手法偏好
    emotion_tone: str  # 情感色调：客观/抒情/激昂/温和
    description_density: str  # 描述密度：简洁/适中/丰富


class LanguageQualityController:
    """语言质量控制器主类"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化语言质量控制器

        Args:
            config_path: 配置文件路径，可选
        """
        self.logger = logging.getLogger(__name__)
        self.config = self._load_config(config_path)

        # 词汇资源
        self.synonyms_dict = self._load_synonyms_dict()
        self.idioms_dict = self._load_idioms_dict()
        self.style_templates = self._load_style_templates()

        # 正则表达式模式
        self.sentence_pattern = re.compile(r'[。！？]')
        self.word_pattern = re.compile(r'[\u4e00-\u9fff]+')
        self.punctuation_pattern = re.compile(r'[，。！？；：""''（）【】]')

        # 统计数据
        self.word_frequency = {}
        self.sentence_lengths = []
        self.style_markers = []

        self.logger.info("语言质量控制器初始化完成")

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """加载配置文件"""
        default_config = {
            "min_sentence_length": 8,
            "max_sentence_length": 50,
            "optimal_sentence_length": 20,
            "max_word_repetition": 3,
            "vocabulary_diversity_threshold": 0.7,
            "style_consistency_threshold": 0.8,
            "enable_auto_correction": False,
            "suggestion_confidence_threshold": 0.6
        }

        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
                self.logger.info(f"配置文件加载成功: {config_path}")
            except Exception as e:
                self.logger.warning(f"配置文件加载失败，使用默认配置: {e}")

        return default_config

    def _load_synonyms_dict(self) -> Dict[str, List[str]]:
        """加载同义词字典"""
        # 简化的同义词字典，实际应用中可以加载更完整的词典
        return {
            "美丽": ["漂亮", "俊美", "秀丽", "美观", "好看"],
            "高兴": ["开心", "快乐", "愉快", "欣喜", "喜悦"],
            "快速": ["迅速", "急速", "飞快", "火速", "火急"],
            "重要": ["关键", "要紧", "紧要", "重大", "主要"],
            "特别": ["特殊", "独特", "非凡", "异常", "格外"],
            "突然": ["忽然", "骤然", "猛然", "突兀", "冷不防"],
            "仔细": ["认真", "细致", "详尽", "周详", "周到"],
            "努力": ["尽力", "竭力", "全力", "奋力", "致力"],
            "温暖": ["温馨", "暖和", "和煦", "和暖", "温和"],
            "安静": ["宁静", "寂静", "平静", "沉静", "幽静"]
        }

    def _load_idioms_dict(self) -> Dict[str, str]:
        """加载成语字典"""
        return {
            "一举两得": "一个行动获得两种好处",
            "三心二意": "不专心，意志不坚定",
            "四面八方": "各个方向",
            "五光十色": "色彩鲜艳，种类繁多",
            "六神无主": "形容慌乱，不知所措",
            "七嘴八舌": "形容人多口杂，议论纷纷",
            "九牛一毛": "比喻极大数量中极微小的部分",
            "十全十美": "各方面都非常完美"
        }

    def _load_style_templates(self) -> Dict[str, StyleProfile]:
        """加载文体模板"""
        return {
            "小说描述": StyleProfile(
                style_name="小说描述",
                sentence_length_range=(10, 40),
                vocabulary_level="中等",
                formal_level="半正式",
                rhetorical_devices=["比喻", "拟人", "排比"],
                emotion_tone="抒情",
                description_density="丰富"
            ),
            "科技说明": StyleProfile(
                style_name="科技说明",
                sentence_length_range=(15, 60),
                vocabulary_level="复杂",
                formal_level="正式",
                rhetorical_devices=["定义", "举例", "对比"],
                emotion_tone="客观",
                description_density="适中"
            ),
            "新闻报道": StyleProfile(
                style_name="新闻报道",
                sentence_length_range=(12, 35),
                vocabulary_level="中等",
                formal_level="半正式",
                rhetorical_devices=["引用", "对比", "举例"],
                emotion_tone="客观",
                description_density="简洁"
            )
        }

    def analyze_sentence_structure(self, text: str) -> List[LanguageQualityIssue]:
        """
        分析句式结构问题

        Args:
            text: 待分析的文本

        Returns:
            发现的句式结构问题列表
        """
        issues = []

        # 1. 句子长度分析
        sentences = self._split_sentences(text)
        for i, sentence in enumerate(sentences):
            length = len(sentence)

            if length < self.config["min_sentence_length"]:
                issues.append(LanguageQualityIssue(
                    issue_type=SuggestionType.SENTENCE_STRUCTURE,
                    severity=QualityLevel.FAIR,
                    location=f"第{i+1}句",
                    original_text=sentence,
                    suggestion="考虑扩展句子，增加更多细节描述",
                    explanation="句子过短可能影响表达的完整性和丰富性",
                    confidence=0.7
                ))
            elif length > self.config["max_sentence_length"]:
                issues.append(LanguageQualityIssue(
                    issue_type=SuggestionType.SENTENCE_STRUCTURE,
                    severity=QualityLevel.FAIR,
                    location=f"第{i+1}句",
                    original_text=sentence,
                    suggestion="考虑拆分为多个句子，提高可读性",
                    explanation="句子过长可能影响读者理解和阅读流畅性",
                    confidence=0.8
                ))

        # 2. 句式多样性分析
        if len(sentences) > 1:
            variety_score = self._calculate_sentence_variety(sentences)
            if variety_score < 0.6:
                issues.append(LanguageQualityIssue(
                    issue_type=SuggestionType.SENTENCE_STRUCTURE,
                    severity=QualityLevel.FAIR,
                    location="全文",
                    original_text="句式结构分析",
                    suggestion="增加句式变化，使用不同长度和结构的句子",
                    explanation="句式多样性可以增强文本的表达效果和阅读体验",
                    confidence=0.6
                ))

        return issues

    def analyze_vocabulary_richness(self, text: str) -> List[LanguageQualityIssue]:
        """
        分析词汇丰富度

        Args:
            text: 待分析的文本

        Returns:
            发现的词汇问题列表
        """
        issues = []

        # 1. 词汇重复分析
        word_count = self._count_words(text)
        repeated_words = self._find_repeated_words(word_count)

        for word, count in repeated_words.items():
            if count > self.config["max_word_repetition"]:
                # 查找重复词的位置
                positions = self._find_word_positions(text, word)

                for pos in positions:
                    alternatives = self._find_synonyms(word)
                    if alternatives:
                        issues.append(LanguageQualityIssue(
                            issue_type=SuggestionType.WORD_CHOICE,
                            severity=QualityLevel.FAIR,
                            location=f"位置 {pos}",
                            original_text=word,
                            suggestion=f"可考虑使用同义词：{', '.join(alternatives[:3])}",
                            explanation=f"词汇'{word}'使用频率过高，影响表达的多样性",
                            confidence=0.8
                        ))

        # 2. 词汇多样性评分
        diversity_score = self._calculate_vocabulary_diversity(word_count)
        if diversity_score < self.config["vocabulary_diversity_threshold"]:
            issues.append(LanguageQualityIssue(
                issue_type=SuggestionType.WORD_CHOICE,
                severity=QualityLevel.FAIR,
                location="全文",
                original_text="词汇多样性分析",
                suggestion="增加词汇丰富度，使用更多样化的表达方式",
                explanation="词汇多样性是衡量文本质量的重要指标",
                confidence=0.7
            ))

        return issues

    def analyze_style_consistency(self, text: str, target_style: Optional[str] = None) -> List[LanguageQualityIssue]:
        """
        分析文风一致性

        Args:
            text: 待分析的文本
            target_style: 目标文体，可选

        Returns:
            发现的文风问题列表
        """
        issues = []

        # 1. 如果指定了目标风格，进行风格一致性检查
        if target_style and target_style in self.style_templates:
            style_profile = self.style_templates[target_style]
            consistency_issues = self._check_style_consistency(text, style_profile)
            issues.extend(consistency_issues)

        # 2. 语言风格统一性检查
        tone_variations = self._analyze_tone_consistency(text)
        if len(tone_variations) > 2:
            issues.append(LanguageQualityIssue(
                issue_type=SuggestionType.STYLE_CONSISTENCY,
                severity=QualityLevel.FAIR,
                location="全文",
                original_text="文风一致性分析",
                suggestion="保持全文语言风格的一致性，避免频繁转换语调",
                explanation="统一的文风有助于提升阅读体验和文章整体性",
                confidence=0.6
            ))

        return issues

    def analyze_expression_accuracy(self, text: str) -> List[LanguageQualityIssue]:
        """
        分析表达准确性

        Args:
            text: 待分析的文本

        Returns:
            发现的表达问题列表
        """
        issues = []

        # 1. 常见表达错误检查
        common_errors = self._find_common_expression_errors(text)
        issues.extend(common_errors)

        # 2. 逻辑连接词使用分析
        connection_issues = self._analyze_logical_connections(text)
        issues.extend(connection_issues)

        # 3. 情感表达准确性分析
        emotion_issues = self._analyze_emotion_expression(text)
        issues.extend(emotion_issues)

        return issues

    def enhance_text_flow(self, text: str) -> Tuple[str, List[LanguageQualityIssue]]:
        """
        增强文本流畅性

        Args:
            text: 待优化的文本

        Returns:
            优化后的文本和修改建议列表
        """
        issues = []

        # 1. 段落结构优化
        enhanced_text = self._optimize_paragraph_structure(text)

        # 2. 句子连接优化
        enhanced_text = self._optimize_sentence_connections(enhanced_text, issues)

        # 3. 过渡词优化
        enhanced_text = self._optimize_transitions(enhanced_text, issues)

        return enhanced_text, issues

    def generate_improvement_suggestions(self, text: str, target_style: Optional[str] = None) -> Dict[str, Any]:
        """
        生成综合改进建议

        Args:
            text: 待分析的文本
            target_style: 目标文体，可选

        Returns:
            改进建议报告
        """
        all_issues = []

        # 1. 各维度分析
        structure_issues = self.analyze_sentence_structure(text)
        vocabulary_issues = self.analyze_vocabulary_richness(text)
        style_issues = self.analyze_style_consistency(text, target_style)
        expression_issues = self.analyze_expression_accuracy(text)

        all_issues.extend(structure_issues)
        all_issues.extend(vocabulary_issues)
        all_issues.extend(style_issues)
        all_issues.extend(expression_issues)

        # 2. 过滤低置信度建议
        threshold = self.config["suggestion_confidence_threshold"]
        filtered_issues = [issue for issue in all_issues if issue.confidence >= threshold]

        # 3. 生成优化版本
        enhanced_text, flow_issues = self.enhance_text_flow(text)
        filtered_issues.extend(flow_issues)

        # 4. 生成报告
        report = {
            "original_text": text,
            "enhanced_text": enhanced_text,
            "quality_score": self._calculate_overall_quality_score(all_issues),
            "statistics": self._generate_text_statistics(text),
            "issues_count": {
                "total": len(filtered_issues),
                "by_type": self._group_issues_by_type(filtered_issues),
                "by_severity": self._group_issues_by_severity(filtered_issues)
            },
            "suggestions": self._format_suggestions(filtered_issues),
            "improvement_priority": self._prioritize_improvements(filtered_issues)
        }

        return report

    def _split_sentences(self, text: str) -> List[str]:
        """分割句子"""
        # 使用正则表达式分割句子
        sentences = re.split(r'[。！？]', text)
        return [s.strip() for s in sentences if s.strip()]

    def _calculate_sentence_variety(self, sentences: List[str]) -> float:
        """计算句式多样性分数"""
        if len(sentences) < 2:
            return 1.0

        lengths = [len(s) for s in sentences]
        avg_length = sum(lengths) / len(lengths)

        # 计算长度的标准差
        variance = sum((length - avg_length) ** 2 for length in lengths) / len(lengths)
        std_dev = variance ** 0.5

        # 多样性分数：标准差与平均长度的比值
        variety_score = min(std_dev / avg_length, 1.0)
        return variety_score

    def _count_words(self, text: str) -> Dict[str, int]:
        """统计词频"""
        words = self.word_pattern.findall(text)
        word_count = {}
        for word in words:
            word_count[word] = word_count.get(word, 0) + 1
        return word_count

    def _find_repeated_words(self, word_count: Dict[str, int]) -> Dict[str, int]:
        """查找重复词汇"""
        # 过滤掉常用字词（如的、是、在等）
        common_words = {'的', '是', '在', '和', '了', '有', '不', '这', '个', '我'}
        return {word: count for word, count in word_count.items()
                if word not in common_words and count > 1}

    def _find_word_positions(self, text: str, word: str) -> List[int]:
        """查找词汇在文本中的位置"""
        positions = []
        start = 0
        while True:
            pos = text.find(word, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        return positions

    def _find_synonyms(self, word: str) -> List[str]:
        """查找同义词"""
        return self.synonyms_dict.get(word, [])

    def _calculate_vocabulary_diversity(self, word_count: Dict[str, int]) -> float:
        """计算词汇多样性分数"""
        total_words = sum(word_count.values())
        unique_words = len(word_count)
        return unique_words / total_words if total_words > 0 else 0

    def _check_style_consistency(self, text: str, style_profile: StyleProfile) -> List[LanguageQualityIssue]:
        """检查文体一致性"""
        issues = []

        # 1. 检查句子长度是否符合风格要求
        sentences = self._split_sentences(text)
        avg_length = sum(len(s) for s in sentences) / len(sentences) if sentences else 0

        min_len, max_len = style_profile.sentence_length_range
        if avg_length < min_len or avg_length > max_len:
            issues.append(LanguageQualityIssue(
                issue_type=SuggestionType.STYLE_CONSISTENCY,
                severity=QualityLevel.FAIR,
                location="全文",
                original_text=f"平均句子长度：{avg_length:.1f}",
                suggestion=f"建议将平均句子长度控制在{min_len}-{max_len}字之间",
                explanation=f"当前文体的理想句子长度范围是{min_len}-{max_len}字",
                confidence=0.7
            ))

        return issues

    def _analyze_tone_consistency(self, text: str) -> List[str]:
        """分析语调一致性"""
        # 简化实现，实际可以使用NLP技术进行情感分析
        tones = []
        # 这里可以添加更复杂的语调识别逻辑
        return tones

    def _find_common_expression_errors(self, text: str) -> List[LanguageQualityIssue]:
        """查找常见表达错误"""
        issues = []

        # 常见错误模式
        error_patterns = {
            r'不.{0,3}不': "双重否定可能导致逻辑错误",
            r'很.{0,2}很': "重复使用程度副词",
            r'了了': "重复使用助词'了'"
        }

        for pattern, explanation in error_patterns.items():
            matches = re.finditer(pattern, text)
            for match in matches:
                issues.append(LanguageQualityIssue(
                    issue_type=SuggestionType.EXPRESSION_ACCURACY,
                    severity=QualityLevel.FAIR,
                    location=f"位置 {match.start()}",
                    original_text=match.group(),
                    suggestion="检查并修正表达方式",
                    explanation=explanation,
                    confidence=0.6
                ))

        return issues

    def _analyze_logical_connections(self, text: str) -> List[LanguageQualityIssue]:
        """分析逻辑连接词使用"""
        issues = []

        # 检查逻辑连接词的使用
        connection_words = ['因为', '所以', '但是', '然而', '因此', '于是']
        # 这里可以添加更复杂的逻辑分析

        return issues

    def _analyze_emotion_expression(self, text: str) -> List[LanguageQualityIssue]:
        """分析情感表达"""
        issues = []

        # 情感词汇分析
        emotion_words = ['高兴', '悲伤', '愤怒', '恐惧', '惊讶', '厌恶']
        # 这里可以添加更复杂的情感分析逻辑

        return issues

    def _optimize_paragraph_structure(self, text: str) -> str:
        """优化段落结构"""
        # 简化实现，实际可以添加更复杂的段落优化逻辑
        return text

    def _optimize_sentence_connections(self, text: str, issues: List[LanguageQualityIssue]) -> str:
        """优化句子连接"""
        # 简化实现，实际可以添加更复杂的连接优化逻辑
        return text

    def _optimize_transitions(self, text: str, issues: List[LanguageQualityIssue]) -> str:
        """优化过渡词使用"""
        # 简化实现，实际可以添加更复杂的过渡优化逻辑
        return text

    def _calculate_overall_quality_score(self, issues: List[LanguageQualityIssue]) -> float:
        """计算整体质量分数"""
        if not issues:
            return 1.0

        # 根据问题严重程度计算分数
        score_weights = {
            QualityLevel.EXCELLENT: 1.0,
            QualityLevel.GOOD: 0.8,
            QualityLevel.FAIR: 0.6,
            QualityLevel.POOR: 0.3
        }

        total_weight = 0
        weighted_score = 0

        for issue in issues:
            weight = issue.confidence
            score = score_weights.get(issue.severity, 0.5)

            total_weight += weight
            weighted_score += weight * score

        if total_weight == 0:
            return 1.0

        return weighted_score / total_weight

    def _generate_text_statistics(self, text: str) -> Dict[str, Any]:
        """生成文本统计信息"""
        sentences = self._split_sentences(text)
        words = self._count_words(text)

        return {
            "character_count": len(text),
            "sentence_count": len(sentences),
            "word_count": sum(words.values()),
            "unique_word_count": len(words),
            "avg_sentence_length": sum(len(s) for s in sentences) / len(sentences) if sentences else 0,
            "vocabulary_diversity": len(words) / sum(words.values()) if words else 0
        }

    def _group_issues_by_type(self, issues: List[LanguageQualityIssue]) -> Dict[str, int]:
        """按类型分组问题"""
        type_counts = {}
        for issue in issues:
            issue_type = issue.issue_type.value
            type_counts[issue_type] = type_counts.get(issue_type, 0) + 1
        return type_counts

    def _group_issues_by_severity(self, issues: List[LanguageQualityIssue]) -> Dict[str, int]:
        """按严重程度分组问题"""
        severity_counts = {}
        for issue in issues:
            severity = issue.severity.value
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        return severity_counts

    def _format_suggestions(self, issues: List[LanguageQualityIssue]) -> List[Dict[str, Any]]:
        """格式化建议列表"""
        return [
            {
                "type": issue.issue_type.value,
                "severity": issue.severity.value,
                "location": issue.location,
                "original": issue.original_text,
                "suggestion": issue.suggestion,
                "explanation": issue.explanation,
                "confidence": issue.confidence
            }
            for issue in issues
        ]

    def _prioritize_improvements(self, issues: List[LanguageQualityIssue]) -> List[str]:
        """确定改进优先级"""
        # 按置信度和严重程度排序
        sorted_issues = sorted(issues, key=lambda x: (x.confidence, x.severity.value), reverse=True)
        return [issue.suggestion for issue in sorted_issues[:10]]  # 返回前10个最重要的建议


def create_language_quality_controller(config_path: Optional[str] = None) -> LanguageQualityController:
    """
    创建语言质量控制器实例

    Args:
        config_path: 配置文件路径，可选

    Returns:
        LanguageQualityController实例
    """
    return LanguageQualityController(config_path)


if __name__ == "__main__":
    # 测试代码
    controller = create_language_quality_controller()

    # 示例文本
    sample_text = """
    今天天气很好。我很高兴。小明也很高兴。我们一起去公园。
    公园里有很多人。大家都很高兴。这是一个高兴的日子。
    """

    # 生成改进建议
    report = controller.generate_improvement_suggestions(sample_text)
    print(json.dumps(report, ensure_ascii=False, indent=2))