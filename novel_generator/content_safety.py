# -*- coding: utf-8 -*-
"""
敏感内容过滤器 (Content Safety Filter)
基于关键词的轻量级敏感内容检测，支持武侠/仙侠白名单。
"""

import re
import logging
from typing import Dict, List, Any, Set

logger = logging.getLogger(__name__)


class ContentSafetyFilter:
    """轻量级敏感内容过滤器"""
    
    # 敏感内容类别及关键词
    SENSITIVE_CATEGORIES = {
        "色情描写": {
            "keywords": [
                "赤裸", "肌肤相亲", "娇喘", "呻吟", "酥胸",
                "玉体", "春光乍泄", "衣衫尽褪", "交缠", "抚摸着她的",
            ],
            "risk_weight": 3,
        },
        "过度暴力": {
            "keywords": [
                "剥皮", "挖眼", "碎尸", "虐杀", "活剐",
                "肠子流出", "血肉模糊", "惨叫声持续",
            ],
            "risk_weight": 2,
            # 武侠/仙侠中合理的战斗描写白名单
            "whitelist_context": ["战斗", "交战", "厮杀", "决斗", "对决"],
        },
        "政治敏感": {
            "keywords": [
                "领导人", "政党", "政权更迭", "颠覆",
            ],
            "risk_weight": 5,
        },
    }
    
    def __init__(self, custom_whitelist: List[str] = None):
        """
        初始化过滤器
        :param custom_whitelist: 自定义白名单关键词
        """
        self.custom_whitelist = set(custom_whitelist or [])
    
    def check_content(self, content: str) -> Dict[str, Any]:
        """
        检查内容的敏感度
        返回: {
            'risk_level': 'safe'/'medium'/'high',
            'risk_score': 0-10,
            'issues': [问题描述],
            'details': {类别: [匹配位置]}
        }
        """
        if not content:
            return {'risk_level': 'safe', 'risk_score': 0, 'issues': [], 'details': {}}
        
        total_score = 0
        issues = []
        details = {}
        
        for category, config in self.SENSITIVE_CATEGORIES.items():
            keywords = config["keywords"]
            weight = config["risk_weight"]
            whitelist_ctx = config.get("whitelist_context", [])
            
            hits = []
            for kw in keywords:
                if kw in self.custom_whitelist:
                    continue  # 跳过白名单词
                
                positions = [m.start() for m in re.finditer(re.escape(kw), content)]
                for pos in positions:
                    # 检查上下文是否在白名单范围内
                    context_start = max(0, pos - 50)
                    context_end = min(len(content), pos + len(kw) + 50)
                    context = content[context_start:context_end]
                    
                    is_whitelisted = any(wctx in context for wctx in whitelist_ctx)
                    if not is_whitelisted:
                        hits.append({
                            "keyword": kw,
                            "position": pos,
                            "context": context.replace('\n', ' ')[:60]
                        })
            
            if hits:
                details[category] = hits
                hit_score = len(hits) * weight
                total_score += hit_score
                issues.append(
                    f"[{category}] 检测到{len(hits)}处敏感内容 "
                    f"(如: '{hits[0]['keyword']}')"
                )
        
        # 判定风险等级
        if total_score >= 10:
            risk_level = 'high'
        elif total_score >= 5:
            risk_level = 'medium'
        else:
            risk_level = 'safe'
        
        return {
            'risk_level': risk_level,
            'risk_score': min(total_score, 10),
            'issues': issues,
            'details': details,
        }
