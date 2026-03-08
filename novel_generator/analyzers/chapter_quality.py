# -*- coding: utf-8 -*-
"""
章节质量分析器
自动评估已生成章节的质量，检测潜在问题
"""

import os
import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class QualityScore:
    """质量评分结果"""
    dimension: str
    score: float  # 0.0 - 1.0
    weight: float
    details: str


class ChapterQualityAnalyzer:
    """章节质量分析器"""
    
    # 程序员相关关键词 (genre-agnostic, always applicable)
    PROGRAMMER_KEYWORDS = [
        "代码", "BUG", "bug", "调试", "算法", "逻辑", "数据", "运行",
        "程序", "编译", "变量", "函数", "接口", "系统", "优化", "循环",
        "分析", "推演", "计算", "效率", "模块", "架构", "底层", "debug"
    ]
    
    # NOTE: Female leads are now loaded dynamically in __init__
    
    # 动作场景关键词
    ACTION_KEYWORDS = [
        "攻击", "一拳", "一剑", "轰", "碎", "杀", "战斗", "冲击",
        "爆发", "斩", "刺", "劈", "砸", "震", "崩", "裂", "喷"
    ]
    
    # 评分维度权重
    DIMENSION_WEIGHTS = {
        "word_count": 0.15,
        "programmer_density": 0.20,
        "female_lead_presence": 0.15,
        "dialogue_ratio": 0.15,
        "action_density": 0.15,
        "paragraph_structure": 0.10,
        "ending_quality": 0.10,
    }
    
    def __init__(self, chapters_dir: str = None, novel_path: str = None):
        self.chapters_dir = chapters_dir
        self.novel_path = novel_path
        
        # Dynamic female leads loading
        self.female_leads = self._load_female_leads()
    
    def _load_female_leads(self):
        """Load female leads from architecture dynamically"""
        try:
            from novel_generator.architecture_parser import ArchitectureParser
            # Derive novel_path from chapters_dir if not provided
            fp = self.novel_path
            if not fp and self.chapters_dir:
                from pathlib import Path
                fp = str(Path(self.chapters_dir).parent)
            if fp:
                parser = ArchitectureParser(fp)
                parser.parse()
                if parser.female_leads:
                    return parser.female_leads
        except Exception:
            pass
        return []  # Empty fallback - no hardcoded defaults
    
    def analyze_chapter(self, content: str, chapter_num: int = None) -> Dict:
        """
        分析单章质量
        
        Args:
            content: 章节内容
            chapter_num: 章节号（可选，用于上下文判断）
        
        Returns:
            {
                "scores": {dimension: QualityScore},
                "weighted_score": float,
                "issues": [str],
                "suggestions": [str]
            }
        """
        scores = {}
        
        # 1. 字数检查
        scores["word_count"] = self._check_word_count(content)
        
        # 2. 程序员关键词密度
        scores["programmer_density"] = self._check_programmer_keywords(content)
        
        # 3. 女主出场检测
        scores["female_lead_presence"] = self._check_female_leads(content, chapter_num)
        
        # 4. 对话比例
        scores["dialogue_ratio"] = self._check_dialogue_ratio(content)
        
        # 5. 动作场景密度
        scores["action_density"] = self._check_action_density(content)
        
        # 6. 段落结构
        scores["paragraph_structure"] = self._check_paragraph_structure(content)
        
        # 7. 结尾质量
        scores["ending_quality"] = self._check_ending_quality(content)
        
        # 计算加权总分
        weighted_score = sum(
            scores[dim].score * self.DIMENSION_WEIGHTS[dim]
            for dim in scores
        )
        
        # 识别问题
        issues = self._identify_issues(scores, chapter_num)
        
        # 生成建议
        suggestions = self._generate_suggestions(scores, issues)
        
        return {
            "scores": scores,
            "weighted_score": weighted_score,
            "issues": issues,
            "suggestions": suggestions
        }
    
    def _check_word_count(self, content: str) -> QualityScore:
        """检查字数是否在合理范围"""
        # 中文字符数
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
        
        # 理想范围：4000-6000字
        if 4000 <= chinese_chars <= 6000:
            score = 1.0
            details = f"字数{chinese_chars}，在理想范围内"
        elif 3000 <= chinese_chars < 4000 or 6000 < chinese_chars <= 7000:
            score = 0.8
            details = f"字数{chinese_chars}，略微偏离理想范围"
        else:
            score = 0.5
            details = f"字数{chinese_chars}，显著偏离理想范围(4000-6000)"
        
        return QualityScore("字数", score, self.DIMENSION_WEIGHTS["word_count"], details)
    
    def _check_programmer_keywords(self, content: str) -> QualityScore:
        """检查程序员特色关键词密度"""
        total_count = sum(content.count(kw) for kw in self.PROGRAMMER_KEYWORDS)
        
        # 理想：每章至少3个程序员隐喻
        if total_count >= 5:
            score = 1.0
            details = f"程序员关键词{total_count}处，特色鲜明"
        elif total_count >= 3:
            score = 0.8
            details = f"程序员关键词{total_count}处，特色较好"
        elif total_count >= 1:
            score = 0.5
            details = f"程序员关键词仅{total_count}处，特色较弱"
        else:
            score = 0.2
            details = "未检测到程序员关键词，特色缺失"
        
        return QualityScore("程序员特色", score, self.DIMENSION_WEIGHTS["programmer_density"], details)
    
    def _check_female_leads(self, content: str, chapter_num: int = None) -> QualityScore:
        """检查女主戏份"""
        lead_counts = {lead: content.count(lead) for lead in self.female_leads}
        total_mentions = sum(lead_counts.values())
        
        # 找出本章出现最多的女主
        if lead_counts:
            main_lead = max(lead_counts, key=lead_counts.get)
            main_count = lead_counts[main_lead]
        else:
            main_lead = None
            main_count = 0
        
        # 评分逻辑：早期章节（1-10）至少需要女主出现
        if chapter_num and chapter_num <= 10:
            min_expected = 3
        else:
            min_expected = 2
        
        if total_mentions >= min_expected * 2:
            score = 1.0
            details = f"女主出场{total_mentions}次，戏份充足"
        elif total_mentions >= min_expected:
            score = 0.8
            details = f"女主出场{total_mentions}次，戏份适中"
        elif total_mentions >= 1:
            score = 0.5
            details = f"女主仅出场{total_mentions}次，戏份偏少"
        else:
            score = 0.3
            details = "本章无女主出场"
        
        return QualityScore("女主戏份", score, self.DIMENSION_WEIGHTS["female_lead_presence"], details)
    
    def _check_dialogue_ratio(self, content: str) -> QualityScore:
        """检查对话比例"""
        # 统计对话数量（支持多种引号格式）
        # 中文左引号: \u201c (") 中文右引号: \u201d (")
        # 直角引号: \u300c (「) \u300d (」)
        chinese_left = content.count('\u201c')  # "
        chinese_right = content.count('\u201d')  # "
        bracket_left = content.count('\u300c')  # 「
        # 英文引号
        english_quote = content.count('"') // 2
        
        # 对话数以左引号为准
        dialogue_count = chinese_left + bracket_left + english_quote
        
        # 统计行数
        lines = [l for l in content.split('\n') if l.strip()]
        line_count = max(len(lines), 1)
        
        # 对话占行数比例
        ratio = dialogue_count / line_count
        
        # 理想：每章至少10处对话
        if dialogue_count >= 15:
            score = 1.0
            details = f"对话{dialogue_count}处，节奏均衡"
        elif dialogue_count >= 10:
            score = 0.9
            details = f"对话{dialogue_count}处，节奏良好"
        elif dialogue_count >= 5:
            score = 0.7
            details = f"对话{dialogue_count}处，节奏适中"
        else:
            score = 0.5
            details = f"对话仅{dialogue_count}处，建议增加"
        
        return QualityScore("对话比例", score, self.DIMENSION_WEIGHTS["dialogue_ratio"], details)
    
    def _check_action_density(self, content: str) -> QualityScore:
        """检查动作场景密度"""
        action_count = sum(content.count(kw) for kw in self.ACTION_KEYWORDS)
        
        # 每千字理想动作词数
        word_count = len(content)
        density = action_count / (word_count / 1000) if word_count > 0 else 0
        
        if density >= 3:
            score = 1.0
            details = f"动作密度{density:.1f}/千字，节奏紧凑"
        elif density >= 1.5:
            score = 0.8
            details = f"动作密度{density:.1f}/千字，节奏适中"
        elif density >= 0.5:
            score = 0.6
            details = f"动作密度{density:.1f}/千字，节奏偏缓"
        else:
            score = 0.4
            details = f"动作密度{density:.1f}/千字，缺少紧张感"
        
        return QualityScore("动作密度", score, self.DIMENSION_WEIGHTS["action_density"], details)
    
    def _check_paragraph_structure(self, content: str) -> QualityScore:
        """检查段落结构"""
        paragraphs = [p for p in content.split('\n\n') if p.strip()]
        
        if len(paragraphs) < 10:
            score = 0.5
            details = f"仅{len(paragraphs)}个段落，结构过于紧凑"
        elif len(paragraphs) > 100:
            score = 0.6
            details = f"{len(paragraphs)}个段落，结构过于零散"
        else:
            # 检查段落长度变化
            lengths = [len(p) for p in paragraphs]
            avg_len = sum(lengths) / len(lengths)
            
            if 50 <= avg_len <= 300:
                score = 1.0
                details = f"{len(paragraphs)}段落，平均{avg_len:.0f}字，结构良好"
            else:
                score = 0.7
                details = f"段落平均{avg_len:.0f}字，建议调整"
        
        return QualityScore("段落结构", score, self.DIMENSION_WEIGHTS["paragraph_structure"], details)
    
    def _check_ending_quality(self, content: str) -> QualityScore:
        """检查结尾质量"""
        # 取最后500字符
        ending = content[-500:] if len(content) > 500 else content
        
        # 检查是否有悬念/hook
        hook_keywords = ["【", "叮", "警告", "任务", "系统", "下一章", "才刚刚开始", "风暴"]
        has_hook = any(kw in ending for kw in hook_keywords)
        
        # 检查是否有情感高潮
        emotion_keywords = ["心中", "眼神", "决心", "坚定", "感受"]
        has_emotion = any(kw in ending for kw in emotion_keywords)
        
        if has_hook and has_emotion:
            score = 1.0
            details = "结尾有悬念和情感收束"
        elif has_hook or has_emotion:
            score = 0.8
            details = "结尾有悬念或情感收束"
        else:
            score = 0.5
            details = "结尾较为平淡，建议添加hook"
        
        return QualityScore("结尾质量", score, self.DIMENSION_WEIGHTS["ending_quality"], details)
    
    def _identify_issues(self, scores: Dict[str, QualityScore], chapter_num: int = None) -> List[str]:
        """识别问题"""
        issues = []
        
        for dim, score_obj in scores.items():
            if score_obj.score < 0.6:
                issues.append(f"⚠️ {score_obj.dimension}: {score_obj.details}")
            elif score_obj.score < 0.8:
                issues.append(f"💡 {score_obj.dimension}: {score_obj.details}")
        
        return issues
    
    def _generate_suggestions(self, scores: Dict[str, QualityScore], issues: List[str]) -> List[str]:
        """生成改进建议"""
        suggestions = []
        
        if scores["programmer_density"].score < 0.6:
            suggestions.append("建议添加更多程序员思维隐喻，如：代码调试、算法优化、逻辑分析等")
        
        if scores["female_lead_presence"].score < 0.6:
            suggestions.append("建议增加女主戏份，至少应有名字提及或互动场景")
        
        if scores["ending_quality"].score < 0.6:
            suggestions.append("建议在结尾添加悬念或情感hook，如系统提示、任务触发等")
        
        return suggestions
    
    def analyze_all_chapters(self) -> Dict:
        """分析所有章节"""
        if not self.chapters_dir or not os.path.exists(self.chapters_dir):
            return {"error": "chapters目录不存在"}
        
        results = {}
        overall_scores = []
        all_issues = []
        
        for filename in sorted(os.listdir(self.chapters_dir)):
            if filename.startswith("chapter_") and filename.endswith(".txt"):
                chapter_num = int(filename.replace("chapter_", "").replace(".txt", ""))
                filepath = os.path.join(self.chapters_dir, filename)
                
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                result = self.analyze_chapter(content, chapter_num)
                results[chapter_num] = result
                overall_scores.append(result["weighted_score"])
                
                if result["issues"]:
                    all_issues.append((chapter_num, result["issues"]))
        
        return {
            "chapters": results,
            "average_score": sum(overall_scores) / len(overall_scores) if overall_scores else 0,
            "total_chapters": len(results),
            "issues_summary": all_issues
        }
    
    def generate_report(self) -> str:
        """生成质量报告"""
        analysis = self.analyze_all_chapters()
        
        if "error" in analysis:
            return f"错误: {analysis['error']}"
        
        lines = [
            "=" * 50,
            "章节质量分析报告",
            "=" * 50,
            f"分析章节数: {analysis['total_chapters']}",
            f"平均质量分: {analysis['average_score']:.2f}/1.0",
            "",
            "各章评分:",
        ]
        
        for ch_num, result in sorted(analysis["chapters"].items()):
            score = result["weighted_score"]
            stars = "⭐" * int(score * 5)
            lines.append(f"  第{ch_num}章: {score:.2f} {stars}")
        
        if analysis["issues_summary"]:
            lines.append("")
            lines.append("问题汇总:")
            for ch_num, issues in analysis["issues_summary"]:
                for issue in issues:
                    lines.append(f"  第{ch_num}章: {issue}")
        
        lines.append("=" * 50)
        
        return "\n".join(lines)


def analyze_chapters(chapters_dir: str) -> Dict:
    """便捷函数：分析章节质量"""
    analyzer = ChapterQualityAnalyzer(chapters_dir)
    return analyzer.analyze_all_chapters()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        chapters_dir = sys.argv[1]
    else:
        print("Usage: python chapter_quality.py <chapters_directory>")
        sys.exit(1)
    analyzer = ChapterQualityAnalyzer(chapters_dir)
    print(analyzer.generate_report())
