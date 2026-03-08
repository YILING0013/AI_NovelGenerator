# prompts/__init__.py
# -*- coding: utf-8 -*-
"""
Prompts模块初始化 - 向后兼容导出所有公共变量

模块结构：
- constraints.py: 公共约束（格式、字数、语言纯度）
- constants.py: 常量配置（修为体系、战斗风格等）
- chapter_prompts.py: 章节生成prompt
- summary_prompts.py: 摘要和知识库prompt
- snowflake_prompts.py: 雪花写作法prompt
- character_prompts.py: 角色状态prompt
- blueprint_prompts.py: 章节目录结构参考
- quality_control.py: 质量控制配置
"""

# ============== 约束模块 ==============
from .constraints import (
    FORMAT_CONSTRAINTS,
    WORD_COUNT_TEMPLATE,
    LANGUAGE_PURITY,
    ANTI_REPETITION,
    get_common_constraints,
    get_chapter_constraints,
)

# ============== 常量模块 ==============
from .constants import (
    ENDING_STYLES,
    BATTLE_STYLE_POOL,
    CULTIVATION_PROGRESS_MAP,
    get_cultivation_constraint,
    VILLAIN_DIALOGUE_STYLES,
    VOLUME_MAPPING,
    get_volume_info,
)

# ============== 章节生成prompt ==============
from .chapter_prompts import (
    first_chapter_draft_prompt,
    next_chapter_draft_prompt,
)

# ============== 摘要和知识库prompt ==============
from .summary_prompts import (
    summarize_recent_chapters_prompt,
    knowledge_search_prompt,
    knowledge_filter_prompt,
    summary_prompt,
)

# ============== 雪花写作法prompt ==============
from .snowflake_prompts import (
    core_seed_prompt,
    character_dynamics_prompt,
    world_building_prompt,
    plot_architecture_prompt,
)

# ============== 角色状态prompt ==============
from .character_prompts import (
    create_character_state_prompt,
    update_character_state_prompt,
)

# ============== 质量控制 ==============
from .quality_control import (
    SCORING_PROMPT,
    IMPROVEMENT_PROMPT,
    QUALITY_CONFIG,
    HOOK_SYSTEM,
    PACING_FORMULA,
    get_rhythm_position,
)

# ============== 导出所有公共变量 ==============
__all__ = [
    # 约束
    'FORMAT_CONSTRAINTS', 'WORD_COUNT_TEMPLATE', 'LANGUAGE_PURITY',
    'ANTI_REPETITION', 'get_common_constraints', 'get_chapter_constraints',
    # 常量
    'ENDING_STYLES', 'BATTLE_STYLE_POOL', 'CULTIVATION_PROGRESS_MAP',
    'get_cultivation_constraint', 'VILLAIN_DIALOGUE_STYLES',
    'VOLUME_MAPPING', 'get_volume_info',
    # 章节prompt
    'first_chapter_draft_prompt', 'next_chapter_draft_prompt',
    # 摘要prompt
    'summarize_recent_chapters_prompt', 'knowledge_search_prompt',
    'knowledge_filter_prompt', 'summary_prompt',
    # 雪花写作法prompt
    'core_seed_prompt', 'character_dynamics_prompt',
    'world_building_prompt', 'plot_architecture_prompt',
    # 角色状态prompt
    'create_character_state_prompt', 'update_character_state_prompt',
    # 质量控制
    'SCORING_PROMPT', 'IMPROVEMENT_PROMPT', 'QUALITY_CONFIG',
    'HOOK_SYSTEM', 'PACING_FORMULA', 'get_rhythm_position',
]
