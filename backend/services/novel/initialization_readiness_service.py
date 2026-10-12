"""从正式事实确定性计算全书初始化就绪状态。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator
from pymongo.errors import ExecutionTimeout, NetworkTimeout, PyMongoError
from pymongo.read_concern import ReadConcern

from backend.api.contracts import ObjectIdString, StrictResponseModel
from backend.api.error_protocol import DomainApiError
from backend.db.mongo import get_client
from backend.db.repositories.initialization_readiness_repository import (
    initialization_readiness_repo,
)
from backend.db.transaction import supports_mongo_transactions
from backend.db.write_contracts import canonical_request_hash


InitializationStepKey = Literal[
    "novel_profile",
    "core_factions",
    "faction_relations",
    "protagonist",
    "core_characters",
    "character_bindings",
    "character_relations",
]
InitializationStepState = Literal["not_started", "in_progress", "ready", "blocked"]


class InitializationStepV1(StrictResponseModel):
    """一个由正式事实重建的初始化步骤状态。"""

    key: InitializationStepKey
    state: InitializationStepState
    count: int = Field(ge=0)
    blockers: list[str] = Field(default_factory=list)
    href: str = Field(pattern=r"^\?workspace=[a-z-]+(?:&view=[a-z-]+)?$")


STEP_HREFS: dict[InitializationStepKey, str] = {
    "novel_profile": "?workspace=novel-info",
    "core_factions": "?workspace=faction-cards&view=profiles",
    "faction_relations": "?workspace=faction-cards&view=relations",
    "protagonist": "?workspace=character-cards&view=profiles",
    "core_characters": "?workspace=character-cards&view=profiles",
    "character_bindings": "?workspace=character-cards&view=bindings",
    "character_relations": "?workspace=character-cards&view=relations",
}


class InitializationReadinessResponseV1(StrictResponseModel):
    """小说全书初始化门禁的只读公开响应。"""

    novel_id: ObjectIdString
    steps: list[InitializationStepV1] = Field(min_length=7, max_length=7)
    ready_for_world_and_volume: bool

    @model_validator(mode="after")
    def require_fixed_steps(self) -> "InitializationReadinessResponseV1":
        """固定七步顺序和服务端 href，防止响应注入任意导航目标。

        Args:
            无。

        Returns:
            已确认只含固定步骤和白名单 href 的响应。
        """
        if tuple(step.key for step in self.steps) != tuple(STEP_HREFS):
            raise ValueError("初始化步骤必须按固定七步顺序返回")
        if any(step.href != STEP_HREFS[step.key] for step in self.steps):
            raise ValueError("初始化步骤 href 必须使用服务端固定映射")
        return self


def _is_usable(document: dict[str, Any]) -> bool:
    """判断关系或绑定是否属于当前有效正式事实。"""
    return document.get("is_deleted") is not True and document.get("is_active") is True


def _optional_state(
    *,
    active_count: int,
    historical_count: int,
) -> InitializationStepState:
    """按正式记录存在性计算建议步骤状态。"""
    if active_count > 0:
        return "ready"
    return "in_progress" if historical_count > 0 else "not_started"


class InitializationReadinessService:
    """读取稳定投影并生成不持久化的阶段 1 导航状态。"""

    @staticmethod
    async def _read_consistent_projection(novel_id: str) -> dict[str, Any]:
        """按部署能力读取 snapshot，standalone 则执行双读签名核对。

        Args:
            novel_id: 小说 ObjectId 字符串。

        Returns:
            同一小说的稳定正式事实投影。

        Raises:
            DomainApiError: 小说不存在、读取漂移、数据库失败或超时时抛出。
        """
        try:
            if await supports_mongo_transactions():
                async with get_client().start_session() as session:
                    async with await session.start_transaction(
                        read_concern=ReadConcern("snapshot")
                    ):
                        projection = await initialization_readiness_repo.read_projection(
                            novel_id,
                            session=session,
                        )
                if projection is None:
                    raise DomainApiError(
                        "NOVEL_NOT_FOUND",
                        "小说不存在或已进入回收站",
                        status_code=404,
                    )
                return projection

            for _attempt in range(2):
                first = await initialization_readiness_repo.read_projection(novel_id)
                second = await initialization_readiness_repo.read_projection(novel_id)
                if first is None and second is None:
                    raise DomainApiError(
                        "NOVEL_NOT_FOUND",
                        "小说不存在或已进入回收站",
                        status_code=404,
                    )
                if first is None or second is None:
                    continue
                if canonical_request_hash(first) == canonical_request_hash(second):
                    return second
            raise DomainApiError(
                "READINESS_SNAPSHOT_UNSTABLE",
                "初始化事实正在变化，请稍后刷新",
                status_code=503,
            )
        except DomainApiError:
            raise
        except (ExecutionTimeout, NetworkTimeout, TimeoutError) as exc:
            raise DomainApiError(
                "READINESS_TIMEOUT",
                "初始化状态读取超时，请重试",
                status_code=504,
            ) from exc
        except PyMongoError as exc:
            raise DomainApiError(
                "READINESS_DEPENDENCY_UNAVAILABLE",
                "初始化状态暂时不可用，请重试",
                status_code=503,
            ) from exc

    @staticmethod
    async def get_readiness(novel_id: str) -> InitializationReadinessResponseV1:
        """计算指定小说的初始化步骤和下一阶段硬门禁。

        Args:
            novel_id: 小说 ObjectId 字符串。

        Returns:
            七个固定步骤及 ``ready_for_world_and_volume``。
        """
        projection = await InitializationReadinessService._read_consistent_projection(
            novel_id
        )
        factions = list(projection.get("factions") or [])
        faction_relations = list(projection.get("faction_relations") or [])
        characters = list(projection.get("characters") or [])
        character_bindings = list(projection.get("character_bindings") or [])
        character_relations = list(projection.get("character_relations") or [])

        active_core_factions = [
            item
            for item in factions
            if item.get("is_deleted") is not True
            and item.get("level_type") == "core"
            and item.get("active_status") == "active"
        ]
        active_characters = [
            item
            for item in characters
            if item.get("is_deleted") is not True and item.get("status") == "active"
        ]
        active_protagonists = [
            item for item in active_characters if item.get("role_type") == "protagonist"
        ]
        active_core_characters = [
            item for item in active_characters if item.get("is_core_character") is True
        ]
        historical_core_characters = [
            item for item in characters if item.get("is_core_character") is True
        ]
        active_faction_relations = [item for item in faction_relations if _is_usable(item)]
        active_bindings = [item for item in character_bindings if _is_usable(item)]
        active_character_relations = [item for item in character_relations if _is_usable(item)]

        faction_ready = bool(active_core_factions)
        protagonist_ready = bool(active_protagonists)
        steps = [
            InitializationStepV1(
                key="novel_profile",
                state="ready",
                count=1,
                href=STEP_HREFS["novel_profile"],
            ),
            InitializationStepV1(
                key="core_factions",
                state="ready" if faction_ready else "blocked",
                count=len(active_core_factions),
                blockers=[] if faction_ready else ["CORE_FACTION_REQUIRED"],
                href=STEP_HREFS["core_factions"],
            ),
            InitializationStepV1(
                key="faction_relations",
                state=_optional_state(
                    active_count=len(active_faction_relations),
                    historical_count=len(faction_relations),
                ),
                count=len(active_faction_relations),
                href=STEP_HREFS["faction_relations"],
            ),
            InitializationStepV1(
                key="protagonist",
                state="ready" if protagonist_ready else "blocked",
                count=len(active_protagonists),
                blockers=[] if protagonist_ready else ["PROTAGONIST_REQUIRED"],
                href=STEP_HREFS["protagonist"],
            ),
            InitializationStepV1(
                key="core_characters",
                state=_optional_state(
                    active_count=len(active_core_characters),
                    historical_count=len(historical_core_characters),
                ),
                count=len(active_core_characters),
                href=STEP_HREFS["core_characters"],
            ),
            InitializationStepV1(
                key="character_bindings",
                state=_optional_state(
                    active_count=len(active_bindings),
                    historical_count=len(character_bindings),
                ),
                count=len(active_bindings),
                href=STEP_HREFS["character_bindings"],
            ),
            InitializationStepV1(
                key="character_relations",
                state=_optional_state(
                    active_count=len(active_character_relations),
                    historical_count=len(character_relations),
                ),
                count=len(active_character_relations),
                href=STEP_HREFS["character_relations"],
            ),
        ]
        return InitializationReadinessResponseV1(
            novel_id=str(projection["novel_id"]),
            steps=steps,
            ready_for_world_and_volume=faction_ready and protagonist_ready,
        )


__all__ = [
    "InitializationReadinessResponseV1",
    "InitializationReadinessService",
    "InitializationStepV1",
    "STEP_HREFS",
]
