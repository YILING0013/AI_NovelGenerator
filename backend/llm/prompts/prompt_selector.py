"""任务图资料字段与模型服务探测提示词。"""

from pathlib import Path
from string import Formatter

import yaml

PROMPT_DIR = Path(__file__).resolve().parent
ITEMS_PROMPT_NAME = "create_items_by_ai"

PROMPT_TEMPLATE_FIELDS: dict[str, set[str]] = {
    "expand_idea_to_full_novel_story_prompt_base": {"user_idea"},
    "extract_idea_prompt_base": {"plot"},
    "core_seed_prompt_base": {
        "plot",
        "genre",
        "tone",
        "target_audience",
        "core_idea",
        "number_of_chapters",
        "words_per_chapter",
    },
    "novel_meta_prompt_base": {
        "plot",
        "genre",
        "tone",
        "target_audience",
        "core_idea",
        "number_of_chapters",
        "words_per_chapter",
        "core_seed",
    },
    "rewrite_novel_field_prompt_base": {
        "target_field_label",
        "target_field",
        "instruction",
        "current_value",
        "context_json",
        "history_text",
    },
    "rewrite_novel_field_prompt_without_schema_suffix": {"target_field"},
    "create_core_factions_prompt_base": {
        "plot",
        "genre",
        "tone",
        "target_audience",
        "core_idea",
        "number_of_chapters",
        "words_per_chapter",
        "core_seed",
        "title",
        "summary",
        "worldview",
        "writing_style",
        "narrative_pov",
        "era_background",
        "tags_json",
        "existing_core_factions_json",
        "faction_count",
        "generation_strategy",
    },
    "create_core_characters_prompt_base": {
        "novel_profile_json",
        "core_factions_json",
        "existing_core_characters_json",
        "character_count",
        "user_guidance",
    },
    "create_character_relations_prompt_base": {
        "novel_profile_json",
        "characters_json",
        "faction_bindings_json",
        "existing_relations_json",
        "allow_isolated_characters",
        "relation_count_limit",
        "user_guidance",
    },
    "create_faction_relations_prompt_base": {
        "novel_profile_json",
        "factions_json",
        "existing_relations_json",
        "allow_isolated_factions",
        "relation_count_limit",
        "user_guidance",
    },
    "create_core_world_rules_prompt_base": {
        "novel_summary",
        "protagonists",
        "characters",
        "factions",
        "faction_relations",
        "existing_world_rules",
        "core_rule_count",
        "allow_incremental",
        "user_guidance",
    },
    "create_volume_skeleton_prompt_base": {
        "novel_profile",
        "worldview_summary",
        "active_world_rules",
        "protagonists",
        "characters",
        "factions_and_relations",
        "existing_volumes",
        "target_volume_count",
        "total_chapter_budget",
        "total_word_budget",
        "mode",
        "target_order_range",
        "user_guidance",
    },
    "create_volume_launch_package_prompt_base": {
        "novel_profile",
        "worldview_summary",
        "active_world_rules",
        "protagonists",
        "characters",
        "factions_and_relations",
        "target_volume",
        "previous_volume",
        "next_volume",
        "target_chapter_count",
        "target_word_count",
        "user_guidance",
    },
    "create_locations_for_volume_prompt_base": {
        "novel_summary",
        "volume_launch_package",
        "character_volume_states",
        "faction_volume_states",
        "active_world_rules",
        "existing_locations",
        "selected_existing_locations",
        "location_count",
        "allow_incremental",
        "user_guidance",
    },
    "create_items_prompt_base": {
        "novel_profile_json",
        "active_world_rules_json",
        "characters_json",
        "factions_json",
        "locations_json",
        "existing_items_json",
        "item_count",
        "allow_incremental",
        "user_guidance",
    },
    "function_result_probe_prompt": {"probe_token", "tool_result"},
}


def load_llm_provider_test_prompts(*, prompt_dir: Path | None = None) -> dict[str, str]:
    """读取并检查模型服务探测提示词。

    Args:
        prompt_dir: 提示词根目录，默认使用本模块目录。
    Returns:
        文本、流式、结构化输出和工具调用的探测提示词。
    """
    directory = prompt_dir or PROMPT_DIR
    custom = directory / "custom" / "llm_provider_test.yaml"
    path = custom if custom.exists() else directory / "default" / "llm_provider_test.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"llm_provider_test"}:
        raise ValueError(f"{path} 必须只包含 llm_provider_test 提示词")
    prompts = data["llm_provider_test"]
    fields = {
        "text_probe_prompt": set(),
        "stream_probe_prompt": set(),
        "json_schema_probe_prompt": set(),
        "function_call_probe_prompt": set(),
        "function_result_probe_prompt": {"tool_result", "probe_token"},
    }
    if not isinstance(prompts, dict) or set(prompts) != set(fields):
        raise ValueError(f"{path} 必须包含全部五项探测提示词")
    for key, expected in fields.items():
        value = prompts[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path} 的 {key} 不能为空")
        actual = {name for _, name, _, _ in Formatter().parse(value) if name is not None}
        if actual != expected:
            raise ValueError(f"{path} 的 {key} 占位符必须为 {sorted(expected)}")
    return prompts
