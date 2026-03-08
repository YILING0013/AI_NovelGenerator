# -*- coding: utf-8 -*-
"""
结构完整性验证器 (P1)
检查蓝图章节是否包含所有必需的模块
"""

import re
from typing import Dict, List
from .base import BaseValidator


class StructureValidator(BaseValidator):
    """检查蓝图结构完整性"""
    
    name = "structure_validator"
    
    # 必需的模块列表
    REQUIRED_MODULES = [
        "基础元信息",
        "张力与冲突",
        "匠心思维应用",
        "伏笔与信息差",
        "暧昧与修罗场",
        "剧情精要",
        "衔接设计",
    ]
    
    # 可选模块（结局章节可能没有）
    OPTIONAL_IN_ENDING = [
        "【多层次悬念体系】",  # 结局章节可能无悬念
    ]
    
    def validate(self, chapter_num: int = None, content: str = None) -> Dict:
        """
        验证单章结构完整性
        
        Returns:
            {
                "passed": bool,
                "score": float (0-1),
                "missing_modules": [module_name, ...],
                "present_modules": [module_name, ...],
                "completeness": float (0-1)
            }
        """
        if content is None:
            if chapter_num is None:
                return {"passed": True, "score": 1.0, "missing_modules": [], 
                        "present_modules": [], "completeness": 1.0}
            content = self.context.blueprint.get_chapter_content(chapter_num)
        
        if not content:
            return {"passed": False, "score": 0.0, "missing_modules": self.REQUIRED_MODULES.copy(),
                    "present_modules": [], "completeness": 0.0}
        
        present = []
        missing = []
        
        for module in self.REQUIRED_MODULES:
            core_name = module

            # 检查多种可能的格式:
            # 1. ## 1. 基础元信息
            # 2. **基础元信息**
            # 3. 基础元信息：
            # 4. 【基础元信息】
            patterns = [
                module,
                f"【{core_name}】",
                core_name,
                f"**{core_name}**"
            ]
            
            found = any(p in content for p in patterns)
            
            if found:
                present.append(core_name)
            else:
                missing.append(core_name)
        
        completeness = len(present) / len(self.REQUIRED_MODULES)
        
        # 90%以上算通过
        passed = completeness >= 0.9
        
        return {
            "passed": passed,
            "score": completeness,
            "missing_modules": missing,
            "present_modules": present,
            "completeness": completeness
        }
    
    def scan_all_chapters(self) -> Dict[int, Dict]:
        """
        扫描所有章节的结构完整性
        
        Returns:
            {chapter_num: {"completeness": float, "missing": [...]}, ...}
        """
        results = {}
        
        for chapter_num in self.context.blueprint.iter_chapters():
            result = self.validate(chapter_num)
            # 只记录不完整的章节
            if result["completeness"] < 1.0:
                results[chapter_num] = {
                    "completeness": result["completeness"],
                    "missing": result["missing_modules"]
                }
        
        return results
    
    def generate_report(self) -> str:
        """生成结构完整性报告"""
        incomplete = self.scan_all_chapters()
        
        if not incomplete:
            return "✅ 所有章节结构完整"
        
        # 按完整度分组
        severe = []  # < 80%
        moderate = []  # 80-90%
        minor = []  # 90-100%
        
        for ch, info in incomplete.items():
            if info["completeness"] < 0.8:
                severe.append((ch, info))
            elif info["completeness"] < 0.9:
                moderate.append((ch, info))
            else:
                minor.append((ch, info))
        
        lines = [f"⚠️ 发现 {len(incomplete)} 个章节结构不完整:\n"]
        
        if severe:
            lines.append(f"  🔴 严重缺失(<80%): {len(severe)}章")
            for ch, info in severe[:5]:
                lines.append(f"      第{ch}章: 缺少 {', '.join(info['missing'][:3])}...")
        
        if moderate:
            lines.append(f"  🟡 中度缺失(80-90%): {len(moderate)}章")
        
        if minor:
            lines.append(f"  🟢 轻度缺失(>90%): {len(minor)}章")
        
        # 统计最常缺失的模块
        missing_counts = {}
        for ch, info in incomplete.items():
            for m in info["missing"]:
                missing_counts[m] = missing_counts.get(m, 0) + 1
        
        if missing_counts:
            lines.append("\n  最常缺失的模块:")
            for m, count in sorted(missing_counts.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"    - {m}: {count}章")
        
        return "\n".join(lines)
