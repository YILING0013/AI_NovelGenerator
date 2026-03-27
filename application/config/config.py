from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any, Dict

import yaml

CONFIG_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config_default.yaml"
CONFIG_PATH = CONFIG_DIR / "config.yaml"

_FALLBACK_DEFAULT_CONFIG: Dict[str, Any] = {
    "mongodb_url": "mongodb://localhost:27017",
    "mongo_database_name": "my_database",
    "mongo_timeout_ms": 5000,
}

_config_lock = RLock()
_cached_config: Dict[str, Any] | None = None
_cached_mtimes: tuple[float | None, float | None] | None = None


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


def _merge_dicts(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并两个配置字典，后者覆盖前者。"""
    merged = deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
            continue
        merged[key] = value
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
        runtime_config = _merge_dicts(default_config, _read_yaml(CONFIG_PATH))

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
        current_config = load_config(force_reload=True)
        next_config = _merge_dicts(current_config, updates)
        _write_yaml(CONFIG_PATH, next_config)

        global _cached_config, _cached_mtimes
        _cached_config = next_config
        _cached_mtimes = (_get_mtime(DEFAULT_CONFIG_PATH), _get_mtime(CONFIG_PATH))
        return deepcopy(next_config)