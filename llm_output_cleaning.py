# -*- coding: utf-8 -*-
"""轻量 LLM 输出清理工具。"""
import re


def remove_think_tags(text: str) -> str:
    """移除 <think>...</think> 包裹的内容。"""
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
