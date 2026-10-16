"""助手的有类型工具目录；所有工具固定在一部小说。"""

from __future__ import annotations

from typing import Any, Literal

from bson import ObjectId
from backend.db.base import BaseRepository
from backend.db.errors import VersionConflictError
from backend.db.write_contracts import canonical_request_hash

from pydantic import Field

from backend.api.error_protocol import DomainApiError
from backend.llm.models import LLMToolDefinition
from backend.services.task_flows.contracts import FlowRef
from backend.services.task_flows.registry import TASKS
from .changes import guard_creation, confirmation_question, guard_pending_writes, apply_change, get_change, prepare_undo, public_change, reconcile_change, review_change, stage_changes, stage_fact_change
from .contracts import AssistantModel, ChangeApproval, ChangeOperation, FactChangeRequest, NavigationTarget, ResourceKind, ResourceRef
from .generation import GENERATION_KINDS, describe_generation, run_generation
from .reading import BookReader, read_chapter_position
from .resources import describe_resource, field_value, get_resource, public_content, sync_index


class EmptyArgs(AssistantModel):
    """无参数工具。"""


class KindArgs(AssistantModel):
    """查看某类资料定义。"""
    kind: ResourceKind


class CatalogueArgs(AssistantModel):
    """有界目录筛选；文字按字面匹配。"""
    kind: ResourceKind | None = None
    query: str = Field(default="", max_length=200)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=50)
    deleted: bool = False
    reference_id: str | None = Field(default=None, max_length=100)
    volume_id: str | None = Field(default=None, max_length=100)


class SearchArgs(AssistantModel):
    """搜索真实业务内容，保留命中位置。"""
    query: str = Field(min_length=1, max_length=200)
    kind: ResourceKind | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=50)


class ReadArgs(ResourceRef):
    """只读指定字段；长文按范围继续。"""
    fields: list[str] = Field(default_factory=list, max_length=20)
    start: int = Field(default=0, ge=0)
    length: int = Field(default=6000, ge=1, le=12000)
    deleted: bool = False


class ReferenceArgs(ResourceRef):
    """从一个实际位置查引用。"""
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=50)


class RelationsArgs(AssistantModel):
    """关系或绑定的有界查询。"""
    kind: Literal["character_relation", "faction_relation", "character_faction_binding"]
    entity_id: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=50)


class StatesArgs(AssistantModel):
    """指定卷内的角色或势力状态。"""
    kind: Literal["character_volume_state", "faction_volume_state"]
    volume_id: str
    entity_id: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=50)


class StageArgs(AssistantModel):
    """同组按依赖顺序提交，新增引用使用前面对象的临时 ID。"""
    operations: list[ChangeOperation] = Field(min_length=1, max_length=50)


class TextEditArgs(ResourceRef):
    """精确字符范围编辑；旧文字必须与已读原文相同。"""
    field: str = Field(min_length=1, max_length=100)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    expected_text: str = Field(max_length=40000)
    replacement: str = Field(max_length=40000)
    reason: str = Field(min_length=1, max_length=2000)


class ChangeArgs(AssistantModel):
    """按服务端 ID 读取当前修改组。"""
    change_id: str


class ReviewArgs(ChangeArgs):
    """审核或自动保存精确修订。"""
    revision: int = Field(ge=1)


class TaskArgs(AssistantModel):
    """检查原 AI 任务的开始表单。"""
    task: str
    flow_ref: FlowRef | None = None


class RunTaskArgs(TaskArgs):
    """只提供开始表单与原按钮位置，不接受客户端伪造候选依据。"""
    inputs: dict[str, Any] = Field(default_factory=dict)
    target: ResourceRef | None = None
    target_field: str | None = None
    depends_on: list[str] = Field(default_factory=list, max_length=20)


class PositionChoice(AssistantModel):
    """问题中的真实位置选项；显示名称由服务端读取。"""
    position: dict[str, Any]


class ChapterRevisionArgs(AssistantModel):
    """先列历史，再按固定版本读取原文；不接受摘要或模型引文。"""
    chapter_id: str | None = None
    chapter_number: int | None = Field(default=None, ge=1)
    version: int | None = Field(default=None, ge=1)
    before_version: int | None = Field(default=None, ge=1)
    start: int = Field(default=0, ge=0)
    length: int = Field(default=6000, ge=1, le=10000)


class AskArgs(AssistantModel):
    """暂停并保留一个作者需要回答的问题。"""
    question: str = Field(min_length=1, max_length=4000)
    choices: list[str] = Field(default_factory=list, max_length=6)
    position_choices: list[PositionChoice] = Field(default_factory=list, max_length=6)
    confirmation_change_id: str | None = None


class FinishArgs(AssistantModel):
    """只总结实际读取和保存结果，不输出私有思考。"""
    message: str = Field(min_length=1, max_length=16000)
    unchecked: list[str] = Field(default_factory=list, max_length=30)


class FactReadArgs(AssistantModel):
    """查询真实位置的三类事实，不使用主档镜像推断剧情状态。"""
    resource_type: Literal["character", "character_relation", "item", "faction"]
    ids: list[str] = Field(min_length=1, max_length=20)
    position: dict[str, Any] | None = None


TOOL_CONTRACTS = {
    "read_chapter_revision": (ChapterRevisionArgs, "读取当前作品的真实章节历史，可按 chapter_id 或作者说的全书 chapter_number 指定。返回真实章号和稳定身份，不传 version 时列版本；指定 version、start、length 返回不可变原文和服务端生成 evidence，可取其中原样子片段用于章后事实；摘要不能作证据。"),
    "reconcile_changes": (ReviewArgs, "修改冲突时先查原回执，再比较原值、拟改值、当前值。未知结果禁止另建；无重叠可重准备，真实冲突用人话 ask_user。"),
    "query_facts": (FactReadArgs, "读取人物、人物关系、势力或物品在明确位置的值和来源，未指定位置则读服务端解析的最新位置。"),
    "stage_fact_change": (FactChangeRequest, "单项新人物/关系/势力/物品及实际状态修改使用此工具；批量人物/关系/势力和卷参与计划使用对应 run_generation_task，不拆成逐项保存。先 query_facts，位置不明确则 ask_user。人工说明由服务器使用作者原话；章后依据须为真实不可变正文。不能提供 confirmed、basis 或伪造来源。"),
    "get_book_overview": (EmptyArgs, "读取当前小说的小型概览和各类资料数量，不展开正文。"),
    "list_resources": (CatalogueArgs, "按类型、文字、位置分页查询摘要目录；每页默认20、最多50条。"),
    "describe_resource": (KindArgs, "查看原业务创建、更新字段定义，准备修改前先了解字段。"),
    "search_resources": (SearchArgs, "在实际保存的业务字段中搜索普通文字，返回带来源的片段。"),
    "read_resource": (ReadArgs, "按明确 fields 读取业务资料；不传字段仅返回摘要。总量默认6000、最多12000字符。"),
    "read_text_range": (ReadArgs, "按字段和字符范围读取长文，继续时使用 next_start。"),
    "find_references": (ReferenceArgs, "查找直接引用此对象的资料；返回分页目录，需要再读具体字段。"),
    "read_relations": (RelationsArgs, "查询当前小说中的人物关系、势力关系或绑定摘要。"),
    "read_volume_states": (StatesArgs, "查询指定卷内的角色或势力状态摘要。"),
    "get_readiness": (ResourceRef, "读取卷、篇章、场景或章节的原生成前置条件，错误不当成资料缺失。"),
    "get_resource_summary": (ResourceRef, "按需生成资料摘要并按内容指纹缓存；可能调用模型，明确标记未读范围。"),
    "stage_create": (StageArgs, "准备增改组，以新建开始；同组依赖按顺序排列，前项 new_ 临时ID可被后项引用，不直接写业务资料。"),
    "stage_update": (StageArgs, "准备增改组，以更新开始；只提交明确字段，同组可包含有关联的其它操作，不直接保存。"),
    "stage_text_edit": (TextEditArgs, "按精确旧文字和字符范围修改管理资料。章节正文必须明确选择创作位置并调用 run_generation_task。"),
    "stage_delete": (StageArgs, "准备回收组，必须等待作者逐次确认，不提供永久删除。"),
    "stage_restore": (StageArgs, "准备恢复组，必须等待作者逐次确认。"),
    "stage_reorder": (StageArgs, "准备完整同父对象排序，fields.ids为期望顺序的完整ID列表。"),
    "stage_status_change": (StageArgs, "准备原业务状态变化，字段和允许状态以业务定义为准。"),
    "stage_preparation_confirmation": (StageArgs, "准备卷内资料确认，fields.kind为factions、characters或locations，地点可附location_ids。"),
    "list_generation_tasks": (EmptyArgs, "列出可复用的原 AI 任务，不运行模型。"),
    "describe_generation_task": (TaskArgs, "读取原任务实际开始表单、默认方案和自定义方案修订。"),
    "run_generation_task": (RunTaskArgs, "执行原任务图。正文及逐级规划必须匹配作者本轮 writing_target，只采用原作者消息和有界数量，不采用模型补写的自由文本；depends_on里的前组必须已保存。"),
    "find_affected_resources": (ChangeArgs, "从修改目标的直接引用、父链、名称和别名查找潜在影响，结果不是已经确认的内容冲突。"),
    "review_changes": (ReviewArgs, "用原服务在回滚事务中预演，再独立检查内容；编辑后必须重新审核。"),
    "apply_changes": (ReviewArgs, "仅在本轮自动模式且审核无明确冲突时保存；回收、恢复仍只由作者确认。"),
    "prepare_undo": (ChangeArgs, "按原回执和当前版本准备反向候选，新增资料的撤销使用回收，不直接覆盖后续修改。"),
    "ask_user": (AskArgs, "确有缺失决定时提问并暂停原任务。事实位置可用 position_choices 列真实章节；风险批准指定 confirmation_change_id，由服务器展示该修订的实际影响。一般澄清不要指定。"),
    "navigate_to_resource": (NavigationTarget, "仅在作者本轮允许跳转时定位资料，普通查询不切换页面。"),
    "finish_turn": (FinishArgs, "结束本轮，说明已保存、待审核、建议和未检查范围，不把候选说成已保存。"),
}


def tool_definitions() -> list[LLMToolDefinition]:
    """生成原生工具定义，工具参数全部使用严格模型。

    Args:
        无。
    Returns:
        当前小说助手允许调用的工具列表。
    """
    return [LLMToolDefinition(name=name, description=description, parameters=model.model_json_schema()) for name, (model, description) in TOOL_CONTRACTS.items()]


async def execute_tool(name: str, arguments: dict, *, run: dict, state: dict, key: str, emit) -> dict:
    """执行当前小说内一个已校验的工具，并记录实际来源。

    Args:
        name: 允许的工具名。
        arguments: 原生调用参数。
        run: 发送时固定的轮次信息。
        state: 可持久化的读取依据和当前状态。
        key: 稳定调用键，用于重试时恢复候选或回执。
        emit: 持久公开事件的回调。
    Returns:
        有界、无凭据的工具结果。
    """
    if name not in TOOL_CONTRACTS:
        raise DomainApiError("ASSISTANT_TOOL_UNKNOWN", "模型调用了未开放的工具")
    args = TOOL_CONTRACTS[name][0].model_validate(arguments)
    novel_id, session_id, run_id = str(run["novel_id"]), str(run["session_id"]), str(run["_id"])
    reader = BookReader(novel_id, state["sources"], state["queries"])
    settings = run["settings"]
    async def reconcile():
        result = await reconcile_change(novel_id, args.change_id, args.revision)
        if result.get("change"):
            state["change_ids"] = list(dict.fromkeys([*state["change_ids"], result["change"]["id"]]))
            await emit("change", result["change"])
        return result
    if name.startswith("stage_") or name == "run_generation_task":
        if name == "stage_fact_change":
            scope = {"kind": "facts", "fact_type": args.resource_type, "fact_target": args.id}
        elif name == "run_generation_task":
            scope = {"kind": "generation", "generation_task": args.task, "creation_context": {"target": args.target.model_dump() if args.target else None}}
        else:
            operations = [item.model_dump() for item in args.operations] if hasattr(args, "operations") else [{"resource_type": args.resource_type, "id": args.id, "action": "update", "fields": {args.field: args.replacement}}]
            guard_creation({"operations": operations, "creation_context": {"contract_version": 1, "semantics": "book_management"}})
            scope = {"kind": "operations", "operations": operations}
        await guard_pending_writes(novel_id, scope)
    if name == "reconcile_changes":
        return await reconcile()
    if name == "read_chapter_revision":
        from backend.services.novel.chapter_service import ChapterService
        from backend.services.novel.chapter_revision_contract import serialize_chapter_revision
        chapter = await read_chapter_position(novel_id, chapter_id=args.chapter_id, chapter_number=args.chapter_number)
        chapter_id = chapter["id"]
        if args.version is None:
            result = await ChapterService.list_revisions(chapter_id, limit=20, before_version=args.before_version)
            return {**result, "chapter": chapter, "data": [serialize_chapter_revision(row, include_content=False) for row in result["data"]]}
        revision = await ChapterService.get_revision(chapter_id, args.version)
        quote = revision["content"][args.start:args.start + args.length]
        if not quote:
            raise DomainApiError("ASSISTANT_EVIDENCE_EMPTY", "这个位置没有正文，请读取该修订的有效正文范围")
        evidence = {"chapter_id": chapter_id, "revision_id": str(revision["_id"]), "version": revision["version"],
                    "content_hash": revision["content_hash"], "start": args.start, "quote": quote}
        await BaseRepository("assistant_runs").collection.update_one({"_id": run["_id"]}, {"$addToSet": {"evidence_reads": evidence}})
        run.setdefault("evidence_reads", []).append(evidence)
        return {"title": revision["title"], "chapter": chapter, "evidence": evidence, "next_start": args.start + len(quote),
                "has_more": args.start + len(quote) < len(revision["content"]), "notice": "这是指定历史修订的原始正文，不能用摘要替代。"}
    if name == "query_facts":
        from backend.services.novel import character_fact_service, character_relation_fact_service, item_fact_service, faction_fact_service
        service = {"character": character_fact_service, "character_relation": character_relation_fact_service, "item": item_fact_service, "faction": faction_fact_service}[args.resource_type]
        id_field = {"character": "character_ids", "character_relation": "relation_ids", "item": "item_ids", "faction": "faction_ids"}[args.resource_type]
        return await getattr(service, f"query_{args.resource_type}_facts")(novel_id, {id_field: args.ids, "position": args.position})
    if name == "stage_fact_change":
        change = await stage_fact_change(run, args, key=key)
        state["change_ids"] = list(dict.fromkeys([*state["change_ids"], str(change["_id"])]))
        await emit("change", public_change(change))
        return {"change_id": str(change["_id"]), "revision": change["revision"], "next": "使用 review_changes 检查，再 apply_changes 保存。"}
    if name == "get_book_overview":
        coverage = await sync_index(novel_id)
        novel = await reader.read(ResourceRef(resource_type="novel", id=novel_id))
        return {"novel": novel, "counts": coverage["counts"], "location": run["request"].get("location"), "mode": settings["mode"]}
    if name == "describe_resource":
        return describe_resource(args.kind)
    if name == "list_resources":
        return await reader.catalogue(args.model_dump())
    if name == "search_resources":
        return await reader.search(args.model_dump())
    if name in {"read_resource", "read_text_range"}:
        return await reader.read(ResourceRef(resource_type=args.resource_type, id=args.id), fields=args.fields, start=args.start, length=args.length, deleted=args.deleted)
    if name == "find_references":
        ref = ResourceRef(resource_type=args.resource_type, id=args.id)
        await reader.read(ref)
        return await reader.catalogue({"reference_id": ref.id, "offset": args.offset, "limit": args.limit})
    if name == "read_relations":
        return await reader.catalogue({"kind": args.kind, "reference_id": args.entity_id, "offset": args.offset, "limit": args.limit})
    if name == "read_volume_states":
        await reader.read(ResourceRef(resource_type="volume", id=args.volume_id))
        return await reader.catalogue({"kind": args.kind, "volume_id": args.volume_id, "reference_id": args.entity_id, "offset": args.offset, "limit": args.limit})
    if name == "get_readiness":
        from backend.services.novel.writing_context import get_writing_readiness
        if args.resource_type not in {"volume", "arc", "scene", "chapter"}:
            raise DomainApiError("ASSISTANT_READINESS_TARGET", "请选择卷、篇章、场景或章节")
        await reader.read(args)
        return await get_writing_readiness(novel_id, args.resource_type, args.id)
    if name == "get_resource_summary":
        return await reader.summary(args, settings)
    if name.startswith("stage_"):
        if name == "stage_text_edit":
            ref = ResourceRef(resource_type=args.resource_type, id=args.id)
            await reader.read(ref, fields=[args.field], start=args.start)
            current = public_content(ref.resource_type, await get_resource(novel_id, ref))
            text = field_value(current, args.field)
            if not isinstance(text, str) or args.end < args.start or args.end > len(text) or text[args.start:args.end] != args.expected_text:
                raise DomainApiError("ASSISTANT_TEXT_CHANGED", "选区旧文字与当前原文不同，请重新读取", status_code=409)
            operations = [ChangeOperation(action="update", resource_type=ref.resource_type, id=ref.id, fields={args.field: text[:args.start] + args.replacement + text[args.end:]}, reason=args.reason)]
        else:
            required = {"stage_status_change": "status", "stage_preparation_confirmation": "preparation"}.get(name, name.removeprefix("stage_"))
            operations = args.operations
            if operations[0].action != required:
                raise DomainApiError("ASSISTANT_TOOL_OPERATION", "第一项操作与当前工具不一致")
        change = await stage_changes(novel_id, session_id, run_id, operations, sources=state["sources"], queries=state["queries"], key=key)
        state["change_ids"] = list(dict.fromkeys([*state["change_ids"], str(change["_id"])]))
        await emit("change", public_change(change))
        return {"change_id": str(change["_id"]), "revision": change["revision"], "status": change["status"], "operations": len(change["operations"]), "next": "检查影响并审核；当前仅为候选。"}
    if name == "list_generation_tasks":
        return {"tasks": [{"task": task, "label": TASKS[task].label} for task in GENERATION_KINDS]}
    if name == "describe_generation_task":
        return describe_generation(args.task, args.flow_ref)
    if name == "run_generation_task":
        for dependency in args.depends_on:
            if (await get_change(novel_id, dependency))["status"] != "applied":
                raise DomainApiError("ASSISTANT_GENERATION_DEPENDENCY", "请先保存依赖的修改组，再按新资料运行原任务", status_code=409)
        change = await run_generation(novel_id, session_id, run_id, task=args.task, inputs=args.inputs, target=args.target, target_field=args.target_field, flow_ref=args.flow_ref, key=key, emit=emit, additional_rounds=run.get("_additional_rounds", 0))
        state["change_ids"] = list(dict.fromkeys([*state["change_ids"], str(change["_id"])]))
        await emit("change", public_change(change))
        return {"change_id": str(change["_id"]), "revision": change["revision"], "status": change["status"], "candidate": change["candidate"]}
    if name == "find_affected_resources":
        change = await get_change(novel_id, args.change_id)
        explicit, possible, queried, parents = [], [], [], []
        visited = set()
        targets = [(item["resource_type"], item.get("id")) for item in change.get("operations", []) if item.get("id") and not item["id"].startswith("new_")]
        if change.get("kind") == "facts":
            target = change["fact_command"]["basis"]["target"]
            if target["kind"] == "existing":
                targets = [(change["fact_type"], target.get({"character": "character_id", "character_relation": "relation_id", "item": "item_id", "faction": "faction_id"}[change["fact_type"]]) or target["entity_id"])]
        if not targets:
            targets = [(item["resource_type"], item["id"]) for item in change.get("sources", [])][:5]
        for kind, identity in list(dict.fromkeys(targets))[:10]:
            info = await reader.read(ResourceRef(resource_type=kind, id=identity), deleted=True)
            references = await reader.catalogue({"reference_id": identity, "limit": 20})
            explicit.append({"target": {"resource_type": kind, "id": identity}, **references})
            content = public_content(kind, await get_resource(novel_id, ResourceRef(resource_type=kind, id=identity), include_deleted=True))
            for parent_kind in ("volume", "arc", "scene", "character", "faction"):
                parent_id = content.get(f"{parent_kind}_id")
                if parent_id and (parent_kind, parent_id) not in visited and (parent_kind, parent_id) != (kind, identity):
                    visited.add((parent_kind, parent_id))
                    parent_ref = ResourceRef(resource_type=parent_kind, id=parent_id)
                    parent_info = await reader.read(parent_ref, deleted=True)
                    parents.append({"target": parent_ref.model_dump(), "context": parent_info})
            terms = [info["name"], *(content.get("aliases") or content.get("alias") or [])]
            for term in terms[:3]:
                if not isinstance(term, str) or len(term.strip()) < 2 or term in queried:
                    continue
                queried.append(term)
                possible.append(await reader.search({"query": term[:200], "limit": 10}))
        return {"direct_references": explicit, "parents_and_entities": parents, "possible_text_references": possible, "unchecked": "这些是潜在影响，父级目前只读了摘要。请按需读取具体字段，再区分必须同步、建议调整与无需改动；分页未读部分仍未检查。"}
    if name == "review_changes":
        try:
            change = await review_change(novel_id, args.change_id, args.revision, settings, sources=state["sources"], queries=state["queries"])
        except (DomainApiError, VersionConflictError) as exc:
            if isinstance(exc, VersionConflictError) or exc.code in {"ASSISTANT_SOURCE_CHANGED", "ASSISTANT_VERSION_CHANGED", "CHARACTER_FACT_CONTEXT_CHANGED", "CHARACTER_RELATION_FACT_CONTEXT_CHANGED", "ITEM_FACT_CONTEXT_CHANGED"}:
                return await reconcile()
            raise
        await emit("change", public_change(change))
        return {"change_id": args.change_id, "revision": change["revision"], "review": change["review"]}
    if name == "apply_changes":
        try:
            result = await apply_change(novel_id, args.change_id, ChangeApproval(expected_revision=args.revision), author_confirmed=False, mode=settings["mode"], lease=run.get("_lease"))
        except (DomainApiError, VersionConflictError) as exc:
            if isinstance(exc, DomainApiError) and exc.code in {"ASSISTANT_LIFECYCLE_APPROVAL", "ASSISTANT_SCOPE_APPROVAL", "ASSISTANT_CONTENT_CONFLICT"}:
                change = await get_change(novel_id, args.change_id)
                if change.get("confirmation"):
                    question = confirmation_question(change, question_id=canonical_request_hash({"run": run_id, "key": key}))
                    await BaseRepository("assistant_runs").collection.update_one({"_id": run["_id"]}, {"$set": {"pending_question": question}})
                    state["stop_reason"] = "waiting_input"
                    await emit("question", question)
                    return question
            if isinstance(exc, VersionConflictError) or exc.code in {"ASSISTANT_SOURCE_CHANGED", "ASSISTANT_VERSION_CHANGED", "CHARACTER_FACT_CONTEXT_CHANGED", "CHARACTER_RELATION_FACT_CONTEXT_CHANGED", "ITEM_FACT_CONTEXT_CHANGED"}:
                return await reconcile()
            raise
        await emit("resources_changed", {"change_id": args.change_id, "resources": [{"resource_type": item["resource_type"], "id": item["id"], "version": item["version"]} for item in result["resources"]]})
        await emit("change", public_change(await get_change(novel_id, args.change_id)))
        return {"change_id": args.change_id, "saved": True, "resources": result["resources"], "next": "已复读写后资料；继续联动检查时使用当前新版本。"}
    if name == "prepare_undo":
        change = await prepare_undo(novel_id, args.change_id, run_id=run_id, key=key)
        state["change_ids"] = list(dict.fromkeys([*state["change_ids"], str(change["_id"])]))
        await emit("change", public_change(change))
        return {"change_id": str(change["_id"]), "revision": change["revision"], "status": change["status"]}
    if name == "navigate_to_resource":
        await get_resource(novel_id, ResourceRef(resource_type=args.resource_type, id=args.id))
        await emit("navigation", {**args.model_dump(), "navigate": run["request"].get("allow_navigation", False)})
        return {"target": args.model_dump(), "navigated": run["request"].get("allow_navigation", False), "note": "未授权自动跳转时仅显示定位按钮。"}
    if name == "ask_user":
        changes = [await get_change(novel_id, identity) for identity in state["change_ids"]]
        question = {**args.model_dump(), "id": canonical_request_hash({"run": run_id, "key": key}),
                    "changes": [{"id": str(item["_id"]), "revision": item["revision"], "status": item["status"]} for item in changes],
                    "target": run["request"].get("writing_target") or run["request"].get("location")}
        from backend.services.novel.character_fact_contract import CharacterFactPositionV1
        position_choices = []
        for choice in args.position_choices:
            position = CharacterFactPositionV1.model_validate(choice.position).model_dump(mode="json")
            ref = ResourceRef(resource_type=position["target_type"], id=position["target_id"])
            content = public_content(ref.resource_type, await get_resource(novel_id, ref))
            label = "书初" if position["intent"] == "book_start" else f"{content.get('title') or content.get('name')}（{'章前' if position['intent'] == 'chapter_before' else '章后'}）"
            position_choices.append({"label": label, "position": position})
        question["position_choices"] = position_choices
        if position_choices:
            question["choices"] = [item["label"] for item in position_choices]
        confirmation = next((item for item in changes if str(item["_id"]) == args.confirmation_change_id and item["status"] == "reviewed" and item.get("confirmation")), None)
        if args.confirmation_change_id and confirmation is None:
            raise DomainApiError("ASSISTANT_CONFIRMATION_CHANGED", "请先完成这份修改的检查，再询问具体改动", status_code=409)
        if confirmation:
            question = confirmation_question(confirmation, question_id=question["id"])
        await BaseRepository("assistant_runs").collection.update_one({"_id": ObjectId(run_id)}, {"$set": {"pending_question": question}})
        state["stop_reason"] = "waiting_input"
        await emit("question", question)
        return question
    if name == "finish_turn":
        state["stop_reason"] = "completed"
        await emit("message", {"content": args.message, "unchecked": args.unchecked})
        return {"finished": True}
    raise DomainApiError("ASSISTANT_TOOL_UNKNOWN", "工具未实现")
