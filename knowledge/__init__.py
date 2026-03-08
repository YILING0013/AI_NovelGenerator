# knowledge/__init__.py
# -*- coding: utf-8 -*-
"""
知识库模块 - 从dynamic_world_knowledge_base.py拆分

使用方式:
    from knowledge import DynamicWorldKnowledgeBase
"""

from .models import (
    KnowledgeType,
    ConsistencyLevel,
    CharacterProfile,
    WorldSetting,
    PlotEvent,
    ConsistencyIssue
)
from .base import DynamicWorldKnowledgeBase

__all__ = [
    'KnowledgeType',
    'ConsistencyLevel',
    'CharacterProfile',
    'WorldSetting',
    'PlotEvent',
    'ConsistencyIssue',
    'DynamicWorldKnowledgeBase'
]
