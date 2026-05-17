"""提示词 YAML 选择与校验工具。

该模块负责在启动时优先选择 `prompt.yaml`，并在自定义提示词不可用时
回退到 `prompt_default.yaml`。所有调用方只需要读取这里返回的配置，
避免在业务代码中重复拼接默认提示词路径。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import logging
from pathlib import Path
from string import Formatter
from typing import Any

import yaml

PROMPT_DIR = Path(__file__).resolve().parent
CUSTOM_PROMPT_FILENAME = "prompt.yaml"
DEFAULT_PROMPT_FILENAME = "prompt_default.yaml"
WORKFLOW_NAME = "create_novel_by_ai"
REWRITE_NOVEL_FIELD_PROMPT_NAME = "rewrite_novel_field"
CORE_FACTIONS_PROMPT_NAME = "create_factions_by_ai"
LLM_PROVIDER_TEST_PROMPT_NAME = "llm_provider_test"

DEFAULT_PROMPT_PATH = PROMPT_DIR / DEFAULT_PROMPT_FILENAME
CUSTOM_PROMPT_PATH = PROMPT_DIR / CUSTOM_PROMPT_FILENAME

REQUIRED_CREATE_NOVEL_PROMPT_KEYS: tuple[str, ...] = (
    "expand_idea_to_full_novel_story_prompt_base",
    "expand_idea_to_full_novel_story_prompt_with_schema_suffix",
    "expand_idea_to_full_novel_story_prompt_without_schema_suffix",
    "extract_idea_prompt_base",
    "extract_idea_prompt_with_schema_suffix",
    "extract_idea_prompt_without_schema_suffix",
    "core_seed_prompt_base",
    "core_seed_prompt_with_schema_suffix",
    "core_seed_prompt_without_schema_suffix",
    "novel_meta_prompt_base",
    "novel_meta_prompt_with_schema_suffix",
    "novel_meta_prompt_without_schema_suffix",
)

REQUIRED_REWRITE_NOVEL_FIELD_PROMPT_KEYS: tuple[str, ...] = (
    "rewrite_novel_field_prompt_base",
    "rewrite_novel_field_prompt_with_schema_suffix",
    "rewrite_novel_field_prompt_without_schema_suffix",
)

REQUIRED_CORE_FACTIONS_PROMPT_KEYS: tuple[str, ...] = (
    "create_core_factions_prompt_base",
    "create_core_factions_prompt_with_schema_suffix",
    "create_core_factions_prompt_without_schema_suffix",
)

REQUIRED_LLM_PROVIDER_TEST_PROMPT_KEYS: tuple[str, ...] = (
    "text_probe_prompt",
    "stream_probe_prompt",
    "json_schema_probe_prompt",
    "function_call_probe_prompt",
    "function_result_probe_prompt",
)

REQUIRED_PROMPT_SECTIONS: dict[str, tuple[str, ...]] = {
    WORKFLOW_NAME: REQUIRED_CREATE_NOVEL_PROMPT_KEYS,
    REWRITE_NOVEL_FIELD_PROMPT_NAME: REQUIRED_REWRITE_NOVEL_FIELD_PROMPT_KEYS,
    CORE_FACTIONS_PROMPT_NAME: REQUIRED_CORE_FACTIONS_PROMPT_KEYS,
}

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
    },
    "function_result_probe_prompt": {"probe_token", "tool_result"},
}

logger = logging.getLogger(__name__)


class PromptConfigError(ValueError):
    """提示词 YAML 结构或内容无法用于运行时提示词配置。"""


@dataclass(frozen=True)
class PromptSelection:
    """当前提示词文件选择结果。"""

    path: Path
    data: dict[str, Any]
    is_default: bool
    warnings: tuple[str, ...] = ()


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    """读取 YAML 文件并确保根节点是映射结构。

    Args:
        path: 需要读取的 YAML 文件路径。

    Returns:
        解析后的 YAML 字典。

    Raises:
        PromptConfigError: 文件不存在、格式错误或根节点不是映射时抛出。
    """
    if not path.exists():
        raise PromptConfigError(f"文件不存在: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            loaded = yaml.safe_load(file) or {}
    except yaml.YAMLError as exc:
        raise PromptConfigError(f"YAML 解析失败: {exc}") from exc
    except OSError as exc:
        raise PromptConfigError(f"文件读取失败: {exc}") from exc

    if not isinstance(loaded, dict):
        raise PromptConfigError("YAML 根节点必须是映射对象")

    return loaded


def _extract_format_fields(template: str) -> set[str]:
    """提取 `str.format` 模板中的占位符根字段。

    Args:
        template: 待检查的提示词模板文本。

    Returns:
        模板中出现过的占位符字段集合。

    Raises:
        PromptConfigError: 模板包含未转义花括号或非法占位符时抛出。
    """
    fields: set[str] = set()

    try:
        parsed_segments = Formatter().parse(template)
        for _literal_text, field_name, _format_spec, _conversion in parsed_segments:
            if not field_name:
                continue
            # 业务层只传入根变量名，属性访问或索引访问都会先依赖这个根变量。
            root_name = field_name.split(".", 1)[0].split("[", 1)[0]
            fields.add(root_name)
    except ValueError as exc:
        raise PromptConfigError(f"格式占位符错误: {exc}") from exc

    return fields


def _validate_prompt_section(
    data: dict[str, Any],
    *,
    source_path: Path,
    section_name: str,
    required_keys: tuple[str, ...],
) -> list[str]:
    """核对指定提示词分组是否包含运行所需的文本。

    Args:
        data: 已解析的提示词 YAML 数据。
        source_path: 数据来源文件路径，用于生成可读错误信息。
        section_name: 需要校验的提示词分组名。
        required_keys: 分组内必须存在的字段名。

    Returns:
        校验发现的错误信息列表。
    """
    errors: list[str] = []
    section_prompts = data.get(section_name)

    # 先确认提示词根节点存在，避免后续业务代码运行时才触发 KeyError。
    if not isinstance(section_prompts, dict):
        return [f"{source_path} 缺少映射节点: {section_name}"]

    for key in required_keys:
        value = section_prompts.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{section_name}.{key} 必须是非空字符串")
            continue

        expected_fields = PROMPT_TEMPLATE_FIELDS.get(key)
        if not expected_fields:
            continue

        try:
            format_fields = _extract_format_fields(value)
        except PromptConfigError as exc:
            errors.append(f"{section_name}.{key} {exc}")
            continue

        missing_fields = expected_fields - format_fields
        unknown_fields = format_fields - expected_fields
        if missing_fields:
            errors.append(f"{section_name}.{key} 缺少占位符: {', '.join(sorted(missing_fields))}")
        if unknown_fields:
            errors.append(f"{section_name}.{key} 包含未支持的占位符: {', '.join(sorted(unknown_fields))}")

    return errors


def validate_prompt_data(data: dict[str, Any], *, source_path: Path) -> None:
    """核对提示词配置是否包含当前工作流运行所需的文本。

    Args:
        data: 已解析的提示词 YAML 数据。
        source_path: 数据来源文件路径，用于生成可读错误信息。

    Returns:
        校验通过时不返回内容。

    Raises:
        PromptConfigError: 工作流节点缺失、字段缺失或字段不是非空字符串时抛出。
    """
    errors: list[str] = []
    for section_name, required_keys in REQUIRED_PROMPT_SECTIONS.items():
        errors.extend(
            _validate_prompt_section(
                data,
                source_path=source_path,
                section_name=section_name,
                required_keys=required_keys,
            )
        )

    if errors:
        joined_errors = "\n".join(f"- {error}" for error in errors)
        raise PromptConfigError(f"{source_path} 提示词内容不完整:\n{joined_errors}")


def _extract_valid_prompt_section(
    data: dict[str, Any],
    *,
    source_path: Path,
    section_name: str,
    required_keys: tuple[str, ...],
) -> dict[str, str]:
    """提取并校验可独立回退的提示词分组。

    Args:
        data: 已解析的提示词 YAML 数据。
        source_path: 数据来源文件路径，用于生成可读错误信息。
        section_name: 需要读取的提示词分组名。
        required_keys: 分组内必须存在的字段名。

    Returns:
        校验通过的提示词分组字典。

    Raises:
        PromptConfigError: 指定分组缺失或内容不完整时抛出。
    """
    errors = _validate_prompt_section(
        data,
        source_path=source_path,
        section_name=section_name,
        required_keys=required_keys,
    )
    if errors:
        joined_errors = "\n".join(f"- {error}" for error in errors)
        raise PromptConfigError(f"{source_path} 提示词分组不可用:\n{joined_errors}")

    section = data[section_name]
    return {key: str(section[key]) for key in required_keys}


def _format_prompt_warning(custom_path: Path, default_path: Path, reasons: tuple[str, ...]) -> str:
    """生成启动时输出的多行提示词告警文本。

    Args:
        custom_path: 校验失败的自定义提示词文件路径。
        default_path: 回退采用的默认提示词文件路径。
        reasons: 自定义提示词不可用的原因列表。

    Returns:
        可直接写入日志的多行告警字符串。
    """
    reason_lines = "\n".join(f"  - {reason}" for reason in reasons)
    return fr"""
+============================================================+
|  PROMPT YAML WARNING                                       |
+============================================================+
  ____  ____   ___  __  __ ____ _____
 |  _ \|  _ \ / _ \|  \/  |  _ \_   _|
 | |_) | |_) | | | | |\/| | |_) || |
 |  __/|  _ <| |_| | |  | |  __/ | |
 |_|   |_| \_\\___/|_|  |_|_|    |_|

提示词文件校验失败，程序将采用默认提示词配置。
自定义文件: {custom_path}
默认文件:   {default_path}

错误原因:
{reason_lines}
+============================================================+
""".strip()


def resolve_prompt_selection(prompt_dir: Path | None = None, *, emit_warning: bool = True) -> PromptSelection:
    """选择当前可用的提示词 YAML 文件。

    Args:
        prompt_dir: 提示词目录；为空时使用当前模块所在目录。
        emit_warning: 自定义提示词失败回退时是否写入多行告警日志。

    Returns:
        包含最终文件路径、解析数据和回退状态的选择结果。

    Raises:
        PromptConfigError: 默认提示词文件不可读取或自身校验失败时抛出。
    """
    prompt_dir = Path(prompt_dir or PROMPT_DIR)
    default_path = prompt_dir / DEFAULT_PROMPT_FILENAME
    custom_path = prompt_dir / CUSTOM_PROMPT_FILENAME

    default_data = _read_yaml_mapping(default_path)
    validate_prompt_data(default_data, source_path=default_path)

    if not custom_path.exists():
        return PromptSelection(path=default_path, data=default_data, is_default=True)

    try:
        custom_data = _read_yaml_mapping(custom_path)
        validate_prompt_data(custom_data, source_path=custom_path)
    except PromptConfigError as exc:
        reasons = (str(exc),)
        # 自定义文件存在但不可用时只降级，不阻断程序启动。
        if emit_warning:
            logger.warning("\n%s", _format_prompt_warning(custom_path, default_path, reasons))
        return PromptSelection(path=default_path, data=default_data, is_default=True, warnings=reasons)

    return PromptSelection(path=custom_path, data=custom_data, is_default=False)


@lru_cache(maxsize=1)
def _cached_prompt_selection() -> PromptSelection:
    """缓存默认提示词目录的选择结果。

    Args:
        无。

    Returns:
        当前默认提示词目录的选择结果。
    """
    return resolve_prompt_selection()


def get_prompt_selection(*, force_reload: bool = False) -> PromptSelection:
    """返回当前提示词选择结果。

    Args:
        force_reload: 为 True 时清空缓存并重新读取磁盘文件。

    Returns:
        当前提示词文件的选择结果。
    """
    if force_reload:
        _cached_prompt_selection.cache_clear()
    return _cached_prompt_selection()


def load_prompt_config(*, force_reload: bool = False) -> dict[str, Any]:
    """加载当前生效的提示词配置。

    Args:
        force_reload: 为 True 时重新校验并读取提示词文件。

    Returns:
        当前生效提示词 YAML 的深拷贝字典。
    """
    selection = get_prompt_selection(force_reload=force_reload)
    return deepcopy(selection.data)


def load_llm_provider_test_prompts(
    *,
    force_reload: bool = False,
    prompt_dir: Path | None = None,
) -> dict[str, str]:
    """加载 LLM Provider 接口测试提示词，必要时仅回退该分组到默认配置。

    Args:
        force_reload: 为 True 时重新校验并读取提示词文件。
        prompt_dir: 提示词目录；为空时使用当前模块所在目录。

    Returns:
        可用于接口探测的提示词字典。

    Raises:
        PromptConfigError: 默认提示词文件中的测试分组不可读取或校验失败时抛出。
    """
    if prompt_dir is None:
        selection = get_prompt_selection(force_reload=force_reload)
        default_path = DEFAULT_PROMPT_PATH
    else:
        selection = resolve_prompt_selection(prompt_dir, emit_warning=False)
        default_path = Path(prompt_dir) / DEFAULT_PROMPT_FILENAME

    if not selection.is_default:
        try:
            return _extract_valid_prompt_section(
                selection.data,
                source_path=selection.path,
                section_name=LLM_PROVIDER_TEST_PROMPT_NAME,
                required_keys=REQUIRED_LLM_PROVIDER_TEST_PROMPT_KEYS,
            )
        except PromptConfigError as exc:
            # 自定义提示词可只覆盖业务创作部分，测试提示词坏掉时只降级这个分组。
            logger.warning("LLM Provider 测试提示词不可用，将回退默认分组: %s", exc)

    default_data = _read_yaml_mapping(default_path)
    return _extract_valid_prompt_section(
        default_data,
        source_path=default_path,
        section_name=LLM_PROVIDER_TEST_PROMPT_NAME,
        required_keys=REQUIRED_LLM_PROVIDER_TEST_PROMPT_KEYS,
    )


def main() -> int:
    """命令行入口：校验并打印当前生效的提示词文件。

    Args:
        无。

    Returns:
        进程退出码，0 表示默认或自定义提示词至少有一个可用。
    """
    selection = resolve_prompt_selection()
    source = "默认配置" if selection.is_default else "自定义配置"
    print(f"当前提示词文件: {selection.path} ({source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
