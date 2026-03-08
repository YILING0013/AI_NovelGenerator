# -*- coding: utf-8 -*-
"""
预生成验证器 - 在批量生成前执行验证检查
v3.1: 修复静默异常、提取魔法数字、优化单例
"""

import logging
from typing import Dict

# Core imports
from novel_generator.core.blueprint import get_blueprint, IndexedBlueprint
from novel_generator.core.rules import get_rules_config, StoryRulesConfig

logger = logging.getLogger(__name__)

# 尝试导入分卷校正函数
try:
    from prompts import get_volume_info, get_cultivation_constraint
    VOLUME_FUNCTIONS_AVAILABLE = True
except ImportError:
    VOLUME_FUNCTIONS_AVAILABLE = False
    logger.warning("分卷校正函数不可用")


# ============================================================
# 配置常量（从硬编码提取，未来可移入 story_rules.json）
# ============================================================
ROMANCE_CHECK_INTERVAL = 10      # 每10章检查一次暧昧密度
ROMANCE_MIDPOINT_OFFSET = 5      # 区间中点偏移量


class PreGenerationValidator:
    """
    预生成验证器
    
    在生成每一章之前，检查蓝图、注入分卷信息、提供增强提示。
    所有验证逻辑都在这里汇总。
    """
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.blueprint: IndexedBlueprint = get_blueprint(filepath)
        self.rules: StoryRulesConfig = get_rules_config()
    
    def validate_chapter(self, chapter_num: int) -> Dict:
        """验证单个章节前置条件"""
        result = {
            "chapter": chapter_num,
            "passed": True,
            "checks": [],
            "warnings": [],
            "volume_info": None,
            "cultivation_info": None,
            "enhancement_text": ""
        }
        
        # 1. 分卷校正
        if VOLUME_FUNCTIONS_AVAILABLE:
            try:
                volume_info = get_volume_info(chapter_num)
                result["volume_info"] = volume_info
                result["checks"].append({
                    "name": "分卷定位",
                    "status": "✅",
                    "detail": volume_info["full_position"]
                })
                result["enhancement_text"] += f"\n{volume_info['position_text']}\n"
            except Exception as e:
                # 不再静默吞掉异常，记录日志
                logger.debug(f"分卷校正失败（章节{chapter_num}）: {e}")
        
        # 2. 修为校正
        if VOLUME_FUNCTIONS_AVAILABLE:
            try:
                cultivation_info = get_cultivation_constraint(chapter_num)
                result["cultivation_info"] = cultivation_info
                if cultivation_info.get("constraint_text"):
                    result["enhancement_text"] += f"\n{cultivation_info['constraint_text']}\n"
            except Exception as e:
                logger.debug(f"修为校正失败（章节{chapter_num}）: {e}")
        
        # 3. 蓝图存在性
        if self.blueprint.chapter_exists(chapter_num):
            result["checks"].append({
                "name": "蓝图存在",
                "status": "✅",
                "detail": f"第{chapter_num}章蓝图已找到"
            })
        else:
            result["checks"].append({
                "name": "蓝图存在",
                "status": "⚠️",
                "detail": f"第{chapter_num}章蓝图未找到"
            })
            result["warnings"].append(f"第{chapter_num}章蓝图缺失")
        
        # 4. 业务规则增强
        self._apply_rule_enhancements(chapter_num, result)
            
        return result
    
    def _apply_rule_enhancements(self, chapter_num: int, result: Dict):
        """应用业务规则增强（提取为独立方法，便于测试和扩展）"""
        
        # 4.1 暧昧间隔提醒（使用常量而非魔法数字）
        if chapter_num % ROMANCE_CHECK_INTERVAL == 0:
            result["warnings"].append(f"第{chapter_num}章是区间末尾，请检查暧昧场景")
            
        # 4.2 重大反转
        if chapter_num in self.rules.major_reversals:
            event = self.rules.major_reversals[chapter_num]
            result["enhancement_text"] += f"\n【重大事件提醒】本章需要体现：{event}\n"
            
        # 4.3 女主成长
        if chapter_num in self.rules.female_milestones:
            m = self.rules.female_milestones[chapter_num]
            result["enhancement_text"] += f"\n【女主成长线·{m.get('lead')}】{m.get('milestone')}\n"
            
        # 4.4 伏笔
        if chapter_num in self.rules.foreshadowing:
            f = self.rules.foreshadowing[chapter_num]
            result["enhancement_text"] += f"\n【伏笔植入·{f.get('tag')}】{f.get('content')}\n"
            
        # 4.5 暧昧建议
        if chapter_num % ROMANCE_CHECK_INTERVAL == ROMANCE_MIDPOINT_OFFSET:
            if chapter_num in self.rules.romance:
                r = self.rules.romance[chapter_num]
                result["enhancement_text"] += f"\n【暧昧场景提醒】建议增加{r.get('lead')}的{r.get('type')}场景\n"
    
    def get_enhancement_for_chapter(self, chapter_num: int) -> str:
        """获取章节增强提示"""
        result = self.validate_chapter(chapter_num)
        return result.get("enhancement_text", "")


# ============================================================
# 模块级缓存（使用字典替代全局变量，支持多路径）
# ============================================================
_validators: Dict[str, PreGenerationValidator] = {}

def get_validator(filepath: str) -> PreGenerationValidator:
    """获取或创建验证器实例（线程不安全，但对于单线程生成足够）"""
    if filepath not in _validators:
        _validators[filepath] = PreGenerationValidator(filepath)
    return _validators[filepath]

def get_chapter_enhancement(filepath: str, chapter_num: int) -> str:
    """对外接口：获取增强文本"""
    return get_validator(filepath).get_enhancement_for_chapter(chapter_num)

def validate_before_generation(filepath: str, chapter_num: int) -> Dict:
    """对外接口：生成前验证"""
    return get_validator(filepath).validate_chapter(chapter_num)
