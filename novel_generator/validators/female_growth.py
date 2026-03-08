# -*- coding: utf-8 -*-
"""
女主成长线验证器
继承自BaseValidator，完全依赖ValidationContext和StoryRulesConfig
"""
from typing import Dict, List
from novel_generator.validators.base import BaseValidator, ValidationContext
from novel_generator.core.rules import get_rules_config


class FemaleGrowthValidator(BaseValidator):
    def __init__(self, context: ValidationContext):
        super().__init__(context)
        self.rules = get_rules_config()
        
    def validate(self) -> Dict:
        results = {
            "name": "女主成长线验证",
            "passed": True,
            "issues": [],
            "warnings": [],
            "details": {}
        }
        
        milestones = self.rules.female_milestones
        if not milestones:
            results["warnings"].append("未配置女主成长里程碑规则")
            return results
            
        total_checks = 0
        passed_checks = 0
        
        for chapter_num, info in milestones.items():
            chapter_content = self.context.get_chapter_content(chapter_num)
            lead_name = info.get("lead", "未知")
            milestone_desc = info.get("milestone", "")
            
            # 基础检查逻辑：章节是否存在
            if not chapter_content:
                results["warnings"].append(f"第{chapter_num}章蓝图缺失，无法验证【{lead_name}】成长节点")
                continue
                
            total_checks += 1
            
            # 关键词匹配逻辑
            keywords = [lead_name]
            # 简单提取描述中的名词作为关键词（依然保持简单的逻辑，后续可对接NLP）
            desc_keywords = [k for k in milestone_desc.split("，") if len(k) > 1]
            keywords.extend(desc_keywords)
            
            matches = [k for k in keywords if k in chapter_content]
            score = len(matches) / len(keywords) * 100 if keywords else 0
            
            if score < 20:  # 阈值20%
                results["issues"].append(f"第{chapter_num}章未检测到【{lead_name}】的成长节点：{milestone_desc}")
            else:
                passed_checks += 1
                
        if total_checks > 0:
            pass_rate = passed_checks / total_checks
            results["score"] = pass_rate * 100
            results["passed"] = pass_rate >= 0.5  # 50%通过率算及格
            
        return results
