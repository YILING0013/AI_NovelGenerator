"""势力卷级参与状态 HTTP Router。"""

from __future__ import annotations

from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Header, Path, Query
from pymongo.errors import PyMongoError

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
from backend.llm.schemas.faction_volume_state_pydantic import (
    FACTION_ID_PATTERN,
    FactionVolumeStateHardDeleteV1,
    FactionVolumeStateInitializeResultV1,
    FactionVolumeStateInitializeV1,
    FactionVolumeStateListV1,
    FactionVolumeStateReadV1, FactionVolumeReadV1, FactionVolumePlanReadV1,
    FactionVolumePlanFieldsV1, FactionVolumePlanUpdateV1,
    FactionVolumeStateUpdateV1,
    FactionVolumeStateUpsertV1,
    FactionVolumeStateVersionRequestV1,
    ParticipationScope,
)
from backend.services.novel.faction_volume_state_service import (
    FactionVolumeStateService,
)


router = APIRouter(
    prefix="/api/faction-volume-states",
    tags=["faction-volume-states"],
)

NovelIdPath = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
VolumeIdPath = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
StateIdPath = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{24}$")]
FactionIdPath = Annotated[str, Path(pattern=FACTION_ID_PATTERN)]
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


def _serialize_state(state: dict) -> FactionVolumeReadV1:
    """过滤内部字段并构造严格势力卷状态响应。

    Args:
        state: Repository、Service 或不可变回执返回的完整 BSON 状态。

    Returns:
        不含 MongoDB 内部 ID、guard 和幂等摘要的公开状态。
    """
    model = FactionVolumePlanReadV1 if state.get("content_contract") == "participation_plan_v1" else FactionVolumeStateReadV1
    public_fields = set(model.model_fields)
    payload = {field: value for field, value in state.items() if field in public_fields}
    for field in ("state_id", "novel_id", "volume_id"):
        if field in payload:
            payload[field] = str(payload[field])
    if payload.get("source_state_id") is not None:
        payload["source_state_id"] = str(payload["source_state_id"])
    return model.model_validate(payload)


def _serialize_list(states: list[dict]) -> FactionVolumeStateListV1:
    """构造卷列表或势力历史的严格 data 外壳。

    Args:
        states: 与领域顺序一致的完整 BSON 状态列表。

    Returns:
        只包含公开状态数组的严格列表响应。
    """
    return FactionVolumeStateListV1(
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
            message="势力卷状态数据库暂时不可用，请稍后重试",
        ) from exc
    status, code, message, field_errors, details = exception_to_error(
        exc,
        fallback_message="势力卷状态请求处理失败",
    )
    raise api_http_exception(
        status_code=status,
        code=code,
        message=message,
        field_errors=field_errors,
        details=details,
    ) from exc


@router.post("/novel/{novel_id}/volume/{volume_id}/faction/{faction_id}/plan", response_model=FactionVolumeReadV1)
async def create_faction_plan(novel_id: NovelIdPath, volume_id: VolumeIdPath, faction_id: FactionIdPath,
    req: FactionVolumePlanFieldsV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> FactionVolumeReadV1:
    """保存作者确认的参与计划，不填充实际剧情状态。

    Args:
        novel_id: 当前作品。
        volume_id: 目标卷。
        faction_id: 已有势力。
        req: 本卷计划。
        idempotency_key: 原保存键。
    Returns:
        首次保存的计划。
    """
    from backend.services.novel.faction_volume_plan_service import create_faction_volume_plan
    try:
        return _serialize_state(await create_faction_volume_plan(novel_id, volume_id, faction_id, req, idempotency_key=idempotency_key))
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)


@router.put("/novel/{novel_id}/{state_id}/plan", response_model=FactionVolumeReadV1)
async def update_faction_plan(novel_id: NovelIdPath, state_id: StateIdPath, req: FactionVolumePlanUpdateV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key")) -> FactionVolumeReadV1:
    """仅保存本次变更的计划，保留旧原文。

    Args:
        novel_id: 当前作品。
        state_id: 原参与记录。
        req: 原版本与实际改动。
        idempotency_key: 原保存键，用于未知响应后的原样恢复。
    Returns:
        更新后的参与计划。
    """
    from backend.services.novel.faction_volume_plan_service import update_faction_volume_plan
    try:
        return _serialize_state(await update_faction_volume_plan(novel_id, state_id, req, idempotency_key=idempotency_key))
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)


@router.post("/novel/{novel_id}/volume/{volume_id}/initialize-plans-from-previous", response_model=FactionVolumeStateInitializeResultV1)
async def initialize_faction_plans(novel_id: NovelIdPath, volume_id: VolumeIdPath,
    req: FactionVolumeStateInitializeV1, idempotency_key: str = Header(..., alias="Idempotency-Key")) -> FactionVolumeStateInitializeResultV1:
    """原子复制上卷参与计划，实际剧情状态仍按位置记录。

    Args:
        novel_id: 当前作品。
        volume_id: 目标卷。
        req: 选中的势力集合。
        idempotency_key: 原复制请求键。
    Returns:
        首次完整计划集合。
    """
    from backend.services.novel.faction_volume_plan_service import initialize_faction_volume_plans
    try:
        result = await initialize_faction_volume_plans(novel_id, volume_id, req, idempotency_key=idempotency_key)
        return FactionVolumeStateInitializeResultV1.model_validate({**result, "states": [_serialize_state(row) for row in result["states"]]})
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)


@router.put(
    "/novel/{novel_id}/volume/{volume_id}/faction/{faction_id}",
    response_model=FactionVolumeReadV1,
)
async def upsert_faction_volume_state(
    novel_id: NovelIdPath,
    volume_id: VolumeIdPath,
    faction_id: FactionIdPath,
    req: FactionVolumeStateUpsertV1,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> FactionVolumeReadV1:
    """按卷与势力复合路径幂等创建或完整更新状态。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        volume_id: 卷 ObjectId 路径参数。
        faction_id: 稳定势力业务 ID 路径参数。
        req: 完整业务字段和可选 expected_version。
        idempotency_key: 创建分支必须提供的幂等键；更新分支可省略。

    Returns:
        新建、更新或幂等重放后的完整公开状态。
    """
    try:
        state = await FactionVolumeStateService.upsert_state(
            novel_id.lower(),
            volume_id.lower(),
            faction_id,
            req,
            idempotency_key=idempotency_key,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return _serialize_state(state)


@router.get(
    "/novel/{novel_id}/volume/{volume_id}",
    response_model=FactionVolumeStateListV1,
)
async def list_faction_volume_states(
    novel_id: NovelIdPath,
    volume_id: VolumeIdPath,
    scope: ParticipationScope | None = Query(default=None),
    status: Literal["active", "deleted", "all"] = Query(default="active"),
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
) -> FactionVolumeStateListV1:
    """读取一卷中的势力状态名册或回收站视图。

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
        states = await FactionVolumeStateService.list_volume_states(
            novel_id.lower(),
            volume_id.lower(),
            scope=scope,
            status=status,
            q=q,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return _serialize_list(states)


@router.post(
    "/novel/{novel_id}/volume/{volume_id}/initialize-from-previous",
    response_model=FactionVolumeStateInitializeResultV1,
)
async def initialize_faction_volume_states_from_previous(
    novel_id: NovelIdPath,
    volume_id: VolumeIdPath,
    req: FactionVolumeStateInitializeV1,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> FactionVolumeStateInitializeResultV1:
    """从上一活动正式卷按白名单初始化选中势力。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        volume_id: 目标卷 ObjectId 路径参数。
        req: 唯一势力 ID 集合和严格零写冲突策略。
        idempotency_key: 调用方提供的批量初始化幂等键。

    Returns:
        源卷、目标卷和首次成功状态快照。
    """
    try:
        result = await FactionVolumeStateService.initialize_from_previous(
            novel_id.lower(),
            volume_id.lower(),
            req,
            idempotency_key=idempotency_key,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return FactionVolumeStateInitializeResultV1(
        source_volume_id=str(result["source_volume_id"]),
        target_volume_id=str(result["target_volume_id"]),
        states=[_serialize_state(state) for state in result["states"]],
    )


@router.get(
    "/novel/{novel_id}/faction/{faction_id}",
    response_model=FactionVolumeStateListV1,
)
async def list_faction_volume_state_history(
    novel_id: NovelIdPath,
    faction_id: FactionIdPath,
) -> FactionVolumeStateListV1:
    """读取一个势力跨卷的完整状态历史。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        faction_id: 稳定势力业务 ID 路径参数。

    Returns:
        含活动与回收站状态数组的 data 外壳。
    """
    try:
        states = await FactionVolumeStateService.list_faction_history(
            novel_id.lower(),
            faction_id,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return _serialize_list(states)


@router.get(
    "/novel/{novel_id}/{state_id}",
    response_model=FactionVolumeReadV1,
)
async def get_faction_volume_state(
    novel_id: NovelIdPath,
    state_id: StateIdPath,
) -> FactionVolumeReadV1:
    """按 ObjectId 读取一条活动或回收站状态。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        state_id: 状态 ObjectId 路径参数。

    Returns:
        指定状态的完整公开投影。
    """
    try:
        state = await FactionVolumeStateService.get_state(
            novel_id.lower(),
            state_id.lower(),
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return _serialize_state(state)


@router.put(
    "/novel/{novel_id}/{state_id}",
    response_model=FactionVolumeReadV1,
)
async def update_faction_volume_state(
    novel_id: NovelIdPath,
    state_id: StateIdPath,
    req: FactionVolumeStateUpdateV1,
) -> FactionVolumeReadV1:
    """按状态 ObjectId 和版本局部更新业务字段。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        state_id: 状态 ObjectId 路径参数。
        req: 含 expected_version 的严格局部更新请求。

    Returns:
        CAS 更新后的完整公开状态。
    """
    try:
        state = await FactionVolumeStateService.update_state(
            novel_id.lower(),
            state_id.lower(),
            req,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return _serialize_state(state)


@router.delete(
    "/novel/{novel_id}/{state_id}",
    response_model=FactionVolumeReadV1,
)
async def soft_delete_faction_volume_state(
    novel_id: NovelIdPath,
    state_id: StateIdPath,
    expected_version: Annotated[int, Query(ge=1)],
) -> FactionVolumeReadV1:
    """按版本给状态添加 user 删除来源。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        state_id: 状态 ObjectId 路径参数。
        expected_version: 调用方持有的公开版本。

    Returns:
        添加用户删除来源后的完整公开状态。
    """
    try:
        state = await FactionVolumeStateService.soft_delete_state(
            novel_id.lower(),
            state_id.lower(),
            expected_version=expected_version,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return _serialize_state(state)


@router.post(
    "/novel/{novel_id}/{state_id}/restore",
    response_model=FactionVolumeReadV1,
)
async def restore_faction_volume_state(
    novel_id: NovelIdPath,
    state_id: StateIdPath,
    req: FactionVolumeStateVersionRequestV1,
) -> FactionVolumeReadV1:
    """按版本仅移除状态的 user 删除来源。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        state_id: 状态 ObjectId 路径参数。
        req: 含 expected_version 的严格生命周期请求。

    Returns:
        移除用户来源后的完整公开状态。
    """
    try:
        state = await FactionVolumeStateService.restore_state(
            novel_id.lower(),
            state_id.lower(),
            expected_version=req.expected_version,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return _serialize_state(state)


@router.delete(
    "/novel/{novel_id}/{state_id}/hard",
    response_model=FactionVolumeStateHardDeleteV1,
)
async def hard_delete_faction_volume_state(
    novel_id: NovelIdPath,
    state_id: StateIdPath,
    expected_version: Annotated[int, Query(ge=1)],
) -> FactionVolumeStateHardDeleteV1:
    """按版本永久删除无后代和结构事件引用的回收站状态。

    Args:
        novel_id: 小说 ObjectId 路径参数。
        state_id: 状态 ObjectId 路径参数。
        expected_version: 调用方持有的公开版本。

    Returns:
        含 deleted=true 与被删除 state_id 的结果。
    """
    try:
        result = await FactionVolumeStateService.hard_delete_state(
            novel_id.lower(),
            state_id.lower(),
            expected_version=expected_version,
        )
    except EXPECTED_STATE_ERRORS as exc:
        _raise_state_http_error(exc)
    return FactionVolumeStateHardDeleteV1.model_validate(
        {**result, "state_id": str(result["state_id"])}
    )


__all__ = ["router"]

