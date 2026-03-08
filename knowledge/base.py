# knowledge/base.py
# -*- coding: utf-8 -*-
"""
动态世界知识库 - 从dynamic_world_knowledge_base.py重构

为保持向后兼容，此文件从原始文件导入主类
"""

# 直接从原始文件导入，保持完全兼容
# 后续可逐步将功能迁移到此模块
import sys
import os

# 添加父目录到路径以导入原始模块
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    from dynamic_world_knowledge_base import DynamicWorldKnowledgeBase
except ImportError:
    # 如果原文件不存在，提供一个占位类
    import logging
    
    class DynamicWorldKnowledgeBase:
        """占位类 - 原始实现已移除"""
        def __init__(self, *args, **kwargs):
            logging.warning("DynamicWorldKnowledgeBase: 使用占位实现")
            self.character_cache = {}
            self.setting_cache = {}
            self.plot_cache = {}
        
        def add_character(self, character):
            self.character_cache[character.id] = character
            return character.id
        
        def add_world_setting(self, setting):
            self.setting_cache[setting.id] = setting
            return setting.id
        
        def add_plot_event(self, event):
            self.plot_cache[event.id] = event
            return event.id
        
        def get_relevant_context(self, query, context_type="all", limit=10):
            return []
        
        def check_consistency(self, chapter_content, chapter_id):
            return []
