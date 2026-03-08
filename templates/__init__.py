# templates/__init__.py
# -*- coding: utf-8 -*-
"""
模板创作引擎模块 - 从template_based_creation_engine.py拆分

使用方式:
    from templates import TemplateBasedCreationEngine
"""

from .models import TemplateType, SceneTemplate, PlotTemplate
from .library import TomatoTemplateLibrary
from .engine import TemplateBasedCreationEngine, SurpriseEventEngine

__all__ = [
    'TemplateType',
    'SceneTemplate',
    'PlotTemplate',
    'TomatoTemplateLibrary',
    'TemplateBasedCreationEngine',
    'SurpriseEventEngine'
]
