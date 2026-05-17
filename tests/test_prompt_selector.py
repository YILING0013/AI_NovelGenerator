from __future__ import annotations

import logging
from pathlib import Path

import yaml

from backend.llm.prompts import prompt_selector


def _build_prompt_data(prefix: str) -> dict[str, dict[str, str]]:
    """构造一份包含全部必需字段的提示词数据。

    Args:
        prefix: 写入每个提示词字段的文本前缀。

    Returns:
        可直接写入 YAML 的提示词配置字典。
    """
    return {
        prompt_selector.WORKFLOW_NAME: {
            key: _build_prompt_value(prefix, key)
            for key in prompt_selector.REQUIRED_CREATE_NOVEL_PROMPT_KEYS
        },
        prompt_selector.REWRITE_NOVEL_FIELD_PROMPT_NAME: {
            key: _build_prompt_value(prefix, key)
            for key in prompt_selector.REQUIRED_REWRITE_NOVEL_FIELD_PROMPT_KEYS
        },
        prompt_selector.CORE_FACTIONS_PROMPT_NAME: {
            key: _build_prompt_value(prefix, key)
            for key in prompt_selector.REQUIRED_CORE_FACTIONS_PROMPT_KEYS
        },
    }


def _build_provider_test_prompts(prefix: str) -> dict[str, str]:
    """构造 LLM Provider 测试提示词分组。

    Args:
        prefix: 写入每个提示词字段的文本前缀。

    Returns:
        可通过测试提示词校验的分组字典。
    """
    return {
        key: _build_prompt_value(prefix, key)
        for key in prompt_selector.REQUIRED_LLM_PROVIDER_TEST_PROMPT_KEYS
    }


def _build_prompt_value(prefix: str, key: str) -> str:
    """构造单个提示词字段文本，并为基础模板补齐占位符。

    Args:
        prefix: 写入提示词字段的文本前缀。
        key: 提示词字段名。

    Returns:
        可通过校验的提示词文本。
    """
    fields = prompt_selector.PROMPT_TEMPLATE_FIELDS.get(key)
    if not fields:
        return f"{prefix}: {key}"

    placeholder_text = " ".join(f"{{{field}}}" for field in sorted(fields))
    return f"{prefix}: {key} {placeholder_text}"


def _write_yaml(path: Path, data: dict) -> None:
    """将测试 YAML 数据写入指定路径。

    Args:
        path: 目标 YAML 文件路径。
        data: 需要写入的 YAML 数据。

    Returns:
        无。
    """
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_resolve_prompt_selection_uses_custom_when_valid(tmp_path: Path) -> None:
    default_data = _build_prompt_data("default")
    custom_data = _build_prompt_data("custom")
    _write_yaml(tmp_path / prompt_selector.DEFAULT_PROMPT_FILENAME, default_data)
    _write_yaml(tmp_path / prompt_selector.CUSTOM_PROMPT_FILENAME, custom_data)

    selection = prompt_selector.resolve_prompt_selection(tmp_path, emit_warning=False)

    assert selection.path == tmp_path / prompt_selector.CUSTOM_PROMPT_FILENAME
    assert selection.is_default is False
    assert selection.data == custom_data


def test_resolve_prompt_selection_falls_back_and_logs_warning(tmp_path: Path, caplog) -> None:
    default_data = _build_prompt_data("default")
    broken_custom_data = {
        prompt_selector.WORKFLOW_NAME: {
            "expand_idea_to_full_novel_story_prompt_base": "",
        }
    }
    _write_yaml(tmp_path / prompt_selector.DEFAULT_PROMPT_FILENAME, default_data)
    _write_yaml(tmp_path / prompt_selector.CUSTOM_PROMPT_FILENAME, broken_custom_data)

    caplog.set_level(logging.WARNING, logger=prompt_selector.logger.name)
    selection = prompt_selector.resolve_prompt_selection(tmp_path, emit_warning=True)

    assert selection.path == tmp_path / prompt_selector.DEFAULT_PROMPT_FILENAME
    assert selection.is_default is True
    assert selection.data == default_data
    assert selection.warnings
    assert "PROMPT YAML WARNING" in caplog.text
    assert "程序将采用默认提示词配置" in caplog.text


def test_resolve_prompt_selection_rejects_unknown_format_placeholder(tmp_path: Path) -> None:
    default_data = _build_prompt_data("default")
    custom_data = _build_prompt_data("custom")
    custom_data[prompt_selector.WORKFLOW_NAME]["extract_idea_prompt_base"] = "{plot} {unknown_field}"
    _write_yaml(tmp_path / prompt_selector.DEFAULT_PROMPT_FILENAME, default_data)
    _write_yaml(tmp_path / prompt_selector.CUSTOM_PROMPT_FILENAME, custom_data)

    selection = prompt_selector.resolve_prompt_selection(tmp_path, emit_warning=False)

    assert selection.path == tmp_path / prompt_selector.DEFAULT_PROMPT_FILENAME
    assert selection.is_default is True
    assert "未支持的占位符" in selection.warnings[0]


def test_repository_default_prompt_file_is_valid() -> None:
    selection = prompt_selector.resolve_prompt_selection(prompt_selector.PROMPT_DIR, emit_warning=False)

    workflow_prompts = selection.data[prompt_selector.WORKFLOW_NAME]
    for key in prompt_selector.REQUIRED_CREATE_NOVEL_PROMPT_KEYS:
        assert isinstance(workflow_prompts[key], str)
        assert workflow_prompts[key].strip()

    rewrite_prompts = selection.data[prompt_selector.REWRITE_NOVEL_FIELD_PROMPT_NAME]
    for key in prompt_selector.REQUIRED_REWRITE_NOVEL_FIELD_PROMPT_KEYS:
        assert isinstance(rewrite_prompts[key], str)
        assert rewrite_prompts[key].strip()

    core_faction_prompts = selection.data[prompt_selector.CORE_FACTIONS_PROMPT_NAME]
    for key in prompt_selector.REQUIRED_CORE_FACTIONS_PROMPT_KEYS:
        assert isinstance(core_faction_prompts[key], str)
        assert core_faction_prompts[key].strip()

    provider_test_prompts = prompt_selector.load_llm_provider_test_prompts(force_reload=True)
    for key in prompt_selector.REQUIRED_LLM_PROVIDER_TEST_PROMPT_KEYS:
        assert isinstance(provider_test_prompts[key], str)
        assert provider_test_prompts[key].strip()


def test_llm_provider_test_prompts_fall_back_to_default_section(tmp_path: Path) -> None:
    default_data = _build_prompt_data("default")
    default_data[prompt_selector.LLM_PROVIDER_TEST_PROMPT_NAME] = _build_provider_test_prompts("default")
    custom_data = _build_prompt_data("custom")
    _write_yaml(tmp_path / prompt_selector.DEFAULT_PROMPT_FILENAME, default_data)
    _write_yaml(tmp_path / prompt_selector.CUSTOM_PROMPT_FILENAME, custom_data)

    prompts = prompt_selector.load_llm_provider_test_prompts(prompt_dir=tmp_path)

    assert prompts == default_data[prompt_selector.LLM_PROVIDER_TEST_PROMPT_NAME]
