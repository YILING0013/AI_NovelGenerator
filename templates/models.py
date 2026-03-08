# templates/models.py
# -*- coding: utf-8 -*-
"""模板数据模型"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple


class TemplateType(Enum):
    """模板类型"""
    REVENGE = "revenge"
    REBIRTH = "rebirth"
    SYSTEM = "system"
    AUCTION = "auction"
    SECRET_REALM = "secret_realm"
    TOURNAMENT = "tournament"
    UNDERCOVER = "undercover"
    BREAKTHROUGH = "breakthrough"


@dataclass
class SceneTemplate:
    """场景模板"""
    scene_id: str
    title: str
    description: str
    emotional_impact: float
    required_elements: List[str] = field(default_factory=list)
    optional_elements: List[str] = field(default_factory=list)
    word_count_range: Tuple[int, int] = (500, 1500)


@dataclass
class PlotTemplate:
    """剧情模板"""
    template_id: str
    name: str
    type: TemplateType
    scenes: List[SceneTemplate] = field(default_factory=list)
    shuangdian_points: List[int] = field(default_factory=list)
    total_word_count: Tuple[int, int] = (2000, 6000)
    tags: List[str] = field(default_factory=list)
    difficulty: str = "normal"
