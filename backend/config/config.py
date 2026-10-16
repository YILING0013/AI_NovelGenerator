from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import os
from pathlib import Path
import re
import secrets
import logging
from threading import RLock
from typing import Any, Dict
from urllib.parse import urlsplit, urlunsplit

import yaml

logger = logging.getLogger(__name__)

from backend.storage import CONFIG_DIR

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config_default.yaml")
CONFIG_PATH = CONFIG_DIR / "config.yaml"

_config_lock = RLock()
_cached_config: Dict[str, Any] | None = None
_cached_mtimes: tuple[float | None, float | None] | None = None
_REPLACE_DICT_PATHS: set[tuple[str, ...]] = {
    ("llm", "providers"),
}
_PROVIDER_RENAMES_KEY = "_provider_renames"
_API_VERSION_RE = re.compile(r"^v\d+(?:[a-z0-9._-]+)?$", re.IGNORECASE)
_PROVIDER_ALIAS_INVALID_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
_MASKED_SECRET_RE = re.compile(r"^(?:\*{3,}|•{3,}|已配置|configured)$", re.IGNORECASE)
_SECRET_UPDATE_ACTIONS = {"preserve", "replace", "clear"}
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


@dataclass(frozen=True, slots=True)
class ConfigSnapshot:
    """保存一次配置提交前的有效配置与运行文件原始字节。"""

    effective_config: Dict[str, Any]
    runtime_bytes: bytes


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


def _rename_llm_references(llm_config: Dict[str, Any], old_alias: str, new_alias: str) -> None:
    """同步更新默认 Provider 和格式审校 Provider。"""
    if llm_config.get("default_provider") == old_alias:
        llm_config["default_provider"] = new_alias
    if llm_config.get("format_review_provider") == old_alias:
        llm_config["format_review_provider"] = new_alias


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

        old_alias = str(operation.get("from") or "").strip()
        new_alias = str(operation.get("to") or "").strip()
        if not old_alias or not new_alias:
            raise ValueError("Provider rename operations must include both source and target aliases")

        operations.append((old_alias, new_alias))

    return operations


def validate_provider_alias(alias: str) -> str:
    """校验直接用于配置和方案引用的 Provider 名称。

    Args:
        alias: 已去除首尾空白的名称。

    Returns:
        通过长度、日志字符及对象键检查的原名称。
    """
    if (not 1 <= len(alias) <= 100 or alias != alias.strip()
            or _PROVIDER_ALIAS_INVALID_RE.search(alias)
            or alias in {"__proto__", "constructor", "prototype"}):
        raise ValueError("Provider 名称须为 1–100 个字符，不能有首尾空白、控制字符或使用保留名称")
    return alias


def _apply_provider_rename_operations(config: Dict[str, Any], operations: list[tuple[str, str]]) -> Dict[str, Any]:
    """将 Provider 重命名操作应用到配置与所有引用字段。

    Args:
        config: 包含 LLM Provider 与工作流引用的配置树。
        operations: 待执行的旧别名到新别名操作。

    Returns:
        Provider 键及全部引用同步更新后的深拷贝。
    """
    if not operations:
        return deepcopy(config)

    updated = deepcopy(config)
    llm_config = updated.get("llm")
    if not isinstance(llm_config, dict):
        return updated

    providers = llm_config.get("providers")
    for old_alias, new_alias in operations:
        validate_provider_alias(old_alias)
        validate_provider_alias(new_alias)
        if old_alias == new_alias:
            continue

        if not isinstance(providers, dict) or old_alias not in providers:
            raise ValueError(f"Provider rename source does not exist: {old_alias}")
        if new_alias in providers:
            raise ValueError(f"Provider rename target already exists: {new_alias}")

        renamed_providers: Dict[str, Any] = {}
        for alias, provider in providers.items():
            renamed_providers[new_alias if alias == old_alias else alias] = provider
        providers = renamed_providers
        llm_config["providers"] = providers

        _rename_llm_references(llm_config, old_alias, new_alias)

    return updated


def _normalize_config_tree(config_data: Dict[str, Any]) -> Dict[str, Any]:
    """统一清洗配置结构，确保返回给前后端的配置可直接使用。

    Args:
        config_data: 默认配置与运行配置合并后的配置树。

    Returns:
        Provider 地址与工作流均完成规范化的深拷贝。
    """
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
    """将配置通过同目录临时文件原子写入 YAML。

    Args:
        path: 目标 YAML 路径。
        data: 待序列化的完整配置映射。

    Returns:
        无。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp")
    try:
        with temp_path.open("x", encoding="utf-8", newline="\n") as file:
            yaml.safe_dump(data, file, allow_unicode=True, sort_keys=False)
            # 先把 Python 与操作系统缓冲区全部刷入磁盘，再执行同目录原子替换。
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    finally:
        # 只清理由本次调用生成且尚未被替换的明确临时文件。
        if temp_path.exists():
            temp_path.unlink()


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    """把既有配置文件字节逐字节原子恢复到目标路径。

    Args:
        path: 需要恢复的明确 YAML 文件路径。
        data: 提交前读取的原始文件字节。

    Returns:
        无。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.rollback.tmp")
    try:
        with temp_path.open("xb") as file:
            file.write(data)
            # 回滚也必须先刷盘再替换，避免恢复动作本身留下半个 YAML。
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _get_config_version(config_data: Dict[str, Any]) -> int:
    """读取配置中的有效版本。

    Args:
        config_data: 当前完整配置。

    Returns:
        大于等于 1 的配置版本。
    """
    value = config_data["config_version"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("config_version 必须是正整数")
    return value


def project_config_for_read(config_data: Dict[str, Any]) -> Dict[str, Any]:
    """生成可安全返回浏览器的脱敏配置投影。

    Args:
        config_data: 服务端当前生效的完整配置。

    Returns:
        Mongo URI 与 Provider 密钥已脱敏，并保留系统提示词及配置版本的深拷贝。
    """
    projected = deepcopy(config_data)
    mongo_url = projected.pop("mongodb_url", None)
    projected["mongodb_url_configured"] = bool(
        isinstance(mongo_url, str) and mongo_url.strip()
    )
    llm_config = projected.get("llm")
    providers = llm_config.get("providers") if isinstance(llm_config, dict) else None
    if isinstance(providers, dict):
        for provider in providers.values():
            if not isinstance(provider, dict):
                continue
            api_key = provider.get("api_key")
            provider["api_key"] = None
            provider["api_key_configured"] = bool(
                isinstance(api_key, str) and api_key.strip()
            )
    projected["config_version"] = _get_config_version(config_data)
    return projected


def _validate_provider_references(config_data: Dict[str, Any]) -> None:
    """校验 Provider 别名和默认引用。

    Args:
        config_data: 已完成合并与归一化的候选配置。

    Returns:
        无。

    Raises:
        ValueError: Provider 别名非法或默认/步骤引用不存在。
    """
    llm_config = config_data.get("llm")
    if not isinstance(llm_config, dict):
        raise ValueError("llm 必须为配置对象")
    providers = llm_config.get("providers")
    if not isinstance(providers, dict):
        raise ValueError("llm.providers 必须为配置对象")
    aliases = set(providers)
    for alias in aliases:
        validate_provider_alias(alias)

    references: list[tuple[str, Any]] = [
        ("llm.default_provider", llm_config.get("default_provider")),
        ("llm.format_review_provider", llm_config.get("format_review_provider")),
    ]
    for field_path, value in references:
        alias = str(value or "").strip()
        if alias and alias not in aliases:
            raise ValueError(f"{field_path} 引用了不存在的 Provider: {alias}")


def _apply_secret_updates(
    current_config: Dict[str, Any],
    updates: Dict[str, Any],
) -> Dict[str, Any]:
    """把 Mongo URI 与 Provider 密钥动作转换为可合并的服务端值。

    Args:
        current_config: 当前完整配置，用于 preserve 动作取回已保存密钥。
        updates: 浏览器提交的配置 patch，会在副本上转换。

    Returns:
        可安全交给配置合并器的更新副本。
    """
    prepared = deepcopy(updates)
    raw_mongo_update = prepared.pop("mongodb_url_update", None)
    legacy_mongo_url = prepared.pop("mongodb_url", None)
    prepared.pop("mongodb_url_configured", None)
    if raw_mongo_update is None:
        if legacy_mongo_url not in (None, ""):
            raise ValueError("mongodb_url 必须通过 mongodb_url_update.replace 显式提交")
        raw_mongo_update = {"action": "preserve"}
    if not isinstance(raw_mongo_update, dict):
        raise ValueError("mongodb_url_update 必须为对象")
    mongo_action = str(raw_mongo_update.get("action") or "preserve").strip().lower()
    mongo_value = raw_mongo_update.get("value")
    if mongo_action not in _SECRET_UPDATE_ACTIONS:
        raise ValueError("mongodb_url_update.action 必须为 preserve、replace 或 clear")
    if mongo_action == "replace":
        if not isinstance(mongo_value, str) or not mongo_value.strip():
            raise ValueError("mongodb_url_update.replace 必须携带非空连接地址")
        if _MASKED_SECRET_RE.fullmatch(mongo_value.strip()):
            raise ValueError("不能把掩码占位符保存为 MongoDB 连接地址")
        prepared["mongodb_url"] = mongo_value.strip()
    elif mongo_value not in (None, ""):
        raise ValueError(f"mongodb_url_update.{mongo_action} 不能携带值")
    elif mongo_action == "clear":
        prepared["mongodb_url"] = ""
    else:
        prepared["mongodb_url"] = current_config.get("mongodb_url", "")

    llm_updates = prepared.get("llm")
    providers = llm_updates.get("providers") if isinstance(llm_updates, dict) else None
    current_providers = (
        current_config.get("llm", {}).get("providers", {})
        if isinstance(current_config.get("llm"), dict)
        else {}
    )
    if not isinstance(providers, dict):
        return prepared

    for alias, provider_update in providers.items():
        if not isinstance(provider_update, dict):
            raise ValueError(f"Provider 配置必须为对象: {alias}")
        raw_secret_update = provider_update.pop("api_key_update", None)
        legacy_api_key = provider_update.pop("api_key", None)
        provider_update.pop("api_key_configured", None)

        if raw_secret_update is None:
            if legacy_api_key not in (None, ""):
                raise ValueError("api_key 明文必须通过 api_key_update.replace 显式提交")
            raw_secret_update = {"action": "preserve"}
        if not isinstance(raw_secret_update, dict):
            raise ValueError("api_key_update 必须为对象")
        action = str(raw_secret_update.get("action") or "preserve").strip().lower()
        if action not in _SECRET_UPDATE_ACTIONS:
            raise ValueError("api_key_update.action 必须为 preserve、replace 或 clear")

        current_provider = current_providers.get(alias, {}) if isinstance(current_providers, dict) else {}
        current_secret = current_provider.get("api_key", "") if isinstance(current_provider, dict) else ""
        if action == "preserve":
            if raw_secret_update.get("value") not in (None, ""):
                raise ValueError("preserve 动作不能携带密钥值")
            provider_update["api_key"] = current_secret
        elif action == "clear":
            if raw_secret_update.get("value") not in (None, ""):
                raise ValueError("clear 动作不能携带密钥值")
            provider_update["api_key"] = ""
        else:
            value = raw_secret_update.get("value")
            if not isinstance(value, str) or not value.strip():
                raise ValueError("replace 动作必须携带非空密钥")
            if _MASKED_SECRET_RE.fullmatch(value.strip()):
                raise ValueError("不能把掩码占位符保存为 API Key")
            provider_update["api_key"] = value.strip()
        # 别名集合仍整体替换以支持删除；每个 Provider 的窄 patch 保留未编辑的旧设置。
        providers[alias] = {**deepcopy(current_provider), **provider_update}
    return prepared


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
    """确保默认配置和运行配置文件存在。

    Args:
        无。

    Returns:
        两个配置文件可读取后结束。
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not DEFAULT_CONFIG_PATH.exists():
        raise FileNotFoundError("内置默认配置缺失，请重新获取完整程序。")

    if not CONFIG_PATH.exists():
        default_config = _read_yaml(DEFAULT_CONFIG_PATH)
        _write_yaml(CONFIG_PATH, default_config)


def load_config(force_reload: bool = False) -> Dict[str, Any]:
    """加载当前生效配置，并在文件变化时刷新缓存。

    Args:
        force_reload: 是否忽略缓存并重新读取配置文件。

    Returns:
        默认配置和运行配置归一化合并后的深拷贝。
    """
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
    """返回当前全部生效配置。

    Args:
        force_reload: 是否强制重新读取文件。

    Returns:
        仅供服务端使用的完整配置深拷贝。
    """
    return load_config(force_reload=force_reload)


def get_config_read_model(force_reload: bool = False) -> Dict[str, Any]:
    """返回可发送给非受信客户端的脱敏配置。

    Args:
        force_reload: 是否忽略缓存并重新读取配置文件。

    Returns:
        含 config_version、但不含任何 Provider 密钥明文的配置投影。
    """
    return project_config_for_read(load_config(force_reload=force_reload))


def get_config_value(key: str, default: Any = None, force_reload: bool = False) -> Any:
    """按键获取单个配置项，不存在时返回默认值。

    Args:
        key: 顶层配置键。
        default: 键不存在时返回的值。
        force_reload: 是否强制重新读取文件。

    Returns:
        对应配置值或调用方提供的默认值。
    """
    return load_config(force_reload=force_reload).get(key, default)


def capture_config_snapshot() -> ConfigSnapshot:
    """捕获依赖切换前可逐字节恢复的运行配置快照。

    Args:
        无。

    Returns:
        同时包含规范化有效配置和运行 YAML 原始字节的不可变快照。
    """
    with _config_lock:
        effective_config = load_config(force_reload=True)
        # 文件字节与有效配置在同一进程锁内捕获，供后续连接失败精确回滚。
        runtime_bytes = CONFIG_PATH.read_bytes()
        return ConfigSnapshot(
            effective_config=deepcopy(effective_config),
            runtime_bytes=runtime_bytes,
        )


def update_config(
    updates: Dict[str, Any],
    *,
    expected_config_version: int | None = None,
) -> Dict[str, Any]:
    """以版本校验和原子替换更新运行配置。

    Args:
        updates: 严格配置 patch、Provider 重命名与密钥动作。
        expected_config_version: 浏览器读取时获得的版本；缺失或漂移时拒绝覆盖。

    Returns:
        写入后重新读取并完成规范化的完整服务端配置。
    """
    global _cached_config, _cached_mtimes

    if not isinstance(updates, dict):
        raise ValueError("Config updates must be a mapping")

    if not updates:
        raise ValueError("Config updates cannot be empty")

    with _config_lock:
        sanitized_updates = deepcopy(updates)
        embedded_version = sanitized_updates.pop("expected_config_version", None)
        sanitized_updates.pop("config_version", None)
        requested_version = expected_config_version or embedded_version
        rename_operations = _extract_provider_rename_operations(sanitized_updates)
        current_config = load_config(force_reload=True)
        current_version = _get_config_version(current_config)
        if (
            isinstance(requested_version, bool)
            or not isinstance(requested_version, int)
            or requested_version != current_version
        ):
            raise ConfigVersionConflictError(
                "配置已被其他会话修改，请重载后合并当前草稿"
            )
        previous_config = deepcopy(current_config)
        renamed_config = _apply_provider_rename_operations(current_config, rename_operations)
        sanitized_updates = _apply_secret_updates(renamed_config, sanitized_updates)
        next_config = _normalize_config_tree(_merge_dicts(renamed_config, sanitized_updates))
        next_config["config_version"] = current_version + 1
        _validate_provider_references(next_config)
        previous_runtime_bytes = CONFIG_PATH.read_bytes()
        try:
            _write_yaml(CONFIG_PATH, next_config)

            # 原子替换后强制重读并比较规范内容，避免缓存或 YAML 序列化漂移。
            reloaded_config = _normalize_config_tree(
                _merge_dicts(_read_yaml(DEFAULT_CONFIG_PATH), _read_yaml(CONFIG_PATH))
            )
            if reloaded_config != next_config:
                raise RuntimeError("配置写入后的重读校验失败")
        except Exception as commit_exc:
            try:
                _write_bytes_atomic(CONFIG_PATH, previous_runtime_bytes)
            except Exception as restore_exc:
                logger.exception("配置提交失败后无法恢复原运行配置文件")
                _cached_config = previous_config
                _cached_mtimes = None
                raise ConfigCommitError("配置提交失败，且旧配置文件恢复失败") from restore_exc
            _cached_config = previous_config
            _cached_mtimes = (_get_mtime(DEFAULT_CONFIG_PATH), _get_mtime(CONFIG_PATH))
            raise ConfigCommitError("配置提交失败，旧配置已恢复") from commit_exc

        _cached_config = reloaded_config
        _cached_mtimes = (_get_mtime(DEFAULT_CONFIG_PATH), _get_mtime(CONFIG_PATH))
        return deepcopy(reloaded_config)


def restore_config_snapshot(
    config_snapshot: ConfigSnapshot,
) -> Dict[str, Any]:
    """在后续依赖刷新失败时原子恢复已知的旧配置快照。

    Args:
        config_snapshot: 保存前捕获的字节快照。

    Returns:
        恢复后强制重读的规范化配置。
    """
    global _cached_config, _cached_mtimes

    restored = _normalize_config_tree(deepcopy(config_snapshot.effective_config))
    with _config_lock:
        _write_bytes_atomic(CONFIG_PATH, config_snapshot.runtime_bytes)
        reloaded = _normalize_config_tree(
            _merge_dicts(_read_yaml(DEFAULT_CONFIG_PATH), _read_yaml(CONFIG_PATH))
        )
        if reloaded != restored:
            _cached_config = None
            _cached_mtimes = None
            raise RuntimeError("配置恢复后的重读校验失败")

        _cached_config = reloaded
        _cached_mtimes = (_get_mtime(DEFAULT_CONFIG_PATH), _get_mtime(CONFIG_PATH))
        return deepcopy(reloaded)


class ConfigVersionConflictError(ValueError):
    """配置版本漂移，调用方必须重载后再提交。"""


class ConfigCommitError(RuntimeError):
    """配置文件或依赖刷新失败，旧版本已尝试恢复。"""
