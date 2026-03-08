# -*- coding: utf-8 -*-
"""
分析器模块
"""

from .chapter_quality import (
    ChapterQualityAnalyzer,
    QualityScore,
    analyze_chapters
)

__all__ = [
    "ChapterQualityAnalyzer",
    "QualityScore", 
    "analyze_chapters"
]
