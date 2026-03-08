# -*- coding: utf-8 -*-
"""
验证器基类与上下文定义
v2.0: 引入IndexedBlueprint，实现真正的高效懒加载
"""
import os
from typing import Dict, List, Optional, Set
from abc import ABC, abstractmethod
from novel_generator.core.blueprint import get_blueprint, IndexedBlueprint


class ValidationContext:
    """验证上下文：共享资源容器，代理访问IndexedBlueprint"""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.architecture_path = os.path.join(filepath, "Novel_architecture.txt")
        # 委托核心蓝图层
        self.blueprint: IndexedBlueprint = get_blueprint(filepath)

    @property
    def blueprint_text(self) -> str:
        # 为了兼容性，不建议直接获取全文，这里返回空或警告
        # 实际业务中应该尽量避免获取全文
        return ""
        
    def get_chapter_title(self, chapter_num: int) -> str:
        return self.blueprint.get_chapter_title(chapter_num)
        
    def get_chapter_content(self, chapter_num: int) -> str:
        return self.blueprint.get_chapter_content(chapter_num)

    def get_existing_chapters(self) -> Set[int]:
        return set(self.blueprint.iter_chapters())


class BaseValidator(ABC):
    """验证器基类"""
    
    def __init__(self, context: ValidationContext):
        self.context = context
        
    @abstractmethod
    def validate(self) -> Dict:
        """
        执行验证
        Returns:
            Dict: {
                "name": "验证项名称",
                "passed": True/False,
                "score": 0-100 (可选),
                "issues": ["问题1", "问题2"],
                "warnings": ["警告1"]
            }
        """
        pass
