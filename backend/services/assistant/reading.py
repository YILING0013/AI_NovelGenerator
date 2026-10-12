"""有来源的分片读取、查询复验和按需摘要。"""

from __future__ import annotations

import json
import re

from bson import ObjectId
from pydantic import Field

from backend.api.error_protocol import DomainApiError, sanitize_json_value
from backend.db.base import BaseRepository
from backend.db.write_contracts import canonical_request_hash
from .contracts import AssistantModel, ResourceRef
from .models import structured_advice
from .resources import RESOURCES, build_index_record, content_fingerprint, field_value, get_resource, public_content, search_text, sync_index


class ResourceSummary(AssistantModel):
    """摘要只说明已读取部分，不改写原资料。"""

    summary: str = Field(min_length=1, max_length=3000)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    unchecked: str = Field(default="", max_length=1000)


def query_fingerprint(result: dict) -> str:
    """固定实际分页结果与空结果，忽略索引维护时间。

    Args:
        result: 返回给模型的目录或搜索结果。
    Returns:
        可在保存前重复计算的查询依据。
    """
    return canonical_request_hash(result)


async def catalogue_query(novel_id: str, arguments: dict, *, session=None, from_source: bool = False) -> dict:
    """在基础索引或原始事务快照中执行同一目录筛选。

    Args:
        novel_id: 当前小说。
        arguments: 已校验的类型、位置、引用和分页参数。
        session: 确认时复验的事务。
        from_source: 复验时从原资料重建目录，索引过期不能影响判断。
    Returns:
        有界目录与完整命中数量。
    """
    kind, query = arguments.get("kind"), arguments.get("query", "").casefold()
    offset, limit = arguments.get("offset", 0), arguments.get("limit", 20)
    deleted = arguments.get("deleted", False)
    reference = arguments.get("reference_id")
    volume = arguments.get("volume_id")
    entries = []
    if from_source:
        for resource_kind, spec in RESOURCES.items():
            if kind and kind != resource_kind:
                continue
            filters = {"_id": ObjectId(novel_id)} if resource_kind == "novel" else {"novel_id": ObjectId(novel_id)}
            filters["is_deleted"] = deleted
            async for document in BaseRepository(spec.collection).collection.find(filters, session=session):
                if resource_kind == "foreshadowing":
                    document = await get_resource(novel_id, ResourceRef(resource_type=resource_kind, id=document[spec.identity]), include_deleted=deleted, session=session)
                entries.append(build_index_record(novel_id, resource_kind, document))
    else:
        filters = {"novel_id": ObjectId(novel_id), "is_deleted": deleted}
        if kind:
            filters["resource_type"] = kind
        entries = await BaseRepository("assistant_resource_index").collection.find(filters).to_list()
    matches = []
    for entry in entries:
        if reference and reference not in entry["references"]:
            continue
        if volume and entry["position"].get("volume_id") != volume:
            continue
        if query and query not in json.dumps([entry["name"], entry["aliases"], entry["summary"], entry["tags"]], ensure_ascii=False).casefold():
            continue
        matches.append({key: value for key, value in entry.items() if key in {"resource_type", "resource_id", "name", "summary", "summary_kind", "aliases", "tags", "position", "fields", "references", "source_version", "fingerprint", "is_deleted", "status", "planted_needs_review", "resolved_needs_review"}})
    matches.sort(key=lambda entry: (entry["resource_type"], entry["position"].get("order_index", 0), entry["resource_id"]))
    return sanitize_json_value({"items": matches[offset:offset + limit], "total": len(matches), "offset": offset, "has_more": offset + limit < len(matches)})


async def replay_queries(novel_id: str, queries: list[dict], *, session=None) -> None:
    """复验真实查询及分页，不把旧空结果当成现在仍无资料。

    Args:
        novel_id: 当前小说。
        queries: 工具执行时保存的参数与结果指纹。
        session: 可选确认事务。
    Returns:
        无；查询结果变化时明确冲突。
    """
    for query in queries:
        if query["name"] == "catalogue":
            result = await catalogue_query(novel_id, query["arguments"], session=session, from_source=True)
        else:
            result = await search_text(novel_id, **query["arguments"], session=session)
        if query_fingerprint(result) != query["fingerprint"]:
            raise DomainApiError("ASSISTANT_QUERY_CHANGED", "此前检索结果已变化，请重新检索后准备候选", status_code=409, details={"query": query["arguments"]})


class BookReader:
    """一轮内的有界读取与实际依据记录，可直接写入检查点。"""

    def __init__(self, novel_id: str, sources: list[dict], queries: list[dict]):
        """复用当前轮次已经保留的依据。

        Args:
            novel_id: 当前小说。
            sources: 持久状态里的资料依据列表。
            queries: 持久状态里的查询依据列表。
        """
        self.novel_id, self.sources, self.queries = novel_id, sources, queries

    async def read(self, ref: ResourceRef, *, fields: list[str] | None = None, start: int = 0, length: int = 6000, deleted: bool = False) -> dict:
        """读取指定业务字段和原文片段，并记录来源指纹。

        Args:
            ref: 资料位置。
            fields: 需要的字段；省略时只返回基础目录信息。
            start: 单字段字符起点。
            length: 本次总字符预算，最多 12000。
            deleted: 是否明确读取回收站内容。
        Returns:
            字段片段、后续位置和来源版本。
        """
        if not 1 <= length <= 12000 or start < 0:
            raise DomainApiError("ASSISTANT_READ_RANGE", "读取长度需为 1–12000，起点不能为负")
        document = await get_resource(self.novel_id, ref, include_deleted=deleted)
        content = public_content(ref.resource_type, document)
        source = {**ref.model_dump(), "version": content["version"], "fingerprint": content_fingerprint(content)}
        old = next((item for item in self.sources if (item["resource_type"], item["id"]) == (ref.resource_type, ref.id)), None)
        refreshed = bool(old and old["fingerprint"] != source["fingerprint"])
        if old and old["fingerprint"] != source["fingerprint"]:
            # 只替换本次重读的对象。模型仍记得其它资料，不能删掉它们的核对依据。
            old.update(source)
        if old is None:
            self.sources.append(source)
        if not fields:
            entry = build_index_record(self.novel_id, ref.resource_type, document)
            return {**source, "name": entry["name"], "summary": entry["summary"], "summary_kind": entry["summary_kind"], "fields": entry["fields"], "position": entry["position"], "notice": "这是目录摘要；需要具体内容时指定 fields。"}
        values, remaining = [], length
        for path in fields:
            value = field_value(content, path)
            is_text = isinstance(value, str)
            text = value if is_text else json.dumps(value, ensure_ascii=False)
            count = min(len(text) - min(start, len(text)), remaining)
            values.append({"field": path, "text": text[start:start + count], "format": "text" if is_text else "json", "start": start,
                           "total_characters": len(text), "has_more": start + count < len(text), "next_start": start + count})
            remaining -= count
        return {**source, "values": values, "is_deleted": content["is_deleted"], "refreshed": refreshed,
                **({"notice": "原修改仍使用原依据。保存冲突请先 reconcile_changes 核对回执及三方值，不能直接换键再写。"} if refreshed else {})}

    async def catalogue(self, arguments: dict) -> dict:
        """刷新基础目录后记录实际分页查询。

        Args:
            arguments: 已校验的目录参数。
        Returns:
            带来源的摘要页。
        """
        await sync_index(self.novel_id)
        result = await catalogue_query(self.novel_id, arguments)
        record = {"name": "catalogue", "arguments": arguments, "fingerprint": query_fingerprint(result)}
        self.queries[:] = [item for item in self.queries if not (item["name"] == "catalogue" and item["arguments"] == arguments)]
        if record not in self.queries:
            self.queries.append(record)
        return result

    async def search(self, arguments: dict) -> dict:
        """搜索真实字段并保存查询依据。

        Args:
            arguments: 已校验的普通文字和分页参数。
        Returns:
            命中片段及其原位置。
        """
        result = await search_text(self.novel_id, **arguments)
        record = {"name": "text", "arguments": arguments, "fingerprint": query_fingerprint(result)}
        self.queries[:] = [item for item in self.queries if not (item["name"] == "text" and item["arguments"] == arguments)]
        if record not in self.queries:
            self.queries.append(record)
        return result

    async def summary(self, ref: ResourceRef, settings: dict) -> dict:
        """按需生成长文摘要，缓存只对完全相同的原内容有效。

        Args:
            ref: 摘要目标。
            settings: 当前模型设置。
        Returns:
            标明摘录范围、模型和来源指纹的摘要。
        """
        await sync_index(self.novel_id)
        info = await self.read(ref)
        key = {"novel_id": ObjectId(self.novel_id), "resource_type": ref.resource_type, "resource_id": ref.id}
        collection = BaseRepository("assistant_resource_index").collection
        index = await collection.find_one(key)
        if index and index.get("ai_summary_fingerprint") == info["fingerprint"] and index.get("ai_summary_prompt_version") == 1:
            return {**info, "summary": index["ai_summary"], "summary_kind": "ai", "model": index["ai_summary_model"], "cached": True}
        document = await get_resource(self.novel_id, ref)
        content = public_content(ref.resource_type, document)
        raw = json.dumps(content, ensure_ascii=False)
        summary, model = await structured_advice(settings, "概括实际资料中的剧情、人物目标、约束与引用。只概括给出的原文；截断或遗漏的内容必须写入 unchecked。", {"resource": ref.model_dump(), "text": raw[:48000], "truncated": len(raw) > 48000}, ResourceSummary)
        if len(raw) > 48000:
            summary.unchecked = "原资料超过 48000 字符，仅概括前段。" + summary.unchecked
        value = summary.model_dump(mode="json")
        # 摘要生成期间原文可能变化；带内容指纹的条件更新防止旧摘要覆盖新条目。
        await sync_index(self.novel_id)
        saved = await collection.update_one({**key, "fingerprint": info["fingerprint"]}, {"$set": {"ai_summary": value, "ai_summary_fingerprint": info["fingerprint"], "ai_summary_model": model, "ai_summary_prompt_version": 1}})
        if saved.matched_count != 1:
            raise DomainApiError("ASSISTANT_SOURCE_CHANGED", "摘要生成期间资料已修改，请重试", status_code=409)
        return {**info, "summary": value, "summary_kind": "ai", "model": model, "cached": False}


async def read_chapter_position(novel_id: str, *, chapter_id: str | None = None, chapter_number: int | None = None, session=None) -> dict:
    """用原章节目录把作者说的章号解析成同书稳定位置，不依赖当前导航。

    Args:
        novel_id: 当前作品。
        chapter_id: 已明确的章节身份。
        chapter_number: 作者指定的全书章号，与身份同时给出时须一致。
        session: 核对保存时沿用原事务。
    Returns:
        真实章名、全书章号及父链身份；不读取正文。
    """
    from backend.services.novel.chapter_service import ChapterService
    rows = await ChapterService.list_chapters(novel_id, session=session)
    chapter = next((row for row in rows if (chapter_id is None or str(row["_id"]) == chapter_id)
                    and (chapter_number is None or row["chapter_number"] == chapter_number)), None)
    if chapter is None or (chapter_id is None and chapter_number is None):
        raise DomainApiError("ASSISTANT_FACT_POSITION_REQUIRED", "没有找到这个章节位置，请核对章号或章节名称", status_code=409)
    return {"id": str(chapter["_id"]), "resource_type": "chapter", "title": chapter["title"], "chapter_number": chapter["chapter_number"],
            **{field: str(chapter[field]) for field in ("volume_id", "arc_id", "scene_id")}}
