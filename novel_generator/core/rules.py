# -*- coding: utf-8 -*-
"""
故事规则配置管理
提供业务规则的统一访问接口（单例模式）
"""

import os
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class StoryRulesConfig:
    """故事规则配置加载器（单例模式）"""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        # 尝试查找配置文件的路径
        # 假设当前文件在 novel_generator/core/rules.py
        # 配置在 config/story_rules.json (root/config)
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(os.path.dirname(current_dir)) # novel_generator -> root
        
        possible_paths = [
            os.path.join(root_dir, "config", "story_rules.json"),
            os.path.join(os.getcwd(), "config", "story_rules.json"),
        ]
        
        for config_path in possible_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        self._config = json.load(f)
                    logger.info(f"成功加载故事规则配置: {config_path}")
                    return
                except Exception as e:
                    logger.error(f"加载配置文件失败: {e}")
        
        # 如果无法加载，使用空配置
        logger.warning("未找到story_rules.json，使用空配置")
        self._config = {}
    
    @property
    def major_reversals(self) -> Dict[int, str]:
        """获取重大反转章节映射"""
        return {int(k): v for k, v in self._config.get("major_reversal_chapters", {}).items()}
    
    @property
    def female_milestones(self) -> Dict[int, dict]:
        """获取女主成长里程碑"""
        return {int(k): v for k, v in self._config.get("female_lead_milestones", {}).items()}
    
    @property
    def foreshadowing(self) -> Dict[int, dict]:
        """获取伏笔要求"""
        return {int(k): v for k, v in self._config.get("foreshadowing_requirements", {}).items()}
    
    @property
    def romance(self) -> Dict[int, dict]:
        """获取暧昧场景建议"""
        return {int(k): v for k, v in self._config.get("romance_suggestions", {}).items()}


# 全局配置实例
_rules_config = None

def get_rules_config() -> StoryRulesConfig:
    """获取规则配置单例"""
    global _rules_config
    if _rules_config is None:
        _rules_config = StoryRulesConfig()
    return _rules_config

# Alias for consistent naming
get_story_rules = get_rules_config
