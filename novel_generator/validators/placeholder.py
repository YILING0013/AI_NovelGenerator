# -*- coding: utf-8 -*-
"""
占位符检测器 (P0)
检测蓝图中未填写的占位符，如 #X、TODO、待补充等
"""

import re
from typing import Dict, List, Tuple
from .base import BaseValidator


class PlaceholderDetector(BaseValidator):
    """检测蓝图中的占位符"""
    
    name = "placeholder_detector"
    
    # 占位符模式及其描述
    # 注意：XXX已移除，因为它可能出现在SQL示例等正文内容中
    PLACEHOLDER_PATTERNS = [
        (r'伏笔#X', "未编号伏笔"),
        (r'#X\]', "未编号引用"),
        (r'\[TODO\]', "待办标记"),
        (r'第X章(?!节)', "未填章节号"),  # 排除"第X章节"这种合理表述
        (r'待补充', "内容缺失标记"),
        (r'待定', "待定标记"),
        (r'\?\?\?', "问号占位符"),
        (r'TBD', "TBD标记"),
    ]
    
    def validate(self, chapter_num: int = None, content: str = None) -> Dict:
        """
        验证单章内容中的占位符
        
        Returns:
            {
                "passed": bool,
                "score": float (0-1),
                "placeholders": [(pattern, description, count), ...],
                "total_count": int
            }
        """
        if content is None:
            if chapter_num is None:
                return {"passed": True, "score": 1.0, "placeholders": [], "total_count": 0}
            content = self.context.blueprint.get_chapter_content(chapter_num)
        
        if not content:
            return {"passed": True, "score": 1.0, "placeholders": [], "total_count": 0}
        
        found_placeholders = []
        total_count = 0
        
        for pattern, description in self.PLACEHOLDER_PATTERNS:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                count = len(matches)
                found_placeholders.append((pattern, description, count))
                total_count += count
        
        passed = total_count == 0
        # 每个占位符扣5分，最多扣到0
        score = max(0, 1.0 - total_count * 0.05)
        
        return {
            "passed": passed,
            "score": score,
            "placeholders": found_placeholders,
            "total_count": total_count
        }
    
    def scan_all_chapters(self) -> Dict[int, List[Tuple[str, str, int]]]:
        """
        扫描所有章节的占位符
        
        Returns:
            {chapter_num: [(pattern, description, count), ...], ...}
        """
        results = {}
        
        for chapter_num in self.context.blueprint.iter_chapters():
            result = self.validate(chapter_num)
            if result["total_count"] > 0:
                results[chapter_num] = result["placeholders"]
        
        return results
    
    def generate_report(self) -> str:
        """生成占位符检测报告"""
        all_placeholders = self.scan_all_chapters()
        
        if not all_placeholders:
            return "✅ 未发现占位符"
        
        lines = [f"⚠️ 发现 {len(all_placeholders)} 个章节包含占位符:\n"]
        
        # 按占位符类型汇总
        type_counts = {}
        for chapter_num, placeholders in all_placeholders.items():
            for pattern, desc, count in placeholders:
                if desc not in type_counts:
                    type_counts[desc] = {"count": 0, "chapters": []}
                type_counts[desc]["count"] += count
                type_counts[desc]["chapters"].append(chapter_num)
        
        for desc, info in sorted(type_counts.items(), key=lambda x: -x[1]["count"]):
            chapters_str = ", ".join(map(str, info["chapters"][:10]))
            if len(info["chapters"]) > 10:
                chapters_str += f" ... 等{len(info['chapters'])}章"
            lines.append(f"  - {desc}: {info['count']}处 (章节: {chapters_str})")
        
        return "\n".join(lines)
