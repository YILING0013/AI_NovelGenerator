"""读取随程序发布的完整默认任务图。"""

from __future__ import annotations

import json
from pathlib import Path

from backend.services.task_flows.contracts import Flow
from backend.services.task_flows.registry import TASKS


DEFAULT_DIR = Path(__file__).with_name("defaults")


def builtin_flow(task: str) -> Flow:
    """读取可恢复的随程序发布的默认方案。

    Args:
        task: 已有业务任务标识。
    Returns:
        含完整提示词的独立流程对象。
    """
    if task not in TASKS:
        raise KeyError(task)
    data = json.loads((DEFAULT_DIR / f"{task}.json").read_text(encoding="utf-8"))
    for node in data["nodes"]:
        config = node["config"]
        for key in ("prompt", "schema_prompt", "text_prompt"):
            reference = config.pop(f"{key}_file", None)
            if reference:
                config[key] = (DEFAULT_DIR / reference).read_text(encoding="utf-8")
    return Flow.model_validate(data)
