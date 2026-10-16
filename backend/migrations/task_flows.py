"""只升级精确匹配的最新旧内置默认；保留自定义和已选历史修订。"""
from pathlib import Path
import difflib
import json
import os
import shutil
import uuid

from backend.services.task_flows.defaults import builtin_flow
from backend.services.task_flows.graph import canonical_hash
from backend.services.task_flows.registry import validate_task_definition
from backend.services.task_flows.store import FlowStore
from . import MigrationError, write_json, inventory

MANIFEST = Path(__file__).with_name("task_flow_baselines.json")

def definition_hash(flow):
    """计算包括名称、标签和编辑信息的定义摘要。

    Args:
        flow: 待核对的流程。
    Returns:
        仅忽略修订号的精确内容摘要。"""
    return canonical_hash(flow.model_dump(mode="json", exclude={"revision"}))


def plan_upgrade(store: FlowStore, manifest_path: Path | None = None, *, require_latest_default: bool = False) -> dict:
    """比较已保存默认方案与已知内置定义。

    Args:
        store: 用户明确选择的流程存储。
        manifest_path: 已发布定义清单，省略时使用启动升级清单。
        require_latest_default: 自动启动升级须保留所有非最新的默认选择。
    Returns:
        不修改存储的升级计划与差异。"""
    manifest = json.loads((manifest_path or MANIFEST).read_text(encoding="utf8"))
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
        elif require_latest_default and ref["revision"] != latest[ref["id"]]:
            row["status"] = "non_latest_default_preserved"
        elif require_latest_default and any(
            path.stem.isdecimal() and int(path.stem) > ref["revision"]
            for path in (store.root / "flows" / ref["id"]).glob("*.json")
        ):
            row["status"] = "unpublished_revision_preserved"
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
    return {"catalog_version": catalog["version"], "known_source_commit": manifest["source_commit"],
            "historical_provenance": manifest.get("historical_provenance"), "tasks": rows}




def _publish(directory: Path, journal_path: Path, journal: dict) -> None:
    stage = Path(journal["stage"])
    current = inventory(directory)
    before, after = journal["before"], journal["after"]
    if current.get("index.json") not in {before["index.json"], after["index.json"]}:
        raise MigrationError("方案索引在迁移期间变化，请保留迁移备份并核对。")
    interrupted = []
    for relative, digest in current.items():
        if relative == ".lock": continue
        if relative.endswith(".migrating"):
            original = str(Path(relative).with_name(Path(relative).name[1:-10])).replace("\\", "/")
            if original in after:
                if after[original] != digest: interrupted.append(directory / relative)
                continue
        if digest not in {before.get(relative), after.get(relative)}:
            raise MigrationError("方案文件在迁移期间变化，请保留迁移备份并核对。")
    for temporary in interrupted:
        temporary.rename(stage.parent / f"interrupted-{uuid.uuid4().hex}")
    for relative, digest in after.items():
        if relative == ".lock" or current.get(relative) == digest: continue
        if relative == "index.json": continue
        target = directory / relative
        if target.exists():
            raise MigrationError("任务方案修订冲突，未覆盖原文件。")
        if inventory(stage / relative).get(".") != digest:
            raise MigrationError("方案暂存文件不完整，请保留备份并核对。")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.migrating")
        shutil.copy2(stage / relative, temporary)
        os.replace(temporary, target)
    if current.get("index.json") != after["index.json"]:
        if inventory(stage / "index.json").get(".") != after["index.json"]:
            raise MigrationError("方案暂存索引不完整，请保留备份并核对。")
        os.replace(stage / "index.json", directory / "index.json")
    journal["status"] = "complete"
    write_json(journal_path, journal)


def prepare_task_flows(data: Path, *, apply: bool) -> list[str]:
    """核对方案格式；备份后升级已知最新旧默认，保留其他用户选择。

    Args: data: 数据根。apply: 本次是否需要准备新版修订。
    Returns: 实际完成的升级及未自动升级的明确提示。
    """
    directory = Path(os.environ.get("TASK_FLOW_STORE_DIR") or data / "task_flows")
    inventory(directory)
    directory = directory.resolve()
    if not (directory / "index.json").exists():
        return []
    journal_path = data / "migrations/task_flows.json"
    store = FlowStore(root=directory)
    with store._locked():
        if journal_path.exists():
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            if journal["status"] != "complete":
                if journal["directory"] != str(directory):
                    raise MigrationError("还有未完成的方案迁移，请恢复原方案目录后重试。")
                _publish(directory, journal_path, journal)
        # format_version 是格式；index.version 和 revision 只是编辑计数。
        for path in (directory / "flows").glob("*/*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if type(payload.get("format_version")) is not int or payload["format_version"] != 1:
                raise MigrationError("任务方案来自不支持的版本，请使用对应程序，不能降级启动。")
        plan = plan_upgrade(store, require_latest_default=True)
        notices = []
        pending = [row for row in plan["tasks"] if row["status"] == "upgrade"]
        for row in plan["tasks"]:
            if row["status"] in ("custom_or_unknown", "newer_revision_preserved"):
                notices.append(f"{row['task']}：自定义或来源未知，未自动升级，请在方案编辑器核对。")
            elif row["status"] == "unpublished_revision_preserved":
                notices.append(f"{row['task']}：发现较新的未发布修订，未自动升级，请在方案编辑器核对。")
            elif row["status"] == "non_latest_default_preserved":
                notices.append(f"{row['task']}：当前选中的不是最新修订，未自动升级，已保留原选择。")
            elif row["status"] == "upgrade" and not apply:
                notices.append(f"{row['task']}：本次升级批次已完成，未再次自动升级，请在方案编辑器核对。")
        if not apply or not pending:
            return notices
        before = inventory(directory)
        run = data / "backups" / f"task-flows-{uuid.uuid4().hex}"
        backup, stage = run / "backup", run / "prepared"
        shutil.copytree(directory, backup, ignore=shutil.ignore_patterns(".lock"))
        shutil.copytree(directory, stage, ignore=shutil.ignore_patterns(".lock"))
        if inventory(backup) != before or inventory(directory) != before:
            raise MigrationError("方案在备份期间变化，已停止。")
        prepared = FlowStore(root=stage)
        default_changes = []
        for row in pending:
            saved = prepared.save(validate_task_definition(builtin_flow(row["task"])), row["expected_revision"])
            selected = prepared.set_default(row["task"], saved.id, saved.revision)
            default_changes.append({"task": row["task"], "before": row["default_before"],
                                    "after": selected["flow_ref"]})
        # 修订文件先发布，最新修订与默认引用一起通过最终索引生效。
        after = inventory(stage)
        journal = {"status": "pending", "directory": str(directory), "stage": str(stage),
                   "backup": str(backup), "before": before, "after": after}
        write_json(run / "report.json", {"tasks": plan["tasks"], "default_changes": default_changes})
        write_json(journal_path, journal)
        _publish(directory, journal_path, journal)
        notices.extend(f"{row['task']}：未修改的旧内置默认已自动升级，原修订和备份已保留。" for row in pending)
    return notices
