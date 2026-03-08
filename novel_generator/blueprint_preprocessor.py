"""
蓝图预处理器模块 (P1优化)

功能：
1. 解析蓝图中的突破事件
2. 与修为约束映射表比对
3. 检测并标注战斗风格
4. 生成预处理报告
"""

import re
import logging
import json
import os
from typing import Dict, List, Tuple, Optional

# 导入修为约束映射
try:
    from prompt_definitions import CULTIVATION_PROGRESS_MAP, BATTLE_STYLE_POOL
    CULTIVATION_MAP_AVAILABLE = True
except ImportError:
    CULTIVATION_MAP_AVAILABLE = False
    CULTIVATION_PROGRESS_MAP = {}
    BATTLE_STYLE_POOL = []

# 突破关键词列表
BREAKTHROUGH_KEYWORDS = [
    "突破", "晋级", "进阶", "跨入", "踏入", "迈入", "升级",
    "境界提升", "修为暴涨", "实力飙升", "脱胎换骨"
]

# 战斗关键词列表
BATTLE_KEYWORDS = [
    "战斗", "交手", "对战", "厮杀", "杀敌", "击败", "反杀",
    "妖兽", "敌人", "围攻", "伏击", "决战", "比试", "擂台"
]


def detect_breakthrough_events(blueprint_content: str) -> List[Dict]:
    """
    检测蓝图中的突破事件
    
    Args:
        blueprint_content: 蓝图文本内容
        
    Returns:
        突破事件列表，每个事件包含章节号、关键词、上下文
    """
    events = []
    
    # 按章节分割
    chapter_pattern = r'第(\d+)章[：:](.*?)(?=第\d+章|$)'
    chapters = re.findall(chapter_pattern, blueprint_content, re.DOTALL)
    
    for chapter_num, chapter_content in chapters:
        chapter_num = int(chapter_num)
        
        # 检测突破关键词
        for keyword in BREAKTHROUGH_KEYWORDS:
            if keyword in chapter_content:
                # 提取关键词周围的上下文
                idx = chapter_content.find(keyword)
                context_start = max(0, idx - 30)
                context_end = min(len(chapter_content), idx + 30)
                context = chapter_content[context_start:context_end].strip()
                
                events.append({
                    "chapter": chapter_num,
                    "keyword": keyword,
                    "context": context,
                    "type": "breakthrough"
                })
                break  # 每章只记录第一个突破事件
    
    return events


def detect_battle_events(blueprint_content: str) -> List[Dict]:
    """
    检测蓝图中的战斗事件
    
    Args:
        blueprint_content: 蓝图文本内容
        
    Returns:
        战斗事件列表
    """
    events = []
    
    # 按章节分割
    chapter_pattern = r'第(\d+)章[：:](.*?)(?=第\d+章|$)'
    chapters = re.findall(chapter_pattern, blueprint_content, re.DOTALL)
    
    for chapter_num, chapter_content in chapters:
        chapter_num = int(chapter_num)
        
        # 检测战斗关键词
        battle_found = False
        for keyword in BATTLE_KEYWORDS:
            if keyword in chapter_content:
                battle_found = True
                break
        
        if battle_found:
            events.append({
                "chapter": chapter_num,
                "has_battle": True,
                "assigned_style": None  # 待分配
            })
    
    return events


def get_expected_realm(chapter_num: int) -> Tuple[str, str]:
    """
    根据章节号获取预期的修为范围
    
    Args:
        chapter_num: 章节号
        
    Returns:
        (当前境界, 最高可达境界)
    """
    if not CULTIVATION_MAP_AVAILABLE:
        return ("未配置", "未配置")
    
    for (start, end), (current, max_realm) in CULTIVATION_PROGRESS_MAP.items():
        if start <= chapter_num <= end:
            return (current, max_realm)
    
    return ("超出范围", "超出范围")


def validate_breakthrough_events(events: List[Dict]) -> List[Dict]:
    """
    验证突破事件是否与修为约束冲突
    
    Args:
        events: 突破事件列表
        
    Returns:
        冲突报告列表
    """
    conflicts = []
    
    for event in events:
        chapter = event["chapter"]
        expected_current, expected_max = get_expected_realm(chapter)
        
        # 检查是否在允许突破的章节范围边界
        is_boundary_chapter = False
        for (start, end), _ in CULTIVATION_PROGRESS_MAP.items():
            if chapter == end:  # 只在范围最后一章允许突破
                is_boundary_chapter = True
                break
        
        if not is_boundary_chapter:
            conflicts.append({
                "chapter": chapter,
                "issue": "非边界章节出现突破事件",
                "expected_realm": expected_current,
                "suggestion": f"建议将突破描写改为'积累'或'感悟瓶颈'",
                "context": event.get("context", "")
            })
    
    return conflicts


def assign_battle_styles(battle_events: List[Dict], total_chapters: int = 10) -> Dict[int, str]:
    """
    为战斗事件分配风格，确保多样性
    
    Args:
        battle_events: 战斗事件列表
        total_chapters: 总章节数
        
    Returns:
        章节号到战斗风格的映射
    """
    if not BATTLE_STYLE_POOL:
        return {}
    
    # 提取风格名称列表（BATTLE_STYLE_POOL 是字典列表）
    style_names = []
    for style in BATTLE_STYLE_POOL:
        if isinstance(style, dict):
            style_names.append(style.get("name", str(style)))
        else:
            style_names.append(str(style))
    
    if not style_names:
        return {}
    
    style_assignment = {}
    style_count = {style: 0 for style in style_names}
    
    # 按章节顺序分配，确保每种风格至少出现一次
    battle_chapters = [e["chapter"] for e in battle_events]
    
    for i, chapter in enumerate(battle_chapters):
        # 找出使用次数最少的风格
        min_count = min(style_count.values())
        available_styles = [s for s, c in style_count.items() if c == min_count]
        
        # 避免连续两章使用相同风格
        if i > 0 and len(available_styles) > 1:
            prev_style = style_assignment.get(battle_chapters[i-1])
            if prev_style in available_styles:
                available_styles.remove(prev_style)
        
        # 选择风格
        selected_style = available_styles[i % len(available_styles)]
        style_assignment[chapter] = selected_style
        style_count[selected_style] += 1
    
    return style_assignment


def preprocess_blueprint(filepath: str) -> Dict:
    """
    预处理蓝图，生成完整报告
    
    Args:
        filepath: 小说项目目录路径
        
    Returns:
        预处理报告
    """
    blueprint_file = os.path.join(filepath, "Novel_directory.txt")
    
    if not os.path.exists(blueprint_file):
        return {
            "success": False,
            "error": f"蓝图文件不存在: {blueprint_file}"
        }
    
    try:
        with open(blueprint_file, 'r', encoding='utf-8') as f:
            blueprint_content = f.read()
    except Exception as e:
        return {
            "success": False,
            "error": f"读取蓝图失败: {e}"
        }
    
    # 检测突破事件
    breakthrough_events = detect_breakthrough_events(blueprint_content)
    
    # 检测战斗事件
    battle_events = detect_battle_events(blueprint_content)
    
    # 验证突破事件
    conflicts = validate_breakthrough_events(breakthrough_events)
    
    # 分配战斗风格
    battle_styles = assign_battle_styles(battle_events)
    
    # 生成报告
    report = {
        "success": True,
        "breakthrough_events": breakthrough_events,
        "battle_events": battle_events,
        "conflicts": conflicts,
        "battle_style_assignment": battle_styles,
        "summary": {
            "total_breakthrough_events": len(breakthrough_events),
            "total_battle_events": len(battle_events),
            "total_conflicts": len(conflicts),
            "style_distribution": {}
        }
    }
    
    # 统计风格分布
    for style in BATTLE_STYLE_POOL:
        style_name = style.get("name", str(style)) if isinstance(style, dict) else str(style)
        report["summary"]["style_distribution"][style_name] = sum(
            1 for s in battle_styles.values() if s == style_name
        )
    
    # 保存预处理结果
    cache_file = os.path.join(filepath, ".blueprint_cache.json")
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logging.info(f"[BlueprintPreprocessor] 预处理结果已缓存: {cache_file}")
    except Exception as e:
        logging.warning(f"[BlueprintPreprocessor] 缓存保存失败: {e}")
    
    return report


def get_chapter_battle_style(filepath: str, chapter_num: int) -> Optional[str]:
    """
    从预处理缓存中获取指定章节的战斗风格
    
    Args:
        filepath: 小说项目目录路径
        chapter_num: 章节号
        
    Returns:
        战斗风格，如果不存在则返回None
    """
    cache_file = os.path.join(filepath, ".blueprint_cache.json")
    
    if not os.path.exists(cache_file):
        # 如果缓存不存在，执行预处理
        report = preprocess_blueprint(filepath)
        if not report.get("success"):
            return None
    else:
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                report = json.load(f)
        except Exception as e:
            logging.warning(f"[BlueprintPreprocessor] 读取缓存失败: {e}")
            return None
    
    return report.get("battle_style_assignment", {}).get(str(chapter_num)) or \
           report.get("battle_style_assignment", {}).get(chapter_num)


def is_breakthrough_chapter(filepath: str, chapter_num: int) -> bool:
    """
    判断指定章节是否为突破章节
    
    Args:
        filepath: 小说项目目录路径
        chapter_num: 章节号
        
    Returns:
        是否为突破章节
    """
    cache_file = os.path.join(filepath, ".blueprint_cache.json")
    
    if not os.path.exists(cache_file):
        report = preprocess_blueprint(filepath)
        if not report.get("success"):
            return False
    else:
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                report = json.load(f)
        except Exception:
            return False
    
    breakthrough_chapters = [e["chapter"] for e in report.get("breakthrough_events", [])]
    return chapter_num in breakthrough_chapters


# 导出函数
__all__ = [
    'preprocess_blueprint',
    'get_chapter_battle_style',
    'is_breakthrough_chapter',
    'detect_breakthrough_events',
    'detect_battle_events',
    'validate_breakthrough_events',
    'assign_battle_styles'
]
