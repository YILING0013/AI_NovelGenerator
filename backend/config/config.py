from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
from threading import RLock
from typing import Any, Dict
from urllib.parse import urlsplit, urlunsplit

import yaml

CONFIG_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config_default.yaml"
CONFIG_PATH = CONFIG_DIR / "config.yaml"

_FALLBACK_DEFAULT_CONFIG: Dict[str, Any] = {
    "mongodb_url": "mongodb://localhost:27017",
    "mongo_database_name": "my_database",
    "mongo_timeout_ms": 5000,
    "mongo_transaction_mode": "auto",
}

_config_lock = RLock()
_cached_config: Dict[str, Any] | None = None
_cached_mtimes: tuple[float | None, float | None] | None = None
_REPLACE_DICT_PATHS: set[tuple[str, ...]] = {
    ("llm", "providers"),
}
_KNOWN_WORKFLOW_STEPS: dict[str, tuple[str, ...]] = {
    "create_novel_by_ai": (
        "expand_idea_to_full_novel_story",
        "extract_idea",
        "core_seed",
        "novel_meta",
    ),
    "create_factions_by_ai": (
        "create_core_factions",
    ),
}
_PROVIDER_RENAMES_KEY = "_provider_renames"
_API_VERSION_RE = re.compile(r"^v\d+(?:[a-z0-9._-]+)?$", re.IGNORECASE)
_OPENAI_ENDPOINT_SUFFIXES: tuple[tuple[str, ...], ...] = (
    ("chat", "completions"),
    ("responses",),
    ("response",),
    ("completions",),
    ("embeddings",),
    ("images",),
    ("audio", "speech"),
    ("audio", "transcriptions"),
    ("audio", "translations"),
    ("moderations",),
    ("models",),
    ("files",),
    ("batches",),
    ("uploads",),
    ("assistants",),
    ("threads",),
    ("vector_stores",),
    ("fine_tuning", "jobs"),
)
_CLAUDE_ENDPOINT_SUFFIXES: tuple[tuple[str, ...], ...] = (
    ("v1", "messages"),
    ("v1", "complete"),
    ("v1", "completions"),
    ("messages",),
    ("complete",),
    ("completions",),
)


def _is_api_version_segment(segment: str) -> bool:
    """判断路径片段是否为 API 版本号。"""
    return bool(_API_VERSION_RE.fullmatch(segment))


def _split_base_url(base_url: str) -> tuple[str, list[str]]:
    """拆分基地址，保留协议/主机并返回路径片段。"""
    trimmed = base_url.strip()
    if not trimmed:
        return "", []

    if "://" not in trimmed:
        return "", [segment for segment in trimmed.split("/") if segment]

    parsed = urlsplit(trimmed)
    prefix = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    segments = [segment for segment in parsed.path.split("/") if segment]
    return prefix, segments


def _join_base_url(prefix: str, segments: list[str]) -> str:
    """按统一格式重新组装基地址。"""
    path = "/".join(segments)
    if prefix:
        return f"{prefix}/{path}" if path else prefix
    return path


def _trim_matching_suffixes(segments: list[str], suffixes: tuple[tuple[str, ...], ...]) -> list[str]:
    """反复移除已知的 API 端点后缀。"""
    remaining = list(segments)
    while remaining:
        lower_segments = [segment.lower() for segment in remaining]
        matched = False
        for suffix in suffixes:
            if len(remaining) < len(suffix):
                continue
            if tuple(lower_segments[-len(suffix) :]) != suffix:
                continue
            del remaining[-len(suffix) :]
            matched = True
            break
        if not matched:
            break
    return remaining


def _normalize_openai_base_url(base_url: str) -> str:
    """OpenAI 兼容接口配置只保存服务根地址，运行时再补 API 版本路径。"""
    prefix, segments = _split_base_url(base_url)
    segments = _trim_matching_suffixes(segments, _OPENAI_ENDPOINT_SUFFIXES)

    # OpenAI SDK 调用时会使用 /chat/completions 等相对路径，这里只保留用户网关根路径。
    while segments and _is_api_version_segment(segments[-1]):
        segments.pop()

    return _join_base_url(prefix, segments)


def _normalize_claude_base_url(base_url: str) -> str:
    """Claude SDK 需要服务根地址，SDK 会自行追加 /v1/messages。"""
    prefix, segments = _split_base_url(base_url)
    segments = _trim_matching_suffixes(segments, _CLAUDE_ENDPOINT_SUFFIXES)

    while segments and (
        _is_api_version_segment(segments[-1])
        or segments[-1].lower() in {"messages", "complete", "completions"}
    ):
        segments.pop()

    return _join_base_url(prefix, segments)


def _normalize_gemini_base_url(base_url: str) -> str:
    """Gemini SDK 需要服务根地址，版本与 models 路径由 SDK 处理。"""
    prefix, segments = _split_base_url(base_url)
    lowered = [segment.lower() for segment in segments]

    version_index = next((idx for idx, segment in enumerate(lowered) if _is_api_version_segment(segment)), None)
    projects_index = next((idx for idx, segment in enumerate(lowered) if segment == "projects"), None)
    locations_index = next((idx for idx, segment in enumerate(lowered) if segment == "locations"), None)
    publishers_index = next((idx for idx, segment in enumerate(lowered) if segment == "publishers"), None)
    models_index = next((idx for idx, segment in enumerate(lowered) if segment == "models"), None)

    cut_candidates: list[int] = []
    if version_index is not None:
        cut_candidates.append(version_index)
    if publishers_index is not None:
        cut_candidates.append(publishers_index)
    if models_index is not None:
        cut_candidates.append(models_index)
    if (
        projects_index is not None
        and locations_index is not None
        and locations_index > projects_index
        and (publishers_index is not None or models_index is not None)
    ):
        cut_candidates.append(projects_index)

    if cut_candidates:
        segments = segments[: min(cut_candidates)]

    return _join_base_url(prefix, segments)


def _normalize_provider_base_url(provider_type: Any, base_url: Any) -> str:
    """按 Provider 类型清洗用户输入的 API 基地址。"""
    if not isinstance(base_url, str):
        return ""

    trimmed = base_url.strip()
    if not trimmed:
        return ""

    provider_type_str = str(provider_type).strip().lower()
    if provider_type_str == "gemini":
        return _normalize_gemini_base_url(trimmed)
    if provider_type_str == "claude":
        return _normalize_claude_base_url(trimmed)
    return _normalize_openai_base_url(trimmed)


def _normalize_step_timeout(value: Any) -> int | None:
    """将流程步骤超时配置归一化为正整数秒。

    Args:
        value: 原始 YAML/JSON 超时字段。

    Returns:
        正整数秒；空值或非法值返回 None，表示继承 Provider 超时。
    """
    if value in (None, ""):
        return None
    try:
        timeout_seconds = int(value)
    except (TypeError, ValueError):
        return None
    return timeout_seconds if timeout_seconds > 0 else None


def _normalize_workflow_step_config(step_config: Any) -> Dict[str, Any]:
    """归一化单个流程步骤配置。

    Args:
        step_config: 原始步骤配置，通常包含 provider 与 timeout_seconds。

    Returns:
        可供前端和 workflow_service 直接使用的步骤配置。
    """
    if not isinstance(step_config, dict):
        step_config = {}
    return {
        "provider": str(step_config.get("provider") or "").strip(),
        "timeout_seconds": _normalize_step_timeout(step_config.get("timeout_seconds")),
    }


def _normalize_workflow_config(
    workflow_name: str,
    workflow_config: Any,
    global_default_provider: str,
) -> Dict[str, Any]:
    """归一化单个工作流配置并补齐内置步骤模板。

    Args:
        workflow_name: 工作流名称。
        workflow_config: 原始工作流配置。
        global_default_provider: 全局默认 Provider，用作新建工作流默认值。

    Returns:
        包含 default_provider 与 steps 的工作流配置。
    """
    if not isinstance(workflow_config, dict):
        workflow_config = {}

    raw_steps = workflow_config.get("steps")
    if not isinstance(raw_steps, dict):
        raw_steps = {}

    # 已实现模块的流程由程序固定定义，旧配置里的手动步骤不再进入运行时配置。
    step_names = list(_KNOWN_WORKFLOW_STEPS.get(workflow_name, raw_steps.keys()))
    return {
        "default_provider": str(workflow_config.get("default_provider") or global_default_provider or "").strip(),
        "steps": {
            step_name: _normalize_workflow_step_config(raw_steps.get(step_name))
            for step_name in step_names
        },
    }


def _normalize_workflows(llm_config: Dict[str, Any]) -> None:
    """归一化 LLM 工作流映射，支持多流程独立 Provider 指派。

    Args:
        llm_config: LLM 配置段，会被原地更新。

    Returns:
        None。
    """
    workflows = llm_config.get("workflows")
    if not isinstance(workflows, dict):
        workflows = {}

    workflow_names = list(_KNOWN_WORKFLOW_STEPS.keys())
    global_default_provider = str(llm_config.get("default_provider") or "").strip()
    llm_config["workflows"] = {
        workflow_name: _normalize_workflow_config(
            workflow_name,
            workflows.get(workflow_name),
            global_default_provider,
        )
        for workflow_name in workflow_names
    }


def _rename_llm_references(llm_config: Dict[str, Any], old_alias: str, new_alias: str) -> None:
    """同步更新默认 Provider、格式审校 Provider 与工作流中的引用。"""
    if llm_config.get("default_provider") == old_alias:
        llm_config["default_provider"] = new_alias
    if llm_config.get("format_review_provider") == old_alias:
        llm_config["format_review_provider"] = new_alias

    workflows = llm_config.get("workflows")
    if not isinstance(workflows, dict):
        return

    for workflow in workflows.values():
        if not isinstance(workflow, dict):
            continue
        if workflow.get("default_provider") == old_alias:
            workflow["default_provider"] = new_alias

        steps = workflow.get("steps")
        if not isinstance(steps, dict):
            continue

        for step in steps.values():
            if isinstance(step, dict) and step.get("provider") == old_alias:
                step["provider"] = new_alias


def _extract_provider_rename_operations(updates: Dict[str, Any]) -> list[tuple[str, str]]:
    """提取前端提交的 Provider 重命名操作。"""
    raw_operations = updates.pop(_PROVIDER_RENAMES_KEY, None)
    if raw_operations in (None, []):
        return []
    if not isinstance(raw_operations, list):
        raise ValueError("Provider rename operations must be a list")

    operations: list[tuple[str, str]] = []
    for operation in raw_operations:
        if not isinstance(operation, dict):
            raise ValueError("Each provider rename operation must be a mapping")

        old_alias = str(operation.get("from") or operation.get("old_alias") or "").strip()
        new_alias = str(operation.get("to") or operation.get("new_alias") or "").strip()
        if not old_alias or not new_alias:
            raise ValueError("Provider rename operations must include both source and target aliases")

        operations.append((old_alias, new_alias))

    return operations


def _apply_provider_rename_operations(config: Dict[str, Any], operations: list[tuple[str, str]]) -> Dict[str, Any]:
    """将 Provider 重命名操作应用到配置与所有引用字段。"""
    if not operations:
        return deepcopy(config)

    updated = deepcopy(config)
    llm_config = updated.get("llm")
    if not isinstance(llm_config, dict):
        return updated

    providers = llm_config.get("providers")
    for old_alias, new_alias in operations:
        if old_alias == new_alias:
            continue

        if isinstance(providers, dict) and old_alias in providers:
            if new_alias in providers and new_alias != old_alias:
                raise ValueError(f"Provider rename target already exists: {new_alias}")

            renamed_providers: Dict[str, Any] = {}
            for alias, provider in providers.items():
                renamed_providers[new_alias if alias == old_alias else alias] = provider
            providers = renamed_providers
            llm_config["providers"] = providers

        _rename_llm_references(llm_config, old_alias, new_alias)

    return updated


def _normalize_config_tree(config_data: Dict[str, Any]) -> Dict[str, Any]:
    """统一清洗配置结构，确保返回给前后端的配置可直接使用。"""
    normalized = deepcopy(config_data)
    normalized.pop(_PROVIDER_RENAMES_KEY, None)

    llm_config = normalized.get("llm")
    if not isinstance(llm_config, dict):
        return normalized

    providers = llm_config.get("providers")
    if not isinstance(providers, dict):
        return normalized

    normalized_providers: Dict[str, Any] = {}
    for alias, provider in providers.items():
        if not isinstance(provider, dict):
            normalized_providers[alias] = provider
            continue

        normalized_provider = deepcopy(provider)
        normalized_provider["base_url"] = _normalize_provider_base_url(
            normalized_provider.get("type", "openai"),
            normalized_provider.get("base_url", ""),
        )
        normalized_providers[alias] = normalized_provider

    llm_config["providers"] = normalized_providers
    _normalize_workflows(llm_config)
    return normalized


def _get_mtime(path: Path) -> float | None:
    """返回配置文件的最后修改时间，不存在时返回None。"""
    if not path.exists():
        return None
    return path.stat().st_mtime


def _read_yaml(path: Path) -> Dict[str, Any]:
    """读取YAML文件并确保返回字典结构。"""
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a mapping: {path}")

    return data


def _write_yaml(path: Path, data: Dict[str, Any]) -> None:
    """将字典配置写入指定YAML文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)


def _merge_dicts(base: Dict[str, Any], updates: Dict[str, Any], path: tuple[str, ...] = ()) -> Dict[str, Any]:
    """递归合并两个配置字典，后者覆盖前者。

    某些用户可管理的映射配置需要整段替换，避免运行时配置与默认配置
    深合并后把已删除条目重新补回。
    """
    merged = deepcopy(base)
    for key, value in updates.items():
        current_path = (*path, key)
        if current_path in _REPLACE_DICT_PATHS and isinstance(value, dict):
            merged[key] = deepcopy(value)
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value, current_path)
            continue
        merged[key] = deepcopy(value)
    return merged


def ensure_config_files() -> None:
    """确保默认配置和运行配置文件存在。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not DEFAULT_CONFIG_PATH.exists():
        _write_yaml(DEFAULT_CONFIG_PATH, _FALLBACK_DEFAULT_CONFIG)

    if not CONFIG_PATH.exists():
        default_config = _read_yaml(DEFAULT_CONFIG_PATH)
        _write_yaml(CONFIG_PATH, default_config)


def load_config(force_reload: bool = False) -> Dict[str, Any]:
    """加载当前生效配置，并在文件变化时刷新缓存。"""
    global _cached_config, _cached_mtimes

    ensure_config_files()
    current_mtimes = (_get_mtime(DEFAULT_CONFIG_PATH), _get_mtime(CONFIG_PATH))

    with _config_lock:
        if not force_reload and _cached_config is not None and _cached_mtimes == current_mtimes:
            return deepcopy(_cached_config)

        default_config = _read_yaml(DEFAULT_CONFIG_PATH)
        runtime_config = _normalize_config_tree(_merge_dicts(default_config, _read_yaml(CONFIG_PATH)))

        _cached_config = runtime_config
        _cached_mtimes = current_mtimes
        return deepcopy(runtime_config)


def get_all_config(force_reload: bool = False) -> Dict[str, Any]:
    """返回当前全部生效配置。"""
    return load_config(force_reload=force_reload)


def get_config_value(key: str, default: Any = None, force_reload: bool = False) -> Any:
    """按键获取单个配置项，不存在时返回默认值。"""
    return load_config(force_reload=force_reload).get(key, default)


def update_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """合并更新运行配置文件并返回最新生效配置。"""
    if not isinstance(updates, dict):
        raise ValueError("Config updates must be a mapping")

    if not updates:
        raise ValueError("Config updates cannot be empty")

    with _config_lock:
        sanitized_updates = deepcopy(updates)
        rename_operations = _extract_provider_rename_operations(sanitized_updates)
        current_config = load_config(force_reload=True)
        current_config = _apply_provider_rename_operations(current_config, rename_operations)
        sanitized_updates = _apply_provider_rename_operations(sanitized_updates, rename_operations)
        next_config = _normalize_config_tree(_merge_dicts(current_config, sanitized_updates))
        _write_yaml(CONFIG_PATH, next_config)

        global _cached_config, _cached_mtimes
        _cached_config = next_config
        _cached_mtimes = (_get_mtime(DEFAULT_CONFIG_PATH), _get_mtime(CONFIG_PATH))
        return deepcopy(next_config)
