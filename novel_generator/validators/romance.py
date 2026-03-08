# -*- coding: utf-8 -*-
"""
暧昧场景密度验证器
继承自BaseValidator
"""
from typing import Dict, List
from novel_generator.validators.base import BaseValidator, ValidationContext
from novel_generator.core.rules import get_rules_config


class RomanceValidator(BaseValidator):
    def __init__(self, context: ValidationContext):
        super().__init__(context)
        self.rules = get_rules_config()
        self.romance_keywords = {
            "高张力": ["心动", "脸红", "耳根", "暧昧", "暧昧等级", "暧昧类型", "好感度"],
            "身体接触": ["疗伤", "触碰", "指尖", "气息", "拥抱", "牵手", "靠近", "依偎"],
            "情感表达": ["表白", "告白", "喜欢", "爱慕", "心意", "守护", "保护"],
            "氛围描写": ["月下", "夜色", "烛光", "温暖", "温柔", "心跳", "脸颊发烫"],
            "修罗场": ["嫉妒", "争风吃醋", "修罗场", "四人", "争夺"]
        }
        # Dynamic female leads loading
        self.female_leads = self._load_female_leads()
    
    def _load_female_leads(self):
        """Load female leads from architecture file"""
        try:
            from novel_generator.architecture_parser import ArchitectureParser
            filepath = getattr(self.context, 'filepath', None) or getattr(self.context, 'novel_path', '')
            if filepath:
                parser = ArchitectureParser(str(filepath))
                parser.parse()
                if parser.female_leads:
                    return parser.female_leads
        except Exception:
            pass
        return []  # Empty fallback - no hardcoded defaults

    def _check_romance_in_chapter(self, chapter_content: str) -> bool:
        """检查章节是否包含暧昧场景"""
        if not chapter_content:
            return False
            
        romance_score = 0
        has_female_lead = any(lead in chapter_content for lead in self.female_leads)
        
        if not has_female_lead:
            return False
            
        for keywords in self.romance_keywords.values():
            for keyword in keywords:
                if keyword in chapter_content:
                    romance_score += 1
                    
        return romance_score >= 3

    def validate(self) -> Dict:
        results = {
            "name": "暧昧密度验证",
            "passed": True,
            "issues": [],
            "warnings": [],
            "score": 100,
            "gaps": []
        }
        
        # 只检查前400章或实际存在的章节
        max_chapter = 400
        existing_chapters = sorted(list(self.context.get_existing_chapters()))
        if not existing_chapters:
            results["warnings"].append("未找到任何章节")
            return results
            
        start_chapter = existing_chapters[0]
        end_chapter = min(existing_chapters[-1], max_chapter)
        
        gaps_count = 0
        total_intervals = 0
        
        # 每10章一个区间
        for start in range(start_chapter, end_chapter + 1, 10):
            end = min(start + 9, end_chapter)
            total_intervals += 1
            has_romance = False
            
            for chapter_num in range(start, end + 1):
                content = self.context.get_chapter_content(chapter_num)
                if self._check_romance_in_chapter(content):
                    has_romance = True
                    break
            
            if not has_romance:
                gaps_count += 1
                suggestion = ""
                # 尝试从规则配置中获取建议
                for c_num in range(start, end + 1):
                    if c_num in self.rules.romance:
                        r = self.rules.romance[c_num]
                        suggestion = f"（建议参考第{c_num}章预设：{r.get('lead')}-{r.get('type')}）"
                        break
                
                results["gaps"].append(f"第{start}-{end}章区间缺失暧昧场景{suggestion}")
                results["issues"].append(f"区间 {start}-{end} 缺少暧昧内容")

        if total_intervals > 0:
            compliance_rate = (total_intervals - gaps_count) / total_intervals
            results["score"] = compliance_rate * 100
            results["passed"] = compliance_rate >= 0.8  # 80%达标率
            
        return results
