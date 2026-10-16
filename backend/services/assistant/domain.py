"""把已审核操作交给原业务服务，所有读写使用调用方的同一个事务。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.api.error_protocol import DomainApiError
from backend.services.novel.novel_service import NovelService
from backend.services.novel.volume_service import VolumeService
from backend.services.novel.arc_service import ArcService
from backend.services.novel.scene_service import SceneService
from backend.services.novel.chapter_service import ChapterService
from backend.services.novel.character_service import CharacterService
from backend.services.novel.faction_service import FactionService
from backend.services.novel.location_service import LocationService
from backend.services.novel.item_service import ItemService
from backend.services.novel.world_rule_service import WorldRuleService
from backend.services.novel.character_relation_service import CharacterRelationService
from backend.services.novel.faction_relation_service import FactionRelationService
from backend.services.novel.character_faction_binding_service import CharacterFactionBindingService
from backend.services.novel.character_volume_state_service import CharacterVolumeStateService
from backend.services.novel.faction_volume_state_service import FactionVolumeStateService
from backend.services.novel.plot_service import confirm_preparation, clear_preparation
from backend.services.novel.plot_contract import VolumePreparationConfirmV1
from .contracts import ChangeOperation, ResourceRef
from .resources import INTERNAL_INPUTS, RESOURCES, get_resource, public_content


HIERARCHY = {"arc": ArcService, "scene": SceneService, "chapter": ChapterService}
PARENT_KIND = {"volume": "novel", "arc": "volume", "scene": "arc", "chapter": "scene"}
ENTITY_SERVICES = {
    "character": (CharacterService, "character"), "faction": (FactionService, "faction"),
    "location": (LocationService, "location"), "item": (ItemService, "item"),
    "world_rule": (WorldRuleService, "world_rule"),
    "character_relation": (CharacterRelationService, "relation"),
    "faction_relation": (FactionRelationService, "relation"),
    "character_faction_binding": (CharacterFactionBindingService, "binding"),
    "character_volume_state": (CharacterVolumeStateService, "state"),
    "faction_volume_state": (FactionVolumeStateService, "state"),
}
REORDER_SERVICES = {
    "volume": VolumeService.reorder_volumes, "arc": ArcService.reorder_arcs,
    "scene": SceneService.reorder_scenes, "chapter": ChapterService.reorder_chapters,
    "item": ItemService.reorder_items, "world_rule": WorldRuleService.reorder_world_rules,
    "location": LocationService.reorder_locations, "faction": FactionService.batch_update_sort_order,
}
STATUS_FIELD = {"novel": "status", "volume": "status", "character": "status", "faction": "active_status", "location": "status", "item": "lifecycle_status", "world_rule": "status", "character_relation": "is_active", "faction_relation": "is_active", "character_faction_binding": "is_active"}


def resolve_temporary(value: Any, identities: dict[str, str], *, reference: bool = False) -> Any:
    """把同组新建资料的临时 ID 换成业务服务分配的 ID。

    Args:
        value: 字段、父级或目标 ID。
        identities: 前面已创建对象的临时 ID 对照。
        reference: 当前值是否为 ID 字段，普通正文不替换。
    Returns:
        替换后的独立副本，未创建的引用明确报错。
    """
    if reference and isinstance(value, str) and value.startswith("new_"):
        if value not in identities:
            raise DomainApiError("ASSISTANT_DEPENDENCY_MISSING", f"请先创建同组资料：{value}")
        return identities[value]
    if isinstance(value, dict):
        return {key: resolve_temporary(item, identities, reference=key.endswith(("_id", "_ids")) or key in {"id", "ids"}) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_temporary(item, identities, reference=reference) for item in value]
    return value


def update_fields(kind: str, fields: dict, before: dict) -> dict:
    """把指定子字段合入原完整字段，保留同一表单里未修改的内容。

    Args:
        kind: 资料类型。
        fields: 作者或模型明确指定的字段。
        before: 保存前读取的业务内容。
    Returns:
        可交给原更新 DTO 的完整顶层字段。
    """
    allowed = set(RESOURCES[kind].update.model_fields) - INTERNAL_INPUTS
    result = {}
    for path, value in fields.items():
        parts = path.split(".")
        if parts[0] not in allowed or any(part.startswith("$") or not part for part in parts):
            raise DomainApiError("ASSISTANT_FIELD_FORBIDDEN", f"不能直接修改字段：{path}")
        if len(parts) == 1:
            if any(other.startswith(path + ".") for other in fields):
                raise DomainApiError("ASSISTANT_FIELD_OVERLAP", "请只提交完整字段或它的子字段，不要同时提交")
            result[path] = value
            continue
        cursor = result.setdefault(parts[0], deepcopy(before.get(parts[0])))
        for part in parts[1:-1]:
            if not isinstance(cursor, dict) or part not in cursor:
                raise DomainApiError("ASSISTANT_FIELD_UNKNOWN", f"资料没有字段：{path}")
            cursor = cursor[part]
        if not isinstance(cursor, dict) or parts[-1] not in cursor:
            raise DomainApiError("ASSISTANT_FIELD_UNKNOWN", f"资料没有字段：{path}")
        cursor[parts[-1]] = value
    return result


async def execute_operation(novel_id: str, operation: ChangeOperation, *, identities: dict[str, str], key: str, session) -> list[dict]:
    """在调用方事务中执行一项原业务命令；不直接修改业务集合。

    Args:
        novel_id: 会话固定的小说。
        operation: 已校验候选。
        identities: 同组已创建对象的正式 ID。
        key: 修改组、版本和操作次序组成的固定确认键。
        session: 必需的外层 Mongo 事务。
    Returns:
        写后原文档列表，供保存回执和复读使用。
    """
    kind, action = operation.resource_type, operation.action
    if kind == "foreshadowing":
        raise DomainApiError("FORESHADOWING_READ_ONLY", "助手只供读取伏笔，请由作者在伏笔工作台记录或修改")
    identity = resolve_temporary(operation.id, identities, reference=True)
    parent = resolve_temporary(operation.parent_id, identities, reference=True)
    fields = resolve_temporary(operation.fields, identities)
    current = None
    if action not in {"create", "reorder"}:
        if not identity:
            raise DomainApiError("ASSISTANT_TARGET_REQUIRED", "请选择要修改的资料")
        current = await get_resource(novel_id, ResourceRef(resource_type=kind, id=identity), include_deleted=action == "restore", session=session)
    expected = current["version"] if current else None
    if action == "create":
        if not operation.temporary_id or identity:
            raise DomainApiError("ASSISTANT_CREATE_INVALID", "新建资料需要唯一临时 ID，不能指定正式 ID")
        spec = RESOURCES[kind]
        if spec.create is None:
            raise DomainApiError("ASSISTANT_CREATE_INVALID", "请在书架创建小说")
        if set(fields) & INTERNAL_INPUTS:
            raise DomainApiError("ASSISTANT_FIELD_FORBIDDEN", "新建资料不能指定版本或内部依据")
        if kind.endswith("_volume_state"):
            entity_kind = kind.removesuffix("_volume_state")
            volume_id, entity_id = fields.pop("volume_id"), fields.pop(f"{entity_kind}_id")
            data = spec.create.model_validate(fields)
            if kind == "faction_volume_state":
                from backend.services.novel.faction_volume_plan_service import create_faction_volume_plan
                result = await create_faction_volume_plan(novel_id, volume_id, entity_id, data, idempotency_key=key, session=session)
            else:
                result = await ENTITY_SERVICES[kind][0].upsert_state(novel_id, volume_id, entity_id, data, idempotency_key=key, session=session)
        else:
            data = spec.create.model_validate({**fields, **({"novel_id": novel_id} if kind == "volume" else {})}).model_dump(mode="json", exclude_unset=True)
            if kind in PARENT_KIND:
                if not parent:
                    parent = novel_id if kind == "volume" else None
                if parent is None:
                    raise DomainApiError("ASSISTANT_PARENT_REQUIRED", "新建层级资料需要指定上级")
                await get_resource(novel_id, ResourceRef(resource_type=PARENT_KIND[kind], id=parent), session=session)
                if kind == "volume":
                    result = await VolumeService.create_volume({**data, "novel_id": novel_id}, idempotency_key=key, session=session)
                else:
                    result = await getattr(HIERARCHY[kind], f"create_{kind}_in_session")(parent, data, idempotency_key=key, session=session)
            else:
                service, name = ENTITY_SERVICES[kind]
                result = await getattr(service, f"create_{name}")(novel_id, data, idempotency_key=key, session=session)
        identities[operation.temporary_id] = str(result["state_id"] if kind.endswith("_volume_state") else result[spec.identity])
        return [result]
    if action == "update":
        payload = update_fields(kind, fields, public_content(kind, current))
        if kind == "character_relation" and "current_state" not in payload:
            # 先按实际字段分流，不能补入未修改的状态再误当成旧原文保存。
            from backend.llm.schemas.character_relation_pydantic import CharacterRelationDesignUpdateRequestV1

            for field in CharacterRelationDesignUpdateRequestV1.model_fields:
                if field != "expected_version" and field not in payload:
                    payload[field] = current[field]
            return [await CharacterRelationService.update_relation_design(
                novel_id, identity, {**payload, "expected_version": expected}, session=session,
            )]
        # 明确提交状态时仍使用旧完整请求，未改动字段沿用本事务原值。
        for field, definition in RESOURCES[kind].update.model_fields.items():
            if field != "expected_version" and definition.is_required() and field not in payload:
                payload[field] = current[field]
        data = RESOURCES[kind].update.model_validate({**payload, "expected_version": expected}).model_dump(mode="json", exclude_unset=True)
        if kind == "faction_volume_state":
            from backend.services.novel.faction_volume_plan_service import update_faction_volume_plan
            result = await update_faction_volume_plan(novel_id, identity, data, session=session)
        elif kind == "novel":
            result = await NovelService.update_novel(novel_id, data, session=session)
        elif kind == "volume":
            result = await VolumeService.update_volume_info(identity, data, session=session)
        elif kind in HIERARCHY:
            if kind == "chapter":
                result = await ChapterService.update_chapter_in_session(identity, data, session=session, source="assistant")
            else:
                result = await getattr(HIERARCHY[kind], f"update_{kind}_in_session")(identity, data, session=session)
        else:
            service, name = ENTITY_SERVICES[kind]
            method = "update_faction_info" if kind == "faction" else f"update_{name}"
            result = await getattr(service, method)(novel_id, identity, data, session=session)
        return [result]
    if action in {"delete", "restore"}:
        if fields:
            raise DomainApiError("ASSISTANT_LIFECYCLE_INVALID", "回收或恢复不接受其它内容字段")
        if kind in HIERARCHY:
            result = await HIERARCHY[kind].set_deleted(identity, expected_version=expected, deleted=action == "delete", session=session)
        else:
            service, name = (NovelService, "novel") if kind == "novel" else (VolumeService, "volume") if kind == "volume" else ENTITY_SERVICES[kind]
            method = f"{'soft_delete' if action == 'delete' else 'restore'}_{name}"
            args = (identity,) if kind in {"novel", "volume"} else (novel_id, identity)
            extra = {"detach_children": False} if kind == "location" and action == "delete" else {}
            result = await getattr(service, method)(*args, expected_version=expected, session=session, **extra)
        return [result]
    if action == "status":
        field = STATUS_FIELD.get(kind)
        if field is None or set(fields) != {field}:
            raise DomainApiError("ASSISTANT_STATUS_INVALID", f"当前资料只支持状态字段：{field}")
        value = fields[field]
        if kind == "novel":
            result = await NovelService.update_status(novel_id, value, expected, session=session)
        elif kind == "character":
            result = await CharacterService.update_character_status(novel_id, identity, value, expected_version=expected, session=session)
        elif kind == "item":
            result = await ItemService.transition_item_status(novel_id, identity, value, expected_version=expected, session=session)
        elif field == "is_active":
            if not isinstance(value, bool):
                raise DomainApiError("ASSISTANT_STATUS_INVALID", "启用状态必须为 true 或 false")
            service, name = ENTITY_SERVICES[kind]
            result = await getattr(service, f"set_{name}_active")(novel_id, identity, expected_version=expected, is_active=value, session=session)
        else:
            return await execute_operation(novel_id, operation.model_copy(update={"action": "update"}), identities=identities, key=key, session=session)
        return [result]
    if action == "reorder":
        if kind not in REORDER_SERVICES or set(fields) != {"ids"} or not isinstance(fields["ids"], list) or not fields["ids"]:
            raise DomainApiError("ASSISTANT_REORDER_INVALID", "请提供可排序资料的完整兄弟 ID 列表")
        items = []
        for index, item_id in enumerate(fields["ids"]):
            document = await get_resource(novel_id, ResourceRef(resource_type=kind, id=item_id), session=session)
            items.append({f"{kind if kind != 'world_rule' else 'rule'}_id": item_id, "sort_order" if kind == "faction" else "order_index": index if kind == "faction" else index + 1, "expected_version": document["version"]})
        if kind in HIERARCHY:
            await get_resource(novel_id, ResourceRef(resource_type=PARENT_KIND[kind], id=parent), session=session)
            return await REORDER_SERVICES[kind](parent, {"items": items}, session=session)
        if kind == "location":
            return await REORDER_SERVICES[kind](novel_id, parent, items, session=session)
        return await REORDER_SERVICES[kind](novel_id, items, session=session)
    if action == "preparation":
        if kind != "volume" or set(fields) - {"kind", "location_ids", "confirmed"} or fields.get("kind") not in {"factions", "characters", "locations"}:
            raise DomainApiError("ASSISTANT_PREPARATION_INVALID", "请选择卷内势力、角色或地点准备阶段")
        if not isinstance(fields.get("confirmed", True), bool):
            raise DomainApiError("ASSISTANT_PREPARATION_INVALID", "准备确认状态必须为 true 或 false")
        if fields.get("confirmed") is False:
            return [await clear_preparation(novel_id, identity, fields["kind"], expected_version=expected, location_ids=fields.get("location_ids"), session=session)]
        request = VolumePreparationConfirmV1.model_validate({"expected_version": expected, **{k: v for k, v in fields.items() if k not in {"kind", "confirmed"}}})
        await confirm_preparation(novel_id, identity, fields["kind"], request, idempotency_key=key, session=session)
        return [await get_resource(novel_id, ResourceRef(resource_type=kind, id=identity), session=session)]
    raise DomainApiError("ASSISTANT_OPERATION_INVALID", "不支持这项操作")
