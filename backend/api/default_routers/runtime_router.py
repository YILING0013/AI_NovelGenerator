"""不写入项目配置的运行中日志开关。"""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from backend.runtime import (
    get_backend_log_level,
    is_backend_debug_enabled,
    set_backend_debug_enabled,
)

router = APIRouter(prefix="/api/runtime", tags=["runtime"])


class DebugLoggingRequest(BaseModel):
    """启动器提交的调试日志开关。"""

    model_config = ConfigDict(extra="forbid", strict=True)
    debug: bool


@router.get("/logging")
async def get_logging_state() -> dict[str, bool | str]:
    """读取当前进程的日志开关。

    Returns:
        调试开关和当前应用日志级别。
    """
    return {"debug": is_backend_debug_enabled(), "level": get_backend_log_level()}


@router.put("/logging")
async def update_logging_state(request: DebugLoggingRequest) -> dict[str, bool | str]:
    """立即调整当前进程的日志输出。

    Args:
        request: 要生效的调试日志开关。

    Returns:
        已生效的调试开关和日志级别。
    """
    set_backend_debug_enabled(request.debug)
    return {"debug": is_backend_debug_enabled(), "level": get_backend_log_level()}
