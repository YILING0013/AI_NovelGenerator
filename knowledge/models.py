# knowledge/models.py
# -*- coding: utf-8 -*-
"""知识库数据模型"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


class KnowledgeType(Enum):
    """知识类型"""
    CHARACTER = "character"
    WORLD_SETTING = "world_setting"
    PLOT_EVENT = "plot_event"
    ITEM = "item"
    LOCATION = "location"
    RELATIONSHIP = "relationship"
    SKILL = "skill"
    ORGANIZATION = "organization"


class ConsistencyLevel(Enum):
    """一致性级别"""
    CRITICAL = "critical"
    IMPORTANT = "important"
    NORMAL = "normal"
    FLEXIBLE = "flexible"


@dataclass
class CharacterProfile:
    """角色档案"""
    id: str
    name: str
    aliases: List[str] = field(default_factory=list)
    appearance: str = ""
    personality: str = ""
    background: str = ""
    cultivation_level: str = ""
    abilities: List[str] = field(default_factory=list)
    relationships: Dict[str, str] = field(default_factory=dict)
    items: List[str] = field(default_factory=list)
    first_appearance: int = 0
    last_appearance: int = 0
    consistency_level: ConsistencyLevel = ConsistencyLevel.IMPORTANT
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class WorldSetting:
    """世界设定"""
    id: str
    name: str
    category: str
    description: str = ""
    rules: List[str] = field(default_factory=list)
    sub_elements: List[str] = field(default_factory=list)
    related_elements: List[str] = field(default_factory=list)
    consistency_level: ConsistencyLevel = ConsistencyLevel.IMPORTANT
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class PlotEvent:
    """情节事件"""
    id: str
    title: str
    chapter_id: int
    timeline_position: int
    location: str = ""
    involved_characters: List[str] = field(default_factory=list)
    event_type: str = ""
    description: str = ""
    consequences: List[str] = field(default_factory=list)
    related_events: List[str] = field(default_factory=list)
    importance: int = 1
    consistency_level: ConsistencyLevel = ConsistencyLevel.NORMAL
    created_at: float = field(default_factory=time.time)


@dataclass
class ConsistencyIssue:
    """一致性问题"""
    id: str
    type: str
    severity: str
    description: str
    conflicting_elements: List[str]
    suggested_resolution: str = ""
    auto_fixable: bool = False
    detected_at: float = field(default_factory=time.time)
    resolved: bool = False
    resolved_at: Optional[float] = None


# === 新增：角色弧线系统（解决角色工具化问题） ===
@dataclass
class CharacterArc:
    """角色独立发展弧线"""
    character_id: str
    character_name: str
    personal_goal: str = ""           # 个人目标（不依赖主角）
    internal_conflict: str = ""       # 内心冲突
    growth_milestones: List[int] = field(default_factory=list)  # 成长里程碑章节
    solo_scene_count: int = 0         # 独立戏份数
    last_solo_chapter: int = 0        # 上次独立戏份章节
    relationship_depth: int = 1       # 与主角关系深度(1-5)
    arc_type: str = "support"         # 弧线类型: support/growth/redemption/tragedy
    
    def needs_solo_scene(self, current_chapter: int, min_interval: int = 10) -> bool:
        """判断是否需要独立戏份"""
        return current_chapter - self.last_solo_chapter >= min_interval


@dataclass  
class PlotPatternUsage:
    """剧情模式使用记录（解决套路化问题）"""
    pattern_id: str
    last_used_chapter: int
    total_uses: int = 0
    
    def can_use(self, current_chapter: int, cooldown: int) -> bool:
        """判断是否可以使用此模式"""
        return current_chapter - self.last_used_chapter >= cooldown


@dataclass
class VillainProfile:
    """反派档案（解决反派智商问题）"""
    villain_id: str
    name: str
    archetype: str  # tactical_genius/philosophical/tragic_hero/mastermind/rival/redeemable
    intelligence_level: int = 3  # 1-5智商等级
    has_backup_plan: bool = True
    motivation: str = ""
    weakness: str = ""
    respect_for_protagonist: bool = False  # 是否尊重主角
    
    def get_dialogue_style(self) -> str:
        """获取对话风格"""
        styles = {
            "tactical_genius": "冷静分析，从不说'不可能'",
            "philosophical": "引经据典，有理有据",
            "tragic_hero": "感慨悲鸣，偶尔流露善意",
            "mastermind": "神秘暗示，点到为止",
            "rival": "高傲但尊重对手",
            "redeemable": "言语矛盾，内心挣扎"
        }
        return styles.get(self.archetype, "普通对白")
