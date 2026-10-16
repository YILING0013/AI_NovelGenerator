"""离线检查已保存的旧内置方案；只有指定 --apply 才会升级。

先检查报告，再单独执行 --apply：
  python scripts/upgrade_task_flows.py --store ABSOLUTE_DIRECTORY --report-dir ABSOLUTE_REPORT_DIRECTORY

只升级与清单精确匹配的旧内置定义，不重写历史修订、自定义方案、候选或保存回执。
执行前停止应用，工具会在新报告目录完整备份原文件，再新增修订并切换默认。
遇到并发变化时停止，不覆盖用户修改；已保存的新修订会保留，重试时可复用。
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.task_flows.contracts import FlowConflictError
from backend.services.task_flows.defaults import builtin_flow
from backend.services.task_flows.graph import canonical_hash
from backend.services.task_flows.registry import validate_task_definition
from backend.services.task_flows.store import FlowStore

MANIFEST = Path(__file__).with_name("task_flow_baselines.json")


def definition_hash(flow):
    """计算包括名称、标签和编辑信息的定义摘要。

    Args:
        flow: 待核对的流程。
    Returns:
        仅忽略修订号的精确内容摘要。"""
    return canonical_hash(flow.model_dump(mode="json", exclude={"revision"}))


def inventory(root: Path) -> dict[str, str]:
    """读取目录内文件摘要，拒绝链接。

    Args:
        root: 已明确选择的目录。
    Returns:
        相对路径到 SHA256 的映射。"""
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"不支持符号链接或目录联接：{path}")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def plan_upgrade(store: FlowStore) -> dict:
    """比较已保存默认方案与已知内置定义。

    Args:
        store: 用户明确选择的流程存储。
    Returns:
        不修改存储的升级计划与差异。"""
    manifest = json.loads(MANIFEST.read_text(encoding="utf8"))
    catalog = store.list_flows()
    latest = {row["id"]: row["revision"] for row in catalog["flows"]}
    rows = []
    for task, known in manifest["tasks"].items():
        ref = catalog["defaults"].get(task)
        row = {"task": task, "default_before": ref, "status": "unconfigured"}
        rows.append(row)
        if not ref:
            continue
        old = store.get(ref["id"], ref["revision"])
        new = validate_task_definition(builtin_flow(task))
        old_hash, new_hash = definition_hash(old), definition_hash(new)
        row.update(before_sha256=old_hash, after_sha256=new_hash)
        if ref["id"] != known["id"]:
            row["status"] = "custom_or_unknown"
        elif old_hash == new_hash:
            row["status"] = "current"
        elif old_hash not in known["sha256"]:
            row["status"] = "custom_or_unknown"
        else:
            latest_revision = latest[ref["id"]]
            newest = store.get(ref["id"], latest_revision)
            if latest_revision != ref["revision"] and definition_hash(newest) != new_hash:
                row["status"] = "newer_revision_preserved"
                continue
            row.update(status="upgrade", expected_revision=latest_revision,
                       reuse_revision=latest_revision if definition_hash(newest) == new_hash else None)
            row["diff"] = "".join(difflib.unified_diff(
                old.model_dump_json(indent=2).splitlines(keepends=True),
                new.model_copy(update={"revision": latest_revision + 1}).model_dump_json(indent=2).splitlines(keepends=True),
                fromfile=f"{old.id}@{old.revision}", tofile="current-shipped-builtin"))
    return {"catalog_version": catalog["version"], "tasks": rows}


def upgrade(directory: Path, report_directory: Path, *, apply: bool = False) -> dict:
    """检查或显式升级精确匹配的内置流程，并保存报告和完整备份。

    Args:
        directory: 绝对存储路径。
        report_directory: 独立的新报告目录。
        apply: 是否真正保存新修订并切换默认值。
    Returns:
        检查或执行结果；并发变化抛出错误并保留报告。"""
    if not directory.is_absolute() or not report_directory.is_absolute():
        raise ValueError("--store 和 --report-dir 都必须指定绝对路径")
    if directory.is_symlink() or directory.is_junction():
        raise ValueError("任务方案目录不能是符号链接或目录联接")
    directory, report_directory = directory.resolve(), report_directory.resolve()
    if not (directory / "index.json").is_file():
        raise ValueError("指定任务方案目录没有 index.json")
    if report_directory == directory or directory in report_directory.parents or report_directory in directory.parents:
        raise ValueError("报告目录和任务方案目录不能相同或互相包含")
    before = inventory(directory)
    store = FlowStore(root=directory)
    plan = plan_upgrade(store)
    if before != inventory(directory):
        raise FlowConflictError("检查期间文件发生变化，请停止应用后重新检查")
    report_directory.mkdir(parents=True, exist_ok=False)
    report = {"store": str(directory), "apply": apply, **plan, "files_before": before, "applied": []}
    def save_report():
        (report_directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    save_report()
    for row in plan["tasks"]:
        if "diff" in row:
            (report_directory / f"{row['task']}.patch").write_text(row["diff"], encoding="utf8")
    pending = [row for row in plan["tasks"] if row["status"] == "upgrade"]
    if not apply or not pending:
        return report
    try:
        backup = report_directory / "backup"
        shutil.copytree(directory, backup)
        if inventory(backup) != before or inventory(directory) != before:
            raise FlowConflictError("备份期间文件发生变化，尚未开始升级")
        report["backup"] = str(backup)
        expected_catalog_version = plan["catalog_version"]
        for row in pending:
            catalog = store.list_flows()
            if catalog["version"] != expected_catalog_version or catalog["defaults"].get(row["task"]) != row["default_before"]:
                raise FlowConflictError("默认方案或目录版本发生变化，已停止后续升级")
            if row["reuse_revision"]:
                saved = store.get(row["default_before"]["id"], row["reuse_revision"])
            else:
                saved = store.save(validate_task_definition(builtin_flow(row["task"])), row["expected_revision"])
                expected_catalog_version += 1
            catalog = store.list_flows()
            if catalog["defaults"].get(row["task"]) != row["default_before"]:
                raise FlowConflictError("保存后默认方案发生变化，新修订已保留，但未切换默认")
            selected = store.set_default(row["task"], saved.id, saved.revision, expected_catalog_version)
            expected_catalog_version = selected["version"]
            report["applied"].append({"task": row["task"], "default_ref": selected["flow_ref"]})
            save_report()
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        save_report()
        raise
    report["files_after"] = inventory(directory)
    save_report()
    return report


def main() -> int:
    """执行命令行检查，只有 --apply 才写入所选存储。

    Args:
        无，参数来自命令行。
    Returns:
        成功时返回零。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--report-dir", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    report = upgrade(args.store, args.report_dir, apply=args.apply)
    print(json.dumps({"apply": args.apply, "tasks": [{"task": r["task"], "status": r["status"]} for r in report["tasks"]],
                      "applied": report["applied"], "report": str(args.report_dir / "report.json")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
