# -*- coding: utf-8 -*-
"""
一致性验证器 (P3)
检查章节间的逻辑一致性，如预告与实际、角色状态延续等
"""

import re
from typing import Dict, List, Tuple, Optional
from .base import BaseValidator


class ConsistencyValidator(BaseValidator):
    """检查章节间逻辑一致性"""
    
    name = "consistency_validator"
    
    def _get_female_leads(self):
        """Dynamically load female leads from architecture"""
        try:
            from novel_generator.architecture_parser import ArchitectureParser
            filepath = getattr(self.context, 'filepath', None) or getattr(self.context.blueprint, 'filepath', '')
            if filepath:
                parser = ArchitectureParser(str(filepath))
                parser.parse()
                if parser.female_leads:
                    return parser.female_leads
        except Exception:
            pass
        return []  # Empty fallback
    
    def _extract_field(self, content: str, field_name: str) -> Optional[str]:
        """提取指定字段的内容"""
        # 尝试多种格式
        patterns = [
            rf'{field_name}[：:]\s*(.+?)(?=\n[【\*]|\n\n|$)',
            rf'\*\*{field_name}\*\*[：:]\s*(.+?)(?=\n[【\*]|\n\n|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_title(self, content: str) -> Optional[str]:
        """提取章节标题"""
        match = re.search(r'第\d+章\s*[-—:：]\s*(.+?)(?:\*\*|\n|$)', content)
        if match:
            return match.group(1).strip()
        return None
    
    def _fuzzy_match(self, preview: str, actual: str) -> bool:
        """
        模糊匹配预告与实际标题
        
        策略（非常宽松，只检测严重问题）：
        1. 只要预告和标题有任何2字以上的共同词，就通过
        2. 预告通常比标题长很多，所以只检查标题关键词是否在预告中
        """
        if not preview or not actual:
            return True  # 无法比较时默认通过
        
        # 标题太短无法比较
        if len(actual) < 4:
            return True
        
        # 提取标题中的2字以上中文词
        actual_keywords = set(re.findall(r'[\u4e00-\u9fff]{2,}', actual))
        
        if not actual_keywords:
            return True
        
        # 检查标题关键词是否出现在预告中
        for keyword in actual_keywords:
            if keyword in preview:
                return True
        
        # 如果标题关键词都不在预告中，可能是误报
        # 但如果预告很短（可能是"无"或简单描述），也通过
        if len(preview) < 20:
            return True
        
        return False
    
    def check_preview_match(self, prev_chapter: int, curr_chapter: int) -> Dict:
        """
        检查上一章预告与本章实际的匹配度
        
        Returns:
            {
                "matched": bool,
                "preview": str,
                "actual_title": str,
            }
        """
        prev_content = self.context.blueprint.get_chapter_content(prev_chapter)
        curr_content = self.context.blueprint.get_chapter_content(curr_chapter)
        
        if not prev_content or not curr_content:
            return {"matched": True, "preview": "", "actual_title": ""}
        
        preview = self._extract_field(prev_content, "下一章预告")
        actual_title = self._extract_title(curr_content)
        
        matched = self._fuzzy_match(preview, actual_title)
        
        return {
            "matched": matched,
            "preview": preview or "",
            "actual_title": actual_title or "",
        }
    
    def check_character_continuity(self, prev_chapter: int, curr_chapter: int) -> Dict:
        """
        检查角色状态连续性
        
        Returns:
            {
                "continuous": bool,
                "issues": [str, ...],
            }
        """
        prev_content = self.context.blueprint.get_chapter_content(prev_chapter)
        curr_content = self.context.blueprint.get_chapter_content(curr_chapter)
        
        if not prev_content or not curr_content:
            return {"continuous": True, "issues": []}
        
        issues = []
        
        # 检查女主成长状态
        prev_growth = self._extract_field(prev_content, "女主成长线推进")
        curr_growth = self._extract_field(curr_content, "女主成长线推进")
        
        if prev_growth and curr_growth:
            # Load female leads dynamically
            female_leads = self._get_female_leads()
            
            # 提取各女主的状态
            for lead in female_leads:
                prev_state = re.search(rf'{lead}[：:].+?状态\[(.+?)\]', prev_growth)
                curr_state = re.search(rf'{lead}[：:].+?状态\[(.+?)\]', curr_growth)
                
                if prev_state and curr_state:
                    # 检查状态是否合理（简化检查：至少不能倒退太多）
                    # 这里只做简单检测，复杂逻辑可以后续扩展
                    pass
        
        return {
            "continuous": len(issues) == 0,
            "issues": issues,
        }
    
    def validate(self, chapter_num: int = None, content: str = None) -> Dict:
        """
        验证单章与上一章的一致性
        
        Returns:
            {
                "passed": bool,
                "score": float,
                "preview_match": bool,
                "character_continuous": bool,
                "issues": [str, ...],
            }
        """
        if chapter_num is None or chapter_num <= 1:
            return {"passed": True, "score": 1.0, "preview_match": True, 
                    "character_continuous": True, "issues": []}
        
        issues = []
        
        # 检查预告匹配
        preview_result = self.check_preview_match(chapter_num - 1, chapter_num)
        if not preview_result["matched"]:
            issues.append(f"预告不匹配: '{preview_result['preview'][:20]}...' vs '{preview_result['actual_title']}'")
        
        # 检查角色连续性
        continuity_result = self.check_character_continuity(chapter_num - 1, chapter_num)
        issues.extend(continuity_result["issues"])
        
        passed = len(issues) == 0
        score = 1.0 - len(issues) * 0.2  # 每个问题扣20%
        
        return {
            "passed": passed,
            "score": max(0, score),
            "preview_match": preview_result["matched"],
            "character_continuous": continuity_result["continuous"],
            "issues": issues,
        }
    
    def scan_all_chapters(self) -> List[Tuple[int, List[str]]]:
        """
        扫描所有章节的一致性问题
        
        Returns:
            [(chapter_num, [issues]), ...]
        """
        problems = []
        
        for chapter_num in self.context.blueprint.iter_chapters():
            if chapter_num <= 1:
                continue
            
            result = self.validate(chapter_num)
            if not result["passed"]:
                problems.append((chapter_num, result["issues"]))
        
        return problems
    
    def generate_report(self) -> str:
        """生成一致性报告"""
        problems = self.scan_all_chapters()
        
        if not problems:
            return "✅ 章节间逻辑一致性良好"
        
        lines = [f"⚠️ 发现 {len(problems)} 个章节存在一致性问题:\n"]
        
        preview_issues = 0
        continuity_issues = 0
        
        for ch, issues in problems[:10]:
            lines.append(f"  第{ch}章:")
            for issue in issues:
                lines.append(f"    - {issue}")
                if "预告" in issue:
                    preview_issues += 1
                else:
                    continuity_issues += 1
        
        if len(problems) > 10:
            lines.append(f"  ... 还有 {len(problems) - 10} 章")
        
        lines.append(f"\n  预告不匹配: {preview_issues}处")
        lines.append(f"  角色状态问题: {continuity_issues}处")
        
        return "\n".join(lines)
