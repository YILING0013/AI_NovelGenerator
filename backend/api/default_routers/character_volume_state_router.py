"""角色卷级参与状态 HTTP Router。"""

from __future__ import annotations

from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Header, Path, Query
from pymongo.errors import PyMongoError

from backend.api.contracts import ObjectIdString
from backend.api.default_routers.arc_router import EXPECTED_ERRORS, raise_arc_http_error
from backend.api.error_protocol import (
    DomainApiError,
    api_http_exception,
    exception_to_error,
)
from backend.db.errors import (
    DuplicateKeyError,
    InvalidIdError,
    NotFoundError,
    TransactionNotSupportedError,
)
from backend.llm.schemas.character_volume_state_pydantic import (
    CHARACTER_ID_PATTERN,
    CharacterId,
    CharacterVolumePlanCreateV1,
    CharacterVolumePlanUpdateV1,
    CharacterVolumeArcReadinessV1,
    CharacterVolumeStateHardDeleteV1,
    CharacterVolumeStateInitializeResultV1,
    CharacterVolumeStateInitializeV1,
    CharacterVolumeStateListV1,
    CharacterVolumeStateReadV1,
    CharacterVolumeStateUpdateV1,
    CharacterVolumeStateUpsertV1,
    CharacterVolumeStateVersionRequestV1,
    ParticipationScope,
)
from backend.services.novel.character_volume_state_service import (
    CharacterVolumeStateService,
)


router = APIRouter(
    prefix="/api/character-volume-states",
    tags=["character-volume-states"],
)

# 参与计划使用独立路由，不扩松旧全字段状态合同。
plan_router = APIRouter(prefix="/api/character-volume-states", tags=["character-volume-plans"])


class CharacterVolumePlanCreateRequestV1(CharacterVolumePlanCreateV1):
    """HTTP 创建请求固定卷和人物，业务内容仍严格限定原六个计划字段。"""

    volume_id: ObjectIdString
    character_id: CharacterId

NovelIdPath = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
VolumeIdPath = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
StateIdPath = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
CharacterIdPath = Annotated[str, Path(pattern=CHARACTER_ID_PATTERN)]
EXPECTED_STATE_ERRORS = (
    DomainApiError,
    DuplicateKeyError,
    InvalidIdError,
    NotFoundError,
    TransactionNotSupportedError,
    PyMongoError,
    TypeError,
    ValueError,
)


def _serialize_state(state: dict) -> CharacterVolumeStateReadV1:
    """过滤内部字段并构造严格角色卷状态响应。

    Args:
        state: Repository、Service 或不可变回执返回的完整 BSON 状态。

    Returns:
        不含 MongoDB 内部 ID、guard 和幂等摘要的公开状态。
    """
    public_fields = set(CharacterVolumeStateReadV1.model_fields)
    payload = {field: value for field, value in state.items() if field in public_fields}
    for field in ("state_id", "novel_id", "volume_id"):
        if field in payload:
            payload[field] = str(payload[field])
    if payload.get("source_state_id") is not None:
        payload["source_state_id"] = str(payload["source_state_id"])
    return CharacterVolumeStateReadV1.model_validate(payload)


def _serialize_list(states: list[dict]) -> CharacterVolumeStateListV1:
    """构造卷列表或角色历史的严格 data 外壳。

    Args:
        states: 与领域顺序一致的完整 BSON 状态列表。

    Returns:
        只包含公开状态数组的严格列表响应。
    """
    return CharacterVolumeStateListV1(
        data=[_serialize_state(state) for state in states]
    )


def _raise_state_http_error(exc: Exception) -> NoReturn:
    """把状态领域和数据库异常转换为公共 HTTP 错误。

    Args:
        exc: Service 或数据库抛出的预期异常。

    Returns:
        不返回；始终抛出符合公共协议的 HTTPException。
    """
    if isinstance(exc, (TransactionNotSupportedError, PyMongoError)):
        raise api_http_exception(
            status_code=503,
            code="DATABASE_UNAVAILABLE",
            message="角色卷状态数据库暂时不可用，请稍后重试",
        ) from exc
    status, code, message, field_errors, details = exception_to_error(
        exc,
        fallback_message="角色卷状态请求处理失败",
    )
    raise api_http_exception(
        status_code=status,
        code=code,
        message=message,
        field_errors=field_errors,
        details=details,
    ) from exc


@router.put(
    "/novel/{novel_id}/volume/{volume_id}/character/{character_id}",
    response_model=CharacterVolumeStateReadV1,
)
async def upsert_character_volume_state(
    novel_id: NovelIdPath,
    volume_id: VolumeIdPath,
    character_id: CharacterIdPath,
    req: CharacterVolumeStateUpsertV1,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CharacterVolumeStateReadV1:
    """按卷与角色复合路径幂等创建或完整更新状态。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        volume_id: 卷 ObjectId 路径参数。
        character_id: 稳定角色业务 ID 路径参数。
        req: 完整业务字段和可选 expected_version。
        idempotency_key: 创建分支必须提供的幂等键；更新分支可省略。

    Returns:
        新建、更新或幂等重放后的完整公开状态。
    """
    try:
        state = await CharacterVolumeStateService.upsert_state(
            novel_id.lower(),
            volume_id.lower(),
            character_id,
            req,
            idempotency_key=idempotency_key,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return _serialize_state(state)


@router.get(
    "/novel/{novel_id}/volume/{volume_id}",
    response_model=CharacterVolumeStateListV1,
)
async def list_character_volume_states(
    novel_id: NovelIdPath,
    volume_id: VolumeIdPath,
    scope: ParticipationScope | None = Query(default=None),
    status: Literal["active", "deleted", "all"] = Query(default="active"),
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
) -> CharacterVolumeStateListV1:
    """读取一卷中的角色状态名册或回收站视图。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        volume_id: 卷 ObjectId 路径参数。
        scope: 可选参与层级筛选。
        status: active、deleted 或 all 生命周期视图。
        q: 可选状态内容搜索词。

    Returns:
        含符合筛选条件状态数组的 data 外壳。
    """
    try:
        states = await CharacterVolumeStateService.list_volume_states(
            novel_id.lower(),
            volume_id.lower(),
            scope=scope,
            status=status,
            q=q,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return _serialize_list(states)


@router.get(
    "/novel/{novel_id}/volume/{volume_id}/arc-readiness",
    response_model=CharacterVolumeArcReadinessV1,
)
async def get_character_volume_arc_readiness(
    novel_id: NovelIdPath,
    volume_id: VolumeIdPath,
) -> CharacterVolumeArcReadinessV1:
    """读取当前卷进入人物弧规划前的主角状态门禁。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        volume_id: 当前规划卷 ObjectId 路径参数。

    Returns:
        活动主角、已有状态主角及 ready 结果。
    """
    try:
        readiness = await CharacterVolumeStateService.get_arc_readiness(
            novel_id.lower(),
            volume_id.lower(),
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return CharacterVolumeArcReadinessV1.model_validate(readiness)


@router.post(
    "/novel/{novel_id}/volume/{volume_id}/initialize-from-previous",
    response_model=CharacterVolumeStateInitializeResultV1,
)
async def initialize_character_volume_states_from_previous(
    novel_id: NovelIdPath,
    volume_id: VolumeIdPath,
    req: CharacterVolumeStateInitializeV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> CharacterVolumeStateInitializeResultV1:
    """从上一活动正式卷按白名单初始化选中角色。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        volume_id: 目标卷 ObjectId 路径参数。
        req: 唯一角色 ID 集合和严格零写冲突策略。
        idempotency_key: 调用方提供的批量初始化幂等键。

    Returns:
        源卷、目标卷和首次成功状态快照。
    """
    try:
        result = await CharacterVolumeStateService.initialize_from_previous(
            novel_id.lower(),
            volume_id.lower(),
            req,
            idempotency_key=idempotency_key,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return CharacterVolumeStateInitializeResultV1(
        source_volume_id=str(result["source_volume_id"]),
        target_volume_id=str(result["target_volume_id"]),
        states=[_serialize_state(state) for state in result["states"]],
    )


@router.get(
    "/novel/{novel_id}/character/{character_id}",
    response_model=CharacterVolumeStateListV1,
)
async def list_character_volume_state_history(
    novel_id: NovelIdPath,
    character_id: CharacterIdPath,
) -> CharacterVolumeStateListV1:
    """读取一个角色跨卷的完整状态历史。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        character_id: 稳定角色业务 ID 路径参数。

    Returns:
        含活动与回收站状态数组的 data 外壳。
    """
    try:
        states = await CharacterVolumeStateService.list_character_history(
            novel_id.lower(),
            character_id,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return _serialize_list(states)


@router.get(
    "/novel/{novel_id}/{state_id}",
    response_model=CharacterVolumeStateReadV1,
)
async def get_character_volume_state(
    novel_id: NovelIdPath,
    state_id: StateIdPath,
) -> CharacterVolumeStateReadV1:
    """按 ObjectId 读取一条活动或回收站状态。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        state_id: 状态 ObjectId 路径参数。

    Returns:
        指定状态的完整公开投影。
    """
    try:
        state = await CharacterVolumeStateService.get_state(
            novel_id.lower(),
            state_id.lower(),
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return _serialize_state(state)


@router.put(
    "/novel/{novel_id}/{state_id}",
    response_model=CharacterVolumeStateReadV1,
)
async def update_character_volume_state(
    novel_id: NovelIdPath,
    state_id: StateIdPath,
    req: CharacterVolumeStateUpdateV1,
) -> CharacterVolumeStateReadV1:
    """按状态 ObjectId 和版本局部更新业务字段。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        state_id: 状态 ObjectId 路径参数。
        req: 含 expected_version 的严格局部更新请求。

    Returns:
        CAS 更新后的完整公开状态。
    """
    try:
        state = await CharacterVolumeStateService.update_state(
            novel_id.lower(),
            state_id.lower(),
            req,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return _serialize_state(state)


@router.delete(
    "/novel/{novel_id}/{state_id}",
    response_model=CharacterVolumeStateReadV1,
)
async def soft_delete_character_volume_state(
    novel_id: NovelIdPath,
    state_id: StateIdPath,
    expected_version: Annotated[int, Query(ge=1)],
) -> CharacterVolumeStateReadV1:
    """按版本给状态添加 user 删除来源。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        state_id: 状态 ObjectId 路径参数。
        expected_version: 调用方持有的公开版本。

    Returns:
        添加用户删除来源后的完整公开状态。
    """
    try:
        state = await CharacterVolumeStateService.soft_delete_state(
            novel_id.lower(),
            state_id.lower(),
            expected_version=expected_version,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return _serialize_state(state)


@router.post(
    "/novel/{novel_id}/{state_id}/restore",
    response_model=CharacterVolumeStateReadV1,
)
async def restore_character_volume_state(
    novel_id: NovelIdPath,
    state_id: StateIdPath,
    req: CharacterVolumeStateVersionRequestV1,
) -> CharacterVolumeStateReadV1:
    """按版本仅移除状态的 user 删除来源。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        state_id: 状态 ObjectId 路径参数。
        req: 含 expected_version 的严格生命周期请求。

    Returns:
        移除用户来源后的完整公开状态。
    """
    try:
        state = await CharacterVolumeStateService.restore_state(
            novel_id.lower(),
            state_id.lower(),
            expected_version=req.expected_version,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return _serialize_state(state)


@router.delete(
    "/novel/{novel_id}/{state_id}/hard",
    response_model=CharacterVolumeStateHardDeleteV1,
)
async def hard_delete_character_volume_state(
    novel_id: NovelIdPath,
    state_id: StateIdPath,
    expected_version: Annotated[int, Query(ge=1)],
) -> CharacterVolumeStateHardDeleteV1:
    """按版本永久删除无后代和结构事件引用的回收站状态。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        state_id: 状态 ObjectId 路径参数。
        expected_version: 调用方持有的公开版本。

    Returns:
        含 deleted=true 与被删除 state_id 的结果。
    """
    try:
        result = await CharacterVolumeStateService.hard_delete_state(
            novel_id.lower(),
            state_id.lower(),
            expected_version=expected_version,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return CharacterVolumeStateHardDeleteV1.model_validate(result)


@plan_router.post("/novel/{novel_id}/plans", response_model=CharacterVolumeStateReadV1)
async def create_character_volume_plan(
    novel_id: NovelIdPath, req: CharacterVolumePlanCreateRequestV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> CharacterVolumeStateReadV1:
    """只建立本卷参与和计划，实际处境由人物事实读取。

    Args:
        novel_id: 当前小说。
        req: 卷、人物身份及六个参与和计划字段。
        idempotency_key: 本次新建固定的请求键。
    Returns:
        原九字段公开状态；三个旧处境槽位由服务端初始化为空。
    """
    try:
        state = await CharacterVolumeStateService.create_plan(
            novel_id.lower(), req.volume_id.lower(), req.character_id,
            req.model_dump(exclude={"volume_id", "character_id"}), idempotency_key=idempotency_key,
        )
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_VOLUME_PLAN", label="人物参与计划")
    return _serialize_state(state)


@plan_router.put("/novel/{novel_id}/{state_id}/plan", response_model=CharacterVolumeStateReadV1)
async def update_character_volume_plan(
    novel_id: NovelIdPath, state_id: StateIdPath, req: CharacterVolumePlanUpdateV1,
) -> CharacterVolumeStateReadV1:
    """按原状态版本局部保存参与和计划，保留已有非权威处境原文。

    Args:
        novel_id: 当前小说。
        state_id: 目标卷状态物理 ID。
        req: 原版本及实际提交的六字段子集。
    Returns:
        版本更新后的原公开状态形状。
    """
    try:
        state = await CharacterVolumeStateService.update_plan(novel_id.lower(), state_id.lower(), req)
    except EXPECTED_ERRORS as exc:
        raise_arc_http_error(exc, prefix="CHARACTER_VOLUME_PLAN", label="人物参与计划")
    return _serialize_state(state)


__all__ = ["router", "plan_router"]
