"""正式世界规则领域服务。"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.client_session import AsyncClientSession

from backend.api.error_protocol import DomainApiError
from backend.db.errors import (
    DuplicateKeyError,
    IdempotencyConflictError,
    InvalidIdError,
    NotFoundError,
)
from backend.db.endpoint_guard import (
    DependencyGuardContribution,
    touch_dependency_endpoint_guards,
)
from backend.db.repositories.character_repository import character_repo
from backend.db.repositories.faction_relation_repository import faction_relation_repo
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.id_sequence_repository import id_sequence_repo
from backend.db.repositories.location_repository import location_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.db.repositories.world_rule_repository import (
    normalize_world_rule_category,
    normalize_world_rule_name,
    world_rule_repo,
)
from backend.db.repositories.confirmation_receipt_repository import (
    world_rule_confirmation_receipt_repo,
)
from backend.db.transaction import run_mongo_write_unit
from backend.db.utils import get_utc_now
from backend.db.write_contracts import (
    build_idempotency_fingerprint,
    resolve_idempotent_replay,
    validate_expected_version,
)
from backend.llm.schemas.world_rule_pydantic import (
    CORE_WORLD_RULES_RESULT_SCHEMA_ID,
    CORE_WORLD_RULES_RESULT_SCHEMA_VERSION,
    CoreWorldRulesConfirmV1,
)
from backend.llm.schemas.character_pydantic import FACTION_BUSINESS_ID_PATTERN
from backend.services.llm.candidate_contract import require_current_candidate_basis
from backend.services.llm.world_rule_generation_contract import (
    CORE_WORLD_RULE_GENERATION_STEP,
    CORE_WORLD_RULE_WORKFLOW,
    compute_core_world_rules_input_fingerprint,
)
from backend.services.novel.location_service import (
    _acquire_novel_write_lock,
    _release_novel_write_lock,
)
from backend.services.llm.world_rule_generation_service import (
    WorldRuleGenerationService,
)
from backend.services.novel.errors import GenerationDomainError


logger = logging.getLogger(__name__)

WORLD_RULE_FIELDS: tuple[str, ...] = (
    "name",
    "category",
    "statement",
    "scope_type",
    "scope_entity_ids",
    "enforcement",
    "exceptions",
    "costs_and_consequences",
    "priority",
    "status",
    "tags",
)

WORLD_RULE_SCOPE_TYPES = {"global", "faction", "character", "location"}
WORLD_RULE_STATUSES = {"draft", "active", "retired"}
RULE_ID_RE = re.compile(r"^rule_[0-9]{6,}$")
FACTION_ID_RE = re.compile(FACTION_BUSINESS_ID_PATTERN)
CHARACTER_ID_RE = re.compile(r"^char_[0-9]{6,}$")
LOCATION_ID_RE = re.compile(r"^loc_[0-9]{6,}$")

WORLD_RULE_RECEIPT_FIELDS: tuple[str, ...] = (
    "rule_id",
    "novel_id",
    "name",
    "category",
    "statement",
    "scope_type",
    "scope_entity_ids",
    "enforcement",
    "exceptions",
    "costs_and_consequences",
    "priority",
    "status",
    "tags",
    "order_index",
    "version",
    "is_deleted",
    "deleted_at",
    "created_at",
    "updated_at",
)


@dataclass(frozen=True, slots=True)
class _AppliedRuleChange:
    """记录 standalone 写入前后状态，供精确反向补偿。"""

    before: dict[str, Any]
    after: dict[str, Any]


def _normalize_rule_content(
    data: Mapping[str, Any],
    *,
    partial: bool,
) -> dict[str, Any]:
    """规范化并校验世界规则正式内容。

    Args:
        data: Router 或后续候选确认流程提交的字段映射。
        partial: 是否按更新语义只处理显式字段。

    Returns:
        只包含正式白名单字段的规范化字典。
    """
    unknown = sorted(set(data) - set(WORLD_RULE_FIELDS))
    if unknown:
        raise DomainApiError(
            "WORLD_RULE_VALIDATION_FAILED",
            "Quy tắc thế giới chứa các trường chưa được đăng ký",
            status_code=422,
            details={"fields": unknown},
        )

    source = dict(data)
    if not partial:
        missing = [
            field for field in ("name", "category", "statement") if field not in source
        ]
        if missing:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "Quy tắc thế giới thiếu các trường bắt buộc",
                status_code=422,
                field_errors={field: "字段必填" for field in missing},
            )
        source.setdefault("scope_type", "global")
        source.setdefault("scope_entity_ids", [])
        source.setdefault("enforcement", "")
        source.setdefault("exceptions", [])
        source.setdefault("costs_and_consequences", [])
        source.setdefault("priority", 0)
        source.setdefault("status", "draft")
        source.setdefault("tags", [])
    elif not source:
        raise DomainApiError(
            "WORLD_RULE_VALIDATION_FAILED",
            "Cập nhật quy tắc thế giới cần ít nhất một trường có thể sửa",
            status_code=422,
        )

    normalized: dict[str, Any] = {}
    if "name" in source:
        try:
            normalized["name"], normalized["normalized_name"] = (
                normalize_world_rule_name(source["name"])
            )
        except (TypeError, ValueError) as exc:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                str(exc),
                status_code=422,
                field_errors={"name": str(exc)},
            ) from exc
    if "category" in source:
        try:
            normalized["category"] = normalize_world_rule_category(source["category"])
        except (TypeError, ValueError) as exc:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                str(exc),
                status_code=422,
                field_errors={"category": str(exc)},
            ) from exc
    if "statement" in source:
        statement = source["statement"]
        if not isinstance(statement, str):
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "Nội dung quy tắc phải là chuỗi",
                status_code=422,
                field_errors={"statement": "必须是字符串"},
            )
        statement = unicodedata.normalize("NFKC", statement).strip()
        if not statement or len(statement) > 2000:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "Phát biểu quy tắc phải dài 1 đến 2000 ký tự",
                status_code=422,
                field_errors={"statement": "长度必须为 1 到 2000 个字符"},
            )
        normalized["statement"] = statement
    if "scope_type" in source:
        scope_type = source["scope_type"]
        if not isinstance(scope_type, str) or scope_type not in WORLD_RULE_SCOPE_TYPES:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "Phạm vi quy tắc của giai đoạn hiện tại chỉ hỗ trợ global, faction hoặc character",
                status_code=422,
                field_errors={"scope_type": "不支持的作用域类型"},
            )
        normalized["scope_type"] = scope_type
    if "scope_entity_ids" in source:
        entity_ids = source["scope_entity_ids"]
        if not isinstance(entity_ids, list) or len(entity_ids) > 100:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "scope_entity_ids phải là mảng không quá 100 phần tử",
                status_code=422,
                field_errors={"scope_entity_ids": "必须是不超过 100 项的数组"},
            )
        cleaned_ids: list[str] = []
        for index, entity_id in enumerate(entity_ids):
            if not isinstance(entity_id, str) or not entity_id.strip():
                raise DomainApiError(
                    "WORLD_RULE_VALIDATION_FAILED",
                    "ID thực thể của phạm vi phải là chuỗi không rỗng",
                    status_code=422,
                    field_errors={f"scope_entity_ids.{index}": "必须是非空字符串"},
                )
            cleaned_ids.append(entity_id.strip())
        if len(cleaned_ids) != len(set(cleaned_ids)):
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "scope_entity_ids không được chứa ID trùng lặp",
                status_code=422,
                field_errors={"scope_entity_ids": "不能包含重复 ID"},
            )
        normalized["scope_entity_ids"] = cleaned_ids
    if "enforcement" in source:
        enforcement = source["enforcement"]
        if not isinstance(enforcement, str) or len(enforcement.strip()) > 1000:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "Cách thức thực hiện phải là chuỗi không quá 1000 ký tự",
                status_code=422,
                field_errors={"enforcement": "最多 1000 个字符"},
            )
        normalized["enforcement"] = enforcement.strip()
    if "exceptions" in source:
        exceptions = source["exceptions"]
        if not isinstance(exceptions, list) or len(exceptions) > 20:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "exceptions phải là mảng không quá 20 phần tử",
                status_code=422,
                field_errors={"exceptions": "必须是不超过 20 项的数组"},
            )
        normalized_exceptions: list[dict[str, str]] = []
        for index, item in enumerate(exceptions):
            if not isinstance(item, Mapping) or set(item) != {"condition", "effect"}:
                raise DomainApiError(
                    "WORLD_RULE_VALIDATION_FAILED",
                    "Mỗi ngoại lệ chỉ được gồm condition và effect",
                    status_code=422,
                    field_errors={f"exceptions.{index}": "字段必须严格为 condition/effect"},
                )
            condition = item["condition"]
            effect = item["effect"]
            if (
                not isinstance(condition, str)
                or not isinstance(effect, str)
                or not condition.strip()
                or not effect.strip()
                or len(condition.strip()) > 500
                or len(effect.strip()) > 500
            ):
                raise DomainApiError(
                    "WORLD_RULE_VALIDATION_FAILED",
                    "condition và effect của mỗi ngoại lệ phải dài 1 đến 500 ký tự",
                    status_code=422,
                    field_errors={f"exceptions.{index}": "condition/effect 长度必须为 1 到 500"},
                )
            normalized_exceptions.append(
                {"condition": condition.strip(), "effect": effect.strip()}
            )
        normalized["exceptions"] = normalized_exceptions
    if "costs_and_consequences" in source:
        costs = source["costs_and_consequences"]
        if not isinstance(costs, list) or len(costs) > 20:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "costs_and_consequences phải là mảng không quá 20 phần tử",
                status_code=422,
                field_errors={"costs_and_consequences": "必须是不超过 20 项的数组"},
            )
        normalized_costs: list[str] = []
        for index, item in enumerate(costs):
            if not isinstance(item, str) or not item.strip() or len(item.strip()) > 500:
                raise DomainApiError(
                    "WORLD_RULE_VALIDATION_FAILED",
                    "Mỗi mục chi phí và hệ quả phải dài 1 đến 500 ký tự",
                    status_code=422,
                    field_errors={f"costs_and_consequences.{index}": "长度必须为 1 到 500"},
                )
            normalized_costs.append(item.strip())
        normalized["costs_and_consequences"] = normalized_costs
    if "priority" in source:
        priority = source["priority"]
        if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 100:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "Độ ưu tiên quy tắc phải là số nguyên từ 0 đến 100",
                status_code=422,
                field_errors={"priority": "必须为 0 到 100 的整数"},
            )
        normalized["priority"] = priority
    if "status" in source:
        status = source["status"]
        if not isinstance(status, str) or status not in WORLD_RULE_STATUSES:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "Trạng thái quy tắc phải là draft, active hoặc retired",
                status_code=422,
                field_errors={"status": "不支持的规则状态"},
            )
        normalized["status"] = status
    if "tags" in source:
        tags = source["tags"]
        if not isinstance(tags, list) or len(tags) > 20:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "tags phải là mảng không quá 20 phần tử",
                status_code=422,
                field_errors={"tags": "必须是不超过 20 项的数组"},
            )
        normalized_tags: list[str] = []
        for index, tag in enumerate(tags):
            if not isinstance(tag, str) or not tag.strip():
                raise DomainApiError(
                    "WORLD_RULE_VALIDATION_FAILED",
                    "Nhãn phải là chuỗi không trống",
                    status_code=422,
                    field_errors={f"tags.{index}": "必须是非空字符串"},
                )
            normalized_tags.append(tag.strip())
        normalized["tags"] = normalized_tags
    return normalized


class WorldRuleService:
    """世界规则正式事实的唯一业务写入口。"""

    @staticmethod
    async def _get_novel(
        novel_id: str,
        *,
        session: AsyncClientSession | None,
    ) -> dict[str, Any]:
        """读取活动小说并统一小说作用域错误。"""
        try:
            return await novel_repo.get_novel_by_id(novel_id, session=session)
        except InvalidIdError as exc:
            raise DomainApiError(
                "INVALID_OBJECT_ID",
                "novel_id không phải ObjectId hợp lệ",
                status_code=422,
                field_errors={"novel_id": "不是有效 ObjectId"},
            ) from exc
        except NotFoundError as exc:
            raise DomainApiError(
                "NOVEL_NOT_FOUND",
                str(exc),
                status_code=404,
            ) from exc

    @staticmethod
    async def _validate_scope(
        novel_id: str,
        scope_type: str,
        scope_entity_ids: Sequence[str],
        *,
        session: AsyncClientSession | None,
    ) -> list[dict[str, Any]]:
        """验证作用域组合、ID 类型及同书活动实体。

        Args:
            novel_id: 小说 ObjectId 字符串。
            scope_type: global、faction、character 或 location。
            scope_entity_ids: 需要解析的稳定实体 ID。
            session: 可选 MongoDB 会话。

        Returns:
            当前非 global 作用域的可用端点文档；global 返回空列表。
        """
        ids = list(scope_entity_ids)
        if scope_type == "global":
            if ids:
                raise DomainApiError(
                    "WORLD_RULE_SCOPE_INVALID",
                    "Phạm vi global không được mang theo ID thực thể",
                    status_code=422,
                    field_errors={"scope_entity_ids": "global 作用域必须为空"},
                )
            return []
        if scope_type not in WORLD_RULE_SCOPE_TYPES:
            raise DomainApiError(
                "WORLD_RULE_SCOPE_INVALID",
                "Phạm vi quy tắc của giai đoạn hiện tại chỉ hỗ trợ global, faction, character hoặc location",
                status_code=422,
            )
        if not ids:
            raise DomainApiError(
                "WORLD_RULE_SCOPE_INVALID",
                f"{scope_type} phạm vi cần ít nhất một ID thực thể",
                status_code=422,
                field_errors={"scope_entity_ids": "至少需要一个实体 ID"},
            )
        pattern = {
            "faction": FACTION_ID_RE,
            "character": CHARACTER_ID_RE,
            "location": LOCATION_ID_RE,
        }[scope_type]
        entities: list[dict[str, Any]] = []
        for entity_id in ids:
            if pattern.fullmatch(entity_id) is None:
                raise DomainApiError(
                    "WORLD_RULE_SCOPE_INVALID",
                    f"{entity_id} không phải là ID bền của phạm vi {scope_type} tương ứng",
                    status_code=422,
                    field_errors={"scope_entity_ids": "实体 ID 类型与作用域不匹配"},
                    details={"entity_id": entity_id, "scope_type": scope_type},
                )
            try:
                if scope_type == "faction":
                    entity = await faction_repo.get_faction(
                        novel_id,
                        entity_id,
                        session=session,
                    )
                    is_available = entity.get("active_status") == "active"
                elif scope_type == "character":
                    entity = await character_repo.get_character(
                        novel_id,
                        entity_id,
                        session=session,
                    )
                    is_available = entity.get("status") == "active"
                else:
                    entity = await location_repo.get_location(
                        novel_id,
                        entity_id,
                        session=session,
                    )
                    is_available = (
                        entity.get("status") == "active"
                        and entity.get("location_order_pending_token") is None
                    )
            except (NotFoundError, InvalidIdError) as exc:
                raise DomainApiError(
                    "SCOPE_ENTITY_NOT_FOUND",
                    f"Thực thể phạm vi {entity_id} không tồn tại, đã bị xóa hoặc không thuộc tiểu thuyết hiện tại",
                    status_code=404,
                    details={"entity_id": entity_id, "scope_type": scope_type},
                ) from exc
            if not is_available:
                raise DomainApiError(
                    "SCOPE_ENTITY_NOT_FOUND",
                    f"Thực thể phạm vi {entity_id} hiện không khả dụng",
                    status_code=404,
                    details={"entity_id": entity_id, "scope_type": scope_type},
                )
            entities.append(entity)
        return entities

    @staticmethod
    async def _touch_location_scope(
        novel_id: str,
        entities: Sequence[Mapping[str, Any]],
        *,
        session: AsyncClientSession | None,
    ) -> list[DependencyGuardContribution]:
        """推进地点作用域端点护栏，阻断并发停用或删除。

        Args:
            novel_id: 当前规则所属小说 ObjectId 字符串。
            entities: `_validate_scope` 返回的地点预镜像。
            session: 可选 MongoDB 会话。

        Returns:
            成功写入的单调 guard 贡献；这些内部修订不会因业务补偿而减回。
        """
        if not entities:
            return []
        novel_lock = await _acquire_novel_write_lock(
            novel_id,
            session=session,
        )
        try:
            try:
                return await touch_dependency_endpoint_guards(
                    location_repo.collection,
                    [
                        {
                            "_id": entity["_id"],
                            "novel_id": entity["novel_id"],
                            "location_id": entity["location_id"],
                            "version": entity["version"],
                            "status": "active",
                            "is_deleted": False,
                            "location_order_pending_token": None,
                        }
                        for entity in entities
                    ],
                    session=session,
                    rollback_on_error=False,
                )
            except DuplicateKeyError as exc:
                raise DomainApiError(
                    "WORLD_RULE_SCOPE_CONFLICT",
                    "Phạm vi địa điểm đã thay đổi trong lúc ghi quy tắc, hãy làm mới rồi thử lại",
                    status_code=409,
                ) from exc
        finally:
            await _release_novel_write_lock(
                novel_id,
                novel_lock,
                session=session,
            )

    @staticmethod
    async def _get_rule(
        novel_id: str,
        rule_id: str,
        *,
        include_deleted: bool,
        session: AsyncClientSession | None,
    ) -> dict[str, Any]:
        """读取规则并把跨小说、缺失和删除统一为 404。"""
        if RULE_ID_RE.fullmatch(rule_id) is None:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "Định dạng rule_id không hợp lệ",
                status_code=422,
                field_errors={"rule_id": "必须匹配 rule_[0-9]{6,}"},
            )
        try:
            if include_deleted:
                return await world_rule_repo.get_deleted_world_rule(
                    novel_id,
                    rule_id,
                    session=session,
                )
            return await world_rule_repo.get_world_rule(
                novel_id,
                rule_id,
                session=session,
            )
        except InvalidIdError as exc:
            raise DomainApiError(
                "INVALID_OBJECT_ID",
                "novel_id không phải ObjectId hợp lệ",
                status_code=422,
            ) from exc
        except NotFoundError as exc:
            raise DomainApiError(
                "WORLD_RULE_NOT_FOUND",
                str(exc),
                status_code=404,
            ) from exc

    @staticmethod
    def _check_version(rule: Mapping[str, Any], expected_version: int) -> None:
        """在多文档写入前验证一条规则的公开版本。"""
        expected = validate_expected_version(expected_version)
        actual = int(rule["version"])
        if actual != expected:
            raise DomainApiError(
                "WORLD_RULE_VERSION_CONFLICT",
                f"Quy tắc {rule.get('rule_id')} xung đột phiên bản",
                status_code=409,
                details={"expected_version": expected, "actual_version": actual},
            )

    @staticmethod
    async def _ensure_name_available(
        novel_id: str,
        normalized_name: str,
        *,
        exclude_rule_id: str | None,
        session: AsyncClientSession | None,
    ) -> None:
        """保证规范名未被另一条活动规则占用。"""
        existing = await world_rule_repo.find_active_by_normalized_name(
            novel_id,
            normalized_name,
            session=session,
        )
        if existing is not None and existing.get("rule_id") != exclude_rule_id:
            raise DomainApiError(
                "WORLD_RULE_NAME_CONFLICT",
                "Đã tồn tại quy tắc đang hoạt động cùng tên trong cùng một tiểu thuyết",
                status_code=409,
                details={"existing_rule_id": existing.get("rule_id")},
            )

    @staticmethod
    async def _apply_change(
        snapshot: Mapping[str, Any],
        update_fields: Mapping[str, Any],
        *,
        increment_version: bool,
        applied: list[_AppliedRuleChange],
        session: AsyncClientSession | None,
    ) -> dict[str, Any]:
        """执行一次精确规则写入并登记 standalone 补偿状态。"""
        try:
            updated = await world_rule_repo.update_from_snapshot(
                snapshot,
                update_fields,
                increment_version=increment_version,
                session=session,
            )
        except DuplicateKeyError as exc:
            raise DomainApiError(
                "WORLD_RULE_ORDER_CONFLICT",
                "Xung đột tên đang hoạt động hoặc thứ tự phân loại của quy tắc thế giới",
                status_code=409,
            ) from exc
        if updated is None:
            raise DomainApiError(
                "WORLD_RULE_VERSION_CONFLICT",
                f"Quy tắc {snapshot.get('rule_id')} đã bị yêu cầu khác sửa đổi",
                status_code=409,
            )
        applied.append(_AppliedRuleChange(dict(snapshot), dict(updated)))
        return updated

    @staticmethod
    async def _compensate_changes(applied: Sequence[_AppliedRuleChange]) -> None:
        """按写入逆序精确恢复 standalone 多文档修改。"""
        for change in reversed(list(applied)):
            await world_rule_repo.restore_snapshot_exact(change.before, change.after)

    @staticmethod
    async def create_world_rule(novel_id: str, data: Mapping[str, Any], *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """幂等创建一条正式世界规则。

        Args:
            novel_id: 小说 ObjectId 字符串。
            data: 世界规则创建白名单字段。
            idempotency_key: 必填的人工创建幂等键。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            新建或同键重放的完整规则文档。
        """
        content = _normalize_rule_content(data, partial=False)
        try:
            fingerprint = build_idempotency_fingerprint(
                idempotency_key,
                {"novel_id": novel_id, "world_rule": content},
            )
        except (TypeError, ValueError) as exc:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                str(exc),
                status_code=422,
                field_errors={"Idempotency-Key": str(exc)},
            ) from exc
        document_id = ObjectId()

        async def _create(session: AsyncClientSession | None) -> dict[str, Any]:
            await WorldRuleService._get_novel(novel_id, session=session)
            scope_entities = await WorldRuleService._validate_scope(
                novel_id,
                content["scope_type"],
                content["scope_entity_ids"],
                session=session,
            )
            existing = await world_rule_repo.find_by_creation_idempotency(
                novel_id,
                fingerprint.key_hash,
                session=session,
            )
            try:
                replay = resolve_idempotent_replay(
                    existing,
                    fingerprint.request_hash,
                    label="世界规则创建",
                )
            except IdempotencyConflictError as exc:
                raise DomainApiError(
                    "IDEMPOTENCY_KEY_REUSED",
                    str(exc),
                    status_code=409,
                ) from exc
            if replay is not None:
                return replay

            await WorldRuleService._ensure_name_available(
                novel_id,
                content["normalized_name"],
                exclude_rule_id=None,
                session=session,
            )
            rule_id = (
                await id_sequence_repo.allocate_many(
                    novel_id,
                    "world_rule",
                    "rule",
                    1,
                    session=session,
                )
            )[0]
            order_index = await world_rule_repo.get_max_order_index(
                novel_id,
                content["category"],
                session=session,
            ) + 1
            document = {
                **content,
                "_id": document_id,
                "novel_id": novel_id,
                "rule_id": rule_id,
                "order_index": order_index,
                **fingerprint.as_creation_fields(),
            }
            created: dict[str, Any] | None = None
            try:
                try:
                    created = await world_rule_repo.create_world_rule(
                        document,
                        session=session,
                    )
                except Exception:
                    if session is not None:
                        raise
                    current = await world_rule_repo.collection.find_one(
                        {"_id": document_id}
                    )
                    if (
                        current is None
                        or current.get("rule_id") != rule_id
                        or current.get("creation_idempotency_key_hash")
                        != fingerprint.key_hash
                        or current.get("creation_request_hash")
                        != fingerprint.request_hash
                        or int(current.get("version", 0)) != 1
                        or any(current.get(field) != value for field, value in content.items())
                    ):
                        raise
                    created = current
                if content["scope_type"] == "location":
                    await WorldRuleService._touch_location_scope(
                        novel_id,
                        scope_entities,
                        session=session,
                    )
                return created
            except Exception:
                if session is None and created is not None:
                    await world_rule_repo.delete_manual_created_exact(
                        document_id,
                        key_hash=fingerprint.key_hash,
                        request_hash=fingerprint.request_hash,
                    )
                    if await world_rule_repo.collection.count_documents(
                        {"_id": document_id}
                    ):
                        raise DomainApiError(
                            "WORLD_RULE_COMPENSATION_FAILED",
                            "Tạo quy tắc phạm vi địa điểm thất bại và bù đắp quy tắc chưa hoàn tất đầy đủ",
                            status_code=503,
                        )
                raise

        if session is not None:
            return await _create(session)

        try:
            return await run_mongo_write_unit(_create, "create_world_rule")
        except DuplicateKeyError as exc:
            existing = await world_rule_repo.find_by_creation_idempotency(
                novel_id,
                fingerprint.key_hash,
            )
            try:
                replay = resolve_idempotent_replay(
                    existing,
                    fingerprint.request_hash,
                    label="世界规则创建",
                )
            except IdempotencyConflictError as conflict:
                raise DomainApiError(
                    "IDEMPOTENCY_KEY_REUSED",
                    str(conflict),
                    status_code=409,
                ) from conflict
            if replay is not None:
                return replay
            same_name = await world_rule_repo.find_active_by_normalized_name(
                novel_id,
                content["normalized_name"],
            )
            if same_name is not None:
                raise DomainApiError(
                    "WORLD_RULE_NAME_CONFLICT",
                    "Đã tồn tại quy tắc đang hoạt động cùng tên trong cùng một tiểu thuyết",
                    status_code=409,
                    details={"existing_rule_id": same_name.get("rule_id")},
                ) from exc
            raise DomainApiError(
                "WORLD_RULE_ORDER_CONFLICT",
                "Thứ tự phân loại khi tạo quy tắc xảy ra xung đột đồng thời, hãy thử lại",
                status_code=409,
            ) from exc

    @staticmethod
    async def bulk_create_core_world_rules(novel_id: str, data: CoreWorldRulesConfirmV1 | Mapping[str, Any], *, idempotency_key: str, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """幂等确认一批核心世界规则候选并返回正式 ID 映射。

        Args:
            novel_id: 小说 ObjectId 字符串。
            data: 已编辑候选、不透明 basis 与精确来源版本。
            idempotency_key: 本次批量确认的 Idempotency-Key。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            完整 candidate_ref 到 rule_id 映射和顺序稳定的正式规则。
        """
        novel_id = novel_id.lower()
        request = CoreWorldRulesConfirmV1.model_validate(
            data.model_dump(mode="json")
            if isinstance(data, CoreWorldRulesConfirmV1)
            else dict(data)
        )
        source = request.model_dump(mode="json")
        candidates = source["candidates"]
        candidate_refs = [str(item["candidate_ref"]) for item in candidates]
        normalized_by_ref: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            content = {
                key: value
                for key, value in candidate.items()
                if key != "candidate_ref"
            }
            # AI 核心规则经用户确认后直接成为可供后续规划读取的活动规则。
            content["status"] = "active"
            normalized_by_ref[str(candidate["candidate_ref"])] = (
                _normalize_rule_content(content, partial=False)
            )

        normalized_names = [
            normalized_by_ref[ref]["normalized_name"] for ref in candidate_refs
        ]
        if len(normalized_names) != len(set(normalized_names)):
            raise DomainApiError(
                "WORLD_RULE_NAME_CONFLICT",
                "Tên ứng viên được xác nhận không được trùng sau chuẩn hóa",
                status_code=409,
            )
        normalized_statements = [
            re.sub(
                r"\s+",
                " ",
                unicodedata.normalize(
                    "NFKC",
                    str(normalized_by_ref[ref]["statement"]),
                ).strip(),
            ).casefold()
            for ref in candidate_refs
        ]
        if len(normalized_statements) != len(set(normalized_statements)):
            raise DomainApiError(
                "WORLD_RULE_SEMANTIC_CONFLICT",
                "Phát biểu quy tắc ứng viên được xác nhận không được trùng sau chuẩn hóa",
                status_code=409,
            )

        try:
            fingerprint = build_idempotency_fingerprint(
                idempotency_key,
                {"novel_id": novel_id, "request": source},
            )
        except (TypeError, ValueError) as exc:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                str(exc),
                status_code=422,
                field_errors={"Idempotency-Key": str(exc)},
            ) from exc

        def _receipt_result(receipt: Mapping[str, Any]) -> dict[str, Any]:
            """从不可变领域回执复制首次确认的公开响应。"""
            world_rules = deepcopy(receipt["world_rules_snapshot"])
            for item in world_rules:
                for field in ("deleted_at", "created_at", "updated_at"):
                    value = item[field]
                    if isinstance(value, datetime):
                        if value.tzinfo is None:
                            value = value.replace(tzinfo=UTC)
                        else:
                            value = value.astimezone(UTC)
                        # BSON 精度为毫秒；首次响应与数据库回放使用同一公开时间值。
                        item[field] = value.replace(
                            microsecond=(value.microsecond // 1000) * 1000
                        )
            return {
                "candidate_ref_map": deepcopy(receipt["candidate_ref_map"]),
                "world_rules": world_rules,
            }

        async def _load_receipt(
            session: AsyncClientSession | None,
        ) -> dict[str, Any] | None:
            """读取不可变领域回执并校验同键请求哈希。"""
            receipt = await world_rule_confirmation_receipt_repo.find_receipt(
                novel_id,
                fingerprint.key_hash,
                session=session,
            )
            if receipt is None:
                return None
            if receipt.get("request_hash") != fingerprint.request_hash:
                raise DomainApiError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "Cùng Idempotency-Key đã được dùng cho yêu cầu xác nhận quy tắc thế giới cốt lõi khác",
                    status_code=409,
                )
            return receipt

        async def _load_inflight_replay(
            session: AsyncClientSession | None,
        ) -> dict[str, Any] | None:
            """仅为同键同载荷的 standalone 在途赢家等待成功回执。"""
            marker = await world_rule_repo.find_by_creation_idempotency(
                novel_id,
                fingerprint.key_hash,
                session=session,
            )
            if marker is None:
                return None
            if marker.get("creation_request_hash") != fingerprint.request_hash:
                raise DomainApiError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "Cùng Idempotency-Key đã được dùng cho yêu cầu xác nhận quy tắc thế giới cốt lõi khác",
                    status_code=409,
                )
            if session is None:
                # 正式规则与不可变回执之间仅 standalone 存在短暂可见窗口。
                for _ in range(20):
                    await asyncio.sleep(0.05)
                    receipt = await _load_receipt(None)
                    if receipt is not None:
                        return _receipt_result(receipt)
            raise DomainApiError(
                "WORLD_RULE_BATCH_CONFLICT",
                "Yêu cầu cùng khóa của xác nhận quy tắc thế giới cốt lõi vẫn đang được xử lý",
                status_code=409,
            )

        async def _validate_basis(
            session: AsyncClientSession | None,
        ) -> dict[str, Any]:
            """重读来源、活动集合和当前执行配置并复核候选 basis。"""
            basis = request.basis
            generation_input = basis.generation_input
            if basis.novel_id != novel_id or generation_input.novel_id != novel_id:
                raise DomainApiError(
                    "CANDIDATE_SOURCE_NOT_FOUND",
                    "Ứng viên quy tắc thế giới cốt lõi không thuộc tiểu thuyết hiện tại",
                    status_code=404,
                )
            if (
                basis.workflow != CORE_WORLD_RULE_WORKFLOW
                or basis.step != CORE_WORLD_RULE_GENERATION_STEP
                or basis.schema_id != CORE_WORLD_RULES_RESULT_SCHEMA_ID
                or basis.schema_version != CORE_WORLD_RULES_RESULT_SCHEMA_VERSION
            ):
                raise DomainApiError(
                    "CANDIDATE_BASIS_CONFLICT",
                    "Hợp đồng của ứng viên quy tắc thế giới nòng cốt đã thay đổi",
                    status_code=409,
                )

            try:
                current_context = await WorldRuleGenerationService.load_context(
                    generation_input,
                    session=session,
                    require_readiness=False,
                )
            except (NotFoundError, InvalidIdError) as exc:
                raise DomainApiError(
                    "CANDIDATE_SOURCE_NOT_FOUND",
                    "Quyển của ứng viên quy tắc thế giới cốt lõi không còn tồn tại",
                    status_code=404,
                ) from exc
            except GenerationDomainError as exc:
                raise DomainApiError(
                    "CANDIDATE_BASIS_CONFLICT",
                    "Sự kiện chính thức đang hoạt động cần cho sinh quy tắc thế giới cốt lõi đã thay đổi",
                    status_code=409,
                ) from exc
            basis_identities = {
                (item.resource_type, item.id) for item in basis.source_refs
            }
            current_identities = {
                (item.resource_type, item.id)
                for item in current_context["source_refs"]
            }
            missing_identities = basis_identities - current_identities
            if missing_identities:
                # 只有来源从活动集合消失时才点读，用于区分“已删除/跨书”与“仍存在但已停用”。
                try:
                    for resource_type, resource_id in sorted(missing_identities):
                        if resource_type == "novel":
                            await WorldRuleService._get_novel(
                                novel_id,
                                session=session,
                            )
                        elif resource_type == "character":
                            await character_repo.get_character(
                                novel_id,
                                resource_id,
                                session=session,
                            )
                        elif resource_type == "faction":
                            await faction_repo.get_faction(
                                novel_id,
                                resource_id,
                                session=session,
                            )
                        elif resource_type == "faction_relation":
                            await faction_relation_repo.get_relation(
                                novel_id,
                                resource_id,
                                session=session,
                            )
                        elif resource_type == "world_rule":
                            await world_rule_repo.get_world_rule(
                                novel_id,
                                resource_id,
                                session=session,
                            )
                        else:
                            raise DomainApiError(
                                "CANDIDATE_BASIS_CONFLICT",
                                f"Loại nguồn của quy tắc thế giới cốt lõi không được hỗ trợ: {resource_type}",
                                status_code=409,
                            )
                except (NotFoundError, InvalidIdError) as exc:
                    raise DomainApiError(
                        "CANDIDATE_SOURCE_NOT_FOUND",
                        "Tài nguyên chính thức trong căn cứ ứng viên không còn tồn tại, đã bị xóa hoặc không thuộc tiểu thuyết hiện tại",
                        status_code=404,
                    ) from exc
                raise DomainApiError(
                    "CANDIDATE_BASIS_CONFLICT",
                    "Tập sự thật chính thức đang hoạt động dùng để sinh quy tắc thế giới cốt lõi đã thay đổi",
                    status_code=409,
                )
            if current_identities - basis_identities:
                raise DomainApiError(
                    "CANDIDATE_BASIS_CONFLICT",
                    "Tập sự thật chính thức đang hoạt động dùng để sinh quy tắc thế giới cốt lõi đã thay đổi",
                    status_code=409,
                )
            source_versions = {
                (item.resource_type, item.id): item.version
                for item in current_context["source_refs"]
            }
            try:
                current_fingerprint = compute_core_world_rules_input_fingerprint(
                    generation_input,
                    current_context["source_refs"],
                    flow_snapshot=basis.flow_snapshot,
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise DomainApiError(
                    "CANDIDATE_BASIS_CONFLICT",
                    "Prompt hoặc cấu hình thực thi của ứng viên quy tắc thế giới cốt lõi đã thay đổi",
                    status_code=409,
                ) from exc
            require_current_candidate_basis(
                basis,
                current_source_versions=source_versions,
                current_fingerprint=current_fingerprint,
            )
            return current_context

        async def _confirm(
            session: AsyncClientSession | None,
        ) -> dict[str, Any]:
            """在一个写入单元内完成全量预校验、ID 分配和批量插入。"""
            await WorldRuleService._get_novel(novel_id, session=session)
            receipt = await _load_receipt(session)
            if receipt is not None:
                return _receipt_result(receipt)
            inflight_replay = await _load_inflight_replay(session)
            if inflight_replay is not None:
                return inflight_replay

            current_context = await _validate_basis(session)
            if set(normalized_statements) & current_context[
                "existing_normalized_statements"
            ]:
                raise DomainApiError(
                    "WORLD_RULE_SEMANTIC_CONFLICT",
                    "Ứng viên đã xác nhận trùng phát biểu với quy tắc đang hoạt động hiện có",
                    status_code=409,
                )
            for ref in candidate_refs:
                content = normalized_by_ref[ref]
                scope_type = content["scope_type"]
                scope_ids = set(content["scope_entity_ids"])
                if scope_type == "faction":
                    invalid_scope_ids = sorted(
                        scope_ids - current_context["allowed_faction_ids"]
                    )
                elif scope_type == "character":
                    invalid_scope_ids = sorted(
                        scope_ids - current_context["allowed_character_ids"]
                    )
                else:
                    invalid_scope_ids = []
                if invalid_scope_ids:
                    raise DomainApiError(
                        "SCOPE_ENTITY_NOT_FOUND",
                        "Thực thể phạm vi không tồn tại, đã bị xóa, đã ngừng kích hoạt hoặc không thuộc tiểu thuyết hiện tại",
                        status_code=404,
                        details={"entity_ids": invalid_scope_ids},
                    )
                await WorldRuleService._ensure_name_available(
                    novel_id,
                    content["normalized_name"],
                    exclude_rule_id=None,
                    session=session,
                )

            rule_ids = await id_sequence_repo.allocate_many(
                novel_id,
                "world_rule",
                "rule",
                len(candidate_refs),
                session=session,
            )
            next_order_by_category: dict[str, int] = {}
            for ref in candidate_refs:
                category = normalized_by_ref[ref]["category"]
                if category not in next_order_by_category:
                    next_order_by_category[category] = (
                        await world_rule_repo.get_max_order_index(
                            novel_id,
                            category,
                            session=session,
                        )
                        + 1
                    )

            created_by_ref: dict[str, dict[str, Any]] = {}
            created_rule_ids: list[str] = []
            receipt_attempted = False
            try:
                for index, (ref, rule_id) in enumerate(
                    zip(candidate_refs, rule_ids),
                ):
                    content = normalized_by_ref[ref]
                    category = content["category"]
                    document = {
                        **content,
                        "novel_id": novel_id,
                        "rule_id": rule_id,
                        "order_index": next_order_by_category[category],
                        "core_batch_idempotency_key_hash": fingerprint.key_hash,
                        "core_batch_request_hash": fingerprint.request_hash,
                        "core_batch_local_ref": ref,
                    }
                    next_order_by_category[category] += 1
                    if index == 0:
                        # 复用现有唯一创建幂等索引作为批次的并发赢家标记。
                        document.update(fingerprint.as_creation_fields())
                    created = await world_rule_repo.create_world_rule(
                        document,
                        session=session,
                    )
                    created_rule_ids.append(rule_id)
                    created_by_ref[ref] = created
                candidate_ref_map = {
                    ref: str(created_by_ref[ref]["rule_id"])
                    for ref in candidate_refs
                }
                world_rules_snapshot = []
                for ref in candidate_refs:
                    snapshot = {
                        field: created_by_ref[ref][field]
                        for field in WORLD_RULE_RECEIPT_FIELDS
                    }
                    snapshot["novel_id"] = str(snapshot["novel_id"])
                    world_rules_snapshot.append(snapshot)
                receipt_attempted = True
                receipt = await world_rule_confirmation_receipt_repo.create_receipt(
                    {
                        "novel_id": novel_id,
                        "idempotency_key_hash": fingerprint.key_hash,
                        "request_hash": fingerprint.request_hash,
                        "candidate_ref_map": candidate_ref_map,
                        "world_rules_snapshot": world_rules_snapshot,
                    },
                    session=session,
                )
                result = _receipt_result(receipt)
            except Exception as exc:
                if session is None:
                    published_receipt_conflict = False
                    if receipt_attempted:
                        published_receipt = (
                            await world_rule_confirmation_receipt_repo.find_receipt(
                                novel_id,
                                fingerprint.key_hash,
                                session=None,
                            )
                        )
                        if published_receipt is not None:
                            if (
                                published_receipt.get("request_hash")
                                != fingerprint.request_hash
                            ):
                                published_receipt_conflict = True
                            else:
                                # insert 已在服务端成功但客户端未收到确认时，回执一旦可见
                                # 就是已发布成功结果；不得再撤销并发请求已经回放的正式规则。
                                return _receipt_result(published_receipt)
                    rules_compensated = 0
                    if created_rule_ids:
                        rules_compensated = await world_rule_repo.delete_core_batch_exact(
                            novel_id,
                            created_rule_ids,
                            key_hash=fingerprint.key_hash,
                            request_hash=fingerprint.request_hash,
                        )
                    if rules_compensated != len(created_rule_ids):
                        raise RuntimeError(
                            "Xác nhận quy tắc thế giới cốt lõi thất bại và bù đắp standalone chưa hoàn tất đầy đủ"
                        ) from exc
                    if published_receipt_conflict:
                        raise DomainApiError(
                            "IDEMPOTENCY_KEY_REUSED",
                            "Cùng Idempotency-Key đã được dùng cho yêu cầu xác nhận quy tắc thế giới cốt lõi khác",
                            status_code=409,
                        ) from exc
                raise
            return result

        if session is not None:
            return await _confirm(session)

        try:
            return await run_mongo_write_unit(
                _confirm,
                "bulk_create_core_world_rules",
            )
        except DuplicateKeyError as exc:
            receipt = await _load_receipt(None)
            if receipt is not None:
                return _receipt_result(receipt)
            inflight_replay = await _load_inflight_replay(None)
            if inflight_replay is not None:
                return inflight_replay
            raise DomainApiError(
                "WORLD_RULE_BATCH_CONFLICT",
                "Xác nhận quy tắc thế giới cốt lõi gặp xung đột tên, thứ tự hoặc xử lý đồng thời",
                status_code=409,
            ) from exc

    @staticmethod
    async def list_world_rules(
        novel_id: str,
        *,
        status: str | None = None,
        category: str | None = None,
        scope_type: str | None = None,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        """读取小说内符合筛选条件的未删除规则。

        Args:
            novel_id: 小说 ObjectId 字符串。
            status: 可选规则状态。
            category: 可选精确分类。
            scope_type: 可选作用域类型。
            q: 可选名称、分类、陈述和标签搜索词。

        Returns:
            按分类、顺序和稳定 ID 排列的正式规则。
        """
        await WorldRuleService._get_novel(novel_id, session=None)
        if status is not None and status not in WORLD_RULE_STATUSES:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "Giá trị lọc status không hợp lệ",
                status_code=422,
            )
        if scope_type is not None and scope_type not in WORLD_RULE_SCOPE_TYPES:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "Giá trị lọc scope_type không hợp lệ",
                status_code=422,
            )
        try:
            normalized_category = (
                normalize_world_rule_category(category) if category is not None else None
            )
        except (TypeError, ValueError) as exc:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                str(exc),
                status_code=422,
                field_errors={"category": str(exc)},
            ) from exc
        normalized_q = q.strip() if q is not None else None
        if normalized_q is not None and (not normalized_q or len(normalized_q) > 200):
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "Độ dài q phải từ 1 đến 200 ký tự",
                status_code=422,
            )
        return await world_rule_repo.list_world_rules(
            novel_id,
            status=status,
            category=normalized_category,
            scope_type=scope_type,
            q=normalized_q,
        )

    @staticmethod
    async def list_deleted_world_rules(
        novel_id: str,
        *,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """读取小说回收站中的世界规则。

        Args:
            novel_id: 小说 ObjectId 字符串。
            category: 可选精确分类。

        Returns:
            按删除时间倒序排列的回收站规则。
        """
        await WorldRuleService._get_novel(novel_id, session=None)
        try:
            normalized_category = (
                normalize_world_rule_category(category) if category is not None else None
            )
        except (TypeError, ValueError) as exc:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                str(exc),
                status_code=422,
                field_errors={"category": str(exc)},
            ) from exc
        return await world_rule_repo.list_deleted_world_rules(
            novel_id,
            category=normalized_category,
        )

    @staticmethod
    async def get_world_rule(novel_id: str, rule_id: str) -> dict[str, Any]:
        """读取小说内一条未删除的世界规则。

        Args:
            novel_id: 小说 ObjectId 字符串。
            rule_id: 稳定规则业务 ID。

        Returns:
            匹配的完整世界规则文档。
        """
        await WorldRuleService._get_novel(novel_id, session=None)
        return await WorldRuleService._get_rule(
            novel_id,
            rule_id,
            include_deleted=False,
            session=None,
        )

    @staticmethod
    async def update_world_rule(novel_id: str, rule_id: str, data: Mapping[str, Any], *, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """以 CAS 更新世界规则内容，并在跨分类时维持连续顺序。

        Args:
            novel_id: 小说 ObjectId 字符串。
            rule_id: 稳定规则业务 ID。
            data: 含 expected_version 的更新白名单字段。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            递增一次目标规则版本后的完整文档。
        """
        source = dict(data)
        if "expected_version" not in source:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "Cập nhật quy tắc thế giới phải cung cấp expected_version",
                status_code=422,
            )
        try:
            expected_version = validate_expected_version(source.pop("expected_version"))
        except ValueError as exc:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                str(exc),
                status_code=422,
            ) from exc
        content = _normalize_rule_content(source, partial=True)

        async def _update(session: AsyncClientSession | None) -> dict[str, Any]:
            await WorldRuleService._get_novel(novel_id, session=session)
            current = await WorldRuleService._get_rule(
                novel_id,
                rule_id,
                include_deleted=False,
                session=session,
            )
            WorldRuleService._check_version(current, expected_version)
            next_scope_type = content.get("scope_type", current["scope_type"])
            next_scope_ids = content.get(
                "scope_entity_ids",
                current.get("scope_entity_ids") or [],
            )
            scope_entities = await WorldRuleService._validate_scope(
                novel_id,
                next_scope_type,
                next_scope_ids,
                session=session,
            )
            if "normalized_name" in content:
                await WorldRuleService._ensure_name_available(
                    novel_id,
                    content["normalized_name"],
                    exclude_rule_id=rule_id,
                    session=session,
                )

            next_category = content.get("category", current["category"])
            applied: list[_AppliedRuleChange] = []
            try:
                if next_category == current["category"]:
                    result = await WorldRuleService._apply_change(
                        current,
                        content,
                        increment_version=True,
                        applied=applied,
                        session=session,
                    )
                else:
                    old_siblings = await world_rule_repo.get_category_rules(
                        novel_id,
                        current["category"],
                        session=session,
                    )
                    new_order = await world_rule_repo.get_max_order_index(
                        novel_id,
                        next_category,
                        session=session,
                    ) + 1
                    staged = await WorldRuleService._apply_change(
                        current,
                        {"order_index": -1},
                        increment_version=False,
                        applied=applied,
                        session=session,
                    )
                    for sibling in old_siblings:
                        if int(sibling["order_index"]) <= int(current["order_index"]):
                            continue
                        await WorldRuleService._apply_change(
                            sibling,
                            {"order_index": int(sibling["order_index"]) - 1},
                            increment_version=True,
                            applied=applied,
                            session=session,
                        )
                    result = await WorldRuleService._apply_change(
                        staged,
                        {**content, "category": next_category, "order_index": new_order},
                        increment_version=True,
                        applied=applied,
                        session=session,
                    )
                if next_scope_type == "location":
                    await WorldRuleService._touch_location_scope(
                        novel_id,
                        scope_entities,
                        session=session,
                    )
                return result
            except Exception as exc:
                if session is None and applied:
                    try:
                        await WorldRuleService._compensate_changes(applied)
                    except Exception as compensation_exc:
                        logger.exception("世界规则更新失败且 standalone 补偿未完成")
                        raise DomainApiError(
                            "WORLD_RULE_COMPENSATION_FAILED",
                            "Cập nhật quy tắc thế giới thất bại và bồi thường cơ sở dữ liệu chưa hoàn tất",
                            status_code=503,
                        ) from compensation_exc
                raise exc

        if session is not None:
            return await _update(session)

        return await run_mongo_write_unit(_update, "update_world_rule")

    @staticmethod
    async def reorder_world_rules(novel_id: str, items: Sequence[Mapping[str, Any]], *, session: AsyncClientSession | None=None) -> list[dict[str, Any]]:
        """以完整同分类兄弟集合执行 1-based CAS 重排。

        Args:
            novel_id: 小说 ObjectId 字符串。
            items: 含 rule_id、order_index 和 expected_version 的完整兄弟集合。

            session: 调用方事务；提供时不另开事务。

        Returns:
            按新顺序排列且各自递增一次版本的规则列表。
        """
        if not items:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                "Sắp xếp lại quy tắc cần ít nhất một mục",
                status_code=422,
            )
        normalized_items: list[dict[str, int | str]] = []
        seen_ids: set[str] = set()
        seen_orders: set[int] = set()
        for item in items:
            rule_id = item.get("rule_id")
            order_index = item.get("order_index")
            try:
                expected_version = validate_expected_version(item.get("expected_version"))
            except ValueError as exc:
                raise DomainApiError(
                    "WORLD_RULE_VALIDATION_FAILED",
                    str(exc),
                    status_code=422,
                ) from exc
            if not isinstance(rule_id, str) or RULE_ID_RE.fullmatch(rule_id) is None:
                raise DomainApiError(
                    "WORLD_RULE_VALIDATION_FAILED",
                    "Sắp xếp lại quy tắc chứa rule_id không hợp lệ",
                    status_code=422,
                )
            if isinstance(order_index, bool) or not isinstance(order_index, int) or order_index < 1:
                raise DomainApiError(
                    "WORLD_RULE_VALIDATION_FAILED",
                    "order_index phải là số nguyên bắt đầu từ 1",
                    status_code=422,
                )
            if rule_id in seen_ids or order_index in seen_orders:
                raise DomainApiError(
                    "WORLD_RULE_VALIDATION_FAILED",
                    "rule_id và order_index khi sắp xếp lại quy tắc đều không được trùng",
                    status_code=422,
                )
            seen_ids.add(rule_id)
            seen_orders.add(order_index)
            normalized_items.append(
                {
                    "rule_id": rule_id,
                    "order_index": order_index,
                    "expected_version": expected_version,
                }
            )
        if seen_orders != set(range(1, len(normalized_items) + 1)):
            raise DomainApiError(
                "WORLD_RULE_ORDER_CONFLICT",
                "Thứ tự quy tắc cùng phân loại phải phủ đầy đủ 1..N",
                status_code=409,
            )

        async def _reorder(session: AsyncClientSession | None) -> list[dict[str, Any]]:
            await WorldRuleService._get_novel(novel_id, session=session)
            rules: list[dict[str, Any]] = []
            for item in normalized_items:
                rule = await WorldRuleService._get_rule(
                    novel_id,
                    str(item["rule_id"]),
                    include_deleted=False,
                    session=session,
                )
                WorldRuleService._check_version(rule, int(item["expected_version"]))
                rules.append(rule)
            categories = {str(rule["category"]) for rule in rules}
            if len(categories) != 1:
                raise DomainApiError(
                    "WORLD_RULE_ORDER_CONFLICT",
                    "Một lần sắp xếp lại chỉ được gửi quy tắc của cùng một phân loại",
                    status_code=409,
                )
            category = next(iter(categories))
            siblings = await world_rule_repo.get_category_rules(
                novel_id,
                category,
                session=session,
            )
            if {str(rule["rule_id"]) for rule in siblings} != seen_ids:
                raise DomainApiError(
                    "WORLD_RULE_ORDER_CONFLICT",
                    "Sắp xếp lại quy tắc phải gửi đầy đủ tập anh em đang hoạt động của phân loại hiện tại",
                    status_code=409,
                    details={
                        "expected_rule_ids": [rule["rule_id"] for rule in siblings],
                        "submitted_rule_ids": sorted(seen_ids),
                    },
                )

            applied: list[_AppliedRuleChange] = []
            staged_by_id: dict[str, dict[str, Any]] = {}
            try:
                # 先移到本领域不可能出现的负数临时位，避免唯一索引阻止合法交换。
                for temp_index, rule in enumerate(rules, start=1):
                    staged_by_id[str(rule["rule_id"])] = (
                        await WorldRuleService._apply_change(
                            rule,
                            {"order_index": -temp_index},
                            increment_version=False,
                            applied=applied,
                            session=session,
                        )
                    )
                updated: list[dict[str, Any]] = []
                for item in sorted(normalized_items, key=lambda value: int(value["order_index"])):
                    rule_id = str(item["rule_id"])
                    updated.append(
                        await WorldRuleService._apply_change(
                            staged_by_id[rule_id],
                            {"order_index": int(item["order_index"])},
                            increment_version=True,
                            applied=applied,
                            session=session,
                        )
                    )
                return updated
            except Exception as exc:
                if session is None and applied:
                    try:
                        await WorldRuleService._compensate_changes(applied)
                    except Exception as compensation_exc:
                        logger.exception("世界规则重排失败且 standalone 补偿未完成")
                        raise DomainApiError(
                            "WORLD_RULE_COMPENSATION_FAILED",
                            "Sắp xếp lại quy tắc thế giới thất bại và bồi thường cơ sở dữ liệu chưa hoàn tất",
                            status_code=503,
                        ) from compensation_exc
                raise exc

        if session is not None:
            return await _reorder(session)

        return await run_mongo_write_unit(_reorder, "reorder_world_rules")

    @staticmethod
    async def soft_delete_world_rule(novel_id: str, rule_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """软删除规则并收紧原分类后续顺序。

        Args:
            novel_id: 小说 ObjectId 字符串。
            rule_id: 稳定规则业务 ID。
            expected_version: 调用方持有的目标规则版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            已进入回收站且版本递增一次的目标规则。
        """
        try:
            expected = validate_expected_version(expected_version)
        except ValueError as exc:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                str(exc),
                status_code=422,
            ) from exc

        async def _delete(session: AsyncClientSession | None) -> dict[str, Any]:
            await WorldRuleService._get_novel(novel_id, session=session)
            current = await WorldRuleService._get_rule(
                novel_id,
                rule_id,
                include_deleted=False,
                session=session,
            )
            WorldRuleService._check_version(current, expected)
            siblings = await world_rule_repo.get_category_rules(
                novel_id,
                current["category"],
                session=session,
            )
            applied: list[_AppliedRuleChange] = []
            try:
                deleted = await WorldRuleService._apply_change(
                    current,
                    {"is_deleted": True, "deleted_at": get_utc_now()},
                    increment_version=True,
                    applied=applied,
                    session=session,
                )
                for sibling in siblings:
                    if int(sibling["order_index"]) <= int(current["order_index"]):
                        continue
                    await WorldRuleService._apply_change(
                        sibling,
                        {"order_index": int(sibling["order_index"]) - 1},
                        increment_version=True,
                        applied=applied,
                        session=session,
                    )
                return deleted
            except Exception as exc:
                if session is None and applied:
                    try:
                        await WorldRuleService._compensate_changes(applied)
                    except Exception as compensation_exc:
                        logger.exception("世界规则软删除失败且 standalone 补偿未完成")
                        raise DomainApiError(
                            "WORLD_RULE_COMPENSATION_FAILED",
                            "Xóa quy tắc thế giới thất bại và bồi thường cơ sở dữ liệu chưa hoàn tất",
                            status_code=503,
                        ) from compensation_exc
                raise exc

        if session is not None:
            return await _delete(session)

        return await run_mongo_write_unit(_delete, "soft_delete_world_rule")

    @staticmethod
    async def restore_world_rule(novel_id: str, rule_id: str, *, expected_version: int, session: AsyncClientSession | None=None) -> dict[str, Any]:
        """以 CAS 恢复回收站规则，并追加到当前分类末尾。

        Args:
            novel_id: 小说 ObjectId 字符串。
            rule_id: 稳定规则业务 ID。
            expected_version: 调用方持有的回收站规则版本。

            session: 调用方的保存事务；提供时不另开事务。

        Returns:
            已恢复且版本递增一次的完整目标规则。
        """
        try:
            expected = validate_expected_version(expected_version)
        except ValueError as exc:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                str(exc),
                status_code=422,
            ) from exc

        async def _restore(session: AsyncClientSession | None) -> dict[str, Any]:
            await WorldRuleService._get_novel(novel_id, session=session)
            current = await WorldRuleService._get_rule(
                novel_id,
                rule_id,
                include_deleted=True,
                session=session,
            )
            WorldRuleService._check_version(current, expected)
            scope_entities = await WorldRuleService._validate_scope(
                novel_id,
                current["scope_type"],
                current.get("scope_entity_ids") or [],
                session=session,
            )
            await WorldRuleService._ensure_name_available(
                novel_id,
                current["normalized_name"],
                exclude_rule_id=rule_id,
                session=session,
            )
            order_index = await world_rule_repo.get_max_order_index(
                novel_id,
                current["category"],
                session=session,
            ) + 1
            applied: list[_AppliedRuleChange] = []
            try:
                restored = await WorldRuleService._apply_change(
                    current,
                    {
                        "is_deleted": False,
                        "deleted_at": None,
                        "order_index": order_index,
                    },
                    increment_version=True,
                    applied=applied,
                    session=session,
                )
                if current["scope_type"] == "location":
                    await WorldRuleService._touch_location_scope(
                        novel_id,
                        scope_entities,
                        session=session,
                    )
                return restored
            except Exception as exc:
                if session is None and applied:
                    try:
                        await WorldRuleService._compensate_changes(applied)
                    except Exception as compensation_exc:
                        raise DomainApiError(
                            "WORLD_RULE_COMPENSATION_FAILED",
                            "Khôi phục quy tắc thế giới thất bại và bồi thường cơ sở dữ liệu chưa hoàn tất đầy đủ",
                            status_code=503,
                        ) from compensation_exc
                if isinstance(exc, DomainApiError) and exc.code == "WORLD_RULE_ORDER_CONFLICT":
                    raise DomainApiError(
                        "WORLD_RULE_RESTORE_CONFLICT",
                        "Khôi phục quy tắc xung đột tên hoặc thứ tự phân loại đang hoạt động",
                        status_code=409,
                    ) from exc
                raise

        if session is not None:
            return await _restore(session)

        return await run_mongo_write_unit(_restore, "restore_world_rule")

    @staticmethod
    async def hard_delete_world_rule(
        novel_id: str,
        rule_id: str,
        *,
        expected_version: int,
    ) -> dict[str, Any]:
        """永久删除没有正式结构或伏笔引用的回收站规则。

        Args:
            novel_id: 小说 ObjectId 字符串。
            rule_id: 稳定规则业务 ID。
            expected_version: 调用方持有的回收站规则版本。

        Returns:
            被删除的 rule_id 及全部受保护集合的零引用统计。
        """
        try:
            expected = validate_expected_version(expected_version)
        except ValueError as exc:
            raise DomainApiError(
                "WORLD_RULE_VALIDATION_FAILED",
                str(exc),
                status_code=422,
            ) from exc

        async def _hard_delete(session: AsyncClientSession | None) -> dict[str, Any]:
            await WorldRuleService._get_novel(novel_id, session=session)
            current = await WorldRuleService._get_rule(
                novel_id,
                rule_id,
                include_deleted=True,
                session=session,
            )
            WorldRuleService._check_version(current, expected)
            if await world_rule_repo.count_pending_location_references(
                novel_id,
                rule_id,
                session=session,
            ):
                # 待提交地点不是公开事实，只阻断删除而不返回其数量或业务 ID。
                raise DomainApiError(
                    "WORLD_RULE_LOCATION_WRITE_CONFLICT",
                    "Việc ghi địa điểm đang sử dụng quy tắc này, hãy thử lại sau",
                    status_code=409,
                )
            references = await world_rule_repo.count_protected_references(
                novel_id,
                rule_id,
                session=session,
            )
            if references["total"] > 0:
                raise DomainApiError(
                    "WORLD_RULE_REFERENCE_PROTECTED",
                    "Quy tắc vẫn được cấu trúc chính thức hoặc chi tiết phục bút tham chiếu, không thể xóa vĩnh viễn",
                    status_code=409,
                    details={"references": references},
                )
            deleted = await world_rule_repo.hard_delete_world_rule(
                current,
                session=session,
            )
            if not deleted:
                raise DomainApiError(
                    "WORLD_RULE_VERSION_CONFLICT",
                    "Quy tắc đã bị yêu cầu khác sửa đổi, hãy làm mới rồi thử lại",
                    status_code=409,
                )
            return {"rule_id": rule_id, "references": references}

        return await run_mongo_write_unit(_hard_delete, "hard_delete_world_rule")

    @staticmethod
    async def get_world_rule_context(
        novel_id: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """联合读取 worldview 摘要与当前可用活动规则。

        Args:
            novel_id: 小说 ObjectId 字符串。
            session: 可选 MongoDB 会话，供候选确认在同一写入单元内复验。

        Returns:
            分来源的摘要、可用活动规则和不可用引用诊断。
        """
        novel = await WorldRuleService._get_novel(novel_id, session=session)
        location_revision = int(novel.get("location_write_lock_revision", 0))
        if novel.get("location_write_lock_token") is not None:
            raise DomainApiError(
                "WORLD_RULE_CONTEXT_CONFLICT",
                "Địa điểm đang được cập nhật, hãy tải lại rồi thử lại",
                status_code=409,
            )
        active_candidates = await world_rule_repo.list_world_rules(
            novel_id,
            status="active",
            session=session,
        )
        active_rules: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        for rule in active_candidates:
            try:
                await WorldRuleService._validate_scope(
                    novel_id,
                    rule["scope_type"],
                    rule.get("scope_entity_ids") or [],
                    session=session,
                )
            except DomainApiError as exc:
                diagnostics.append(
                    {
                        "rule_id": rule["rule_id"],
                        "code": exc.code,
                        "message": exc.message,
                        "scope_type": rule["scope_type"],
                        "scope_entity_ids": list(rule.get("scope_entity_ids") or []),
                    }
                )
                continue
            active_rules.append(rule)
        current_novel = await WorldRuleService._get_novel(
            novel_id,
            session=session,
        )
        if (
            current_novel.get("location_write_lock_token") is not None
            or int(current_novel.get("location_write_lock_revision", 0))
            != location_revision
        ):
            raise DomainApiError(
                "WORLD_RULE_CONTEXT_CONFLICT",
                "Địa điểm đang được cập nhật, hãy tải lại rồi thử lại",
                status_code=409,
            )
        return {
            "worldview_summary": str(novel.get("worldview") or ""),
            "active_rules": active_rules,
            "diagnostics": diagnostics,
        }


__all__ = [
    "CHARACTER_ID_RE",
    "FACTION_ID_RE",
    "RULE_ID_RE",
    "WORLD_RULE_FIELDS",
    "WORLD_RULE_SCOPE_TYPES",
    "WORLD_RULE_STATUSES",
    "WorldRuleService",
]
