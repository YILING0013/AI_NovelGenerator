"""启动器的本机端口设置读写。"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

SETTINGS_VERSION = 1
_SETTINGS_LOCK = threading.RLock()


@dataclass(frozen=True)
class LauncherSettings:
    """启动器需要持久化的前后端端口。"""

    backend_port: int
    frontend_port: int


def get_launcher_settings_path() -> Path:
    """返回当前项目专属的启动器设置文件路径。

    Args:
        无。

    Returns:
        项目 user_data/config 下的 JSON 路径。
    """
    from backend.storage import CONFIG_DIR
    return CONFIG_DIR / "launcher_settings.json"


def validate_launcher_port(value: object, label: str) -> int:
    """把输入转换为有效的 TCP 端口。

    Args:
        value: 输入框、环境变量或 JSON 中读取的端口值。
        label: 用于错误提示的字段名称。

    Returns:
        位于 1 到 65535 之间的整数端口。

    Raises:
        ValueError: 输入不是整数或超出有效端口范围。
    """
    if isinstance(value, bool):
        raise ValueError(f"{label}必须是 1 到 65535 之间的整数")

    try:
        port = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是 1 到 65535 之间的整数") from exc

    if not 1 <= port <= 65535:
        raise ValueError(f"{label}必须位于 1 到 65535 之间")
    return port


def validate_launcher_settings(backend_port: object, frontend_port: object) -> LauncherSettings:
    """校验前后端端口并生成不可变设置对象。

    Args:
        backend_port: 后端监听端口。
        frontend_port: 前端监听端口。

    Returns:
        已完成范围和冲突校验的启动器设置。

    Raises:
        ValueError: 任一端口无效，或两个服务配置了相同端口。
    """
    backend = validate_launcher_port(backend_port, "后端端口")
    frontend = validate_launcher_port(frontend_port, "前端端口")
    if backend == frontend:
        raise ValueError("前端端口与后端端口不能相同")
    return LauncherSettings(backend_port=backend, frontend_port=frontend)


def load_launcher_settings(
    default_backend_port: int,
    default_frontend_port: int,
    path: Path | None = None,
) -> tuple[LauncherSettings, str | None]:
    """读取本机启动器设置，损坏时保留原文件并回退默认值。

    Args:
        default_backend_port: 没有可用设置时采用的后端端口。
        default_frontend_port: 没有可用设置时采用的前端端口。
        path: 可选的自定义设置路径，主要供测试使用。

    Returns:
        设置对象与可选警告；成功加载或文件不存在时警告为 None。
    """
    defaults = validate_launcher_settings(default_backend_port, default_frontend_port)
    settings_path = path or get_launcher_settings_path()
    try:
        with _SETTINGS_LOCK:
            if not settings_path.exists():
                return defaults, None
            payload = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("配置根节点必须是 JSON 对象")
        if payload.get("version") != SETTINGS_VERSION:
            raise ValueError("配置版本不受支持")
        settings = validate_launcher_settings(payload.get("backend_port"), payload.get("frontend_port"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        warning = f"端口设置读取失败，已回退默认值：{exc}"
        return defaults, warning
    return settings, None


def save_launcher_settings(settings: LauncherSettings, path: Path | None = None) -> Path:
    """以原子替换方式保存启动器端口设置。

    Args:
        settings: 已校验的端口设置。
        path: 可选的自定义设置路径，主要供测试使用。

    Returns:
        成功写入的设置文件路径。

    Raises:
        OSError: 创建目录、写入或替换设置文件失败。
        ValueError: 设置中的端口无效或冲突。
    """
    validated = validate_launcher_settings(settings.backend_port, settings.frontend_port)
    settings_path = path or get_launcher_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = settings_path.with_name(f"{settings_path.name}.{os.getpid()}.tmp")
    payload = {
        "version": SETTINGS_VERSION,
        "backend_port": validated.backend_port,
        "frontend_port": validated.frontend_port,
    }

    try:
        with _SETTINGS_LOCK:
            with temp_path.open("w", encoding="utf-8", newline="\n") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, settings_path)
    except Exception:
        # 仅清理本次写入使用的明确临时文件，旧设置始终保持不变。
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return settings_path
