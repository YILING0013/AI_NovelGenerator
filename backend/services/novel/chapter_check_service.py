"""只读选定章修订及明确选择的资料，为作者生成待审阅的章后检查结果。"""

import hashlib
import json

from bson import ObjectId

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.transaction import run_mongo_write_unit
from backend.services.novel.chapter_check_contract import (
    ChapterCheckInputV1, ChapterCheckResultV1, ChapterCheckSourceV1,
    ChapterItemOwnerCheckInputV1, ChapterItemOwnerCheckResultV1,
    ChapterCharacterRelationStateCheckInputV1, ChapterCharacterRelationStateCheckResultV1,
    ChapterWorldRulesCheckInputV1, ChapterWorldRulesCheckResultV1,
)
from backend.services.llm.candidate_contract import CandidateSourceRefV1
from backend.services.novel.writing_context import load_writing_parents
from backend.services.novel.character_fact_service import read_character_facts
from backend.services.novel.character_relation_fact_service import read_character_relation_facts


CHAPTER_CHECK_RULES_MAX_CHARACTERS = 60000


async def _load_chapter_check_source(novel_id: str, source: ChapterCheckSourceV1, *, session) -> tuple[dict, str]:
    """章后检查共用同一个原修订和当前正文核对。

    Args:
        novel_id: 当前小说。
        source: 作者固定的章修订。
        session: 当前只读事务。
    Returns:
        章节文档和未经处理的原文。
    """
    chain = await load_writing_parents(novel_id, "chapter", source.chapter_id, session=session)
    novel, chapter = chain[0][1], chain[-1][1]
    if "hard_delete_claim" in novel:
        raise DomainApiError("CHAPTER_RECORD_PARENT_BUSY", "Tiểu thuyết đang bị xóa vĩnh viễn, không thể dùng nguồn chương", status_code=409)
    revision = await BaseRepository("chapter_revisions").collection.find_one({
        "_id": ObjectId(source.revision_id), "chapter_id": chapter["_id"], "version": source.version,
        **{name: chapter[name] for name in ("novel_id", "volume_id", "arc_id", "scene_id")},
    }, session=session)
    if revision is None:
        raise DomainApiError("CHAPTER_RECORD_REVISION_NOT_FOUND", "Bản chỉnh sửa đã chọn không tồn tại hoặc không thuộc chương hiện tại, hãy chọn lại phiên bản lịch sử", status_code=404)
    content = revision["content"]
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if content_hash != revision["content_hash"]:
        raise DomainApiError("CHAPTER_RECORD_REVISION_INVALID", "Hợp lệ hoá nội dung chính của bản chỉnh sửa đã chọn thất bại", status_code=409)
    if content_hash != source.content_hash:
        raise DomainApiError("CHAPTER_RECORD_SOURCE_CHANGED", "hash nội dung chính không khớp bản chỉnh sửa đã chọn, hãy đọc lại phiên bản lịch sử", status_code=409)
    # 只比较正文；改标题等元数据不应让相同原文失效。
    if hashlib.sha256(chapter["content"].encode("utf-8")).hexdigest() != content_hash:
        raise DomainApiError("CHAPTER_RECORD_SOURCE_OUTDATED", "Nội dung chính nguồn đã thay đổi, hãy chọn bản chỉnh sửa của nội dung hiện tại rồi kiểm tra lại", status_code=409)
    return chapter, content


async def load_chapter_check_context(request: ChapterCheckInputV1) -> dict:
    """在同一只读事务核对章来源、参与身份及章前的已确认心理。

    Args:
        request: 服务器固定的章修订及目标状态，不采用图端口中的身份。
    Returns:
        完整原文、章前心理和原读取依据；未知心理须先由作者处理。
    """
    async def read(session):
        chapter, content = await _load_chapter_check_source(request.novel_id, request.source, session=session)
        state = await BaseRepository("character_volume_states").collection.find_one({
            "_id": ObjectId(request.state_id), "novel_id": chapter["novel_id"],
            "volume_id": chapter["volume_id"], "is_deleted": False,
        }, session=session)
        if state is None:
            raise DomainApiError("CHAPTER_CHECK_STATE_NOT_FOUND", "Trạng thái quyển của nhân vật không tồn tại, đã bị thu hồi hoặc không thuộc quyển của chương nguồn", status_code=404)
        if state["version"] != request.expected_version:
            raise DomainApiError("CHAPTER_CHECK_STATE_CHANGED", "Trạng thái quyển của nhân vật đã thay đổi, hãy đọc lại rồi kiểm tra", status_code=409)
        facts = await read_character_facts(request.novel_id, [state["character_id"]], {
            "target_type": "chapter", "target_id": request.source.chapter_id,
            "reading_intent": "chapter_before", "reading_version": 1,
        }, session=session)
        if not facts["characters"]:
            raise DomainApiError("CHAPTER_CHECK_CHARACTER_NOT_FOUND", "Nhân vật không tồn tại hoặc đã bị thu hồi, hãy chọn lại trạng thái quyển của nhân vật", status_code=404)
        character = facts["characters"][0]
        if "psychological_state" in character["unknown"]:
            raise DomainApiError("CHARACTER_FACT_UNKNOWN", "Tâm lý trước chương của nhân vật này chưa được xác định, hãy nhận hoặc rà soát lại sự thật nhân vật trước", status_code=409,
                                 details={"field": "psychological_state", "reason": character["unknown"]["psychological_state"],
                                          "blockers": character["blockers"].get("psychological_state", [])})
        psychological_state = character["values"]["psychological_state"]
        return {
            "chapter_content": content,
            "psychological_state": psychological_state,
            "character_name": character["name"],
            "target": {
                "state_id": str(state["_id"]), "expected_version": state["version"],
                "psychological_state": psychological_state,
                "character_id": state["character_id"], "volume_id": str(state["volume_id"]),
            },
            "fact_reads": facts["reads"],
            # 原状态版本只固定作者选择；心理正文及其来源由同一事实读取负责。
            "source_refs": [],
        }

    return await run_mongo_write_unit(read, "read_chapter_psychological_check", require_transaction=True)


def validate_chapter_check_result(candidate: dict, data: dict) -> dict:
    """校验唯一建议及原文出处，不判断文学解释是否成立。

    Args:
        candidate: 模型返回的问题和零或一条建议。
        data: 本次服务器读取的完整章正文和原状态。
    Returns:
        严格校验后的候选；引文保留所有空白、换行及 Unicode 字符。
    """
    result = ChapterCheckResultV1.model_validate(candidate)
    suggestion = result.suggestion
    if suggestion is not None:
        content = data["chapter_content"]
        if content[suggestion.start:suggestion.start + len(suggestion.quote)] != suggestion.quote:
            raise DomainApiError("CHAPTER_CHECK_QUOTE_MISMATCH", "Đoạn văn bản gốc đề xuất không khớp vị trí của bản chỉnh sửa đã chọn, hãy kiểm tra lại", status_code=422)
    return result.model_dump(mode="json")


async def load_chapter_item_owner_sources_in_session(request: ChapterItemOwnerCheckInputV1, *, session, require_current_owner: bool = True) -> dict:
    """独立读取固定物品和两个人物，供检查与确认共同使用。

    Args:
        request: 物品、作者原版本及固定的持有人 A→B。
        session: 调用方必需事务。
        require_current_owner: 旧检查仍核当前字段；新版另读章前完整状态。
    Returns:
        三个真实文档及其完整版本依据；不采用客户端给出的来源子集。
    """
    if session is None or not session.in_transaction:
        raise RuntimeError("Việc xác minh nguồn người giữ vật phẩm phải thực hiện trong transaction của bên gọi")
    novel_id = ObjectId(request.novel_id)
    item = await BaseRepository("items").collection.find_one({
        "novel_id": novel_id, "item_id": request.item_id, "is_deleted": False,
        "item_write_pending_token": None,
    }, session=session)
    if item is None:
        raise DomainApiError("CHAPTER_CHECK_ITEM_NOT_FOUND", "Vật phẩm không tồn tại trong sách này, đã bị thu hồi hoặc đang được lưu", status_code=404)
    if item["version"] != request.expected_version:
        raise DomainApiError("CHAPTER_CHECK_ITEM_CHANGED", "Vật phẩm đã thay đổi, hãy đọc lại rồi kiểm tra", status_code=409)
    if require_current_owner and item["lifecycle_status"] != "held":
        raise DomainApiError("CHAPTER_CHECK_ITEM_NOT_HELD", "Chỉ vật phẩm đang được giữ mới xác nhận được thay đổi người giữ", status_code=409)
    if require_current_owner and item["owner_character_id"] != request.from_character_id:
        raise DomainApiError("CHAPTER_CHECK_ITEM_OWNER_CHANGED", "Người giữ hiện tại của vật phẩm đã thay đổi, hãy đọc lại rồi kiểm tra", status_code=409)
    characters = []
    for identity in (request.from_character_id, request.to_character_id):
        character = await BaseRepository("characters").collection.find_one({
            "novel_id": novel_id, "character_id": identity, "is_deleted": False, "status": "active",
        }, session=session)
        if character is None:
            raise DomainApiError("CHAPTER_CHECK_CHARACTER_NOT_FOUND", "Người giữ không tồn tại trong sách này, đã bị thu hồi hoặc đã ngưng hoạt động", status_code=404)
        characters.append(character)
    refs = [CandidateSourceRefV1(resource_type=kind, id=str(row["_id"]), version=row["version"])
            for kind, row in (("item", item), ("character", characters[0]), ("character", characters[1]))]
    return {"item": item, "from_character": characters[0], "to_character": characters[1], "source_refs": refs}


async def load_chapter_item_owner_check_context(request: ChapterItemOwnerCheckInputV1) -> dict:
    """只读固定章原文和物品、两个人物的最少识别信息。

    Args:
        request: 服务器固定的章修订、物品版本和持有人方向。
    Returns:
        模型可见的最少信息及服务器校验用的完整来源版本。
    """
    async def read(session):
        _, content = await _load_chapter_check_source(request.novel_id, request.source, session=session)
        sources = await load_chapter_item_owner_sources_in_session(request, session=session)
        return {
            "chapter_content": content,
            "item": {key: sources["item"][key] for key in ("item_id", "name", "aliases")},
            "from_character": {key: sources["from_character"][key] for key in ("character_id", "name", "aliases")},
            "to_character": {key: sources["to_character"][key] for key in ("character_id", "name", "aliases")},
            "target": request.model_dump(mode="json", exclude={"novel_id", "source"}),
            "source_refs": sources["source_refs"],
        }

    return await run_mongo_write_unit(read, "read_chapter_item_owner_check", require_transaction=True)


def validate_chapter_item_owner_check_result(candidate: dict, data: dict) -> dict:
    """严格校验固定转交的唯一原文证据。

    Args:
        candidate: 模型返回的问题和零或一条引文。
        data: 本次服务器读取的原章正文。
    Returns:
        不含身份、版本或任意修改字段的检查结果。
    """
    result = ChapterItemOwnerCheckResultV1.model_validate(candidate)
    suggestion = result.suggestion
    if suggestion is not None:
        if "checked_facts" in data:
            before = data["checked_facts"]
            if before["values"] is None:
                message = "章前物品状态需要复核，请先确认完整状态" if before["unknown"] == "needs_review" else "章前物品状态未知，请先确认完整状态"
                raise DomainApiError("CHAPTER_CHECK_ITEM_STATE_UNKNOWN", message, status_code=409)
            if before["values"]["lifecycle_status"] != "held":
                raise DomainApiError("CHAPTER_CHECK_ITEM_NOT_HELD", "Vật phẩm trước chương không ở trạng thái đang giữ, không thể áp dụng chuyển giao người giữ", status_code=409)
            if before["values"]["owner_character_id"] != data["target"]["from_character_id"]:
                raise DomainApiError("CHAPTER_CHECK_ITEM_OWNER_CHANGED", "Người giữ trước chương khác người giữ gốc đã chọn lần này, hãy chọn lại", status_code=409)
        content = data["chapter_content"]
        if content[suggestion.start:suggestion.start + len(suggestion.quote)] != suggestion.quote:
            raise DomainApiError("CHAPTER_CHECK_QUOTE_MISMATCH", "Đoạn văn bản gốc đề xuất không khớp vị trí của bản chỉnh sửa đã chọn, hãy kiểm tra lại", status_code=422)
    return result.model_dump(mode="json")


async def load_chapter_item_owner_facts_check_context(request: ChapterItemOwnerCheckInputV1, *, session=None) -> dict:
    """读取原章之前的完整物品状态；未知和待复核不从旧字段补齐。

    Args:
        request: 固定章修订、物品版本和持有人 A→B。
        session: 采用准备时复用的只读事务。
    Returns:
        原文、识别信息、完整章前状态与原读取依据。
    """
    from backend.services.novel.item_fact_service import read_item_facts

    async def read(current_session):
        _, content = await _load_chapter_check_source(request.novel_id, request.source, session=current_session)
        sources = await load_chapter_item_owner_sources_in_session(request, session=current_session, require_current_owner=False)
        facts = await read_item_facts(request.novel_id, [request.item_id], {
            "target_type": "chapter", "target_id": request.source.chapter_id,
            "reading_intent": "chapter_before", "reading_version": 1,
        }, session=current_session)
        before = {key: facts["items"][0][key] for key in ("values", "unknown", "blockers", "origin", "claimed")}
        return {
            "chapter_content": content,
            "item": {**{key: sources["item"][key] for key in ("item_id", "name", "aliases")}, "before_state": before},
            "from_character": {key: sources["from_character"][key] for key in ("character_id", "name", "aliases")},
            "to_character": {key: sources["to_character"][key] for key in ("character_id", "name", "aliases")},
            "target": {"entity_id": str(sources["item"]["_id"]), **request.model_dump(mode="json", exclude={"novel_id", "source"})},
            "checked_facts": {"position": facts["position"], **before},
            "fact_reads": [facts["read"]], "source_refs": sources["source_refs"],
        }

    return await read(session) if session is not None else await run_mongo_write_unit(read, "read_chapter_item_owner_facts_check", require_transaction=True)


async def prepare_chapter_item_owner_facts(novel_id: str, data: dict) -> dict:
    """作者采用固定转交时，复查原检查并准备现有整组保存，不写新回执。

    Args:
        novel_id: 当前小说。
        data: 原检查依据、物品版本、固定方向和作者采用的原文证据。
    Returns:
        现有物品事实预览及完整后值；确认继续使用 confirm_item_facts。
    """
    from backend.services.novel.chapter_check_contract import CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK
    from backend.services.novel.chapter_record_contract import ChapterItemOwnerConfirmV1
    from backend.services.novel.item_fact_service import preview_item_facts, revalidate_item_fact_reads
    from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint
    from backend.services.task_flows.registry import TASKS

    command = ChapterItemOwnerConfirmV1.model_validate(data)
    novel_id = str(ObjectId(novel_id))
    fields = command.model_dump(mode="json")
    for name in ("chapter_id", "revision_id"):
        fields["evidence"][name] = str(ObjectId(fields["evidence"][name]))
    fixed = ChapterItemOwnerCheckInputV1.model_validate({
        "novel_id": novel_id, "source": {key: fields["evidence"][key] for key in ("chapter_id", "revision_id", "version", "content_hash")},
        **{key: fields[key] for key in ("item_id", "expected_version", "from_character_id", "to_character_id")},
    })

    async def prepare(session):
        basis, task = command.basis, CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK
        snapshot, spec = basis.flow_snapshot, TASKS[task]
        fixed_input = fixed.model_dump(mode="json")
        if (basis.novel_id != novel_id or basis.workflow != task
                or (basis.step, basis.schema_id, basis.schema_version) != (spec.step, spec.schema_id, spec.schema_version)
                or snapshot["scope"] != fixed_input or snapshot["business_input"] != fixed_input):
            raise DomainApiError("CANDIDATE_BASIS_CONFLICT", "Vật phẩm, hướng hoặc bản chỉnh sửa chương khác với kiểm tra ban đầu, hãy kiểm tra lại", status_code=409)
        execution = snapshot["execution"]
        if execution.get("item_reading_contract") != "item_facts_v1" or not execution.get("item_fact_reads"):
            raise DomainApiError("ITEM_FACT_CONTRACT_REQUIRED", "Kiểm tra ban đầu không có căn cứ trạng thái vật phẩm đầy đủ, hãy kiểm tra lại", status_code=409)
        await revalidate_item_fact_reads(execution["item_fact_reads"], session=session)
        context = await load_chapter_item_owner_facts_check_context(fixed, session=session)
        refs = context["source_refs"]
        ref_values = [ref.model_dump(mode="json") for ref in refs]
        reads = execution.get("source_refs_by_node")
        if (basis.source_refs != refs or any(read not in execution["item_fact_reads"] for read in context["fact_reads"])
                or not isinstance(reads, dict) or reads.get("preflight") != ref_values or any(value != ref_values for value in reads.values())):
            raise DomainApiError("CANDIDATE_BASIS_CONFLICT", "Tư liệu dùng để kiểm tra vật phẩm đã thay đổi, hãy kiểm tra lại", status_code=409)
        try:
            fingerprint = compute_flow_candidate_fingerprint(task, fixed, refs, snapshot)
        except (KeyError, ValueError) as exc:
            raise DomainApiError("CANDIDATE_BASIS_CONFLICT", "Luồng hoặc đầu vào của kiểm tra ban đầu đã thay đổi, hãy kiểm tra lại", status_code=409) from exc
        if fingerprint != basis.input_fingerprint:
            raise DomainApiError("CANDIDATE_FINGERPRINT_CONFLICT", "Căn cứ của kiểm tra ban đầu đã thay đổi, hãy kiểm tra lại", status_code=409)
        validate_chapter_item_owner_check_result({"issues": [], "suggestion": {key: fields["evidence"][key] for key in ("start", "quote")}}, context)
        # 只替换原章前状态的持有人；其余三项不能从模型或今日字段取得。
        after = {**context["checked_facts"]["values"], "owner_character_id": fixed.to_character_id}
        preview = await preview_item_facts(novel_id, {
            "operation": "change", "kind": "change",
            "target": {"entity_id": context["target"]["entity_id"], "item_id": fixed.item_id, "expected_version": fixed.expected_version},
            "position": {"version": 1, "intent": "chapter_after", "target_type": "chapter", "target_id": fixed.source.chapter_id},
            "source": {"kind": "chapter", "evidence": fields["evidence"]},
            "reference_selection": {key: after[key] for key in ("owner_character_id", "controlling_faction_id", "current_location_id")},
        }, session=session)
        return {"preview": preview, "after": after}

    return await run_mongo_write_unit(prepare, "prepare_chapter_item_owner_facts", require_transaction=True)


async def load_chapter_character_relation_state_sources_in_session(request: ChapterCharacterRelationStateCheckInputV1, *, session) -> dict:
    """按真实关系读取两端人物，供检查与确认核验完整版本。

    Args:
        request: 固定的关系 ID 与作者原版本。
        session: 调用方已经开启的事务。
    Returns:
        活动关系、两个活动人物及三个物理身份和版本；不限制所在卷。
    """
    if session is None or not session.in_transaction:
        raise RuntimeError("Việc xác minh nguồn quan hệ nhân vật phải thực hiện trong transaction của bên gọi")
    novel_id = ObjectId(request.novel_id)
    relation = await BaseRepository("character_relations").collection.find_one({
        "novel_id": novel_id, "relation_id": request.relation_id, "is_deleted": False,
    }, session=session)
    if relation is None:
        raise DomainApiError("CHAPTER_CHECK_RELATION_NOT_FOUND", "Quan hệ nhân vật không tồn tại trong sách này hoặc đã bị thu hồi", status_code=404)
    if relation["version"] != request.expected_version:
        raise DomainApiError("CHAPTER_CHECK_RELATION_CHANGED", "Quan hệ nhân vật đã thay đổi, hãy đọc lại rồi kiểm tra", status_code=409)
    if not relation["is_active"]:
        raise DomainApiError("CHAPTER_CHECK_RELATION_INACTIVE", "Chỉ quan hệ nhân vật đang hoạt động mới kiểm tra được trạng thái hiện tại", status_code=409)
    characters = []
    for identity in (relation["source_character_id"], relation["target_character_id"]):
        character = await BaseRepository("characters").collection.find_one({
            "novel_id": novel_id, "character_id": identity, "is_deleted": False, "status": "active",
        }, session=session)
        if character is None:
            raise DomainApiError("CHAPTER_CHECK_CHARACTER_NOT_FOUND", "Nhân vật trong quan hệ không tồn tại trong sách này, đã bị thu hồi hoặc đã ngưng hoạt động", status_code=404)
        characters.append(character)
    refs = [CandidateSourceRefV1(resource_type=kind, id=str(row["_id"]), version=row["version"])
            for kind, row in (("character_relation", relation), ("character", characters[0]), ("character", characters[1]))]
    return {"relation": relation, "source_character": characters[0], "target_character": characters[1], "source_refs": refs}


async def load_chapter_character_relation_state_check_context(request: ChapterCharacterRelationStateCheckInputV1) -> dict:
    """在只读事务中取得原章、当前关系和两端识别信息。

    Args:
        request: 固定章修订、关系和原版本。
    Returns:
        模型使用的有限资料、固定目标和完整来源依据。
    """
    async def read(session):
        _, content = await _load_chapter_check_source(request.novel_id, request.source, session=session)
        sources = await load_chapter_character_relation_state_sources_in_session(request, session=session)
        relation = sources["relation"]
        return {
            "chapter_content": content,
            "relation": {key: relation[key] for key in ("relation_id", "relation_type", "current_state", "source_character_id", "target_character_id")},
            "source_character": {key: sources["source_character"][key] for key in ("character_id", "name", "aliases")},
            "target_character": {key: sources["target_character"][key] for key in ("character_id", "name", "aliases")},
            "target": {
                "entity_id": str(relation["_id"]), "expected_version": relation["version"],
                **{key: relation[key] for key in ("relation_id", "source_character_id", "target_character_id", "current_state")},
            },
            "source_refs": sources["source_refs"],
        }

    return await run_mongo_write_unit(read, "read_chapter_character_relation_state_check", require_transaction=True)


async def load_chapter_character_relation_facts_check_context(request: ChapterCharacterRelationStateCheckInputV1) -> dict:
    """在同一事务读取原章、关系身份及章前事实，未知仍可检查章内证据。

    Args:
        request: 作者固定的章修订、关系和原版本。
    Returns:
        原样正文、章前已知值或未知原因，以及原来源版本和事实读取依据。
    """
    async def read(session):
        _, content = await _load_chapter_check_source(request.novel_id, request.source, session=session)
        sources = await load_chapter_character_relation_state_sources_in_session(request, session=session)
        relation = sources["relation"]
        facts = await read_character_relation_facts(request.novel_id, [request.relation_id], {
            "target_type": "chapter", "target_id": request.source.chapter_id,
            "reading_intent": "chapter_before", "reading_version": 1,
        }, session=session)
        # 活动关系已在同一事务核对；未知值保持缺省，不能借裸主档补齐。
        before_state = {key: facts["relations"][0][key] for key in (
            "values", "unknown", "blockers", "origins", "claimed_fields",
        )}
        return {
            "chapter_content": content,
            "relation": {
                **{key: relation[key] for key in ("relation_id", "relation_type", "source_character_id", "target_character_id")},
                "before_state": before_state,
            },
            "source_character": {key: sources["source_character"][key] for key in ("character_id", "name", "aliases")},
            "target_character": {key: sources["target_character"][key] for key in ("character_id", "name", "aliases")},
            "target": {
                "entity_id": str(relation["_id"]), "expected_version": relation["version"],
                **{key: relation[key] for key in ("relation_id", "source_character_id", "target_character_id")},
            },
            "checked_facts": {"position": facts["position"], **before_state},
            "fact_reads": facts["reads"],
            "source_refs": sources["source_refs"],
        }

    return await run_mongo_write_unit(read, "read_chapter_character_relation_facts_check", require_transaction=True)


def validate_chapter_character_relation_state_check_result(
    candidate: dict, data: dict, *,
    result_model: type[ChapterCharacterRelationStateCheckResultV1] = ChapterCharacterRelationStateCheckResultV1,
) -> dict:
    """校验唯一关系建议和原文位置，不判断文学解释是否成立。

    Args:
        candidate: 模型返回的问题和零或一条当前状态建议。
        data: 本次服务器读取的原样章正文。
        result_model: 当前任务的结果版本；旧版清理关系值，新版原样保留。
    Returns:
        按任务版本校验的结果，引文原样保留。
    """
    result = result_model.model_validate(candidate)
    suggestion = result.suggestion
    if suggestion is not None:
        content = data["chapter_content"]
        if content[suggestion.start:suggestion.start + len(suggestion.quote)] != suggestion.quote:
            raise DomainApiError("CHAPTER_CHECK_QUOTE_MISMATCH", "Đoạn văn bản gốc đề xuất không khớp vị trí của bản chỉnh sửa đã chọn, hãy kiểm tra lại", status_code=422)
    return result.model_dump(mode="json")


async def load_chapter_world_rules_check_context(request: ChapterWorldRulesCheckInputV1) -> dict:
    """在只读事务中取得原章及作者明确选择的全书活动规则。

    Args:
        request: 固定章修订和一至五条规则的原版本。
    Returns:
        原样正文、完整规则业务快照及物理身份和版本；不展开实体或写入资料。
    """
    async def read(session):
        chapter, content = await _load_chapter_check_source(request.novel_id, request.source, session=session)
        rules, refs = [], []
        for selection in request.rules:
            rule = await BaseRepository("world_rules").collection.find_one({
                "novel_id": chapter["novel_id"], "rule_id": selection.rule_id,
                "is_deleted": False, "status": "active", "scope_type": "global",
            }, session=session)
            if rule is None:
                raise DomainApiError("CHAPTER_CHECK_RULE_NOT_FOUND", "Quy tắc thế giới đã chọn không tồn tại trong sách này, đã bị thu hồi hoặc không phải quy tắc đang hoạt động của toàn sách, hãy chọn lại", status_code=404)
            if rule["version"] != selection.expected_version:
                raise DomainApiError("CHAPTER_CHECK_RULE_CHANGED", "Quy tắc thế giới đã chọn đã thay đổi, hãy đọc lại rồi kiểm tra", status_code=409)
            # 所有规则业务字段都保留，尤其不能省略例外和代价来压缩资料。
            rules.append({
                "entity_id": str(rule["_id"]), "novel_id": str(rule["novel_id"]),
                **{key: rule[key] for key in (
                    "rule_id", "version", "name", "category", "statement", "scope_type", "scope_entity_ids",
                    "enforcement", "exceptions", "costs_and_consequences", "priority", "status", "tags",
                    "order_index", "is_deleted",
                )},
            })
            refs.append(CandidateSourceRefV1(resource_type="world_rule", id=str(rule["_id"]), version=rule["version"]))
        rules_context = json.dumps(rules, ensure_ascii=False)
        if len(rules_context) > CHAPTER_CHECK_RULES_MAX_CHARACTERS:
            raise DomainApiError("CHAPTER_CHECK_RULES_BUDGET_EXCEEDED", "Tư liệu quy tắc đã chọn vượt 60000 ký tự, hãy giảm số quy tắc đã chọn rồi thử lại; không cắt ngắn quy tắc, ngoại lệ hay cái giá", status_code=422)
        return {"chapter_content": content, "rules": rules, "world_rules_context": rules_context, "source_refs": refs}

    return await run_mongo_write_unit(read, "read_chapter_world_rules_check", require_transaction=True)


def validate_chapter_world_rules_check_result(candidate: dict, data: dict) -> dict:
    """校验疑点引用的所选规则和原样引文，不判定疑点结论是否正确。

    Args:
        candidate: 模型返回的零至十条结构化疑点。
        data: 服务器读取的原章正文和实际规则快照。
    Returns:
        严格结果；只有合法空数组才表示没有报告疑点。
    """
    result = ChapterWorldRulesCheckResultV1.model_validate(candidate)
    selected = {rule["rule_id"] for rule in data["rules"]}
    content = data["chapter_content"]
    for issue in result.issues:
        if not set(issue.rule_ids).issubset(selected):
            raise DomainApiError("CHAPTER_CHECK_RULE_NOT_SELECTED", "Điểm nghi vấn tham chiếu quy tắc thế giới chưa được chọn, hãy kiểm tra lại", status_code=422)
        if content[issue.start:issue.start + len(issue.quote)] != issue.quote:
            raise DomainApiError("CHAPTER_CHECK_QUOTE_MISMATCH", "Đoạn văn bản gốc của điểm nghi vấn không khớp vị trí bản chỉnh sửa đã chọn, hãy kiểm tra lại", status_code=422)
    return result.model_dump(mode="json")
