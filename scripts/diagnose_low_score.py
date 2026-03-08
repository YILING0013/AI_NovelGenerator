#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""诊断章节问题 - 分析高分章节为何被检测为有问题"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from batch_quality_check import load_novel_directory
from quality_checker import QualityChecker

chapters = load_novel_directory('wxhyj/Novel_directory.txt')
checker = QualityChecker()

# 分析第1章
for ch in chapters:
    if ch['chapter_number'] == 1:
        report = checker.check_chapter_quality(ch['content'], {'chapter_number': 1})
        print(f'第1章评分: {report.overall_score:.1f}')
        print(f'质量等级: {report.quality_level}')
        print('\n问题列表:')
        for issue in report.issues:
            print(f'  - [{issue.severity}] {issue.description}')
        print('\n指标详情:')
        for m in report.metrics:
            name = m.get('name', 'unknown')
            score = m.get('score', 0)
            weight = m.get('weight', 0)
            desc = m.get('description', '')
            print(f'  - {name}: {score:.1f} (权重 {weight}) | {desc}')
        
        print('\n' + '='*50)
        print('章节内容前500字:')
        print(ch['content'][:500])
        break
