# templates/engine.py
# -*- coding: utf-8 -*-
"""模板创作引擎 - 从template_based_creation_engine.py提取"""

import random
import logging
from typing import Dict, List, Any, Optional
from .models import TemplateType, SceneTemplate, PlotTemplate
from .library import TomatoTemplateLibrary

logger = logging.getLogger(__name__)


class SurpriseEventEngine:
    """意外事件随机引擎"""
    
    def __init__(self, template_library: TomatoTemplateLibrary):
        self.template_library = template_library
        self.event_history: List[str] = []
        self.event_weights: Dict[str, float] = {}
        self._initialize_event_weights()
    
    def _initialize_event_weights(self):
        """初始化事件权重"""
        for event in self.template_library.surprise_events:
            self.event_weights[event["id"]] = 1.0
    
    def select_surprise_event(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """根据上下文选择合适的意外事件"""
        available_events = [
            e for e in self.template_library.surprise_events
            if e["id"] not in self.event_history[-5:]
        ]
        
        if not available_events:
            return None
        
        # 加权随机选择
        weights = [self.event_weights.get(e["id"], 1.0) for e in available_events]
        selected = random.choices(available_events, weights=weights, k=1)[0]
        
        self.event_history.append(selected["id"])
        return selected


class TemplateBasedCreationEngine:
    """模板化创作引擎主类"""
    
    def __init__(self):
        self.template_library = TomatoTemplateLibrary()
        self.surprise_engine = SurpriseEventEngine(self.template_library)
        logger.info("模板化创作引擎初始化完成")
    
    def select_template(self, novel_style: str = "mixed", difficulty: str = "normal") -> PlotTemplate:
        """选择合适的模板"""
        templates = list(self.template_library.templates.values())
        
        # 根据风格过滤
        if novel_style != "mixed":
            try:
                template_type = TemplateType(novel_style)
                templates = self.template_library.get_templates_by_type(template_type)
            except ValueError:
                pass
        
        # 根据难度过滤
        templates = [t for t in templates if t.difficulty == difficulty]
        
        if not templates:
            templates = list(self.template_library.templates.values())
        
        return random.choice(templates) if templates else None
    
    def generate_scene_content(self, scene: SceneTemplate, context: Dict[str, Any]) -> Dict[str, Any]:
        """生成场景内容"""
        # 决定是否添加意外事件
        add_surprise = random.random() < 0.3
        surprise_event = None
        
        if add_surprise:
            surprise_event = self.surprise_engine.select_surprise_event(context)
        
        return {
            "scene": scene,
            "context": context,
            "surprise_event": surprise_event,
            "prompt": self._build_scene_prompt(scene, context, surprise_event)
        }
    
    def _build_scene_prompt(self, scene: SceneTemplate, context: Dict[str, Any],
                           surprise_event: Optional[Dict] = None) -> str:
        """构建场景生成提示词"""
        prompt_parts = [
            f"场景：{scene.title}",
            f"描述：{scene.description}",
            f"情感强度：{scene.emotional_impact}"
        ]
        
        if scene.required_elements:
            prompt_parts.append(f"必需元素：{', '.join(scene.required_elements)}")
        
        if surprise_event:
            prompt_parts.append(f"意外事件：{surprise_event['name']}")
        
        return "\n".join(prompt_parts)
    
    def generate_plot_outline(self, template: PlotTemplate, 
                              customization: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """生成剧情大纲"""
        outline = []
        
        for scene in template.scenes:
            scene_content = self.generate_scene_content(scene, customization or {})
            outline.append(scene_content)
        
        return outline


def create_template_based_creation_engine() -> TemplateBasedCreationEngine:
    """创建模板化创作引擎实例"""
    return TemplateBasedCreationEngine()
