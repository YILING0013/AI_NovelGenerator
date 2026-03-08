# -*- coding: utf-8 -*-
"""
信息密度/注水检测器 (Density Checker)
检测文本中的注水段落：同义反复、无剧情环境描写、车轱辘话。
"""

import re
import logging
from typing import Dict, List, Any
from collections import Counter

logger = logging.getLogger(__name__)


class DensityChecker:
    """信息密度检测器"""
    
    # 注水特征模式
    FILLER_PATTERNS = {
        "同义反复": [
            r'([\u4e00-\u9fff]{2,4})(?:[\s，,。！？]{0,3})\1',  # 原词重复
            r'(?:非常|十分|极其|无比|万分)(?:[\s，]*(?:非常|十分|极其|无比|万分))',  # 程度副词堆叠
        ],
        "描写堆砌": [
            r'(?:四周|周围|身旁)(?:的)?(?:一切|万物)(?:都|皆)(?:变得|显得)',  # 泛化环境描写
            r'(?:仿佛|好似|犹如|宛如|恰似).*?(?:仿佛|好似|犹如|宛如|恰似)',  # 连续比喻
        ],
        "车轱辘话": [
            r'(?:正是因为如此|就是这样|由此可见|不言而喻|毋庸置疑)',  # 空洞连接词
        ],
    }
    
    # 段落最小有效信息占比阈值
    MIN_INFO_RATIO = 0.3
    
    def analyze(self, content: str) -> Dict[str, Any]:
        """
        分析文本的信息密度
        返回: {
            'filler_ratio': 注水比例,
            'filler_segments': [注水段落描述],
            'density_score': 信息密度评分(0-10),
            'details': {类型: [问题描述]}
        }
        """
        if not content:
            return {'filler_ratio': 0, 'filler_segments': [], 'density_score': 10, 'details': {}}
        
        paragraphs = [p.strip() for p in content.split('\n') if p.strip() and len(p.strip()) > 10]
        if not paragraphs:
            return {'filler_ratio': 0, 'filler_segments': [], 'density_score': 10, 'details': {}}
        
        filler_paragraphs = []
        details = {}
        
        for i, para in enumerate(paragraphs):
            issues = self._check_paragraph(para)
            if issues:
                for issue_type, issue_desc in issues:
                    if issue_type not in details:
                        details[issue_type] = []
                    details[issue_type].append(f"段落{i+1}: {issue_desc}")
                filler_paragraphs.append(i)
        
        # 检测段落间重复
        cross_para_issues = self._check_cross_paragraph_repetition(paragraphs)
        if cross_para_issues:
            details["跨段重复"] = cross_para_issues
            filler_paragraphs.extend([i for i in range(len(paragraphs)) 
                                     if any(f"段落{i+1}" in desc for desc in cross_para_issues)])
        
        filler_ratio = len(set(filler_paragraphs)) / max(len(paragraphs), 1)
        density_score = max(0, 10 - filler_ratio * 15)  # 注水越多分越低
        
        # 生成人类可读的注水段落描述
        filler_segments = []
        for issue_type, issues_list in details.items():
            for issue in issues_list[:2]:  # 每类最多显示2个
                filler_segments.append(f"[{issue_type}] {issue}")
        
        return {
            'filler_ratio': filler_ratio,
            'filler_segments': filler_segments[:5],  # 最多返回5条
            'density_score': round(density_score, 1),
            'details': details,
        }
    
    def _check_paragraph(self, para: str) -> List[tuple]:
        """检查单段落的注水问题"""
        issues = []
        
        for issue_type, patterns in self.FILLER_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, para)
                if matches:
                    sample = matches[0] if isinstance(matches[0], str) else str(matches[0])
                    issues.append((issue_type, f"'{sample[:15]}...' — {issue_type}"))
        
        # 检测纯环境描写段落（无对话、无动作、无情节推进）
        has_dialogue = '"' in para or '"' in para or '「' in para
        has_action = any(kw in para for kw in ['他', '她', '主角', '萧', '陈', '林',
                                                 '走', '跑', '打', '挥', '踏', '飞'])
        if not has_dialogue and not has_action and len(para) > 100:
            issues.append(("纯描写堆砌", f"'{para[:20]}...' — 长段落无对话/动作"))
        
        return issues
    
    def _check_cross_paragraph_repetition(self, paragraphs: List[str]) -> List[str]:
        """检测段落间的语义重复"""
        issues = []
        if len(paragraphs) < 2:
            return issues
        
        # 提取每段的关键词
        para_keywords = []
        for para in paragraphs:
            # 提取2-4字词组
            words = re.findall(r'[\u4e00-\u9fff]{2,4}', para)
            para_keywords.append(Counter(words))
        
        # 比较相邻段落
        for i in range(len(para_keywords) - 1):
            if not para_keywords[i] or not para_keywords[i+1]:
                continue
            
            # 计算Jaccard相似度
            common = set(para_keywords[i].keys()) & set(para_keywords[i+1].keys())
            union = set(para_keywords[i].keys()) | set(para_keywords[i+1].keys())
            if len(union) > 0:
                similarity = len(common) / len(union)
                if similarity > 0.6:
                    common_words = list(common)[:5]
                    issues.append(
                        f"段落{i+1}和段落{i+2}内容高度相似({similarity:.0%}): "
                        f"重复词[{'、'.join(common_words)}]"
                    )
        
        return issues
