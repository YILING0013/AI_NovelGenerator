"""启动前文件检查与迁移；失败时保留记录，下次启动继续核对。"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

from backend.storage import PROJECT_ROOT, USER_DATA_DIR

LAYOUT_VERSION = 1
TASK_FLOW_VERSION = 3


class MigrationError(RuntimeError):
    """需要先处理的存储冲突或不支持的版本。"""


def inventory(root: Path) -> dict[str, str]:
    """读取文件摘要并拒绝链接，避免迁移越出指定目录。

    Args: root: 文件或目录。
    Returns: 相对文件名和 SHA256 摘要。
    """
    if not root.exists():
        return {}
    files = [root, *root.rglob("*")] if root.is_dir() else [root]
    result = {}
    for path in files:
        if path.is_symlink() or path.is_junction():
            raise MigrationError(f"请先处理链接路径：{path}")
        if path.is_file() and path.name != ".lock":
            with path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            result[path.relative_to(root).as_posix() if root.is_dir() else "."] = digest
    return result


def write_json(path: Path, payload: dict) -> None:
    """原子保存迁移记录，不写入配置或提示词内容。

    Args: path: 目标路径。payload: JSON 数据。
    Returns: 无。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


@contextmanager
def storage_lock(path: Path):
    """独占启动或运行目录；进程退出后系统自动释放锁。

    Args: path: 锁文件路径。
    Returns: 持锁的上下文。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        try:
            if os.name == "nt":
                import msvcrt
                if handle.tell() == 0:
                    handle.write(b"0"); handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise MigrationError("这个数据目录正在使用，请关闭原实例后重试。") from None
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _check_versions(data: Path) -> dict:
    path = data / "migrations/state.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for key, supported in (("layout_version", LAYOUT_VERSION), ("task_flow_version", TASK_FLOW_VERSION)):
        value = state.get(key, 0)
        if type(value) is not int or value < 0 or value > supported:
            raise MigrationError(f"{key} 不受此版本支持，请使用对应的新版程序，不能降级启动。")
    return state


def _resume_layout(data: Path, journal_path: Path, journal: dict) -> None:
    # 先核对所有副本，之后才逐项发布。中断后仍用同一份记录，不重新猜来源。
    for item in journal["items"]:
        source, target, backup, retired = (Path(item[k]) for k in ("source", "target", "backup", "retired"))
        expected = item["files"]
        if inventory(backup) != expected:
            raise MigrationError(f"迁移备份不完整，请保留现场并检查：{backup}")
        for candidate in (source, target, retired):
            if candidate.exists() and inventory(candidate) != expected:
                raise MigrationError(f"迁移期间文件已变化，请核对后重试：{candidate}")
        if not source.exists() and not retired.exists() and not item["copy_only"]:
            raise MigrationError(f"迁移原件缺失，请检查备份记录：{journal_path}")
    for item in journal["items"]:
        source, target, backup, retired = (Path(item[k]) for k in ("source", "target", "backup", "retired"))
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            staged = Path(item["staged"])
            if staged.exists() and inventory(staged) != item["files"]:
                # 保留复制中断的暂存件，再从已核验的备份恢复。
                staged.rename(backup.parent / f"interrupted-{uuid.uuid4().hex}")
            if not staged.exists():
                if backup.is_dir(): shutil.copytree(backup, staged)
                else: shutil.copy2(backup, staged)
            if inventory(staged) != item["files"]:
                raise MigrationError(f"迁移暂存副本不完整，请保留现场：{staged}")
            os.replace(staged, target)
        if source.exists() and not item["copy_only"]:
            if inventory(source) != item["files"]:
                raise MigrationError(f"原目录已变化，尚未移走：{source}")
            retired.parent.mkdir(parents=True, exist_ok=True)
            source.rename(retired)
    journal["status"] = "complete"
    write_json(journal_path, journal)


def prepare_files(project: Path = PROJECT_ROOT, data: Path = USER_DATA_DIR, *, legacy_launcher: Path | None = None) -> list[str]:
    """在业务读取前迁移旧文件、准备新版方案并核对版本。

    Args:
        project: 旧布局所在项目，测试使用独立副本。
        data: 新数据根目录。
        legacy_launcher: 测试可指定旧启动器配置；共享原件只复制。
    Returns: 应展示给用户的简短提示。
    """
    for candidate in (project, data, *data.parents):
        if candidate.is_symlink() or candidate.is_junction():
            raise MigrationError(f"请先处理链接路径：{candidate}")
    project, data = project.resolve(), data.resolve()
    # 实例显式选择独立数据根时，不读取另一个实例的旧目录。
    use_legacy = data == (project / "user_data").resolve()
    if data.is_symlink() or data.is_junction():
        raise MigrationError("user_data 不能是链接目录。")
    state = _check_versions(data)
    with storage_lock(data / "migrations/startup.lock"), storage_lock(data / "migrations/service.lock"):
        state = _check_versions(data)
        journal_path = data / "migrations/layout.json"
        if journal_path.exists():
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            if journal["status"] != "complete":
                if journal.get("project") != str(project) or journal.get("data") != str(data):
                    raise MigrationError("未完成迁移属于另一个目录，请保留现场并恢复原路径。")
                _resume_layout(data, journal_path, journal)
        mappings = [("backend/config/config.yaml", "config/config.yaml"),
                    ("data/task_flows", "task_flows"), ("static", "static"),
                    ("logs", "logs"), ("exports", "exports")]
        sources = [(project / old, data / new, False) for old, new in mappings
                   if use_legacy and (project / old).exists()]
        if sources and not state.get("layout_version"):
            if legacy_launcher is None:
                base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") if sys.platform == "win32" else Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
                legacy_launcher = base / "PrivateAINovelGenerator/launcher_settings.json"
            if legacy_launcher.is_file():
                sources.append((legacy_launcher, data / "config/launcher_settings.json", True))
        # 完整冲突检查先于备份、移动和版本写入。
        items = []
        run = data / "backups" / f"layout-{uuid.uuid4().hex}"
        for number, (source, target, copy_only) in enumerate(sources):
            for candidate in (source, target, *source.parents, *target.parents):
                if candidate.is_symlink() or candidate.is_junction():
                    raise MigrationError(f"请先处理链接路径：{candidate}")
            files = inventory(source)
            if target.exists() and (source.is_dir() != target.is_dir() or inventory(target) != files):
                raise MigrationError(f"旧、新目录内容不同，未覆盖任何文件。请核对：{source} 与 {target}")
            if target.is_symlink() or target.is_junction():
                raise MigrationError(f"请先处理链接路径：{target}")
            items.append(dict(source=str(source), target=str(target), files=files, copy_only=copy_only,
                              backup=str(run / f"copy-{number}"), retired=str(run / f"original-{number}"),
                              staged=str(target.with_name(f".{target.name}.migrating-{uuid.uuid4().hex}"))))
        if items:
            run.mkdir(parents=True, exist_ok=False)
            for item in items:
                source, backup = Path(item["source"]), Path(item["backup"])
                if source.is_dir(): shutil.copytree(source, backup, ignore=shutil.ignore_patterns(".lock"))
                else: shutil.copy2(source, backup)
                if inventory(source) != item["files"] or inventory(backup) != item["files"]:
                    raise MigrationError("备份期间原文件变化，尚未迁移，请关闭原实例后重试。")
            journal = {"status": "pending", "project": str(project), "data": str(data), "items": items}
            write_json(journal_path, journal)
            _resume_layout(data, journal_path, journal)
        for name in ("config", "task_flows", "static/covers", "logs", "exports", "backups"):
            (data / name).mkdir(parents=True, exist_ok=True)
        launcher_settings = data / "config/launcher_settings.json"
        if launcher_settings.exists():
            payload = json.loads(launcher_settings.read_text(encoding="utf-8"))
            if type(payload.get("version")) is not int or payload["version"] != 1:
                raise MigrationError("启动器设置版本不受支持，请使用对应程序，不能降级启动。")
        from .task_flows import prepare_task_flows
        notices = prepare_task_flows(data, apply=state.get("task_flow_version", 0) < TASK_FLOW_VERSION)
        next_state = {"layout_version": LAYOUT_VERSION, "task_flow_version": TASK_FLOW_VERSION}
        if state != next_state:
            write_json(data / "migrations/state.json", next_state)
        return notices
