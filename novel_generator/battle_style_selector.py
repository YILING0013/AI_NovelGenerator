# novel_generator/battle_style_selector.py
# -*- coding: utf-8 -*-
"""
战斗风格策略池选择器
确保战斗描写多样化，同一风格不连续出现超过2次
"""
import os
import json
import logging
from prompt_definitions import BATTLE_STYLE_POOL

logging.basicConfig(level=logging.INFO)


def get_battle_style(filepath: str, chapter_num: int) -> dict:
    """
    根据章节号选择战斗风格，确保同一风格不连续出现超过2次
    
    Args:
        filepath: 小说项目目录
        chapter_num: 当前章节号
    
    Returns:
        选中的战斗风格字典
    """
    history_file = os.path.join(filepath, "battle_style_history.json")
    
    # 读取历史
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except (json.JSONDecodeError, IOError):
            history = []
    
    # 获取最近2次使用的风格
    recent_styles = [h['style'] for h in history[-2:]] if len(history) >= 2 else []
    
    # 如果最近2次是同一风格，排除该风格
    available_styles = BATTLE_STYLE_POOL.copy()
    if len(recent_styles) == 2 and recent_styles[0] == recent_styles[1]:
        excluded_style = recent_styles[0]
        available_styles = [s for s in available_styles if s['name'] != excluded_style]
        logging.info(f"战斗风格 '{excluded_style}' 已连续使用2次，本次排除")
    
    # 轮询选择 (基于章节号取模)
    selected = available_styles[chapter_num % len(available_styles)]
    
    # 记录历史
    history.append({"chapter": chapter_num, "style": selected['name']})
    # 只保留最近20条记录
    history = history[-20:]
    
    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logging.warning(f"无法保存战斗风格历史: {e}")
    
    logging.info(f"第{chapter_num}章选择战斗风格: {selected['name']}")
    return selected


def get_battle_style_prompt(style: dict) -> str:
    """
    将战斗风格转换为提示词片段
    
    Args:
        style: 战斗风格字典
    
    Returns:
        可插入提示词的文本片段
    """
    return f"""
【本章战斗风格指引】
风格类型：{style['name']}
风格说明：{style['description']}
写作要点：{style['writing_guide']}
关键词参考：{', '.join(style['keywords'])}
⚠️ 本章如有战斗场景，请严格按照上述风格进行描写，避免使用其他风格的描写模式。
"""


def reset_battle_history(filepath: str):
    """重置战斗风格历史（用于新小说开始时）"""
    history_file = os.path.join(filepath, "battle_style_history.json")
    if os.path.exists(history_file):
        os.remove(history_file)
        logging.info("战斗风格历史已重置")
