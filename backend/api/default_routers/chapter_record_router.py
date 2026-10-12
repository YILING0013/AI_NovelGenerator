"""作者确认的章节事件、逐版报告和人物实际心理状态。"""

from typing import Annotated, Literal

from fastapi import APIRouter, Header, Path

from backend.api.contracts import ObjectIdString
from backend.api.error_protocol import DomainApiError
from backend.api.default_routers.arc_router import EXPECTED_ERRORS, raise_arc_http_error
from backend.services.novel.chapter_record_contract import (
    ChapterEventConfirmV1, ChapterEventReadV1, ChapterReportConfirmV1,
    ChapterReportReadV1, ChapterReportHeadReadV1, ChapterRecordVoidV1,
    ChapterPsychologicalStateConfirmV1, ChapterPsychologicalStateResultV1,
    ChapterStateHistoryReadV1, ChapterItemOwnerConfirmV1, ChapterItemOwnerResultV1,
    ChapterCharacterRelationStateConfirmV1, ChapterCharacterRelationStateResultV1,
    ChapterRecordSourceReadV1,
)
from backend.services.novel.chapter_record_service import ChapterRecordService
from backend.services.novel.chapter_check_contract import CHAPTER_CHECK_TASK, CHAPTER_ITEM_OWNER_CHECK_TASK, CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, CHAPTER_WORLD_RULES_CHECK_TASK
from backend.services.task_flows.contracts import GraphRunRequest
from backend.services.task_flows.integration import generate_task_flow


router = APIRouter(prefix="/api/chapter-records/novel/{novel_id}", tags=["chapter-records"])


@router.post("/psychological-state/check")
async def check_psychological_state(novel_id: ObjectIdString, req: GraphRunRequest):
    """按选定章修订生成单个人物心理建议，不写入业务资料。

    Args:
        novel_id: 当前小说，由路径固定。
        req: 原任务图封套，scope 指定章修订和已有卷状态版本。
    Returns:
        待作者审阅的候选封套或 SSE；确认仍使用原心理状态接口。
    """
    try:
        return await generate_task_flow(CHAPTER_CHECK_TASK, req, scope={"novel_id": novel_id}, stream=True)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_CHECK", label="章后心理检查")


@router.get("/chapters/{chapter_id}/revisions/{version}", response_model=ChapterRecordSourceReadV1)
async def get_source_revision(novel_id: ObjectIdString, chapter_id: ObjectIdString, version: Annotated[int, Path(ge=1, le=2**63 - 1)]) -> dict:
    """读取原修订和回收位置，包括小说或任一父级已回收的来源。

    Args:
        novel_id: 记录所属小说。
        chapter_id: 来源章节。
        version: 来源修订版本。
    Returns:
        完整原修订和实际回收位置；不修改记录或实体。
    """
    try:
        return await ChapterRecordService.get_source_revision(novel_id, chapter_id, version)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后记录")


@router.post("/item-owner/check")
async def check_item_owner(novel_id: ObjectIdString, req: GraphRunRequest):
    """只读检查固定物品的持有人 A→B。

    Args:
        novel_id: 由路径固定的小说。
        req: 原任务图封套及固定章修订、物品版本和持有人方向。
    Returns:
        待作者审阅的证据候选或 SSE。
    """
    try:
        return await generate_task_flow(CHAPTER_ITEM_OWNER_CHECK_TASK, req, scope={"novel_id": novel_id}, stream=True)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_CHECK", label="章后持有人检查")


@router.post("/character-relation-state/check")
async def check_character_relation_state(novel_id: ObjectIdString, req: GraphRunRequest):
    """只读检查一条既有活动人物关系的当前状态。

    Args:
        novel_id: 由路径固定的小说。
        req: 原任务图封套及固定章修订、关系和版本。
    Returns:
        供作者审阅的问题、零或一条状态建议及完整依据。
    """
    try:
        return await generate_task_flow(CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK, req, scope={"novel_id": novel_id}, stream=True)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_CHECK", label="章后人物关系检查")


@router.post("/world-rules/check")
async def check_world_rules(novel_id: ObjectIdString, req: GraphRunRequest):
    """只读检查一章与作者选择的全书活动世界规则。

    Args:
        novel_id: 由路径固定的小说。
        req: 原任务图封套及固定章修订、规则编号和原版本。
    Returns:
        供作者整理报告的结构化疑点和实际规则快照，不保存报告或实体。
    """
    try:
        return await generate_task_flow(CHAPTER_WORLD_RULES_CHECK_TASK, req, scope={"novel_id": novel_id}, stream=True)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_CHECK", label="章后世界规则检查")


@router.post("/item-owner/confirm", response_model=ChapterItemOwnerResultV1)
async def confirm_item_owner(novel_id: ObjectIdString, req: ChapterItemOwnerConfirmV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """作者明确确认检查时固定的持有人变化。

    Args:
        novel_id: 当前小说。
        req: 固定物品、版本、方向、完整检查依据和原文证据。
        idempotency_key: 本次确认固定使用的请求键。
    Returns:
        实际变化及历史，或同键原成功响应。
    """
    try:
        return await ChapterRecordService.confirm_item_owner(novel_id, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后持有人确认")


@router.post("/character-relation-state/confirm", response_model=ChapterCharacterRelationStateResultV1)
async def confirm_character_relation_state(novel_id: ObjectIdString, req: ChapterCharacterRelationStateConfirmV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """作者逐项确认既有关系的当前状态，不修改关系身份及其他字段。

    Args:
        novel_id: 当前小说。
        req: 原关系版本、作者编辑的状态、完整检查依据和原文证据。
        idempotency_key: 本次确认固定使用的请求键。
    Returns:
        实际状态和可空变化历史，或同键原成功响应。
    """
    try:
        return await ChapterRecordService.confirm_character_relation_state(novel_id, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后人物关系确认")


@router.post("/events", response_model=ChapterEventReadV1)
async def confirm_event(novel_id: ObjectIdString, req: ChapterEventConfirmV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """作者明确确认一条已发生事件。

    Args:
        novel_id: 小说 ID。
        req: 已发生内容、相关实体与原文证据。
        idempotency_key: 本次确认的固定键。
    Returns:
        新事件或原成功快照。
    """
    try:
        return await ChapterRecordService.confirm(novel_id, "event", req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后记录")


@router.post("/reports", response_model=ChapterReportReadV1)
async def confirm_report(novel_id: ObjectIdString, req: ChapterReportConfirmV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """在作者已读报告版本之后追加一版。

    Args:
        novel_id: 小说 ID。
        req: 已读报告版本、章末摘要、问题和原文证据。
        idempotency_key: 本次确认的固定键。
    Returns:
        新报告或原成功快照。
    """
    try:
        return await ChapterRecordService.confirm(novel_id, "report", req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后记录")


@router.post("/psychological-state", response_model=ChapterPsychologicalStateResultV1)
async def confirm_psychological_state(novel_id: ObjectIdString, req: ChapterPsychologicalStateConfirmV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """按作者原版本确认人物本卷实际心理状态。

    Args:
        novel_id: 小说 ID。
        req: 卷状态身份、原版本、心理状态和原文证据。
        idempotency_key: 本次确认的固定键。
    Returns:
        原成功状态及真实变化历史；无变化时 history 为 null。
    """
    try:
        return await ChapterRecordService.confirm_psychological_state(novel_id, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后记录")


@router.get("/events", response_model=list[ChapterEventReadV1])
async def list_events(novel_id: ObjectIdString, chapter_id: ObjectIdString | None = None, revision_id: ObjectIdString | None = None) -> list[dict]:
    """读取本书事件，包括作废记录和软删除来源。

    Args:
        novel_id: 小说 ID。
        chapter_id: 可选来源章。
        revision_id: 可选来源修订。
    Returns:
        按确认时间倒序的事件。
    """
    try:
        return await ChapterRecordService.list(novel_id, "event", chapter_id=chapter_id, revision_id=revision_id)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后记录")


@router.get("/reports", response_model=list[ChapterReportReadV1])
async def list_reports(novel_id: ObjectIdString, chapter_id: ObjectIdString | None = None, revision_id: ObjectIdString | None = None) -> list[dict]:
    """读取本书所有报告版本，包括作废版本。

    Args:
        novel_id: 小说 ID。
        chapter_id: 可选来源章。
        revision_id: 可选来源修订。
    Returns:
        按确认时间倒序的报告，不把旧版当作当前版本。
    """
    try:
        return await ChapterRecordService.list(novel_id, "report", chapter_id=chapter_id, revision_id=revision_id)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后记录")


@router.get("/state-history", response_model=list[ChapterStateHistoryReadV1])
async def list_state_history(novel_id: ObjectIdString, chapter_id: ObjectIdString | None = None, revision_id: ObjectIdString | None = None, state_id: ObjectIdString | None = None, entity_type: Literal["character_volume_state", "item", "character_relation"] | None = None, entity_id: ObjectIdString | None = None) -> list[dict]:
    """读取本书真实执行过的人物心理、物品持有人和人物关系状态变化。

    Args:
        novel_id: 小说 ID。
        chapter_id: 可选来源章。
        revision_id: 可选来源修订。
        state_id: 可选人物卷状态 ID。
        entity_type: 与实体物理 ID 成对使用的历史类型。
        entity_id: 对应类型的实体物理 ID，不能与旧 state_id 混用。
    Returns:
        按确认时间倒序的历史，允许普通编辑造成版本空号。
    """
    try:
        if ((state_id is not None and (entity_type is not None or entity_id is not None))
                or ((entity_type is None) != (entity_id is None))):
            raise DomainApiError("CHAPTER_RECORD_HISTORY_FILTER_INVALID", "人物卷状态 ID 不能与实体筛选混用；实体类型和 ID 必须一起提供", status_code=422)
        if state_id is not None:
            return await ChapterRecordService.list(novel_id, "history", chapter_id=chapter_id, revision_id=revision_id, entity_id=state_id, entity_type="character_volume_state")
        return await ChapterRecordService.list(novel_id, "history", chapter_id=chapter_id, revision_id=revision_id, entity_id=entity_id, entity_type=entity_type)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后记录")


@router.get("/events/{identity}", response_model=ChapterEventReadV1)
async def get_event(novel_id: ObjectIdString, identity: ObjectIdString) -> dict:
    """读取单条事件及当前正文复核标记。

    Args:
        novel_id: 小说 ID。
        identity: 事件 ID。
    Returns:
        同书事件详情。
    """
    try:
        return await ChapterRecordService.get(novel_id, "event", identity)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后记录")


@router.get("/reports/{identity}", response_model=ChapterReportReadV1)
async def get_report(novel_id: ObjectIdString, identity: ObjectIdString) -> dict:
    """读取指定报告版本及当前正文复核标记。

    Args:
        novel_id: 小说 ID。
        identity: 报告版本 ID。
    Returns:
        同书原报告详情。
    """
    try:
        return await ChapterRecordService.get(novel_id, "report", identity)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后记录")


@router.get("/state-history/{identity}", response_model=ChapterStateHistoryReadV1)
async def get_state_history(novel_id: ObjectIdString, identity: ObjectIdString) -> dict:
    """读取一次实际状态变化。

    Args:
        novel_id: 小说 ID。
        identity: 历史 ID。
    Returns:
        同书实际变化及原文来源。
    """
    try:
        return await ChapterRecordService.get(novel_id, "history", identity)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后记录")


@router.get("/chapters/{chapter_id}/report", response_model=ChapterReportHeadReadV1)
async def get_report_head(novel_id: ObjectIdString, chapter_id: ObjectIdString) -> dict:
    """读取下次追加需提交的报告版本和当前有效报告。

    Args:
        novel_id: 小说 ID。
        chapter_id: 来源章 ID。
    Returns:
        当前 head；最新报告作废时 report 为 null。
    """
    try:
        return await ChapterRecordService.report_head(novel_id, chapter_id)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后记录")


@router.post("/events/{identity}/void", response_model=ChapterEventReadV1)
async def void_event(novel_id: ObjectIdString, identity: ObjectIdString, req: ChapterRecordVoidV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """单向作废事件，保留原内容和来源。

    Args:
        novel_id: 小说 ID。
        identity: 事件 ID。
        req: 作废原因。
        idempotency_key: 本次作废的固定键。
    Returns:
        原作废成功响应。
    """
    try:
        return await ChapterRecordService.void(novel_id, "event", identity, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后记录")


@router.post("/reports/{identity}/void", response_model=ChapterReportReadV1)
async def void_report(novel_id: ObjectIdString, identity: ObjectIdString, req: ChapterRecordVoidV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> dict:
    """单向作废指定报告，head 与报告版本均不倒退。

    Args:
        novel_id: 小说 ID。
        identity: 报告 ID。
        req: 作废原因。
        idempotency_key: 本次作废的固定键。
    Returns:
        原作废成功响应。
    """
    try:
        return await ChapterRecordService.void(novel_id, "report", identity, req, idempotency_key=idempotency_key)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHAPTER_RECORD", label="章后记录")
