"""固定当前小说和位置的只读工具，以及确认时的同事务重放。"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from bson import ObjectId
from pydantic import Field
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.api.contracts import ObjectIdString
from backend.db.base import BaseRepository
from backend.db.write_contracts import canonical_request_hash
from backend.llm.models import LLMToolDefinition
from backend.services.novel.writing_context import (
    COLLECTIONS, ENTITY_FIELDS, PARENTS, RESOURCE_COLLECTIONS,
    load_writing_parents, protect_writing_sources, position_content, character_position_content,
    character_relation_position_content, read_character_relation_context,
    item_position_content, read_item_context,
    faction_position_content,
    writing_order, resolve_writing_position, chapter_visible_at_position,
    chapter_scope_content, CHAPTER_PARENT_FIELDS,
)
from backend.services.novel.character_fact_contract import CharacterFactReadV1
from backend.services.novel.character_relation_fact_contract import CharacterRelationFactReadV1
from backend.services.novel.item_fact_contract import ItemFactReadV1
from backend.services.novel.faction_fact_contract import FactionFactReadV1
from .agent_contract import AgentModel, BookReadV1, EntityKind, PreparedTargetV1


class EmptyToolArgs(AgentModel):
    """不接受模型更改小说或操作位置。"""


class ParentFieldArgs(AgentModel):
    """补读一个真实祖先的允许原文字段。"""

    resource_type: Literal["novel", "volume", "arc", "scene"]
    id: ObjectIdString
    field: str


class ScopeArgs(AgentModel):
    """旧调用仍为空参数；本章模式及补读字段进入实际读取记录。"""

    view: Literal["chapter_local_v1"] | None = Field(default=None, exclude_if=lambda value: value is None)
    parent_field: ParentFieldArgs | None = Field(default=None, exclude_if=lambda value: value is None)


class DirectoryArgs(AgentModel):
    """目录固定在当前小说内，只能指定层级和页码。"""

    resource_type: Literal["volume", "arc", "scene", "chapter"]
    ids: list[ObjectIdString] | None = Field(default=None, min_length=1, max_length=20, description="可选：按最多20个本书层级ID读取详细规划与剧情；不填则分页浏览目录。")
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=20, ge=1, le=50)


class SearchEntityArgs(AgentModel):
    """仅按普通文字检索可用实体，数据库条件不对模型开放。"""

    resource_type: EntityKind
    query: str = Field(default="", max_length=100)
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=20, ge=1, le=50)


class SearchBookArgs(AgentModel):
    """检索规划与允许阅读的前文，不接受原始查询条件。"""

    resource_type: Literal["volume", "arc", "scene", "chapter", "foreshadowing"]
    query: str = Field(min_length=1, max_length=100)
    range: Literal["current_part", "novel"] = "current_part"
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=20, ge=1, le=50)


class ReadEntityArgs(AgentModel):
    """按业务 ID 读取当前小说可用实体。"""

    resource_type: EntityKind
    ids: list[str] = Field(min_length=1, max_length=20)


class ReadVolumeStateArgs(AgentModel):
    """查询已读人物或势力在当前卷的状态和关系。"""

    resource_type: Literal["character", "faction"]
    ids: list[str] = Field(min_length=1, max_length=20)
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=20, ge=1, le=50)


class ReadPreviousArgs(AgentModel):
    """从当前位置往前分页阅读，不能越过当前写作边界。"""

    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=1, ge=1, le=5)
    excerpt_characters: int = Field(default=6000, ge=500, le=12000)


BOOK_TOOL_MODELS = {
    "get_scope": (ScopeArgs, "先核对当前目标和相邻边界。本章模式只返回局部资料；需补读上层原文时按 parent_sources 指定一个 parent_field（resource_type、id、field），不能读取父链之外的资料。"),
    "list_directory": (DirectoryArgs, "分页阅读本书指定层级的详细规划和已保存剧情，可用ids读取指定卷、篇章、场景或章节；不返回章节正文，前文须用read_previous；has_more为真时仍有下一页。"),
    "search_book": (SearchBookArgs, "按普通文字检索当前部分或本书的规划、剧情及伏笔；伏笔只读，返回作者状态、实际证据和需复核标记，不自动改状态。正文仅检索当前位置以前的章节。"),
    "search_entities": (SearchEntityArgs, "在本书可用角色、势力、地点、物品或规则中检索普通文字，空文字用于浏览；采用前须 read_entity。"),
    "read_entity": (ReadEntityArgs, "读取已知业务 ID 的完整可用实体资料；不存在的 ID 不会返回。"),
    "read_volume_state": (ReadVolumeStateArgs, "先调用 read_entity，使用其实际返回的角色或势力 ID 读取当前卷状态及有效关系；分别提供分页信息。"),
    "read_previous": (ReadPreviousArgs, "倒序读取当前位置以前已写正文的末尾片段，绝不返回未来或当前章正文。"),
}


def normalize_agent_scope(scope: dict[str, Any], *, task: str | None = None) -> dict[str, Any]:
    """把路径给定的卷或下级位置规范为唯一作用范围。

    Args:
        scope: 服务端已经固定的路径范围，不使用模型参数。
        task: 服务端任务，用于区分追加与整段重规划。
    Returns:
        小说、目标类别与目标 ID。
    """
    kind = scope.get("target_type")
    identity = scope.get("target_id")
    if not kind:
        kind = next((value for value in ("chapter", "scene", "arc", "volume") if scope.get(f"{value}_id")), None)
        identity = scope.get(f"{kind}_id")
    intent = scope.get("reading_intent") or ("chapter_before" if kind == "chapter" else "append")
    if task == "write_chapter_by_ai":
        intent = "chapter_before"
    elif task in {"plan_arcs_by_ai", "plan_scenes_by_ai", "plan_chapters_by_ai"}:
        intent = "append"
    if task in {"generate_volume_plot_by_ai", "generate_arc_plot_by_ai", "create_characters_for_volume_by_ai", "create_factions_for_volume_by_ai", "create_locations_for_volume_by_ai"}:
        intent = "replan"
    return PreparedTargetV1.model_validate({"novel_id": scope.get("novel_id"), "target_type": kind, "target_id": identity,
                                            "reading_version": scope.get("reading_version") or 1, "reading_intent": intent}).model_dump(mode="json")


class BookTools:
    """一次节点执行的只读能力；保留实际读到的文档供确认复查。"""

    def __init__(self, scope: dict[str, Any], reads: list[dict[str, Any]], *, session: AsyncClientSession | None = None) -> None:
        """固定小说和目标，生成时记录读取，确认时复用同一会话。

        Args:
            scope: 服务端路径范围。
            reads: 接收规范化工具读取的列表。
            session: 可选的确认事务会话。
        """
        self.scope = normalize_agent_scope(scope)
        self.chapter_local = scope.get("chapter_context_version") == 1
        self.reads = reads
        self.session = session
        self.guards: dict[tuple[str, str], dict[str, Any]] = {}
        self.foreshadowing_evidence_guards: dict[tuple[str, str], dict[str, Any]] = {}
        self.sources: dict[tuple[str, str], dict[str, Any]] = {}
        self.selected_entities: dict[tuple[str, str], dict[str, Any]] = {}
        self.volume_states: dict[str, dict[str, Any]] = {}
        self.relations: dict[str, dict[str, Any]] = {}
        self.previous_text: dict[str, dict[str, Any]] = {}
        self.parent_fields: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.chain: list[tuple[str, dict[str, Any]]] = []

    def definitions(self, names: list[str]) -> list[LLMToolDefinition]:
        """返回启用工具的说明和严格输入边界。

        Args:
            names: 节点启用的工具名。
        Returns:
            原生 Function Calling 工具定义。
        """
        result = [LLMToolDefinition(name=name, description=BOOK_TOOL_MODELS[name][1],
                                   parameters=BOOK_TOOL_MODELS[name][0].model_json_schema())
                  for name in names if name in BOOK_TOOL_MODELS]
        if not self.chapter_local:
            for definition in result:
                if definition.name == "get_scope":
                    definition.parameters = EmptyToolArgs.model_json_schema()
                    definition.description = "读取当前小说主线、当前父链、相邻部分和已有下级；整理必须首先使用。"
        return result

    def _remember(self, kind: str, document: dict[str, Any], *, detail: bool = False, facts: dict[str, Any] | None = None) -> dict[str, Any]:
        """提取内容并记录实际文档；统计和锁字段不参与内容散列。"""
        if kind == "foreshadowing":
            from backend.services.novel.foreshadowing_contract import serialize_foreshadowing
            value = serialize_foreshadowing(document)
            value.update(resource_type=kind, id=document["foreshadowing_id"], content_semantics="design_plan", evidence_semantics="visible_chapter_evidence")
            collection = "foreshadowings"
        elif kind == "character":
            if facts is None:
                raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "人物资料缺少明确位置的读取结果，请重新读取", status_code=409)
            value = character_position_content(document, facts)
            collection = RESOURCE_COLLECTIONS[kind]
        elif kind == "faction":
            if facts is None:
                raise DomainApiError("FACTION_FACT_CONTEXT_CHANGED", "势力资料缺少明确位置的读取结果，请重新读取", status_code=409)
            value = faction_position_content(document, facts)
            collection = "factions"
        elif kind == "character_relation":
            if facts is None:
                raise DomainApiError("CHARACTER_RELATION_FACT_CONTEXT_CHANGED", "关系资料缺少明确位置的读取结果，请重新读取", status_code=409)
            value = character_relation_position_content(document, facts)
            collection = "character_relations"
        elif kind == "item":
            if facts is None:
                raise DomainApiError("ITEM_FACT_CONTEXT_CHANGED", "物品资料缺少明确位置的读取结果，请重新读取", status_code=409)
            value = item_position_content(document, facts)
            collection = "items"
        elif kind == "faction_relation":
            value = position_content(document, kind)
            collection = f"{kind}s"
        else:
            value = position_content(document, kind)
            collection = RESOURCE_COLLECTIONS[kind]
        self.guards[(collection, str(document["_id"]))] = document
        self.sources[(kind, value["id"])] = {"resource_type": kind, "id": value["id"], "version": document["version"]}
        if detail:
            self.selected_entities[(kind, value["id"])] = value
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行一项受控读取并记录返回内容，包括空查询。

        Args:
            name: 固定工具名。
            arguments: 按该工具 Schema 验证的模型参数。
        Returns:
            可提供给模型的资料及明确的分页/截断信息。
        """
        if name not in BOOK_TOOL_MODELS:
            raise DomainApiError("AGENT_TOOL_UNKNOWN", "资料整理请求了未开放的工具", status_code=422)
        if name == "get_scope" and self.chapter_local:
            arguments = {**arguments, "view": "chapter_local_v1"}
        model = EmptyToolArgs if name == "get_scope" and not self.chapter_local else BOOK_TOOL_MODELS[name][0]
        args = model.model_validate(arguments).model_dump(mode="json")
        if not self.chain or name == "get_scope":
            self.chain = await load_writing_parents(*(self.scope[key] for key in ("novel_id", "target_type", "target_id")), session=self.session)
        novel_id = ObjectId(self.scope["novel_id"])
        volume_id = next(document["_id"] for kind, document in self.chain if kind == "volume")
        target_kind, target = self.chain[-1]
        directories = {}
        position = None
        fact_reads = []
        if name in {"get_scope", "read_previous", "search_book"}:
            for kind in ("volume", "arc", "scene", "chapter"):
                documents = await BaseRepository(COLLECTIONS[kind]).collection.find({"novel_id": novel_id, "is_deleted": False}, {"content": 0}, session=self.session).limit(10001).to_list(length=10001)
                if len(documents) > 10000:
                    raise DomainApiError("AGENT_DIRECTORY_TOO_LARGE", "本书目录超过读取上限", status_code=422)
                directories[kind] = {document["_id"]: document for document in documents}
            position = resolve_writing_position(self.scope, directories)
        if name == "get_scope":
            plans = [self._remember(kind, document) for kind, document in self.chain]
            parent_kind = PARENTS[target_kind]
            siblings = await BaseRepository(COLLECTIONS[target_kind]).collection.find({"novel_id": novel_id, f"{parent_kind}_id": target[f"{parent_kind}_id"], "is_deleted": False}, {"content": 0}, session=self.session).sort([("order_index", 1), ("_id", 1)]).limit(10001).to_list(length=10001)
            if len(siblings) > 10000:
                raise DomainApiError("AGENT_DIRECTORY_TOO_LARGE", "当前同级目录超过读取上限", status_code=422)
            sibling_index = next(index for index, document in enumerate(siblings) if document["_id"] == target["_id"])
            neighbors = {"previous": self._remember(target_kind, siblings[sibling_index - 1]) if sibling_index else None,
                         "next": self._remember(target_kind, siblings[sibling_index + 1]) if sibling_index + 1 < len(siblings) else None}
            child_kind = {"volume": "arc", "arc": "scene", "scene": "chapter"}.get(target_kind)
            children = []
            if child_kind:
                documents = await BaseRepository(COLLECTIONS[child_kind]).collection.find({"novel_id": novel_id, f"{target_kind}_id": target["_id"], "is_deleted": False}, {"content": 0}, session=self.session).sort([("order_index", 1), ("_id", 1)]).limit(10001).to_list(length=10001)
                if len(documents) > 10000:
                    raise DomainApiError("AGENT_DIRECTORY_TOO_LARGE", "已有下级超过读取上限", status_code=422)
                children = [self._remember(child_kind, document) for document in documents]
            output = {"target": self.scope, "plan": plans, "neighbors": neighbors, "existing_children": children}
            if args.get("view") == "chapter_local_v1":
                if target_kind != "chapter" or self.scope["reading_intent"] != "chapter_before":
                    raise ValueError("本章资料只能用于章前写作")
                output.update(chapter_scope_content(plans, neighbors))
                if selection := args.get("parent_field"):
                    kind, identity, field = selection["resource_type"], selection["id"], selection["field"]
                    document = next((doc for part, doc in self.chain[:-1] if part == kind and str(doc["_id"]) == identity), None)
                    if document is None or field not in CHAPTER_PARENT_FIELDS[kind]:
                        raise ValueError("只能补读本书真实父链中允许的原文字段")
                    value = self._remember(kind, document)
                    for key in field.split("."):
                        value = value.get(key) if isinstance(value, dict) else None
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError("该祖先字段没有可读取的原文，请核对缺项")
                    original = {**selection, "version": document["version"], "text": value}
                    self.parent_fields[(kind, identity, field)] = original
                    output["parent_field"] = original
            elif args.get("parent_field"):
                raise ValueError("祖先字段补读需要本章资料模式")
        elif name == "list_directory":
            kind = args["resource_type"]
            query = {"novel_id": novel_id, "is_deleted": False}
            if args["ids"] is not None:
                query["_id"] = {"$in": [ObjectId(identity) for identity in args["ids"]]}
            documents = await BaseRepository(COLLECTIONS[kind]).collection.find(query, {"content": 0}, session=self.session).sort([("volume_id", 1), ("arc_id", 1), ("scene_id", 1), ("order_index", 1), ("_id", 1)]).skip(args["offset"]).limit(args["limit"] + 1).to_list(length=args["limit"] + 1)
            output = {"items": [self._remember(kind, document) for document in documents[:args["limit"]]], "offset": args["offset"], "limit": args["limit"], "has_more": len(documents) > args["limit"]}
        elif name in {"search_entities", "read_entity"}:
            kind = args["resource_type"]
            collection, _, id_field, status_field = next(value for value in ENTITY_FIELDS.values() if value[1] == kind)
            query: dict[str, Any] = {"novel_id": novel_id, "is_deleted": False}
            if status_field:
                query[status_field] = "active"
            if kind == "faction":
                query["$or"] = [{"level_type": "core", "volume_id": None}, {"level_type": {"$in": ["volume", "local"]}, "volume_id": volume_id}]
            if kind == "location":
                query["location_order_pending_token"] = None
            if kind == "item":
                query["item_write_pending_token"] = None
            if name == "read_entity":
                query[id_field] = {"$in": args["ids"]}
                documents = await BaseRepository(collection).collection.find(query, session=self.session).sort(id_field, 1).to_list(length=20)
            else:
                documents = await BaseRepository(collection).collection.find(query, session=self.session).sort([(id_field, 1), ("_id", 1)]).limit(10001).to_list(length=10001)
                if len(documents) > 10000:
                    raise DomainApiError("AGENT_DIRECTORY_TOO_LARGE", "该类实体超过检索上限", status_code=422)
            facts = {}
            if kind == "character":
                from backend.services.novel.character_fact_service import read_character_facts
                # search 的原查询仍由 BookRead 保存；这里的 IDs 冻结本次完整候选范围。
                selected_ids = args["ids"] if name == "read_entity" else [row[id_field] for row in documents]
                fact_result = await read_character_facts(str(novel_id), selected_ids, self.scope, session=self.session)
                fact_reads.extend(fact_result["reads"])
                position = fact_result["position"]
                facts = {row["character_id"]: row for row in fact_result["characters"]}
                if any(row[id_field] not in facts for row in documents):
                    raise DomainApiError("CHARACTER_FACT_CONTEXT_CHANGED", "人物在读取期间已变化，请重新读取", status_code=409)
            elif kind == "faction":
                from backend.services.novel.faction_fact_service import read_faction_facts
                selected_ids = args["ids"] if name == "read_entity" else [row[id_field] for row in documents]
                fact_result = await read_faction_facts(str(novel_id), selected_ids, self.scope, session=self.session)
                fact_reads.extend(fact_result["reads"])
                position = fact_result["position"]
                facts = {row["faction_id"]: row for row in fact_result["factions"]}
                if any(row[id_field] not in facts for row in documents):
                    raise DomainApiError("FACTION_FACT_CONTEXT_CHANGED", "势力在读取期间已变化，请重新读取", status_code=409)
            elif kind == "item":
                selected_ids = args["ids"] if name == "read_entity" else [row[id_field] for row in documents]
                facts, item_reads, position = await read_item_context(str(novel_id), selected_ids, self.scope, session=self.session)
                fact_reads.extend(item_reads)
                if any(row[id_field] not in facts for row in documents):
                    raise DomainApiError("ITEM_FACT_CONTEXT_CHANGED", "物品在读取期间已变化，请重新读取", status_code=409)
            if name == "read_entity":
                output = {"items": [self._remember(kind, document, detail=True, facts=facts.get(document[id_field])) for document in documents]}
            else:
                # 搜索实际可读字段，也覆盖人物动机、嵌套设定和规则数组；内部统计不参与命中。
                matches = [document for document in documents
                           if args["query"].casefold() in json.dumps(
                                character_position_content(document, facts[document[id_field]]) if kind == "character" else
                                faction_position_content(document, facts[document[id_field]]) if kind == "faction" else
                                item_position_content(document, facts[document[id_field]]) if kind == "item" else position_content(document, kind),
                               ensure_ascii=False).casefold()]
                items = [self._remember(kind, document, facts=facts.get(document[id_field]))
                         for document in matches[args["offset"]:args["offset"] + args["limit"]]]
                output = {"items": items, "offset": args["offset"], "limit": args["limit"],
                          "has_more": len(matches) > args["offset"] + args["limit"], "total_matches": len(matches)}
        elif name == "read_volume_state":
            kind = args["resource_type"]
            missing_ids = [identity for identity in args["ids"] if (kind, identity) not in self.selected_entities]
            if missing_ids:
                raise DomainApiError(
                    "AGENT_REFERENCE_UNREAD", "请先读取这些实体的详情，再读取卷状态", status_code=422,
                    details={"resource_type": kind, "missing_ids": missing_ids, "next_tool": "read_entity"},
                )
            state_kind = f"{kind}_volume_state"
            query = {"novel_id": novel_id, "volume_id": volume_id, f"{kind}_id": {"$in": args["ids"]}, "is_deleted": False}
            documents = await BaseRepository(RESOURCE_COLLECTIONS[state_kind]).collection.find(query, session=self.session).sort([(f"{kind}_id", 1), ("_id", 1)]).skip(args["offset"]).limit(args["limit"] + 1).to_list(length=args["limit"] + 1)
            states = [self._remember(state_kind, document) for document in documents[:args["limit"]]]
            for value in states:
                self.volume_states[value["id"]] = value
            relation_kind = f"{kind}_relation"
            query = {"novel_id": novel_id, "is_deleted": False, "is_active": True, "$or": [{f"source_{kind}_id": {"$in": args["ids"]}}, {f"target_{kind}_id": {"$in": args["ids"]}}]}
            relation_facts = {}
            if kind == "character":
                relation_docs = await BaseRepository("character_relations").collection.find(query, session=self.session).sort([("relation_id", 1), ("_id", 1)]).limit(10001).to_list(length=10001)
                if len(relation_docs) > 10000:
                    raise DomainApiError("AGENT_DIRECTORY_TOO_LARGE", "相关关系超过读取上限，请缩小人物范围", status_code=422)
                # 原人物范围与分页留在 BookRead；事实读取覆盖整个关系集合，空查询也不能丢失。
                relation_facts, relation_reads, position = await read_character_relation_context(
                    str(novel_id), [row["relation_id"] for row in relation_docs], self.scope, session=self.session)
                fact_reads.extend(relation_reads)
                page = relation_docs[args["offset"]:args["offset"] + args["limit"]]
                relations_has_more = len(relation_docs) > args["offset"] + args["limit"]
            else:
                relation_docs = await BaseRepository("faction_relations").collection.find(query, session=self.session).sort([("relation_id", 1), ("_id", 1)]).skip(args["offset"]).limit(args["limit"] + 1).to_list(length=args["limit"] + 1)
                page = relation_docs[:args["limit"]]
                relations_has_more = len(relation_docs) > args["limit"]
            relations = [self._remember(relation_kind, document, facts=relation_facts.get(document["relation_id"])) for document in page]
            for value in relations:
                self.relations[value["id"]] = value
            output = {"states": states, "relations": relations, "offset": args["offset"], "limit": args["limit"], "states_has_more": len(documents) > args["limit"], "relations_has_more": relations_has_more}
            if kind == "character":
                from backend.services.novel.character_fact_service import read_character_facts
                fact_result = await read_character_facts(str(novel_id), args["ids"], self.scope, session=self.session)
                fact_reads.extend(fact_result["reads"])
                position = fact_result["position"]
                # 卷状态只保留参与和计划；心理等事实统一按人物提供一次。
                output["character_facts"] = [{key: value for key, value in row.items() if key not in {"entity_id", "version"}}
                                             for row in fact_result["characters"]]
            else:
                from backend.services.novel.faction_fact_service import read_faction_facts
                fact_result = await read_faction_facts(str(novel_id), args["ids"], self.scope, session=self.session)
                fact_reads.extend(fact_result["reads"])
                position = fact_result["position"]
                output["faction_facts"] = [{key: value for key, value in row.items() if key not in {"entity_id", "version"}}
                                           for row in fact_result["factions"]]
        elif name == "search_book" and args["resource_type"] == "foreshadowing":
            from backend.services.novel.foreshadowing_service import ForeshadowingService
            rows = await ForeshadowingService.list(str(novel_id), session=self.session)
            # 先去掉当前位置以后的实际证据，再匹配、计数和分页；作者计划仍可作为计划阅读。
            for row in rows:
                for field, review_field in (("planted_evidence", "planted_needs_review"), ("resolved_evidence", "resolved_needs_review")):
                    evidence = row[field]
                    chapter = directories["chapter"].get(ObjectId(evidence["chapter_id"])) if evidence else None
                    if chapter is None or not chapter_visible_at_position(chapter, directories, position):
                        row[field] = None
                        row[review_field] = False
                row["status"] = "resolved" if row["resolved_evidence"] else "planted" if row["planted_evidence"] else "planned"
            if args["range"] == "current_part":
                positions = {(kind, str(row["_id"])) for kind, row in self.chain if kind in {"volume", "arc", "scene"}}
                rows = [row for row in rows if any(row[field] is not None and (row[field]["kind"], row[field]["id"]) in positions for field in ("planting_position", "resolution_position"))
                        or target_kind == "chapter" and any(row[field] is not None and row[field]["chapter_id"] == str(target["_id"]) for field in ("planted_evidence", "resolved_evidence"))]
            rows = [row for row in rows if args["query"].casefold() in json.dumps({key: row[key] for key in ("title", "content", "target_effect", "planting_position", "resolution_position", "status", "planted_evidence", "resolved_evidence")}, ensure_ascii=False).casefold()]
            selected = rows[args["offset"]:args["offset"] + args["limit"]]
            # 复核标记也来自当前章正文；确认时保护这些章，防止标记检查后正文又被改掉。
            for row in selected:
                for field in ("planted_evidence", "resolved_evidence"):
                    if row[field] is not None:
                        chapter = await BaseRepository("chapters").collection.find_one({"_id": ObjectId(row[field]["chapter_id"]), "novel_id": novel_id}, session=self.session)
                        if chapter is not None:
                            self.foreshadowing_evidence_guards[("chapters", str(chapter["_id"]))] = chapter
            output = {"items": [self._remember("foreshadowing", row) for row in selected], "offset": args["offset"], "limit": args["limit"], "has_more": len(rows) > args["offset"] + args["limit"], "total_matches": len(rows)}
        else:
            if name == "search_book":
                kind = args["resource_type"]
                candidates = [(key, document) for document in directories[kind].values()
                              if (key := writing_order(kind, document, directories)) is not None
                              and (args["range"] == "novel" or document["_id"] == target["_id"]
                                   or document.get(f"{target_kind}_id") == target["_id"])]
                candidates.sort(key=lambda pair: (pair[0], str(pair[1]["_id"])))
                body_matches = {}
                if kind == "chapter":
                    prior_ids = [document["_id"] for _, document in candidates if chapter_visible_at_position(document, directories, position)]
                    documents = await BaseRepository("chapters").collection.find({
                        "novel_id": novel_id, "_id": {"$in": prior_ids}, "is_deleted": False,
                        "content": {"$regex": re.escape(args["query"]), "$options": "i"},
                    }, session=self.session).to_list(length=10000)
                    body_matches = {document["_id"]: document for document in documents
                                    if chapter_visible_at_position(document, directories, position)}
                matches = []
                for _, document in candidates:
                    value = position_content(document, kind)
                    fields = ["planning"] if args["query"].casefold() in json.dumps(value, ensure_ascii=False).casefold() else []
                    if document["_id"] in body_matches:
                        fields.append("content")
                    if fields:
                        matches.append((document, fields))
                items = []
                for document, fields in matches[args["offset"]:args["offset"] + args["limit"]]:
                    document = body_matches.get(document["_id"], document)
                    value = self._remember(kind, document)
                    value["matched_fields"] = fields
                    if "content" in fields:
                        match = re.search(re.escape(args["query"]), document["content"], re.IGNORECASE)
                        start = max(0, match.start() - 400) if match is not None else 0
                        value.update(excerpt=document["content"][start:start + 2000], excerpt_start=start,
                                     truncated=start > 0 or len(document["content"]) > 2000,
                                     content_fingerprint=canonical_request_hash(document["content"]), content_semantics="design_plan_with_prior_text")
                        key = f'{value["id"]}:{start}:{start + len(value["excerpt"])}' if self.chapter_local else value["id"]
                        self.previous_text[key] = value
                    items.append(value)
                output = {"items": items, "offset": args["offset"], "limit": args["limit"],
                          "has_more": len(matches) > args["offset"] + args["limit"], "total_matches": len(matches),
                          "before_order": position["order"], "query": args["query"], "range": args["range"]}
            else:
                prior = sorted(((key, document) for document in directories["chapter"].values() if (key := writing_order("chapter", document, directories)) is not None and chapter_visible_at_position(document, directories, position)), key=lambda pair: (pair[0], str(pair[1]["_id"])), reverse=True)
                identities = [document["_id"] for _, document in prior]
                documents = await BaseRepository("chapters").collection.find({"novel_id": novel_id, "_id": {"$in": identities}, "is_deleted": False, "content": {"$regex": r"\S"}}, session=self.session).to_list(length=10000)
                by_id = {document["_id"]: document for document in documents
                         if chapter_visible_at_position(document, directories, position)}
                written = [by_id[identity] for identity in identities if identity in by_id]
                items = []
                for document in written[args["offset"]:args["offset"] + args["limit"]]:
                    value = self._remember("chapter", document)
                    value.update(excerpt=document["content"][-args["excerpt_characters"]:], truncated=len(document["content"]) > args["excerpt_characters"], content_fingerprint=canonical_request_hash(document["content"]), content_semantics="design_plan_with_prior_text")
                    if self.chapter_local:
                        value["excerpt_start"] = len(document["content"]) - len(value["excerpt"])
                    key = f'{value["id"]}:{value["excerpt_start"]}:{len(document["content"])}' if self.chapter_local else value["id"]
                    self.previous_text[key] = value
                    items.append(value)
                # 先后次序和已写章节集合也属于读取依据；新的前章会使旧候选过期。
                output = {"items": items, "offset": args["offset"], "limit": args["limit"], "has_more": len(written) > args["offset"] + args["limit"], "before_order": position["order"], "written_order": [str(document["_id"]) for document in written]}
        if position is not None:
            # 目录和正文分开读取；在把任何片段交给模型前，拒绝读取期间的插入或重排。
            order_fields = ("novel_id", "volume_id", "arc_id", "scene_id", "order_index")
            for kind, original in directories.items():
                current = await BaseRepository(COLLECTIONS[kind]).collection.find({"novel_id": novel_id, "is_deleted": False}, {"content": 0}, session=self.session).limit(10001).to_list(length=10001)
                before = {identity: tuple(document.get(field) for field in order_fields) for identity, document in original.items()}
                after = {document["_id"]: tuple(document.get(field) for field in order_fields) for document in current}
                if before != after:
                    raise DomainApiError("AGENT_SCOPE_CHANGED", "读取期间目录位置已变化，请重新整理", status_code=409)
            output["position"] = position
        if len(json.dumps(output, ensure_ascii=False)) > 200000:
            raise DomainApiError("AGENT_TOOL_RESULT_TOO_LARGE", "资料结果过长，请缩小页数或读取范围", status_code=422)
        self.reads.extend(fact_reads)
        self.reads.append(BookReadV1(tool=name, arguments=args, scope=self.scope, fingerprint=canonical_request_hash(output)).model_dump(mode="json"))
        return output


def select_chapter_sources(report: Any, material: dict[str, Any]) -> dict[str, Any]:
    """从实际读过的同版本资料取本章采用内容，不接受模型自由拼接原文。

    Args:
        report: 已校验格式的整理报告。
        material: 当前工具读取或完整重放得到的原资料。
    Returns:
        已核对的祖先原文、前文和关系；缺项交回原整理恢复流程。
    """
    if report.chapter_sources is None:
        raise ValueError("请明确填写本章采用的原文、前文和关系，未采用的列表填空")
    chosen = report.chapter_sources
    excerpts = []
    for ref in chosen.parent_excerpts:
        source = next((value for value in material.get("parent_fields", [])
                       if (value["resource_type"], value["id"], value["field"], value["version"]) ==
                       (ref.resource_type, ref.id, ref.field, ref.version)), None)
        if (source is None or not ref.quote.strip() or ref.end <= ref.start or ref.end > len(source["text"])
                or source["text"][ref.start:ref.end] != ref.quote):
            raise ValueError("采用原文必须是实际补读的同版本祖先字段中有效的一段连续原文")
        value = ref.model_dump(mode="json")
        if value not in excerpts:
            excerpts.append(value)
    previous = material.get("previous_text", [])
    relations = {value["id"]: value for value in material.get("relations", [])}
    if set(chosen.previous_chapter_ids) - {value["id"] for value in previous} or set(chosen.relation_ids) - relations.keys():
        raise ValueError("采用的前文或关系尚未实际读到，请先补读")
    for identity in chosen.relation_ids:
        relation = relations[identity]
        kind = {"character_relation": "character", "faction_relation": "faction"}.get(relation.get("resource_type"))
        if kind is None:
            raise ValueError("采用的关系类型不受支持，请核对实际读取来源")
        selected = set(getattr(report.selected_entities, f"{kind}_ids"))
        if not selected.intersection({relation.get(f"source_{kind}_id"), relation.get(f"target_{kind}_id")}):
            raise ValueError("采用的关系至少一端应属于本章采用的对应人物或势力")
    return {"parent_excerpts": excerpts,
            "previous_text": [value for identity in dict.fromkeys(chosen.previous_chapter_ids) for value in previous if value["id"] == identity],
            "relations": [relations[identity] for identity in dict.fromkeys(chosen.relation_ids)]}


def assemble_chapter_context(context: dict[str, Any], report: Any, material: dict[str, Any]) -> dict[str, Any]:
    """为新版正文和预览组装一份资料；阅读意见与工具历史只留在报告中。

    Args:
        context: 正式资料节点的局部上下文。
        report: 本次整理结果。
        material: 实际工具读取资料；预览只可使用明确标为示例的资料。
    Returns:
        正文唯一资料输入，必要原文保留，不拼入整份整理报告。
    """
    adopted = select_chapter_sources(report, material)
    result = {key: value for key, value in context.items()
              if key not in {"candidate_entities", "required_entities", "parent_sources", "search_results", "previous_written"}}
    result["parent_excerpts"] = adopted["parent_excerpts"]
    result["relations"] = adopted["relations"]
    previous_sources = list(adopted["previous_text"])
    if nearest := context.get("previous_written"):
        previous_sources.insert(0, {"id": nearest["chapter_id"], **{key: nearest[key]
            for key in ("title", "excerpt", "excerpt_start", "truncated", "content_fingerprint") if key in nearest}})
    previous = []
    for value in previous_sources:
        # 同章、同正文指纹且区间完全包含才去重；原始读取记录不变。
        covered = False
        start = value.get("excerpt_start")
        if start is not None and value.get("content_fingerprint"):
            end = start + len(value["excerpt"])
            for existing in list(previous):
                if (existing["id"] != value["id"] or existing.get("content_fingerprint") != value["content_fingerprint"]
                        or existing.get("excerpt_start") is None):
                    continue
                old_start = existing["excerpt_start"]
                old_end = old_start + len(existing["excerpt"])
                if old_start <= start and end <= old_end:
                    covered = True
                    break
                if start <= old_start and old_end <= end:
                    previous.remove(existing)
        if covered:
            continue
        previous.append({key: value[key] for key in ("id", "title", "excerpt", "excerpt_start", "truncated", "content_fingerprint", "content_semantics") if key in value})
    result["previous_text"] = previous
    return result


async def replay_book_reads(scope: dict[str, Any], reads: list[dict[str, Any]], *, session: AsyncClientSession | None = None, protect: bool = False) -> dict[str, Any]:
    """重放生成期间全部资料查询；确认可在同一事务内保护读到的文档。

    Args:
        scope: 原任务的服务端小说与位置。
        reads: 生成时记录的工具、参数和内容指纹。
        session: 确认写入使用的同一个事务会话。
        protect: 是否对重读资料执行现有事务写保护，必须提供 session。
    Returns:
        当前来源、写保护文档、规范读取记录和实际读取过的实体详情。
    """
    if protect and session is None:
        raise ValueError("确认资料保护必须使用同一个 MongoDB 事务")
    current: list[dict[str, Any]] = []
    tools = BookTools(scope, current, session=session)
    pending_facts = []
    for raw in reads:
        if raw.get("kind") == "character_facts":
            pending_facts.append(CharacterFactReadV1.model_validate(raw).model_dump(mode="json"))
            continue
        if raw.get("kind") == "character_relation_facts":
            pending_facts.append(CharacterRelationFactReadV1.model_validate(raw).model_dump(mode="json"))
            continue
        if raw.get("kind") == "item_facts":
            pending_facts.append(ItemFactReadV1.model_validate(raw).model_dump(mode="json"))
            continue
        if raw.get("kind") == "faction_facts":
            pending_facts.append(FactionFactReadV1.model_validate(raw).model_dump(mode="json"))
            continue
        if "kind" in raw:
            raise DomainApiError("CANDIDATE_READING_CONTRACT_CHANGED", "事实读取种类不受支持，请保留草稿并重新整理", status_code=409)
        if raw.get("scope", {}).get("reading_version") != 1 or not raw.get("scope", {}).get("reading_intent"):
            raise DomainApiError("AGENT_READS_CHANGED", "旧资料整理未保存读取位置，请保留草稿并重新整理", status_code=409)
        original = BookReadV1.model_validate(raw)
        if original.scope.model_dump(mode="json") != tools.scope:
            raise DomainApiError("AGENT_SCOPE_CHANGED", "资料整理的小说或位置不一致", status_code=409)
        start = len(current)
        await tools.execute(original.tool, original.arguments)
        # 比较本次工具实际产生的完整读取段；不能把新事实依据写回旧累计历史。
        if current[start:] != [*pending_facts, original.model_dump(mode="json")]:
            raise DomainApiError("AGENT_READS_CHANGED", "资料整理依据已变化，请重新整理并生成", status_code=409)
        pending_facts = []
    if pending_facts:
        raise DomainApiError("AGENT_READS_CHANGED", "事实读取缺少原工具查询，请保留草稿并重新整理", status_code=409)
    data = {"source_refs": list(tools.sources.values()), "guards": tools.guards,
            "reads": current, "selected_entities": list(tools.selected_entities.values()),
            "volume_states": list(tools.volume_states.values()), "relations": list(tools.relations.values()),
            "previous_text": list(tools.previous_text.values())}
    if any(read.get("arguments", {}).get("view") == "chapter_local_v1" for read in current):
        data["parent_fields"] = list(tools.parent_fields.values())
    if protect:
        from backend.services.novel.foreshadowing_service import protect_foreshadowing_sources
        await protect_foreshadowing_sources(tools.foreshadowing_evidence_guards, session=session)
        # 关系表没有主档的 dependency_guard_revision；直接触碰关系文档以争用其修改。
        ordinary = {key: value for key, value in tools.guards.items() if key[0] not in {"character_relations", "faction_relations", "foreshadowings"}}
        await protect_writing_sources({"guards": ordinary, "fact_reads": [
            read for read in reads if read.get("kind") in {"character_facts", "character_relation_facts", "item_facts", "faction_facts"}
        ]}, session=session)
        for (collection_name, _), document in tools.guards.items():
            if collection_name not in {"character_relations", "faction_relations", "foreshadowings"}:
                continue
            result = await BaseRepository(collection_name).collection.update_one(
                {"_id": document["_id"], "version": document["version"], "is_deleted": False},
                {"$inc": {"writing_guard_revision": 1}}, session=session,
            )
            if result.matched_count != 1:
                raise DomainApiError("AGENT_READS_CHANGED", "资料在确认期间发生变化，请重新整理", status_code=409)
    return data
