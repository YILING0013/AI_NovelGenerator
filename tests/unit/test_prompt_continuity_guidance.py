from __future__ import annotations

import prompt_definitions
import prompts


def test_chapter_prompts_include_continuity_priority_guidance() -> None:
    assert "【连续性执行优先级】" in prompts.first_chapter_draft_prompt
    assert "【核心约束：反重复与剧情连续性】" in prompts.next_chapter_draft_prompt
    assert "不得像重启剧情一样另起炉灶" in prompts.next_chapter_draft_prompt


def test_summary_prompts_preserve_long_horizon_state() -> None:
    assert "保留优先级（高于文采润色）" in prompts.summarize_recent_chapters_prompt
    assert "长期信息保留优先级" in prompts.summary_prompt
    assert "规则与代价变化" in prompts.summary_prompt
    assert "当前摘要中仍未解决的冲突、伏笔、误会、债务、代价" in prompts.knowledge_search_prompt
    assert "长期连续性价值" in prompts.knowledge_filter_prompt
    assert "每个分类最多保留3条" in prompts.knowledge_filter_prompt


def test_character_state_prompt_filters_transient_noise() -> None:
    assert "只保留对后续仍有影响的物品、能力、关系、事件" in prompts.update_character_state_prompt
    assert "避免无限累积流水账" in prompts.update_character_state_prompt


def test_blueprint_and_runtime_guides_emphasize_continuity() -> None:
    assert "承接上一阶段的后果" in prompt_definitions.chunked_chapter_blueprint_prompt
    assert "连续性铁律" in prompt_definitions.STEP2_GUIDED_STRICT_BLUEPRINT_PROMPT
    assert "既有设定一致性" in prompt_definitions.COT_INSTRUCTIONS
    assert "不得无解释重置" in prompt_definitions.TWO_TRACK_NARRATIVE_RULE


def test_snowflake_prompts_encode_long_form_pressure() -> None:
    assert "若失败将失去什么" in prompts.core_seed_prompt
    assert "压力源、债务、限制或执念" in prompts.character_dynamics_prompt
    assert "避免百科全书式堆砌静态设定" in prompts.world_building_prompt
    assert "每幕都必须承接上一阶段留下的后果" in prompts.plot_architecture_prompt
