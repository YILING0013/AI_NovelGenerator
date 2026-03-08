# templates/library.py
# -*- coding: utf-8 -*-
"""模板库 - 从template_based_creation_engine.py提取"""

import logging
from typing import Dict, List, Any
from .models import TemplateType, SceneTemplate, PlotTemplate

logger = logging.getLogger(__name__)


class TomatoTemplateLibrary:
    """番茄平台模板库"""
    
    def __init__(self):
        self.templates: Dict[str, PlotTemplate] = {}
        self.surprise_events: List[Dict[str, Any]] = []
        self.character_archetypes: Dict[str, Dict[str, Any]] = {}
        self._initialize_library()
    
    def _initialize_library(self):
        """初始化模板库"""
        self._create_classic_templates()
        self._create_surprise_events()
        self._create_character_archetypes()
    
    def _create_classic_templates(self):
        """创建经典模板"""
        # 复仇模板
        self.templates["revenge_basic"] = PlotTemplate(
            template_id="revenge_basic",
            name="经典复仇",
            type=TemplateType.REVENGE,
            scenes=[
                SceneTemplate("r1", "屈辱开场", "主角受辱", 0.8),
                SceneTemplate("r2", "获得机缘", "得到金手指", 0.9),
                SceneTemplate("r3", "初步反击", "小规模报复", 0.85)
            ],
            shuangdian_points=[2, 5, 10],
            tags=["复仇", "爽文", "逆袭"]
        )
        
        # 重生模板
        self.templates["rebirth_basic"] = PlotTemplate(
            template_id="rebirth_basic",
            name="重生逆袭",
            type=TemplateType.REBIRTH,
            scenes=[
                SceneTemplate("rb1", "重生觉醒", "回到过去", 0.9),
                SceneTemplate("rb2", "布局先机", "利用前世记忆", 0.8),
                SceneTemplate("rb3", "改写命运", "避免悲剧", 0.85)
            ],
            shuangdian_points=[1, 3, 8],
            tags=["重生", "先知", "逆袭"]
        )
        
        # 系统模板
        self.templates["system_basic"] = PlotTemplate(
            template_id="system_basic",
            name="系统流",
            type=TemplateType.SYSTEM,
            scenes=[
                SceneTemplate("s1", "系统绑定", "获得系统", 0.9),
                SceneTemplate("s2", "首次任务", "完成任务获奖励", 0.85),
                SceneTemplate("s3", "实力飙升", "快速成长", 0.8)
            ],
            shuangdian_points=[1, 5, 15],
            tags=["系统", "任务", "升级"]
        )
    
    def _create_surprise_events(self):
        """创建意外事件库"""
        self.surprise_events = [
            {"id": "se1", "name": "神秘传承", "impact": 0.9, "type": "opportunity"},
            {"id": "se2", "name": "强敌来袭", "impact": 0.8, "type": "challenge"},
            {"id": "se3", "name": "贵人相助", "impact": 0.7, "type": "support"},
            {"id": "se4", "name": "意外发现", "impact": 0.6, "type": "discovery"},
            {"id": "se5", "name": "背叛危机", "impact": 0.85, "type": "crisis"}
        ]
    
    def _create_character_archetypes(self):
        """创建角色原型"""
        self.character_archetypes = {
            "protagonist": {"traits": ["坚韧", "智慧", "潜力无限"]},
            "mentor": {"traits": ["神秘", "强大", "引导者"]},
            "rival": {"traits": ["傲慢", "天才", "竞争者"]},
            "villain": {"traits": ["阴险", "强大", "野心勃勃"]}
        }
        
        # === 新增：剧情模式库（解决套路化问题） ===
        self.plot_patterns = {
            "crisis_reversal": {
                "name": "危机逆转",
                "description": "主角陷入困境后绝地反击",
                "cooldown": 3  # 3章内不重复
            },
            "strategic_retreat": {
                "name": "战略撤退", 
                "description": "主角主动撤退保存实力",
                "cooldown": 5
            },
            "pyrrhic_victory": {
                "name": "惨胜",
                "description": "虽然胜利但付出重大代价",
                "cooldown": 5
            },
            "unexpected_ally": {
                "name": "意外盟友",
                "description": "敌人变盟友或意外获得帮助",
                "cooldown": 5
            },
            "moral_dilemma": {
                "name": "道德困境",
                "description": "面临两难选择，无论怎样都有牺牲",
                "cooldown": 4
            },
            "false_victory": {
                "name": "虚假胜利",
                "description": "表面胜利实际落入陷阱",
                "cooldown": 6
            },
            "sacrifice_play": {
                "name": "牺牲打",
                "description": "配角牺牲自己成全主角",
                "cooldown": 8
            },
            "intelligence_war": {
                "name": "智斗",
                "description": "以智取胜而非武力",
                "cooldown": 3
            },
            "negotiation": {
                "name": "谈判",
                "description": "通过谈判解决冲突",
                "cooldown": 5
            },
            "hidden_enemy": {
                "name": "隐藏敌人",
                "description": "盟友中有内奸或敌方有内应",
                "cooldown": 6
            },
            "power_seal": {
                "name": "封印力量",
                "description": "主角被封印力量需另辟蹊径",
                "cooldown": 5
            },
            "role_reversal": {
                "name": "角色反转",
                "description": "弱者变强，强者落难",
                "cooldown": 4
            }
        }
        
        # === 新增：反派类型库（解决反派智商问题） ===
        self.villain_archetypes = {
            "tactical_genius": {
                "name": "战术家",
                "traits": ["善于谋划", "多步棋局", "从不轻敌"],
                "dialogue_style": "冷静分析型"
            },
            "philosophical": {
                "name": "理念者",
                "traits": ["有自己的信仰", "不认为自己是恶人", "有理想"],
                "dialogue_style": "布道说教型"
            },
            "tragic_hero": {
                "name": "堕落英雄",
                "traits": ["有悲惨过往", "曾经是正派", "被逼无奈"],
                "dialogue_style": "感慨悲鸣型"
            },
            "mastermind": {
                "name": "幕后黑手",
                "traits": ["操控一切", "从不亲自出手", "多重身份"],
                "dialogue_style": "神秘暗示型"
            },
            "rival": {
                "name": "宿敌",
                "traits": ["与主角势均力敌", "互相尊重", "追求超越"],
                "dialogue_style": "高傲挑战型"
            },
            "redeemable": {
                "name": "可救赎者",
                "traits": ["内心有善念", "可能被感化", "有底线"],
                "dialogue_style": "矛盾挣扎型"
            }
        }
        
        # 记录使用历史避免重复
        self.pattern_history: List[str] = []
        self.villain_history: List[str] = []
    
    def get_template(self, template_id: str) -> PlotTemplate:
        """获取模板"""
        return self.templates.get(template_id)
    
    def get_templates_by_type(self, template_type: TemplateType) -> List[PlotTemplate]:
        """按类型获取模板"""
        return [t for t in self.templates.values() if t.type == template_type]
