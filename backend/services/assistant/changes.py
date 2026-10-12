"""持久候选、独立审核、事务保存和基于当前版本的撤销。"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from bson import BSON, ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.api.error_protocol import DomainApiError, sanitize_json_value, sse_error_payload
from backend.db.base import BaseRepository
from backend.db.errors import VersionConflictError
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now
from backend.db.write_contracts import canonical_request_hash
from .contracts import ChangeApproval, ChangeEdit, ChangeOperation, ResourceRef, ReviewResult
from .domain import PARENT_KIND, RESOURCES, STATUS_FIELD, execute_operation, update_fields
from .models import structured_advice
from .generation import POSITION_REVIEW_TASKS, FACT_GENERATION_CONTRACTS
from .resources import content_fingerprint, get_resource, public_content
from backend.services.task_flows.registry import CONTENT_TASKS


POSITION_REVIEW_CONTRACT = "assistant_position_review_v1"


class _PreviewComplete(Exception):
    """仅用于退出预演事务；确保已执行的业务写入全部中止。"""

    def __init__(self, result: dict):
        self.result = result


def creation_error(change: dict) -> dict | None:
    """判断候选是否缺少位置或作者正文来源，供页面和最终执行共用。

    Args:
        change: 当前候选记录。
    Returns:
        不可继续时的明确错误；普通全书管理不要求按章依据。
    """
    context = change.get("creation_context", {})
    operations = change.get("operations", [])
    body = any(value["resource_type"] == "chapter" and any(field.split(".")[0] == "content" for field in value.get("fields", {})) for value in operations)
    positional = change.get("generation_task") in CONTENT_TASKS
    if change.get("generation_task") in FACT_GENERATION_CONTRACTS and change.get("generation_policy", {}).get("contract") != FACT_GENERATION_CONTRACTS[change["generation_task"]]:
        return {"code": "ASSISTANT_CREATION_REQUEST_EXPIRED", "message": "旧批量候选缺少原作者要求或明确起点，请保留原稿并另发请求；已保存回执仍可重放"}
    if (positional or body) and context.get("contract_version") != 1:
        return {"code": "ASSISTANT_CREATION_REQUEST_EXPIRED", "message": "旧候选缺少创作来源，请保留记录并另建请求；已保存回执仍可重放"}
    if positional and context.get("semantics") != "position_writing":
        return {"code": "ASSISTANT_CREATION_REQUEST_EXPIRED", "message": "此候选缺少按位置创作依据，请另建请求"}
    if positional and context.get("author_dialogue_version") == 1:
        return {"code": "ASSISTANT_CREATION_REQUEST_EXPIRED", "message": "旧候选包含尚未按位置核对的问题语境，请保留原稿并另发请求；已保存回执仍可重放"}
    author = change.get("author_text", {})
    if positional and author and author.get("candidate_hash") != canonical_request_hash(change.get("candidate")):
        return {"code": "ASSISTANT_CREATION_REQUEST_EXPIRED", "message": "作者编辑的候选内容已变化，请重新核对"}
    if body and change.get("author_text", {}).get("operations_hash") != canonical_request_hash(operations):
        return {"code": "ASSISTANT_POSITION_GENERATION_REQUIRED", "message": "全书助手不能直接提交正文，请明确选择创作位置后运行原生成任务，或由作者在正文编辑器直接修改"}
    return None


def guard_creation(change: dict) -> None:
    """在候选编辑、审核和执行前拒绝没有可靠来源的正文。

    Args:
        change: 待处理的候选。
    Returns:
        合同时正常返回，否则抛出可展示的错误。
    """
    error = creation_error(change)
    if error:
        raise DomainApiError(error["code"], error["message"], status_code=409)


async def check_character_fields(change: dict, *, session=None, protect: bool = False) -> None:
    """整组检查旧人物字段；保存时在任何业务写入前保护认领的空查询。

    Args:
        change: 原候选或作者正在编辑的完整操作组，不改变操作和确认键。
        session: 执行时使用调用方的真实事务，准备候选时可省略。
        protect: 仅组执行传 True；候选准备和编辑只读，不制造临时事务。
    Returns:
        未涉及已认领字段时正常返回；否则整组拒绝。
    """
    from backend.services.novel.character_fact_contract import CHARACTER_FACT_FIELDS
    from backend.services.novel.character_fact_service import ensure_character_fields_unmanaged
    from backend.services.novel.character_volume_state_service import STATE_FACT_FIELDS

    novel_id = str(change["novel_id"])
    selected: dict[str, set[str]] = {}
    new_states: dict[str, str] = {}
    for value in change.get("operations", []):
        kind, action = value["resource_type"], value["action"]
        fields = {field.split(".")[0] for field in value.get("fields", {})}
        if kind == "character" and action == "update":
            character_id = value.get("id")
            involved = fields & CHARACTER_FACT_FIELDS
        elif kind == "character_volume_state" and action in {"create", "update"}:
            if action == "create":
                character_id = value.get("fields", {}).get("character_id")
                if value.get("temporary_id") and isinstance(character_id, str):
                    new_states[value["temporary_id"]] = character_id
                # 原 upsert 即使没填写三项，也会补空串并写回，不能把它当窄计划。
                involved = set(STATE_FACT_FIELDS)
            else:
                identity = value.get("id")
                if identity and identity.startswith("new_"):
                    character_id = new_states.get(identity)
                else:
                    state = await get_resource(novel_id, ResourceRef(resource_type=kind, id=identity), include_deleted=True, session=session)
                    character_id = state["character_id"]
                involved = fields & set(STATE_FACT_FIELDS)
        else:
            continue
        # 新人物仍由原创建服务拒绝；助手不能代作者生成起点预览。
        if isinstance(character_id, str) and not character_id.startswith("new_"):
            selected.setdefault(character_id, set()).update(involved)
    for character_id, fields in sorted(selected.items()):
        await ensure_character_fields_unmanaged(
            novel_id, [character_id], sorted(fields), session=session, protect=protect,
        )


async def check_relation_fields(change: dict, *, session=None, protect: bool = False) -> None:
    """整组先拒绝新关系和已认领状态，设计字段仍可正常编辑。

    Args:
        change: 原候选或作者正在编辑的完整操作组。
        session: 执行时使用调用方事务。
        protect: 执行时保护认领空查询；暂存和编辑只读检查。
    Returns:
        无；任何一项不允许时，在第一项业务写入前拒绝整组。
    """
    from backend.services.novel.character_relation_fact_service import ensure_character_relation_state_unmanaged

    relation_ids = set()
    for value in change.get("operations", []):
        if value["resource_type"] != "character_relation":
            continue
        if value["action"] == "create":
            raise DomainApiError("CHARACTER_RELATION_FACT_REQUIRED", "新关系请由作者设置明确起点后确认", status_code=409)
        fields = {field.split(".")[0] for field in value.get("fields", {})}
        if value["action"] == "update" and "current_state" in fields:
            identity = value.get("id")
            if identity and not identity.startswith("new_"):
                relation_ids.add(identity)
    if relation_ids:
        await ensure_character_relation_state_unmanaged(
            str(change["novel_id"]), sorted(relation_ids), session=session, protect=protect,
        )


async def check_item_fields(change: dict, *, session=None, protect: bool = False) -> None:
    """助手整组写入前检查物品起点和已认领状态，普通设计不受影响。

    Args:
        change: 原操作组，保留原请求和确认键。
        session: 保存时的调用方事务。
        protect: 保存时保护尚未认领的空查询。
    Returns:
        无；任一项需要作者确认时在整组首个写入前拒绝。
    """
    from backend.services.novel.item_fact_contract import ITEM_FACT_FIELDS
    from backend.services.novel.item_fact_service import ensure_item_fields_unmanaged

    identities = set()
    for operation in change.get("operations", []):
        if operation["resource_type"] != "item":
            continue
        if operation["action"] == "create":
            raise DomainApiError("ITEM_FACT_REQUIRED", "新物品请由作者选择明确起点后确认", status_code=409)
        fields = {key.split(".")[0] for key in operation.get("fields", {})}
        if operation["action"] == "status" or operation["action"] == "update" and fields & ITEM_FACT_FIELDS:
            identities.add(operation["id"])
    if identities:
        await ensure_item_fields_unmanaged(str(change["novel_id"]), sorted(identities), session=session, protect=protect)


def public_change(document: dict) -> dict:
    """只向页面返回候选、依据位置和审核结果。

    Args:
        document: 服务端修改组记录。
    Returns:
        不含原生历史、确认键和私有流程状态的公开修改组。
    """
    fields = {"schema_version", "revision", "status", "kind", "operations", "diffs", "review", "created_at", "updated_at", "result", "undo_of", "generation_task", "candidate", "source_refs", "program_error", "child_usage", "creation_context", "author_text", "apply_attempt", "confirmation", "reprepared_from"}
    return sanitize_json_value({"id": str(document["_id"]), **{key: value for key, value in document.items() if key in fields},
                                "creation_error": creation_error(document) if document.get("status") != "applied" else None})


async def guard_pending_writes(novel_id: str, proposed: dict, *, exclude_id=None, session=None) -> None:
    """按本作品的实际对象阻挡未决保存；跨轮次、跨会话仍使用原操作回执。

    Args:
        novel_id: 当前作品，绝不查询其它作品的未决写入。
        proposed: 正要准备或保存的修改。
        exclude_id: 只允许原修改重放自己。
        session: 保存时的原事务。
    Returns:
        不重叠时返回；重叠时给出可恢复的原修改和修订。
    """
    async def scope(change):
        refs, kinds, structural = set(), set(), set()
        if change.get("kind") == "facts":
            kind = change["fact_type"]
            target = change.get("fact_command", {}).get("basis", {}).get("target", {})
            identity = change.get("fact_target") or target.get({"character": "character_id", "character_relation": "relation_id", "item": "item_id"}[kind])
            if identity:
                refs.add((kind, identity))
            else:
                kinds.add(kind)
        elif change.get("kind") == "generation":
            from .generation import GENERATION_KINDS
            target = change.get("creation_context", {}).get("target")
            task = change.get("generation_task")
            if target and task in POSITION_REVIEW_TASKS:
                refs.add((target["resource_type"], target["id"]))
                structural.update(refs)
                if task.startswith("create_"):
                    kinds.update(set(GENERATION_KINDS[task]) - {"volume"})
            else:
                kinds.update(GENERATION_KINDS.get(task, RESOURCES))
        else:
            for operation in change.get("operations", []):
                kind = operation["resource_type"]
                identities = operation.get("fields", {}).get("ids", []) if operation["action"] == "reorder" else [operation.get("id")]
                for identity in identities:
                    if identity and not identity.startswith("new_"):
                        refs.add((kind, identity))
                        if operation["action"] in {"delete", "restore", "reorder"}:
                            structural.add((kind, identity))
                    else:
                        kinds.add(kind)
                if operation.get("parent_id"):
                    refs.add((PARENT_KIND.get(kind, kind), operation["parent_id"]))
        ancestors, normalized, normalized_structural = set(), set(), set()
        for kind, identity in refs:
            if identity.startswith("new_"):
                continue
            document = await get_resource(novel_id, ResourceRef(resource_type=kind, id=identity), include_deleted=True, session=session)
            actual = (kind, str(document[RESOURCES[kind].identity]))
            normalized.add(actual)
            if (kind, identity) in structural:
                normalized_structural.add(actual)
            # 使用实际父链身份，不拿作品 ID 把全书无关修改都锁住。
            for parent in ("volume", "arc", "scene", "chapter"):
                if document.get(f"{parent}_id"):
                    ancestors.add((parent, str(document[f"{parent}_id"])))
        return normalized, kinds, normalized_structural, ancestors

    wanted = None
    query = {"novel_id": ObjectId(novel_id), "apply_attempt.outcome": "unknown"}
    if exclude_id is not None:
        query["_id"] = {"$ne": ObjectId(exclude_id)}
    async for pending in BaseRepository("assistant_changes").collection.find(query, session=session):
        receipt = await BaseRepository("assistant_receipts").collection.find_one({"novel_id": ObjectId(novel_id), "change_id": pending["_id"], "revision": pending["revision"]}, session=session)
        if receipt:
            continue
        wanted = wanted or await scope(proposed)
        old = await scope(pending)
        refs, kinds, structural, ancestors = wanted
        old_refs, old_kinds, old_structural, old_ancestors = old
        overlaps = (refs & old_refs or kinds & old_kinds or kinds & {kind for kind, _ in old_refs}
                    or old_kinds & {kind for kind, _ in refs} or structural & old_ancestors or old_structural & ancestors)
        if overlaps:
            raise DomainApiError("ASSISTANT_SAVE_UNKNOWN", "这个对象的上次保存结果仍待核对，已保留原修改；请先恢复原保存，再处理新要求", status_code=409,
                details={"change_id": str(pending["_id"]), "revision": pending["revision"], "run_id": str(pending["run_id"]), "session_id": str(pending["session_id"]), "next": "用原 change_id 和 revision 调用 apply_changes 或 reconcile_changes，不另建操作。"})


def confirmation_for(change: dict, preview: dict, review: dict) -> dict | None:
    """从事务预演的实际旧对象变化生成一次确认，不把纯新增批次当成覆盖。

    Args:
        change: 固定修订的候选。
        preview: 原业务服务的真实前后结果。
        review: 此修订的内容风险。
    Returns:
        具体对象、字段前后值及绑定范围的凭据；普通改动返回空。
    """
    targets = []
    for result in preview.get("operations", []):
        operation = result["operation"]
        originals = {item["id"]: item for item in result["before"]}
        for after in result["after"]:
            before = originals.get(after["id"])
            if before is None:
                continue
            fields = {field: {"before": before.get(field), "after": after.get(field)}
                      for field in sorted({field.split(".")[0] for field in operation.get("fields", {})}) if before.get(field) != after.get(field)}
            action = operation["action"]
            if action == "reorder":
                fields = {field: {"before": before.get(field), "after": after.get(field)}
                          for field in ("order_index", "sort_order") if before.get(field) != after.get(field)}
            if action in {"delete", "restore"}:
                fields = {"is_deleted": {"before": before.get("is_deleted"), "after": after.get("is_deleted")}}
            if fields or action in {"delete", "restore", "reorder"}:
                targets.append({"resource_type": after["resource_type"], "id": after["id"],
                    "name": before.get("name") or before.get("title") or after["id"], "action": action, "fields": fields})
    conflicts = [issue["message"] for issue in review.get("issues", []) if issue["severity"] == "conflict"]
    structural = any(item["action"] in {"delete", "restore", "reorder"} for item in targets)
    volumes = {item["id"] for item in targets if item["resource_type"] == "volume" and item["action"] == "update"}
    if not (structural or len(volumes) > 1 or len(targets) >= 10 or conflicts):
        return None
    if not targets:  # 事实内容风险仍有真实的对象和字段。
        targets = [{"resource_type": item["resource_type"], "id": item["id"],
                    "name": change.get("candidate", {}).get("name") or item["id"], "action": item["action"],
                    "fields": {field: {"before": item["before"].get(field), "after": value} for field, value in item["after"].items()}}
                   for item in change.get("diffs", [])]
    scope = {"targets": targets, "conflicts": conflicts}
    token = canonical_request_hash({"change": str(change["_id"]), "revision": change["revision"],
        "scope": scope, "candidate": change.get("candidate"), "operations": change.get("operations")})
    return {**scope, "token": token, "revision": change["revision"],
            "message": "请确认以下具体改动；确认后会保存并继续原任务。"}


def confirmation_question(change: dict, *, question_id: str) -> dict:
    """把已审核的实际影响绑定到原任务的问题，模型不能自授确认。

    Args:
        change: 已审核并需要作者决定的修改。
        question_id: 原工具调用生成的稳定问题标识。
    Returns:
        仅对应当前修订的公开问题。
    """
    confirmation = change["confirmation"]
    return {"id": question_id, "question": confirmation["message"], "choices": ["确认并继续", "先调整"],
            "changes": [{"id": str(change["_id"]), "revision": change["revision"], "status": change["status"]}],
            "confirmation": {**confirmation, "change_id": str(change["_id"])},
            "target": change.get("creation_context", {}).get("target")}


async def get_change(novel_id: str, change_id: str, *, session=None) -> dict:
    """读取同一本书的修改组，跨书 ID 不可查询或保存。

    Args:
        novel_id: 路由固定的小说。
        change_id: 修改组 ID。
        session: 可选保存事务。
    Returns:
        原修改组文档。
    """
    if not ObjectId.is_valid(change_id):
        raise DomainApiError("ASSISTANT_CHANGE_NOT_FOUND", "修改组不存在", status_code=404)
    result = await BaseRepository("assistant_changes").collection.find_one({"_id": ObjectId(change_id), "novel_id": ObjectId(novel_id)}, session=session)
    if result is None:
        raise DomainApiError("ASSISTANT_CHANGE_NOT_FOUND", "修改组不存在或不属于当前小说", status_code=404)
    return result


async def settle_run_changes(run: dict, status: str, *, pending_review: dict | None = None) -> list[dict]:
    """结束已停止轮次的生成或审核，保存结果仍以原修订回执为准。

    Args:
        run: 调用方持有书级占用的原轮次。
        status: 根轮次的结束状态。
        pending_review: 检查点中尚未返回的审核调用，仅处理原修订。
    Returns:
        实际更新的修改组；未知保存和已完成候选不改写。
    """
    collection = BaseRepository("assistant_changes").collection
    updated = []
    terminal = status if status in {"failed", "cancelled"} else "interrupted"
    messages = {"failed": "这次生成未完成。原请求已保留，可以重试。",
                "cancelled": "已停止这次生成。原请求已保留，可以重试。",
                "interrupted": "这次生成已暂停。原请求和已完成步骤已保留。"}
    unfinished = [{"status": "generating"}]
    if pending_review and ObjectId.is_valid(pending_review.get("change_id")) and type(pending_review.get("revision")) is int and pending_review["revision"] > 0:
        unfinished.append({"_id": ObjectId(pending_review["change_id"]), "revision": pending_review["revision"], "status": "draft"})
    async for change in collection.find({"novel_id": run["novel_id"], "run_id": run["_id"], "$or": unfinished}):
        receipt = await BaseRepository("assistant_receipts").collection.find_one(
            {"novel_id": run["novel_id"], "change_id": change["_id"], "revision": change["revision"]})
        if receipt:
            fields = {"status": "applied", "result": receipt["result"],
                      "apply_attempt": {"revision": change["revision"], "outcome": "committed"}}
        else:
            attempt = change.get("apply_attempt", {})
            # 未见回执不是失败证据；缺失旧记录和未知提交均保留原恢复路径。
            if change.get("result") or attempt.get("revision") != change["revision"] or attempt.get("outcome") not in {"not_sent", "not_committed"}:
                continue
            fields = {"status": terminal, "program_error": {
                "code": f"ASSISTANT_GENERATION_{terminal.upper()}", "message": messages[terminal]}}
            if change["status"] == "draft":
                fields = {"status": "draft", "program_error": {
                    "code": "ASSISTANT_REVIEW_INCOMPLETE", "message": "这次审核未完成。修改草稿已保留，重试会重新核对。"}}
        value = await collection.find_one_and_update(
            {"_id": change["_id"], "novel_id": run["novel_id"], "run_id": run["_id"],
             "revision": change["revision"], "status": change["status"], "apply_attempt": change.get("apply_attempt"),
             "updated_at": change.get("updated_at")},
            {"$set": {**fields, "updated_at": get_utc_now()}}, return_document=ReturnDocument.AFTER)
        if value:
            updated.append(value)
    return updated


async def stage_changes(novel_id: str, session_id: str, run_id: str, operations: list[ChangeOperation], *, sources: list[dict], queries: list[dict], key: str, author_text: dict | None = None) -> dict:
    """固定操作前值和实际来源；同一工具重试只返回同一候选。

    Args:
        novel_id: 当前小说。
        session_id: 当前对话。
        run_id: 当前轮次。
        operations: 依赖顺序排列的业务操作。
        sources: 本轮真正读到的内容指纹。
        queries: 本轮真正执行的分页查询及结果指纹。
        key: 服务端固定的工具调用键。
        author_text: 仅人工撤销入口传入的原回执来源，工具不能提供。
    Returns:
        已保存但未执行业务写入的修改组。
    """
    if not 1 <= len(operations) <= 50:
        raise DomainApiError("ASSISTANT_CHANGE_SIZE", "一组需要包含 1–50 项操作")
    change_id = ObjectId(canonical_request_hash({"run": run_id, "key": key})[:24])
    collection = BaseRepository("assistant_changes").collection
    existing = await collection.find_one({"_id": change_id, "novel_id": ObjectId(novel_id)})
    if existing:
        if existing["status"] != "applied":
            guard_creation(existing)
            await check_relation_fields(existing)
            await check_item_fields(existing)
            await check_character_fields(existing)
        return existing
    serialized = [operation.model_dump(mode="json") for operation in operations]
    creation_context = {"contract_version": 1, "semantics": "book_management"}
    text_source = {**author_text, "operations_hash": canonical_request_hash(serialized)} if author_text else {}
    guard_creation({"operations": serialized, "creation_context": creation_context, "author_text": text_source})
    await check_relation_fields({"novel_id": novel_id, "operations": serialized})
    await check_item_fields({"novel_id": novel_id, "operations": serialized})
    await check_character_fields({"novel_id": novel_id, "operations": serialized})
    source_map = {(source["resource_type"], source["id"]): source for source in sources}
    before, diffs, temporary = {}, [], set()
    for operation in operations:
        kind = operation.resource_type
        if kind == "foreshadowing":
            raise DomainApiError("FORESHADOWING_READ_ONLY", "助手不能暂存伏笔修改，请由作者操作")
        if operation.action == "create":
            if not operation.temporary_id or operation.temporary_id in temporary:
                raise DomainApiError("ASSISTANT_TEMPORARY_ID", "新建资料需要不重复的临时 ID")
            temporary.add(operation.temporary_id)
        references = []
        if operation.id and not operation.id.startswith("new_"):
            references.append(ResourceRef(resource_type=kind, id=operation.id))
        if operation.parent_id and not operation.parent_id.startswith("new_"):
            parent_kind = PARENT_KIND.get(kind, "location" if kind == "location" else kind)
            references.append(ResourceRef(resource_type=parent_kind, id=operation.parent_id))
        if operation.action == "reorder":
            if not isinstance(operation.fields.get("ids"), list):
                raise DomainApiError("ASSISTANT_REORDER_INVALID", "排序需要提供完整 ID 列表")
            references.extend(ResourceRef(resource_type=kind, id=identity) for identity in operation.fields["ids"] if not identity.startswith("new_"))
        for ref in references:
            document = await get_resource(novel_id, ref, include_deleted=True)
            content = public_content(ref.resource_type, document)
            source = {**ref.model_dump(), "version": content["version"], "fingerprint": content_fingerprint(content)}
            prior = source_map.get((ref.resource_type, ref.id))
            if prior and prior["fingerprint"] != source["fingerprint"]:
                raise DomainApiError("ASSISTANT_SOURCE_CHANGED", "资料已被修改，请重新读取后准备候选", status_code=409)
            source_map[(ref.resource_type, ref.id)] = source
            before[f"{ref.resource_type}:{ref.id}"] = content
        original = before.get(f"{kind}:{operation.id}", {})
        changed_fields = update_fields(kind, operation.fields, original) if operation.action == "update" and original else operation.fields
        diffs.append({"action": operation.action, "resource_type": kind, "id": operation.id or operation.temporary_id,
                      "reason": operation.reason, "before": {field: original.get(field) for field in changed_fields}, "after": changed_fields})
    now = get_utc_now()
    document = {"_id": change_id, "schema_version": 1, "novel_id": ObjectId(novel_id), "session_id": ObjectId(session_id), "run_id": ObjectId(run_id),
                "kind": "operations", "status": "draft", "revision": 1, "operations": [operation.model_dump(mode="json") for operation in operations],
                "creation_context": creation_context, "author_text": text_source,
                "sources": list(source_map.values()), "queries": queries, "before": before, "source_refs": list(source_map.values()),
                "diffs": diffs, "review": None, "apply_attempt": {"revision": 1, "outcome": "not_sent"}, "created_at": now, "updated_at": now}
    if len(BSON.encode(document)) > 8_000_000:
        raise DomainApiError("ASSISTANT_CHANGE_SIZE", "本组内容过大，请按独立修改拆分")
    try:
        await collection.insert_one(document)
    except DuplicateKeyError:
        return await get_change(novel_id, str(change_id))
    return document


async def edit_change(novel_id: str, change_id: str, request: ChangeEdit) -> dict:
    """保留原依据编辑候选；编辑后必须重新审核。

    Args:
        novel_id: 当前小说。
        change_id: 待修改的组。
        request: 原版本和新候选。
    Returns:
        版本加一且审核清空的修改组。
    """
    change = await get_change(novel_id, change_id)
    guard_creation(change)
    if change.get("apply_attempt", {}).get("outcome") == "unknown":
        raise DomainApiError("ASSISTANT_SAVE_UNKNOWN", "正在核对原保存结果，原请求不能修改", status_code=409)
    if change["kind"] == "facts":
        raise DomainApiError("ASSISTANT_FACT_EDIT_IN_CHAT", "请在对话里说明要调整的内容，原修改会保留", status_code=409)
    await check_relation_fields(change)
    await check_item_fields(change)
    await check_character_fields(change)
    if change["kind"] == "generation":
        from .generation import validate_creation
        await validate_creation(change)
    if change["kind"] == "operations":
        if request.operations is None:
            raise DomainApiError("ASSISTANT_CHANGE_KIND", "此修改组需要提交操作列表")
        # 编辑内容不能偷换目标或删去依赖；新的业务范围应另建候选。
        old_identity = [(o["action"], o["resource_type"], o.get("id"), o.get("parent_id"), o.get("temporary_id")) for o in change["operations"]]
        new_identity = [(o.action, o.resource_type, o.id, o.parent_id, o.temporary_id) for o in request.operations]
        if old_identity != new_identity:
            raise DomainApiError("ASSISTANT_CHANGE_SCOPE", "此处只能编辑候选内容；更换目标、增删操作请另建修改组")
        updates = {"operations": [operation.model_dump(mode="json") for operation in request.operations]}
        # 只有人工 PATCH 路由能进入此函数，原候选必须先通过来源检查。
        updates["author_text"] = {"source": "author_candidate_edit", "revision": request.expected_revision + 1,
                                  "operations_hash": canonical_request_hash(updates["operations"])}
        guard_creation({**change, **updates})
        await check_relation_fields({**change, **updates})
        await check_item_fields({**change, **updates})
        await check_character_fields({**change, **updates})
        diffs = []
        for operation in request.operations:
            original = change["before"].get(f"{operation.resource_type}:{operation.id}", {})
            fields = update_fields(operation.resource_type, operation.fields, original) if operation.action == "update" and original else operation.fields
            diffs.append({"action": operation.action, "resource_type": operation.resource_type, "id": operation.id or operation.temporary_id,
                          "reason": operation.reason, "before": {key: original.get(key) for key in fields}, "after": fields})
        updates["diffs"] = diffs
    else:
        if request.candidate is None:
            raise DomainApiError("ASSISTANT_CHANGE_KIND", "此修改组需要提交原生成任务的候选")
        updates = {"candidate": request.candidate}
        updates["author_text"] = {"source": "author_candidate_edit", "revision": request.expected_revision + 1,
                                  "candidate_hash": canonical_request_hash(request.candidate)}
    if change.get("apply_attempt", {}).get("outcome") in {"not_sent", "not_committed"}:
        updates["apply_attempt"] = {"revision": request.expected_revision + 1, "outcome": "not_sent"}
    result = await BaseRepository("assistant_changes").collection.find_one_and_update(
        {"_id": change["_id"], "novel_id": change["novel_id"], "revision": request.expected_revision, "status": {"$in": ["draft", "reviewed"]}},
        {"$set": {**updates, "status": "draft", "review": None, "updated_at": get_utc_now()}, "$unset": {"program_error": ""}, "$inc": {"revision": 1}}, return_document=ReturnDocument.AFTER)
    if result is None:
        raise DomainApiError("ASSISTANT_CHANGE_CONFLICT", "修改组已保存或已被编辑，请刷新", status_code=409)
    return result


async def check_sources(change: dict, *, session=None, protect: bool = False) -> list[dict]:
    """复读实际依据；确认事务通过内部保护写入阻止并发覆盖。

    Args:
        change: 固定来源的候选。
        session: 当前预演或保存事务。
        protect: 是否在事务中保护已读文档。
    Returns:
        校验通过的当前业务资料。
    """
    novel_id = str(change["novel_id"])
    materials = []
    if protect and change.get("queries"):
        # 空结果和未返回的行也可能被并发增改。保护查询涉及的整类资料，
        # 再保护新建使用的父记录和业务 ID 序列；不只锁已经命中的对象。
        kinds = {query["arguments"].get("kind") for query in change["queries"]}
        kinds = set(RESOURCES) if None in kinds else kinds
        for kind in sorted(kinds | {"novel"}):
            spec = RESOURCES[kind]
            filters = {"_id": change["novel_id"]} if kind == "novel" else {"novel_id": change["novel_id"]}
            await BaseRepository(spec.collection).collection.update_many(filters, {"$inc": {"writing_guard_revision": 1}}, session=session)
        sequences = kinds & {"character", "faction", "location", "item", "world_rule", "character_relation", "faction_relation", "character_faction_binding"}
        for kind in sorted(sequences):
            await BaseRepository("id_sequences").collection.update_one(
                {"novel_id": change["novel_id"], "entity_type": kind},
                {"$inc": {"writing_guard_revision": 1}, "$setOnInsert": {"value": 0, "created_at": get_utc_now()}}, upsert=True, session=session)
    for source in change.get("sources", []):
        ref = ResourceRef(resource_type=source["resource_type"], id=source["id"])
        document = await get_resource(novel_id, ref, session=session, include_deleted=True)
        content = public_content(ref.resource_type, document)
        if content_fingerprint(content) != source["fingerprint"]:
            raise DomainApiError("ASSISTANT_SOURCE_CHANGED", "候选使用的资料已修改，请保留候选并重新准备", status_code=409, details={"source": ref.model_dump()})
        # 目标版本严格保持，纯字数变化的参考资料仍可复验其内容。
        if f"{ref.resource_type}:{ref.id}" in change.get("before", {}) and content["version"] != source["version"]:
            raise DomainApiError("ASSISTANT_VERSION_CHANGED", "候选目标的版本已变化，请重新准备", status_code=409, details={"source": ref.model_dump()})
        if protect:
            if ref.resource_type == "foreshadowing":
                from backend.services.novel.foreshadowing_service import protect_foreshadowing_sources
                guards = {}
                # 直接按ID读伏笔没有查询记录，复核标记所依赖的章也必须在确认事务内保护。
                for field in ("planted_evidence", "resolved_evidence"):
                    if document[field] is not None:
                        chapter = await BaseRepository("chapters").collection.find_one({"_id": ObjectId(document[field]["chapter_id"]), "novel_id": document["novel_id"]}, session=session)
                        if chapter is not None:
                            guards[("chapters", str(chapter["_id"]))] = chapter
                await protect_foreshadowing_sources(guards, session=session)
            result = await BaseRepository(RESOURCES[ref.resource_type].collection).collection.update_one(
                {"_id": document["_id"], "version": document["version"], "is_deleted": document["is_deleted"]}, {"$inc": {"writing_guard_revision": 1}}, session=session)
            if result.matched_count != 1:
                raise DomainApiError("ASSISTANT_SOURCE_CHANGED", "资料在确认期间变化，请重试", status_code=409)
        materials.append(content)
    if change.get("queries"):
        from .reading import replay_queries
        await replay_queries(novel_id, change["queries"], session=session)
    return materials


async def execute_group(change: dict, *, session) -> dict:
    """依次调用原服务并保留可撤销的前后内容，不调用模型。

    Args:
        change: 当前已固定的修改组。
        session: 外层必需事务。
    Returns:
        实际前后资料、正式 ID 对照和原服务结果。
    """
    novel_id, identities, results = str(change["novel_id"]), {}, []
    guard_creation(change)
    if change["kind"] == "facts":
        from backend.services.novel import character_fact_service, character_relation_fact_service, item_fact_service
        policy = change.get("fact_policy", {})
        run = await BaseRepository("assistant_runs").collection.find_one({"_id": change["run_id"], "novel_id": change["novel_id"]}, session=session)
        if not run or policy.get("version") not in {1, 2} or policy.get("request_hash") != run["request_hash"]:
            raise DomainApiError("ASSISTANT_FACT_SOURCE_REQUIRED", "这份修改缺少原作者要求，请保留并重新说明", status_code=409)
        if policy.get("version") == 2:
            answers = policy["author_answers"]
            if (run.get("answers", [])[:len(answers)] != answers
                    or canonical_request_hash(run["request"]) != run["request_hash"]
                    or policy["author_request"] != "\n".join([run["request"]["message"], *(item["message"] for item in answers)])):
                raise DomainApiError("ASSISTANT_FACT_SOURCE_REQUIRED", "原问题和回答已不匹配，请保留修改并重新核对", status_code=409)
        if policy.get("position_context"):
            from .reading import read_chapter_position
            current_position = await read_chapter_position(novel_id, chapter_id=policy["position_context"]["id"], session=session)
            if current_position != policy["position_context"]:
                raise DomainApiError("ASSISTANT_FACT_POSITION_CHANGED", "章节名称或顺序已变化，原位置选择已保留，请核对后继续", status_code=409)
        await check_sources(change, session=session, protect=True)
        kind = change["fact_type"]
        service = {"character": character_fact_service, "character_relation": character_relation_fact_service, "item": item_fact_service}[kind]
        result = await getattr(service, f"confirm_{kind}_facts")(novel_id, {**change["fact_command"], "confirmed": True},
            idempotency_key=f"assistant:{change['_id']}:{change['revision']}:fact", session=session)
        business_id = result[{"character": "character_id", "character_relation": "relation_id", "item": "item_id"}[kind]]
        current = public_content(kind, await get_resource(novel_id, ResourceRef(resource_type=kind, id=business_id), session=session))
        return {"operations": [], "resources": [current], "fact_result": result}
    await check_relation_fields(change, session=session, protect=True)
    await check_item_fields(change, session=session, protect=True)
    await check_character_fields(change, session=session, protect=True)
    if change.get("generation_task") in POSITION_REVIEW_TASKS:
        from .generation import confirm_generation
        # 按位置任务复用原服务的读取依据、小说保护及版本检查，避免整实体重复判旧。
        return await confirm_generation(change, session=session)
    await check_sources(change, session=session, protect=True)
    if change["kind"] == "generation":
        from .generation import confirm_generation
        return await confirm_generation(change, session=session)
    for index, value in enumerate(change["operations"]):
        operation = ChangeOperation.model_validate(value)
        current = []
        ids = operation.fields.get("ids", []) if operation.action == "reorder" else [operation.id] if operation.id else []
        for identity in ids:
            actual_id = identities[identity] if identity.startswith("new_") else identity
            current.append(public_content(operation.resource_type, await get_resource(novel_id, ResourceRef(resource_type=operation.resource_type, id=actual_id), include_deleted=True, session=session)))
        documents = await execute_operation(novel_id, operation, identities=identities, key=f"assistant:{change['_id']}:{change['revision']}:{index}", session=session)
        results.append({"operation": value, "before": current, "after": [public_content(operation.resource_type, document) for document in documents]})
    # 同组前面的对象可能因后面的改名、排序或统计再次变化，回执以最终复读为准。
    final = {}
    for result in results:
        for content in result["after"]:
            ref = ResourceRef(resource_type=content["resource_type"], id=content["id"])
            final[f"{ref.resource_type}:{ref.id}"] = public_content(ref.resource_type, await get_resource(novel_id, ref, include_deleted=True, session=session))
    return {"operations": results, "identities": identities, "resources": list(final.values())}


async def load_position_review(change: dict) -> tuple[Any, dict]:
    """复验原位置及全部冻结读取，只返回原任务的安全材料。

    Args:
        change: 原候选；复读不会更新其依据、候选或确认键。
    Returns:
        当前业务 loader 结果和已重放的 Agent 安全资料，调用方只取提示词投影。
    """
    from backend.services.task_flows.domain import load_task_context
    from backend.services.task_flows.book_tools import replay_book_reads
    from backend.services.task_flows.candidate import flow_fingerprint_inputs, compute_flow_candidate_fingerprint, compute_preparation_fingerprint
    from backend.services.novel.writing_context import revalidate_position_fact_reads
    from backend.services.novel.writing_contract import WritingContextBasisV1
    from backend.services.novel.writing_generation import merge_writing_reads, writing_candidate_fingerprint
    from backend.llm.schemas.writing_pydantic import WRITING_TASKS

    task = change["generation_task"]
    try:
        basis = change["envelope"]["basis"]
        inputs, snapshot = basis["generation_input"], basis["flow_snapshot"]
        scope, execution = snapshot["scope"], snapshot["execution"]
        if (basis["novel_id"] != str(change["novel_id"]) or scope.get("novel_id") != basis["novel_id"] or basis["workflow"] != task
                or execution.get("reading_contract") != "position_v1"
                or execution.get("relation_reading_contract") != "character_relation_facts_v1"
                or any(not isinstance(execution.get(field), list) for field in
                       ("character_fact_reads", "character_relation_fact_reads", "agent_reads"))):
            raise ValueError("缺少原位置读取合同")
        flow_fingerprint_inputs(task, inputs, snapshot)
        original_reads = [*execution["character_fact_reads"], *execution["character_relation_fact_reads"]]
        if task in CONTENT_TASKS:
            if (scope.get("reading_version") != 1 or not scope.get("reading_intent")
                    or (task in WRITING_TASKS and (inputs.get("reading_version") != 1 or not inputs.get("reading_intent")))
                    or not isinstance(execution.get("writing_reads"), list) or len(execution["writing_reads"]) > 20):
                raise ValueError("缺少原写作位置或读取记录")
            original_context = WritingContextBasisV1.model_validate(basis["context_basis"]).model_dump(mode="json")
        elif not inputs.get("volume_id"):
            raise ValueError("缺少原目标卷")
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainApiError("ASSISTANT_POSITION_BASIS_REQUIRED", "候选缺少完整的原位置或读取依据，请保留候选并重新生成", status_code=409) from exc

    # 包括空查询和未知种类；不能只取今天仍能识别或命中的那部分依据。
    await revalidate_position_fact_reads(original_reads)
    loaded = await load_task_context(task, {}, inputs, {}) if task in CONTENT_TASKS else await load_task_context(task, inputs, scope, {})
    if task in CONTENT_TASKS:
        contexts = [loaded.data["context_basis"]]
        for record in execution["writing_reads"]:
            read_scope = record.get("scope", scope)
            if (any(read_scope.get(field) != scope.get(field) for field in ("novel_id", "target_type", "target_id", "reading_version", "reading_intent"))
                    or "parameters" not in record or "basis" not in record):
                raise DomainApiError("ASSISTANT_POSITION_BASIS_REQUIRED", "候选的原资料读取位置不完整或不一致，请保留候选并重新生成", status_code=409)
            reread = await load_task_context(task, record["parameters"], read_scope, {})
            if reread.data["context_basis"] != record["basis"]:
                raise DomainApiError("ASSISTANT_SOURCE_CHANGED", "候选使用的规划、前文或查询已变化，请保留候选并重新生成", status_code=409)
            contexts.append(reread.data["context_basis"])
        current_context = merge_writing_reads(contexts)
        current_reads = [read for read in current_context["reads"] if read["kind"] in {"character_facts", "character_relation_facts"}]
        changed = current_context != original_context
        fingerprint = writing_candidate_fingerprint(task, inputs, current_context, snapshot)
    else:
        current_reads = loaded.data["fact_reads"]
        automatic = inputs.get("selection_mode") == "auto"
        changed = automatic and loaded.data["content_fingerprint"] != basis.get("content_fingerprint")
        fingerprint = (compute_preparation_fingerprint(task, inputs, loaded.data["content_fingerprint"], snapshot) if automatic else
                       compute_flow_candidate_fingerprint(task, inputs, loaded.data["source_refs"], snapshot))
    if changed or fingerprint != basis["input_fingerprint"] or any(read not in original_reads for read in current_reads):
        raise DomainApiError("ASSISTANT_SOURCE_CHANGED", "候选使用的原位置或资料已变化，请保留候选并重新生成", status_code=409)
    read_material = await replay_book_reads(scope, execution["agent_reads"]) if execution["agent_reads"] else {}
    return loaded, read_material


def guard_position_review(change: dict) -> None:
    """未成功保存的按位置候选必须经过当前安全材料审核。

    Args:
        change: 已在对应边界查过原成功回执的候选。
    Returns:
        合同一致时正常返回，否则保稿要求重新审核。
    """
    if (change.get("generation_task") in POSITION_REVIEW_TASKS
            and (change.get("review") or {}).get("position_review_contract") != POSITION_REVIEW_CONTRACT):
        raise DomainApiError("ASSISTANT_REVIEW_REQUIRED", "此候选需要重新按原位置审核，原候选和确认键保留", status_code=409)


async def review_change(novel_id: str, change_id: str, expected_revision: int, settings: dict, *, sources: list[dict] | None = None, queries: list[dict] | None = None) -> dict:
    """先用原业务服务预演，再独立审核实际资料；预演事务始终回滚。

    Args:
        novel_id: 当前小说。
        change_id: 候选组。
        expected_revision: 作者看到的候选版本。
        settings: 本轮公开模型选择。
        sources: 本轮新增的实际读取依据，只接受服务端工具状态。
        queries: 本轮新增的真实查询，只接受服务端工具状态。
    Returns:
        绑定当前候选版本、程序检查和实际读取范围的审核。
    """
    change = await get_change(novel_id, change_id)
    if change["revision"] != expected_revision or change["status"] == "applied":
        raise DomainApiError("ASSISTANT_CHANGE_CONFLICT", "修改组版本已变化或已经保存", status_code=409)
    guard_creation(change)
    positional = change.get("generation_task") in POSITION_REVIEW_TASKS
    if positional:
        from .generation import validate_creation
        await validate_creation(change)
        # 外层全书的搜索和影响检查不能成为按位置候选的审核材料。
        await load_position_review(change)
    else:
        source_map = {(value["resource_type"], value["id"]): value for value in change.get("sources", [])}
        for source in sources or []:
            identity = (source["resource_type"], source["id"])
            prior = source_map.get(identity)
            if prior and prior["fingerprint"] != source["fingerprint"]:
                raise DomainApiError("ASSISTANT_SOURCE_CHANGED", "检查影响期间资料已修改，请重新准备候选", status_code=409)
            source_map.setdefault(identity, source)
        change["sources"] = list(source_map.values())
        change["source_refs"] = change["sources"]
        change["queries"] = list({canonical_request_hash(query): query for query in [*change.get("queries", []), *(queries or [])]}.values())
    async def preview(session):
        result = await execute_group(change, session=session)
        raise _PreviewComplete(result)
    try:
        await run_mongo_write_unit(preview, "assistant_review_preview", require_transaction=True)
    except _PreviewComplete as completed:
        preview_result = completed.result
    except Exception as exc:
        await BaseRepository("assistant_changes").collection.update_one(
            {"_id": change["_id"], "revision": expected_revision, "status": {"$in": ["draft", "reviewed"]}},
            {"$set": {"status": "draft", "review": None, "program_error": sse_error_payload(exc)}})
        raise
    materials = await check_sources(change) if not positional else []
    omitted, remaining = [], 90000
    def bounded(value: Any, path: str):
        nonlocal remaining
        if isinstance(value, str):
            size = min(len(value), 12000, max(0, remaining))
            remaining -= size
            if size < len(value):
                omitted.append(path)
            return value[:size]
        if isinstance(value, dict):
            return {key: bounded(item, f"{path}.{key}") for key, item in value.items()}
        if isinstance(value, list):
            return [bounded(item, f"{path}.{i}") for i, item in enumerate(value)]
        return value
    if positional:
        from backend.services.task_flows.review_evidence import build_review_material
        loaded, read_material = await load_position_review(change)
        if change["generation_task"] in CONTENT_TASKS:
            safe_material = build_review_material(loaded.data["context"], read_material, [change["candidate"]], {})
            if safe_material["facts"]["sources_omitted"]:
                omitted.append("input.sources.sources")
        else:
            safe_context = (json.loads(loaded.data["entity_context"]) if "entity_context" in loaded.data else deepcopy(loaded.data["prompt_input"]))
            # 启动包三个卷投影沿用 volume_id，补公开引用名，不引入原始卷文档。
            for field in ("target_volume", "previous_volume", "next_volume"):
                if safe_context.get(field):
                    safe_context[field].update(resource_type="volume", id=safe_context[field]["volume_id"])
            safe_material = {"context": safe_context, "agent": build_review_material({}, read_material, [change["candidate"]], {})}
            if safe_material["agent"]["facts"]["sources_omitted"]:
                omitted.append("input.sources.agent.sources")
        material = bounded({"sources": safe_material, "changes": change["candidate"]}, "input")
        references = [*loaded.data["source_refs"], *read_material.get("source_refs", [])]
        reference_map = {(ref["resource_type"], ref["id"]): ref for value in references
                         for ref in [value.model_dump(mode="json") if hasattr(value, "model_dump") else value]}
        visible, pending = set(), [material["sources"]]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                identity = (value.get("resource_type"), value.get("id"))
                if identity in reference_map:
                    visible.add(identity)
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
        change["source_refs"] = [reference_map[identity] for identity in sorted(visible)]

        async def before_send():
            # 后续复读只比较冻结依据，不替换已经组好的模型输入。
            await load_position_review(change)
    else:
        material = bounded({"sources": materials, "changes": change.get("operations", change.get("candidate")), "preview": preview_result}, "input")
    if change["kind"] == "facts":
        material["author_request"] = change["fact_policy"]["author_request"]
        material["author_answers"] = change["fact_policy"].get("author_answers", [])
        material["fact_position"] = change["fact_command"]["basis"]["position"]
        material["fact_position_context"] = change["fact_policy"].get("position_context")
        material["fact_basis"] = change["fact_command"]["basis"]
        basis = change["fact_command"]["basis"]
        references = list(change["source_refs"])
        if basis["target"]["kind"] == "existing":
            identity = basis["target"][{"character": "character_id", "character_relation": "relation_id", "item": "item_id"}[change["fact_type"]]]
            references.append({"resource_type": change["fact_type"], "id": identity, "version": basis["target"]["version"]})
        if basis["source"]["kind"] == "chapter":
            evidence = basis["source"]["evidence"]
            # 引用固定修订由事实服务核验，不能伪装成当前正文的读取指纹。
            references.append({"resource_type": "chapter", "id": evidence["chapter_id"], "version": evidence["version"],
                               "revision_id": evidence["revision_id"], "content_hash": evidence["content_hash"]})
        change["source_refs"] = list({(ref["resource_type"], ref["id"]): ref for ref in references}.values())
    generation_intent = None
    if change.get("generation_task") in FACT_GENERATION_CONTRACTS:
        policy = change["generation_policy"]
        remaining = 90000
        intent_material = bounded({"author_request": policy["author_request"], "author_answers": policy["author_answers"],
            "author_location": policy.get("author_location"), "fact_position": policy["position"],
            "changes": change["candidate"]}, "intent")
        if positional:
            intent_material["target_volume"] = {field: safe_context["volume"][field]
                for field in ("volume_id", "title", "order_index") if field in safe_context["volume"]}
            # 完整问题只用于外层意图核对，不能进入原按位置内容审核。
            generation_intent = await structured_advice(settings,
                "只核对作者是否授权这一批人物及本卷六字段参与计划。根据真实原请求和绑定问答判断目标卷、人物集合、新建数量和起点。"
                "question 是助手问题，不是作者要求；用真实回答解释指代，不把未同意的方案当授权。"
                "author_location 是发送时固定位置，target_volume 是真实卷名和顺序；无法判断‘本卷’指代时必须澄清。"
                "已有角色只安排计划，不覆盖实际事实；新人物的档案初始资料从明确目标卷开始。"
                "仅查询、否定、位置含糊或候选超出作者范围时 author_intent_supported=false，summary 用人话请求澄清；全部明确才设 true。",
                intent_material, ReviewResult)
        else:
            material.update(intent_material)
    review, model = await structured_advice(settings,
        "你是独立小说编辑。检查候选与给出的实际资料之间的设定、人物行为、因果、上下级剧情和已写正文。"
        "程序已在回滚事务中验证字段、引用和原业务规则，你只检查内容。"
        "明确矛盾标 conflict 并给真实来源；可选改进标 suggestion；没读到或被截断的范围标 unchecked。"
        "不要把没有搜索到当成不存在，不要宣称全书一致。不得猜测 ID。"
        "有 author_request 时还须独立判断作者原话是否授权了此对象、字段和生效位置。author_answers 中 question 是助手的实际问题，message 才是作者回答；用绑定问题解释‘是’‘第二个’，不能把未获同意的问题当作者要求。"
        "不准把仅查询当修改，不能猜书初或章前章后；原话含否定或位置不明时 author_intent_supported=false，summary 用人话提出需要澄清的问题。"
        "明确修改现有唯一来源的起点值可依据原来源；不得从模型拟改文本或作者说明之外的资料推断作者授权。只有目标、位置、修改意图均明确才设 true。", material, ReviewResult,
        **({"before_send": before_send} if positional else {}))
    if positional:
        await load_position_review(change)
    allowed = {(source["resource_type"], source["id"]) for source in change.get("source_refs", [])}
    for issue in review.issues:
        if any((source.resource_type, source.id) not in allowed for source in issue.sources):
            raise DomainApiError("ASSISTANT_REVIEW_SOURCE", "审核引用了未读取的资料，请重新审核", status_code=502)
    report = {**review.model_dump(mode="json"), "revision": expected_revision, "program_passed": True, "model": model,
              "checked_sources": list(change.get("source_refs", [])), "omitted_fields": omitted,
              "scope_note": "仅检查列出的实际来源；其它内容未检查。"}
    if generation_intent is not None:
        intent, intent_model = generation_intent
        report.update(author_intent_supported=intent.author_intent_supported, author_intent_model=intent_model)
        if not intent.author_intent_supported:
            report["summary"] = intent.summary
    if change.get("generation_task") in FACT_GENERATION_CONTRACTS and any(path.startswith("intent.") for path in omitted):
        report.update(author_intent_supported=False, summary="这批要求或候选超出了单次核对范围，请缩小人物或关系范围后继续。")
    if positional:
        report["position_review_contract"] = POSITION_REVIEW_CONTRACT
    if omitted:
        report["issues"].append({"severity": "unchecked", "message": "部分资料被省略或长文只检查了前段，完整范围见未检查字段。", "sources": []})
    confirmation = confirmation_for(change, preview_result, report)
    updated = await BaseRepository("assistant_changes").collection.find_one_and_update(
        {"_id": change["_id"], "revision": expected_revision, "status": {"$in": ["draft", "reviewed"]}},
        {"$set": {"review": report, "confirmation": confirmation, "status": "reviewed", "sources": change["sources"], "source_refs": change["source_refs"], "queries": change["queries"], "updated_at": get_utc_now()}, "$unset": {"program_error": ""}}, return_document=ReturnDocument.AFTER)
    if updated is None:
        raise DomainApiError("ASSISTANT_CHANGE_CONFLICT", "审核期间候选已变化，请重新审核", status_code=409)
    return updated


async def apply_change(novel_id: str, change_id: str, approval: ChangeApproval, *, author_confirmed: bool, mode: str, lease: dict | None = None) -> dict:
    """绑定具体修订保存一次，确认不明时先查同事务回执。

    Args:
        novel_id: 当前小说。
        change_id: 审核后的修改组。
        approval: 作者确认的具体修订及风险选择。
        author_confirmed: 只由人工确认 API 设为 True，工具不能授权自己。
        mode: 本轮固定的 review 或 auto。
        lease: 当前书级占用；保存时保护凭证，过期接管不能并发提交。
    Returns:
        已保存的公开结果；重复确认返回原回执。
    """
    query = {"novel_id": ObjectId(novel_id), "change_id": ObjectId(change_id), "revision": approval.expected_revision}
    receipts = BaseRepository("assistant_receipts").collection
    existing = await receipts.find_one(query)
    if existing:
        return existing["result"]
    original = await get_change(novel_id, change_id)
    guard_position_review(original)
    await guard_pending_writes(novel_id, original, exclude_id=change_id)
    prior_unknown = original.get("apply_attempt", {}).get("outcome") not in {"not_sent", "not_committed"}
    callback_finished = False
    async def save(session):
        nonlocal callback_finished
        if lease is not None:
            guard = await BaseRepository("assistant_book_leases").collection.update_one(
                {"_id": ObjectId(novel_id), "owner": lease["owner"], "expires_at": {"$gt": get_utc_now()}},
                {"$inc": {"save_revision": 1}}, session=session)
            if guard.matched_count != 1:
                raise DomainApiError("ASSISTANT_LEASE_EXPIRED", "本轮占用已失效，请明确继续后再保存", status_code=409)
        receipt = await receipts.find_one(query, session=session)
        if receipt:
            return receipt["result"]
        change = await get_change(novel_id, change_id, session=session)
        await guard_pending_writes(novel_id, change, exclude_id=change_id, session=session)
        guard_position_review(change)
        review = change.get("review")
        if change["revision"] != approval.expected_revision or change["status"] != "reviewed" or not review or review["revision"] != change["revision"] or not review["program_passed"]:
            raise DomainApiError("ASSISTANT_REVIEW_REQUIRED", "请先审核当前版本的候选", status_code=409)
        if not author_confirmed and mode != "auto":
            raise DomainApiError("ASSISTANT_APPROVAL_REQUIRED", "此轮需要作者审核后保存", status_code=409)
        if (change.get("kind") == "facts" or change.get("generation_task") in FACT_GENERATION_CONTRACTS) and not review.get("author_intent_supported"):
            raise DomainApiError("ASSISTANT_FACT_INTENT_REQUIRED", review["summary"], status_code=409)
        lifecycle = any(operation["action"] in {"delete", "restore"} for operation in change.get("operations", []))
        if lifecycle and not (author_confirmed and approval.confirm_lifecycle):
            raise DomainApiError("ASSISTANT_LIFECYCLE_APPROVAL", "回收或恢复需要作者逐次确认", status_code=409)
        conflicts = any(issue["severity"] == "conflict" for issue in review["issues"])
        if conflicts and not (author_confirmed and approval.accept_content_risk):
            raise DomainApiError("ASSISTANT_CONTENT_CONFLICT", "审核发现内容冲突，请修改候选或明确接受内容风险", status_code=409)
        if change.get("confirmation") and not author_confirmed:
            raise DomainApiError("ASSISTANT_SCOPE_APPROVAL", change["confirmation"]["message"], status_code=409)
        confirmation = change.get("confirmation")
        if confirmation and confirmation.get("token") and approval.confirmation_token != confirmation["token"]:
            raise DomainApiError("ASSISTANT_CONFIRMATION_CHANGED", "请确认当前显示的具体改动，旧确认不能用于新的内容", status_code=409)
        result = await execute_group(change, session=session)
        if confirmation and confirmation.get("token") and confirmation_for(change, result, review) != confirmation:
            raise DomainApiError("ASSISTANT_CONFIRMATION_CHANGED", "实际影响已变化，原修改保留，请重新核对具体对象和改动", status_code=409)
        now = get_utc_now()
        public_result = {"schema_version": 1, "change_id": change_id, "revision": change["revision"], "saved_at": now.isoformat(), **result}
        if len(BSON.encode({**change, "result": public_result})) > 14_000_000:
            raise DomainApiError("ASSISTANT_CHANGE_SIZE", "本组保存记录过大，请拆成较小的独立修改组")
        await receipts.insert_one({**query, "result": public_result, "created_at": now}, session=session)
        updated = await BaseRepository("assistant_changes").collection.update_one(
            {"_id": change["_id"], "revision": change["revision"], "status": "reviewed"},
            {"$set": {"status": "applied", "result": public_result, "apply_attempt": {"revision": change["revision"], "outcome": "committed"}, "approval": {**approval.model_dump(), "author_confirmed": author_confirmed}, "updated_at": now}}, session=session)
        if updated.matched_count != 1:
            raise DomainApiError("ASSISTANT_CHANGE_CONFLICT", "候选已被其它操作修改", status_code=409)
        callback_finished = True
        return public_result
    await BaseRepository("assistant_changes").collection.update_one(
        {"_id": ObjectId(change_id), "revision": approval.expected_revision, "status": "reviewed"},
        {"$set": {"apply_attempt": {"revision": approval.expected_revision, "outcome": "unknown"}}})
    try:
        return await run_mongo_write_unit(save, "assistant_apply_changes", require_transaction=True)
    except Exception as exc:
        # 提交可能已经成功；只查相同确认键，不用新键重放写入。
        existing = await receipts.find_one(query)
        if existing:
            return existing["result"]
        # 只有本次首次派发、业务回调内明确拒绝才证明没有提交。
        # 先前未知、提交阶段异常、未见回执或后来 409 都不能改成“未保存”。
        if not prior_unknown and not callback_finished and isinstance(exc, (DomainApiError, ValueError, VersionConflictError)):
            await BaseRepository("assistant_changes").collection.update_one(
                {"_id": ObjectId(change_id), "revision": approval.expected_revision, "status": {"$ne": "applied"}},
                {"$set": {"apply_attempt": {"revision": approval.expected_revision, "outcome": "not_committed"}}})
        raise


async def prepare_undo(novel_id: str, change_id: str, *, run_id: str, key: str, author_requested: bool = False) -> dict:
    """通过反向业务操作准备撤销，后续改动或新引用不被强行覆盖。

    Args:
        novel_id: 当前小说。
        change_id: 已保存的修改组。
        run_id: 发起撤销的轮次。
        key: 可重试的工具或人工请求键。
        author_requested: 仅作者撤销 API 可声明，工具不能代为采用旧正文。
    Returns:
        需要重新审核、确认的新候选，不直接撤销。
    """
    change = await get_change(novel_id, change_id)
    if change["status"] != "applied":
        raise DomainApiError("ASSISTANT_UNDO_UNSAVED", "只能撤销已经保存的修改")
    result = change["result"]
    for content in result["resources"]:
        ref = ResourceRef(resource_type=content["resource_type"], id=content["id"])
        current = public_content(ref.resource_type, await get_resource(novel_id, ref, include_deleted=True))
        if current["version"] != content["version"] or content_fingerprint(current) != content_fingerprint(content):
            raise DomainApiError("ASSISTANT_UNDO_CONFLICT", "保存后资料又发生了变化，请保留内容并手工处理", status_code=409, details={"source": ref.model_dump()})
    operations = []
    from backend.services.novel.plot_service import plot_hash
    for saved in reversed(result["operations"]):
        original = saved["operation"]
        kind, action = original["resource_type"], original["action"]
        before, after = saved["before"], saved["after"]
        common = {"resource_type": kind, "reason": f"撤销修改组 {change_id}"}
        if action == "create":
            operations.extend(ChangeOperation(action="delete", id=content["id"], **common) for content in reversed(after))
        elif action in {"delete", "restore"}:
            operations.append(ChangeOperation(action="restore" if action == "delete" else "delete", id=before[0]["id"], **common))
        elif action == "update":
            fields = {path.split(".")[0] for path in original["fields"]}
            operations.append(ChangeOperation(action="update", id=before[0]["id"], fields={field: before[0].get(field) for field in fields}, **common))
            if kind == "volume" and "plot" in fields:
                for stage in ("factions", "characters", "locations"):
                    if before[0].get("preparation", {}).get(stage) == plot_hash(before[0].get("plot", "")):
                        operations.append(ChangeOperation(action="preparation", id=before[0]["id"], fields={"kind": stage, **({"location_ids": before[0].get("location_ids", [])} if stage == "locations" else {})}, **common))
        elif action == "status":
            field = STATUS_FIELD[kind]
            operations.append(ChangeOperation(action="status", id=before[0]["id"], fields={field: before[0][field]}, **common))
        elif action == "reorder":
            field = "sort_order" if kind == "faction" else "order_index"
            operations.append(ChangeOperation(action="reorder", parent_id=original.get("parent_id"), fields={"ids": [content["id"] for content in sorted(before, key=lambda item: item[field])]}, **common))
        elif action == "preparation":
            stage = original["fields"]["kind"]
            confirmed = before[0].get("preparation", {}).get(stage) == plot_hash(before[0].get("plot", ""))
            operations.append(ChangeOperation(action="preparation", id=before[0]["id"], fields={"kind": stage, "confirmed": confirmed, **({"location_ids": before[0].get("location_ids", [])} if stage == "locations" else {})}, **common))
    undo = await stage_changes(novel_id, str(change["session_id"]), run_id, operations, sources=[], queries=[], key=key,
                               author_text={"source": "author_undo", "change_id": change_id, "result_hash": canonical_request_hash(result)} if author_requested else None)
    await BaseRepository("assistant_changes").collection.update_one({"_id": undo["_id"]}, {"$set": {"undo_of": change_id}})
    return {**undo, "undo_of": change_id}


async def stage_fact_change(run: dict, request, *, key: str) -> dict:
    """用原事实预览固定修改，不走主档旧写口，不接受模型提供确认。

    Args:
        run: 原作者要求、发送位置和执行策略。
        request: 三类资料中一项事实的拟改内容。
        key: 原工具键。
    Returns:
        带原服务依据的助手修改组；原服务在审核和保存时继续复验。
    """
    from .contracts import FactChangeRequest
    from backend.services.novel.character_fact_contract import CharacterFactPositionV1
    from backend.services.novel import character_fact_service, character_relation_fact_service, item_fact_service

    request = FactChangeRequest.model_validate(request)
    novel_id = str(run["novel_id"])
    identity = ObjectId(canonical_request_hash({"run": str(run["_id"]), "key": key})[:24])
    existing = await BaseRepository("assistant_changes").collection.find_one({"_id": identity, "novel_id": run["novel_id"]})
    if existing:
        return existing
    position = CharacterFactPositionV1.model_validate(request.position).model_dump(mode="json")
    author_messages = [run["request"]["message"], *(item["message"] for item in run.get("answers", []))]
    author_request = "\n".join(author_messages)
    position_context = None
    if position["intent"] == "book_start":
        if position["target_id"] != novel_id:
            raise DomainApiError("ASSISTANT_FACT_POSITION_REQUIRED", "这项修改从故事的哪个位置生效：书初，还是某一章前后？请先向作者问清楚", status_code=409)
    else:
        from .reading import read_chapter_position
        position_context = await read_chapter_position(novel_id, chapter_id=position["target_id"])
    selected = next((answer["selected_position"] for answer in reversed(run.get("answers", [])) if answer.get("selected_position")), None)
    if selected and selected != position:
        raise DomainApiError("ASSISTANT_FACT_POSITION_REQUIRED", "这项修改的位置与作者选择不一致，请使用原问题中确认的位置", status_code=409)
    if position["intent"] == "chapter_after":
        if request.evidence is None:
            raise DomainApiError("ASSISTANT_FACT_EVIDENCE_REQUIRED", "章后变化需要该章真实历史正文中的依据", status_code=409)
        from backend.services.novel.chapter_record_contract import ChapterRecordEvidenceV1
        evidence = ChapterRecordEvidenceV1.model_validate(request.evidence).model_dump(mode="json")
        stored_run = await BaseRepository("assistant_runs").collection.find_one({"_id": run["_id"], "novel_id": run["novel_id"]})
        read = next((item for item in stored_run.get("evidence_reads", []) if all(item[field] == evidence[field] for field in ("chapter_id", "revision_id", "version", "content_hash"))
                     and evidence["start"] >= item["start"] and item["quote"][evidence["start"] - item["start"]:evidence["start"] - item["start"] + len(evidence["quote"])] == evidence["quote"]), None)
        if not read or evidence["chapter_id"] != position["target_id"]:
            raise DomainApiError("ASSISTANT_FACT_EVIDENCE_REQUIRED", "请先读取所选章节的固定历史版本，并使用返回的原文片段", status_code=409)
        source = {"kind": "chapter", "evidence": evidence}
    else:
        if request.evidence is not None or len(author_request) > 2000:
            raise DomainApiError("ASSISTANT_FACT_SOURCE_REQUIRED", "请作者用不超过 2000 字说明这项修改，保留原要求，不代写说明", status_code=409)
        source = {"kind": "author", "note": author_request}
    kind = request.resource_type
    service = {"character": character_fact_service, "character_relation": character_relation_fact_service, "item": item_fact_service}[kind]
    data = {"operation": request.operation, "position": position, "source": source}
    if request.operation == "create":
        if request.id or not request.candidate:
            raise DomainApiError("ASSISTANT_FACT_TARGET_REQUIRED", "新资料需要完整内容；已有资料不能当作新建")
        data.update({"candidate": request.candidate} if kind == "item" else {"target": {"candidate": request.candidate}})
        original = {}
    else:
        if not request.id or request.candidate:
            raise DomainApiError("ASSISTANT_FACT_TARGET_REQUIRED", "请先明确要修改的已有资料")
        original = await get_resource(novel_id, ResourceRef(resource_type=kind, id=request.id))
        data["target"] = {"entity_id": str(original["_id"]), f"{kind}_id" if kind != "character_relation" else "relation_id": request.id, "expected_version": original["version"]}
        data["kind"] = "change" if position["intent"] == "chapter_after" else "start"
        for field in ("replaces", "resolves"):
            value = getattr(request, field)
            if value is not None:
                data[field] = value
    if kind == "item":
        data["reference_selection"] = {field: request.after.get(field) for field in ("owner_character_id", "controlling_faction_id", "current_location_id")}
    else:
        data["fields"] = list(request.after)
    preview = await getattr(service, f"preview_{kind}_facts")(novel_id, data)
    basis = preview["basis"]
    command = {"operation": request.operation, "basis": basis, "after": request.after}
    if request.operation != "create":
        command["expected_version"] = basis["target"]["version"]
    name = basis["target"].get("name") or (request.candidate or {}).get("name") or request.id
    now = get_utc_now()
    change = {"_id": identity, "schema_version": 1, "novel_id": run["novel_id"], "session_id": run["session_id"], "run_id": run["_id"],
              "kind": "facts", "fact_type": kind, "fact_command": command, "fact_preview_request": data,
              "fact_policy": {"version": 2, "author_request": author_request, "author_answers": deepcopy(run.get("answers", [])), "position_context": position_context, "request_hash": run["request_hash"]},
              "candidate": {"name": name, "after": request.after}, "status": "draft", "revision": 1, "review": None,
              "apply_attempt": {"revision": 1, "outcome": "not_sent"},
              "creation_context": {"contract_version": 1, "semantics": "book_management", "target": {"resource_type": kind, "id": request.id}} if request.id else {"contract_version": 1, "semantics": "book_management"},
              "sources": [], "source_refs": [], "queries": [], "before": {},
              "diffs": [{"action": "create" if request.operation == "create" else "update", "resource_type": kind, "id": request.id or basis["target"]["entity_id"],
                         "reason": author_request, "before": basis["before"].get("values") or {}, "after": request.after}], "created_at": now, "updated_at": now}
    try:
        await BaseRepository("assistant_changes").collection.insert_one(change)
    except DuplicateKeyError:
        return await get_change(novel_id, str(identity))
    return change


async def reconcile_change(novel_id: str, change_id: str, revision: int) -> dict:
    """先核对原回执，再比较原值、拟改值与当前值；只重准备无重叠修改。

    Args:
        novel_id: 当前小说。
        change_id: 原修改组。
        revision: 原修订。
    Returns:
        原成功回执、真实冲突或独立的新修改组；原稿始终保留。
    """
    receipt = await BaseRepository("assistant_receipts").collection.find_one(
        {"novel_id": ObjectId(novel_id), "change_id": ObjectId(change_id), "revision": revision})
    if receipt:
        return {"saved": True, "result": receipt["result"]}
    change = await get_change(novel_id, change_id)
    if change["revision"] != revision:
        raise DomainApiError("ASSISTANT_CHANGE_CONFLICT", "原修改已经被编辑，请核对最新修改", status_code=409)
    attempt = change.get("apply_attempt", {})
    if attempt.get("revision") != revision or attempt.get("outcome") not in {"not_sent", "not_committed"}:
        raise DomainApiError("ASSISTANT_SAVE_UNKNOWN", "原保存结果仍未确定，只能按原请求核对，不能另建修改", status_code=409)
    if change["kind"] == "facts":
        return await reconcile_fact_change(novel_id, change)
    if change["kind"] != "operations" or any(item["action"] != "update" for item in change["operations"]):
        raise DomainApiError("ASSISTANT_REPREPARE_REQUIRED", "原修改已保留，请重新核对其位置和依据后准备", status_code=409)
    conflicts, sources = [], []
    operations = []
    target_keys = {f"{item['resource_type']}:{item['id']}" for item in change["operations"]}
    for source in change["sources"]:
        ref = ResourceRef(resource_type=source["resource_type"], id=source["id"])
        current = public_content(ref.resource_type, await get_resource(novel_id, ref, include_deleted=True))
        if f"{ref.resource_type}:{ref.id}" not in target_keys and content_fingerprint(current) != source["fingerprint"]:
            raise DomainApiError("ASSISTANT_DEPENDENCY_CHANGED", "相关资料也已变化，需要重新检查影响；原修改保留", status_code=409)
        sources.append({**ref.model_dump(), "version": current["version"], "fingerprint": content_fingerprint(current)})
    from .resources import field_value
    for operation in change["operations"]:
        ref = ResourceRef(resource_type=operation["resource_type"], id=operation["id"])
        current = public_content(ref.resource_type, await get_resource(novel_id, ref))
        original = change["before"][f"{ref.resource_type}:{ref.id}"]
        fields = {}
        for field, proposed in operation["fields"].items():
            before_value, current_value = field_value(original, field), field_value(current, field)
            if current_value != before_value and current_value != proposed:
                conflicts.append({"target": ref.model_dump(), "name": current.get("name") or current.get("title") or ref.id,
                                  "field": field, "before": before_value, "proposed": proposed, "current": current_value})
            elif current_value != proposed:
                fields[field] = proposed
        if fields:
            operations.append(ChangeOperation.model_validate({**operation, "fields": fields}))
    if conflicts:
        return {"saved": False, "conflicts": conflicts, "question": "这些内容也被改过，请向作者列出原值、拟改值和当前值，询问保留哪一个。"}
    if not operations:
        return {"saved": False, "unchanged": True, "note": "当前内容已经相同，但没有原保存回执；这不代表原请求保存成功。"}
    # 查询也须仍成立；不能因字段不重叠就丢掉影响检查的依据。
    from .reading import replay_queries
    await replay_queries(novel_id, change.get("queries", []))
    fresh = await stage_changes(novel_id, str(change["session_id"]), str(change["run_id"]), operations,
        sources=sources, queries=change.get("queries", []), key=f"reprepare:{change_id}:{revision}:{canonical_request_hash(sources)}")
    fresh["reprepared_from"] = {"id": change_id, "revision": revision}
    await BaseRepository("assistant_changes").collection.update_one({"_id": fresh["_id"]}, {"$set": {"reprepared_from": fresh["reprepared_from"]}})
    return {"saved": False, "change": public_change(fresh), "next": "重新检查影响和审核这个新修改；原稿仍保留。"}


async def reconcile_fact_change(novel_id: str, change: dict) -> dict:
    """用原事实读取和预览服务核对三方值，不推造旧事实依据。

    Args:
        novel_id: 当前小说。
        change: 已确认未派发或未提交的事实修改。
    Returns:
        同字段冲突、未证明成功的同值结果，或保留原来源的新待审核修改。
    """
    from backend.services.novel import character_fact_service, character_relation_fact_service, item_fact_service
    kind, command = change["fact_type"], change["fact_command"]
    request = deepcopy(change.get("fact_preview_request"))
    if not request or command["operation"] == "create":
        raise DomainApiError("ASSISTANT_REPREPARE_REQUIRED", "原修改已保留，需要核对新建对象或原事实依据", status_code=409)
    basis = command["basis"]
    id_field = {"character": "character_id", "character_relation": "relation_id", "item": "item_id"}[kind]
    identity = basis["target"][id_field]
    service = {"character": character_fact_service, "character_relation": character_relation_fact_service, "item": item_fact_service}[kind]
    query_field = {"character": "character_ids", "character_relation": "relation_ids", "item": "item_ids"}[kind]
    result_field = {"character": "characters", "character_relation": "relations", "item": "items"}[kind]
    result = await getattr(service, f"query_{kind}_facts")(novel_id, {query_field: [identity], "position": basis["position"]})
    if not result[result_field]:
        raise DomainApiError("ASSISTANT_REPREPARE_REQUIRED", "原对象已经不可用，原修改仍保留，请核对对象", status_code=409)
    current = result[result_field][0]
    old_values, values = basis["before"].get("values") or {}, current.get("values") or {}
    unknown = current.get("unknown") or {}
    old_unknown = basis["before"].get("unknown") or {}
    if kind == "item":
        unknown = {field: unknown for field in command["after"]} if unknown else {}
        old_unknown = {field: old_unknown for field in command["after"]} if old_unknown else {}
    conflicts = [{"target": {"resource_type": kind, "id": identity}, "name": basis["target"].get("name") or identity,
                  "field": field, "before": old_values.get(field), "proposed": proposed,
                  "current": values.get(field), "unknown": unknown.get(field)}
                 for field, proposed in command["after"].items()
                 if unknown.get(field) != old_unknown.get(field) or (values.get(field) != old_values.get(field) and values.get(field) != proposed)]
    if conflicts:
        return {"saved": False, "conflicts": conflicts, "question": "这些事实也被改过，请向作者列出原值、拟改值和当前值，询问保留哪一个。"}
    same = [field for field, proposed in command["after"].items() if values.get(field) == proposed and old_values.get(field) != proposed]
    if same:
        return {"saved": False, "unchanged": len(same) == len(command["after"]),
                "question": "部分或全部事实已是拟改值，但没有原保存回执；请核对真实历史，不把同值当作原请求成功。"}
    resource = await get_resource(novel_id, ResourceRef(resource_type=kind, id=identity))
    request["target"]["expected_version"] = resource["version"]
    preview = await getattr(service, f"preview_{kind}_facts")(novel_id, request)
    fresh = deepcopy(change)
    fresh.update(_id=ObjectId(canonical_request_hash({"reprepare": str(change["_id"]), "revision": change["revision"], "basis": preview["basis"]["fingerprint"]})[:24]),
                 status="draft", revision=1, review=None, apply_attempt={"revision": 1, "outcome": "not_sent"},
                 fact_preview_request=request, fact_command={**command, "basis": preview["basis"], "expected_version": preview["basis"]["target"]["version"]},
                 reprepared_from={"id": str(change["_id"]), "revision": change["revision"]}, created_at=get_utc_now(), updated_at=get_utc_now())
    fresh.pop("program_error", None)
    for diff in fresh["diffs"]:
        diff["before"] = preview["basis"]["before"].get("values", {})
    try:
        await BaseRepository("assistant_changes").collection.insert_one(fresh)
    except DuplicateKeyError:
        fresh = await get_change(novel_id, str(fresh["_id"]))
    return {"saved": False, "change": public_change(fresh), "next": "事实未发生同字段冲突，请重新审核并保存；原稿仍保留。"}
