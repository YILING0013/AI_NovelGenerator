# word_count_config.py
# -*- coding: utf-8 -*-
"""
智能字数控制配置文件
管理字数控制的默认参数和策略
"""

# 默认字数控制配置
DEFAULT_WORD_COUNT_CONFIG = {
    # 基础设置
    "enabled": True,                    # 是否启用智能字数控制
    "tolerance": 0.05,                 # 字数容差范围（5%）
    "max_retries": 5,                  # 最大重试次数

    # 质量控制
    "quality_priority": True,           # 优先保证内容质量
    "auto_adjust_temperature": True,    # 自动调整温度参数以获得更稳定的输出

    # 扩写策略
    "expansion_strategies": [
        "对话扩展", "心理描写深化", "环境细节丰富",
        "动作细节描写", "感官体验增强", "回忆插入",
        "伏笔细节补充", "情感变化细化"
    ],

    # 缩写策略
    "compression_strategies": [
        "保留核心情节", "简化描述", "合并次要情节",
        "精简对话", "压缩环境描写", "删除冗余"
    ],

    # 针对不同字数的特殊设置
    "chapter_configs": {
        "short": {     # < 2000字
            "tolerance": 0.08,           # 短章节允许更大容差
            "max_retries": 3,            # 减少重试次数
            "temperature_adjustment": 0.6 # 降低温度提高稳定性
        },
        "medium": {    # 2000-4000字
            "tolerance": 0.05,           # 标准容差
            "max_retries": 5,            # 标准重试次数
            "temperature_adjustment": 0.7 # 标准温度
        },
        "long": {      # > 4000字
            "tolerance": 0.03,           # 长章节要求更精确
            "max_retries": 7,            # 增加重试次数
            "temperature_adjustment": 0.6 # 降低温度提高稳定性
        }
    }
}

def get_word_count_config(target_words: int) -> dict:
    """
    根据目标字数获取最佳配置

    Args:
        target_words: 目标字数

    Returns:
        dict: 字数控制配置
    """
    config = DEFAULT_WORD_COUNT_CONFIG.copy()

    # 根据字数选择合适的配置
    if target_words < 2000:
        config.update(config["chapter_configs"]["short"])
    elif target_words <= 4000:
        config.update(config["chapter_configs"]["medium"])
    else:
        config.update(config["chapter_configs"]["long"])

    return config

def get_optimal_temperature(target_words: int, base_temperature: float) -> float:
    """
    根据目标字数获取最佳温度设置

    Args:
        target_words: 目标字数
        base_temperature: 基础温度

    Returns:
        float: 调整后的温度
    """
    config = get_word_count_config(target_words)
    return config.get("temperature_adjustment", base_temperature)

def calculate_word_count_tolerance(target_words: int) -> float:
    """
    计算字数容差

    Args:
        target_words: 目标字数

    Returns:
        float: 容差值
    """
    config = get_word_count_config(target_words)
    return int(target_words * config["tolerance"])

def is_word_count_achieved(actual_words: int, target_words: int, tolerance: float = None) -> bool:
    """
    检查字数是否达标

    Args:
        actual_words: 实际字数
        target_words: 目标字数
        tolerance: 自定义容差（可选）

    Returns:
        bool: 是否达标
    """
    if tolerance is None:
        tolerance = get_word_count_config(target_words)["tolerance"]

    deviation = abs(actual_words - target_words) / target_words
    return deviation <= tolerance