"""用不可变 JSON 修订保存方案，并用一次原子替换更新目录索引。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import lru_cache
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from typing import Any

from backend.storage import TASK_FLOWS_DIR

from .contracts import Flow, FlowConflictError, FlowRef
from .defaults import builtin_flow
from .graph import validate_flow


class FlowStore:
    """管理本地方案修订和每个任务的默认选择。"""

    def __init__(
        self, default_factory: Callable[[str], Flow] | None = None,
        root: str | Path | None = None,
    ) -> None:
        """选择存储目录，不在构造时写入文件。

        Args:
            default_factory: 首次打开任务时生成内置默认图的函数。
            root: 测试或调用方指定的目录，默认读取 TASK_FLOW_STORE_DIR。
        """
        self.root = Path(root or os.environ.get("TASK_FLOW_STORE_DIR") or
                         TASK_FLOWS_DIR)
        self.default_factory = default_factory
        self._thread_lock = RLock()

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True)
        with self._thread_lock, (self.root / ".lock").open("a+b") as lock_file:
            # 文件锁同时保护同一进程的多个实例和多个后端进程。
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0, os.SEEK_END)
                if lock_file.tell() == 0:
                    lock_file.write(b"0")
                    lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "nt":
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_index(self) -> dict[str, Any]:
        path = self.root / "index.json"
        if not path.exists():
            return {"version": 0, "flows": {}, "defaults": {}}
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def _atomic_write(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                             prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
                temporary = handle.name
                json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            # 只清理这次写入创建的一个明确临时文件。
            if temporary is not None and Path(temporary).exists():
                Path(temporary).unlink()

    def _read_flow(self, flow_id: str, revision: int) -> Flow:
        reference = FlowRef(id=flow_id, revision=revision)
        path = self.root / "flows" / reference.id / f"{reference.revision}.json"
        if not path.exists():
            raise KeyError(f"方案或修订不存在：{flow_id}@{revision}")
        with path.open(encoding="utf-8") as handle:
            return Flow.model_validate(json.load(handle))

    def list_flows(self, task: str | None = None) -> dict[str, Any]:
        """读取最新方案摘要和当前默认引用。

        Args:
            task: 仅列出此业务任务的方案；为空时列出全部已保存方案。

        Returns:
            包含 version、flows 摘要数组和 defaults 映射的目录快照。
        """
        index = self._read_index()
        summaries = []
        for flow_id, item in index["flows"].items():
            if task is not None and item["task"] != task:
                continue
            selected = index["defaults"].get(item["task"])
            is_default = selected is not None and selected["id"] == flow_id
            summaries.append({
                "id": flow_id, **item, "is_default": is_default,
                "default_revision": selected["revision"] if is_default else None,
            })
        summaries.sort(key=lambda item: (item["task"], item["name"], item["id"]))
        return {
            "version": index["version"], "flows": summaries,
            "defaults": {key: value for key, value in index["defaults"].items()
                         if task is None or key == task},
        }

    def get(self, flow_id: str, revision: int | None = None) -> Flow:
        """读取一份不可变方案修订。

        Args:
            flow_id: 方案 ID。
            revision: 指定修订；为空时读取最新修订。

        Returns:
            独立的方案模型。
        """
        index = self._read_index()
        if flow_id not in index["flows"]:
            raise KeyError(f"方案不存在：{flow_id}")
        return self._read_flow(flow_id, revision if revision is not None else index["flows"][flow_id]["revision"])

    def save(self, flow: Flow | dict[str, Any], expected_revision: int | None = None) -> Flow:
        """在版本仍匹配时保存一个新修订，不覆盖历史文件。

        Args:
            flow: 待保存的完整方案。
            expected_revision: 编辑时看到的最新修订；新建使用 0 或 None。

        Returns:
            带实际新修订号的方案。
        """
        flow = validate_flow(flow)
        with self._locked():
            index = self._read_index()
            current = index["flows"].get(flow.id)
            current_revision = current["revision"] if current else 0
            if (expected_revision or 0) != current_revision:
                raise FlowConflictError("方案已被其他页面修改，请重新打开后再保存")
            if current and current["task"] != flow.task:
                raise ValueError("已有方案不能改到另一类任务，请复制为新方案")
            next_revision = current_revision + 1
            # 索引提交前中断可能留下未发布文件，不能覆盖那份历史内容。
            while (self.root / "flows" / flow.id / f"{next_revision}.json").exists():
                next_revision += 1
            saved = flow.model_copy(update={"revision": next_revision}, deep=True)
            self._atomic_write(self.root / "flows" / flow.id / f"{next_revision}.json",
                               saved.model_dump(mode="json"))
            index["flows"][flow.id] = {"task": saved.task, "name": saved.name, "revision": next_revision}
            index["version"] += 1
            self._atomic_write(self.root / "index.json", index)
            return saved

    def set_default(
        self, task: str, flow_id: str, revision: int | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        """用目录版本保护默认选择，可选择已经保存的历史修订。

        Args:
            task: 业务任务名。
            flow_id: 要使用的方案 ID。
            revision: 指定修订；为空时选择该方案最新修订。
            expected_version: 页面读到的目录版本；提供时发生变化则拒绝覆盖。

        Returns:
            更新后的目录 version 和明确的 flow_ref。
        """
        with self._locked():
            index = self._read_index()
            if expected_version is not None and index["version"] != expected_version:
                raise FlowConflictError("默认方案已被其他页面修改，请刷新后重试")
            if flow_id not in index["flows"]:
                raise KeyError(f"方案不存在：{flow_id}")
            selected = self._read_flow(flow_id, revision if revision is not None else index["flows"][flow_id]["revision"])
            if selected.task != task:
                raise ValueError("默认方案必须属于当前任务")
            reference = {"id": selected.id, "revision": selected.revision}
            if index["defaults"].get(task) != reference:
                index["defaults"][task] = reference
                index["version"] += 1
                self._atomic_write(self.root / "index.json", index)
            return {"version": index["version"], "flow_ref": reference}

    def get_default(self, task: str) -> Flow:
        """读取默认方案，首次访问时只导入一次内置图。

        Args:
            task: 业务任务名。

        Returns:
            当前默认引用对应的不可变方案修订。
        """
        with self._locked():
            index = self._read_index()
            selected = index["defaults"].get(task)
            if selected:
                return self._read_flow(selected["id"], selected["revision"])
            if self.default_factory is None:
                raise KeyError(f"任务尚未设置默认方案：{task}")
            flow = validate_flow(self.default_factory(task))
            if flow.task != task:
                raise ValueError("默认工厂返回了另一类任务")
            existing = index["flows"].get(flow.id)
            if existing:
                flow = self._read_flow(flow.id, existing["revision"])
            else:
                next_revision = 1
                while (self.root / "flows" / flow.id / f"{next_revision}.json").exists():
                    next_revision += 1
                flow = flow.model_copy(update={"revision": next_revision}, deep=True)
                self._atomic_write(self.root / "flows" / flow.id / f"{next_revision}.json", flow.model_dump(mode="json"))
                index["flows"][flow.id] = {"task": flow.task, "name": flow.name, "revision": next_revision}
            index["defaults"][task] = {"id": flow.id, "revision": flow.revision}
            index["version"] += 1
            self._atomic_write(self.root / "index.json", index)
            return flow

@lru_cache(maxsize=8)
def _store_at(directory: str) -> FlowStore:
    return FlowStore(default_factory=builtin_flow, root=directory or None)


def flow_store() -> FlowStore:
    """返回当前配置目录的方案存储，测试可用环境变量选择隔离目录。

    Returns:
        负责版本检查与原子写入的本地存储。
    """
    return _store_at(os.environ.get("TASK_FLOW_STORE_DIR", ""))
