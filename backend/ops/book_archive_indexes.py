"""空目标恢复使用的当前单书索引；导入时不读取配置或连接数据库。"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from pymongo import IndexModel


# 保留当前单书集合的显式索引；_id 索引由创建集合时自动建立。
# factions 原先分两次初始化，这里保留两组全部定义。
BOOK_INDEXES: dict[str, list[IndexModel]] = {
    "foreshadowings": [
        IndexModel([("novel_id", 1), ("foreshadowing_id", 1)], unique=True, name="foreshadowing_business_id"),
        IndexModel([("novel_id", 1), ("is_deleted", 1), ("status", 1)], unique=False, name="foreshadowing_filter"),
        *[IndexModel([("novel_id", 1), (f"{field}.kind", 1), (f"{field}.id", 1)], unique=False, name=f"foreshadowing_{field}") for field in ("planting_position", "resolution_position")],
        *[IndexModel([("novel_id", 1), (f"{field}.chapter_id", 1)], unique=False, name=f"foreshadowing_{field}") for field in ("planted_evidence", "resolved_evidence")],
    ],
    "foreshadowing_creation_receipts": [
        IndexModel([("novel_id", 1), ("idempotency_key_hash", 1)], unique=True, name="foreshadowing_creation_key"),
    ],
    "chapter_revisions": [
        IndexModel([("chapter_id", 1), ("version", 1)], unique=True, name="chapter_revision_version"),
        IndexModel([("novel_id", 1), ("chapter_id", 1)], unique=False, name="chapter_revision_book"),
    ],
    "novels": [
        IndexModel(
            [("title", 1)],
            name="title_1",
            unique=False,
        ),
        IndexModel(
            [("status", 1)],
            name="status_1",
            unique=False,
        ),
        IndexModel(
            [("tags", 1)],
            name="tags_1",
            unique=False,
        ),
        IndexModel(
            [("updated_at", -1)],
            name="updated_at_-1",
            unique=False,
        ),
        IndexModel(
            [("is_deleted", 1)],
            name="is_deleted_1",
            unique=False,
        ),
        IndexModel(
            [("is_deleted", 1), ("updated_at", -1)],
            name="is_deleted_1_updated_at_-1",
            unique=False,
        ),
        IndexModel(
            [("is_deleted", 1), ("title", 1)],
            name="is_deleted_1_title_1",
            unique=False,
        ),
        IndexModel(
            [("creation_idempotency_key_hash", 1)],
            name="novels_creation_idempotency_unique",
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
        ),
    ],
    "volumes": [
        IndexModel(
            [("novel_id", 1)],
            name="novel_id_1",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("order_index", 1)],
            name="volumes_active_novel_order_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False},
        ),
        IndexModel(
            [("novel_id", 1), ("is_deleted", 1), ("order_index", 1)],
            name="novel_id_1_is_deleted_1_order_index_1",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("status", 1), ("order_index", 1)],
            name="volumes_novel_status_order",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("is_deleted", 1), ("deleted_at", -1)],
            name="volumes_novel_trash_recent",
            unique=False,
        ),
        IndexModel(
            [("updated_at", -1)],
            name="updated_at_-1",
            unique=False,
        ),
    ],
    "arcs": [
        IndexModel(
            [("volume_id", 1), ("order_index", 1)],
            name="arc_active_volume_order",
            unique=True,
            partialFilterExpression={"is_deleted": False},
        ),
        IndexModel(
            [("novel_id", 1), ("volume_id", 1), ("is_deleted", 1), ("order_index", 1)],
            name="arc_novel_directory",
            unique=False,
        ),
        IndexModel(
            [("volume_id", 1), ("creation_idempotency_key_hash", 1)],
            name="arc_creation_idempotency",
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
        ),
    ],
    "scenes": [
        IndexModel(
            [("arc_id", 1), ("order_index", 1)],
            name="scene_active_arc_order",
            unique=True,
            partialFilterExpression={"is_deleted": False},
        ),
        IndexModel(
            [
                ("novel_id", 1),
                ("volume_id", 1),
                ("arc_id", 1),
                ("is_deleted", 1),
                ("order_index", 1),
            ],
            name="scene_novel_directory",
            unique=False,
        ),
        IndexModel(
            [("arc_id", 1), ("creation_idempotency_key_hash", 1)],
            name="scene_creation_idempotency",
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
        ),
    ],
    "chapters": [
        IndexModel(
            [("scene_id", 1), ("order_index", 1)],
            name="chapter_active_scene_order",
            unique=True,
            partialFilterExpression={"is_deleted": False},
        ),
        IndexModel(
            [
                ("novel_id", 1),
                ("volume_id", 1),
                ("arc_id", 1),
                ("scene_id", 1),
                ("is_deleted", 1),
                ("order_index", 1),
            ],
            name="chapter_novel_directory",
            unique=False,
        ),
        IndexModel(
            [("scene_id", 1), ("creation_idempotency_key_hash", 1)],
            name="chapter_creation_idempotency",
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
        ),
    ],
    "characters": [
        IndexModel(
            [("novel_id", 1), ("character_id", 1)],
            name="characters_novel_character_unique",
            unique=True,
        ),
        IndexModel(
            [("novel_id", 1), ("normalized_name", 1)],
            name="characters_active_novel_normalized_name_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False},
        ),
        IndexModel(
            [
                ("novel_id", 1),
                ("is_deleted", 1),
                ("is_core_character", 1),
                ("status", 1),
                ("sort_order", 1),
                ("character_id", 1),
            ],
            name="characters_novel_core_sort",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("role_type", 1), ("importance_level", 1)],
            name="characters_novel_role_importance",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
            name="characters_creation_idempotency_unique",
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
        ),
    ],
    "factions": [
        IndexModel(
            [("novel_id", 1), ("normalized_name", 1)],
            name="factions_active_core_normalized_name_unique",
            unique=True,
            partialFilterExpression={
                "is_deleted": False,
                "level_type": "core",
                "active_status": "active",
            },
        ),
        IndexModel(
            [("novel_id", 1), ("faction_id", 1)],
            name="factions_novel_faction_unique",
            unique=True,
        ),
        IndexModel(
            [("novel_id", 1), ("level_type", 1)],
            name="novel_id_1_level_type_1",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("parent_faction_id", 1)],
            name="novel_id_1_parent_faction_id_1",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("name", 1)],
            name="novel_id_1_name_1",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
            name="factions_creation_idempotency_unique",
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
        ),
        IndexModel(
            [("novel_id", 1), ("core_batch_idempotency_key_hash", 1)],
            name="factions_core_batch_command_unique",
            unique=True,
            partialFilterExpression={"core_batch_command_marker": True},
        ),
        IndexModel(
            [
                ("novel_id", 1),
                ("core_batch_idempotency_key_hash", 1),
                ("core_batch_local_ref", 1),
            ],
            name="factions_core_batch_local_ref_unique",
            unique=True,
            partialFilterExpression={
                "core_batch_idempotency_key_hash": {"$type": "string"},
                "core_batch_local_ref": {"$type": "string"},
            },
        ),
        IndexModel(
            [("novel_id", 1), ("is_deleted", 1), ("sort_order", 1)],
            name="novel_id_1_is_deleted_1_sort_order_1",
            unique=False,
        ),
        IndexModel(
            [("updated_at", -1)],
            name="updated_at_-1",
            unique=False,
        ),
        IndexModel(
            [
                ("novel_id", 1),
                ("level_type", 1),
                ("volume_id", 1),
                ("parent_faction_id", 1),
                ("is_deleted", 1),
                ("sort_order", 1),
            ],
            name="factions_scope_parent_order",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("level_type", 1), ("volume_id", 1), ("normalized_name", 1)],
            name="factions_active_scope_normalized_name_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False, "active_status": "active"},
        ),
    ],
    "character_relations": [
        IndexModel(
            [("novel_id", 1), ("relation_id", 1)],
            name="character_relations_novel_relation_unique",
            unique=True,
        ),
        IndexModel(
            [
                ("novel_id", 1),
                ("normalized_source_character_id", 1),
                ("normalized_target_character_id", 1),
                ("relation_type", 1),
            ],
            name="character_relations_active_semantic_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False, "is_active": True},
        ),
        IndexModel(
            [("novel_id", 1), ("source_character_id", 1), ("is_active", 1)],
            name="character_relations_source_lookup",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("target_character_id", 1), ("is_active", 1)],
            name="character_relations_target_lookup",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
            name="character_relations_creation_idempotency_unique",
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
        ),
        IndexModel(
            [("novel_id", 1), ("batch_idempotency_key_hash", 1)],
            name="character_relations_batch_command_unique",
            unique=True,
            partialFilterExpression={"batch_command_marker": True},
        ),
        IndexModel(
            [("novel_id", 1), ("batch_idempotency_key_hash", 1), ("batch_local_ref", 1)],
            name="character_relations_batch_local_ref_unique",
            unique=True,
            partialFilterExpression={
                "batch_idempotency_key_hash": {"$type": "string"},
                "batch_local_ref": {"$type": "string"},
            },
        ),
    ],
    "faction_relations": [
        IndexModel(
            [("novel_id", 1), ("relation_id", 1)],
            name="faction_relations_novel_relation_unique",
            unique=True,
        ),
        IndexModel(
            [
                ("novel_id", 1),
                ("normalized_source_faction_id", 1),
                ("normalized_target_faction_id", 1),
                ("relation_type", 1),
            ],
            name="faction_relations_active_semantic_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False, "is_active": True},
        ),
        IndexModel(
            [("novel_id", 1), ("source_faction_id", 1)],
            name="novel_id_1_source_faction_id_1",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("target_faction_id", 1)],
            name="novel_id_1_target_faction_id_1",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("is_deleted", 1), ("is_active", 1), ("intensity", -1)],
            name="novel_id_1_is_deleted_1_is_active_1_intensity_-1",
            unique=False,
        ),
        IndexModel(
            [("updated_at", -1)],
            name="updated_at_-1",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
            name="faction_relations_creation_idempotency_unique",
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
        ),
        IndexModel(
            [("novel_id", 1), ("batch_idempotency_key_hash", 1)],
            name="faction_relations_batch_command_unique",
            unique=True,
            partialFilterExpression={"batch_command_marker": True},
        ),
        IndexModel(
            [("novel_id", 1), ("batch_idempotency_key_hash", 1), ("batch_local_ref", 1)],
            name="faction_relations_batch_local_ref_unique",
            unique=True,
            partialFilterExpression={
                "batch_idempotency_key_hash": {"$type": "string"},
                "batch_local_ref": {"$type": "string"},
            },
        ),
    ],
    "character_faction_bindings": [
        IndexModel(
            [("novel_id", 1), ("binding_id", 1)],
            name="character_faction_bindings_novel_binding_unique",
            unique=True,
        ),
        IndexModel(
            [("novel_id", 1), ("character_id", 1)],
            name="character_faction_bindings_active_membership_primary_unique",
            unique=True,
            partialFilterExpression={
                "membership_type": "primary",
                "is_active": True,
                "is_deleted": False,
            },
        ),
        IndexModel(
            [("novel_id", 1), ("character_id", 1), ("faction_id", 1), ("membership_type", 1)],
            name="character_faction_bindings_active_semantic_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False, "is_active": True},
        ),
        IndexModel(
            [("novel_id", 1), ("character_id", 1), ("is_active", 1)],
            name="character_faction_bindings_character_lookup",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("faction_id", 1), ("is_active", 1)],
            name="character_faction_bindings_faction_lookup",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
            name="character_faction_bindings_creation_idempotency_unique",
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
        ),
        IndexModel(
            [("novel_id", 1), ("primary_switch_idempotency_key_hash", 1)],
            name="character_faction_bindings_primary_switch_idempotency_unique",
            unique=True,
            partialFilterExpression={"primary_switch_idempotency_key_hash": {"$type": "string"}},
        ),
    ],
    "world_rules": [
        IndexModel(
            [("novel_id", 1), ("rule_id", 1)],
            name="world_rules_novel_rule_unique",
            unique=True,
        ),
        IndexModel(
            [("novel_id", 1), ("normalized_name", 1)],
            name="world_rules_active_novel_normalized_name_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False},
        ),
        IndexModel(
            [("novel_id", 1), ("category", 1), ("order_index", 1)],
            name="world_rules_active_novel_category_order_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False},
        ),
        IndexModel(
            [
                ("novel_id", 1),
                ("is_deleted", 1),
                ("status", 1),
                ("category", 1),
                ("scope_type", 1),
                ("order_index", 1),
                ("rule_id", 1),
            ],
            name="world_rules_novel_filter_order",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("is_deleted", 1), ("scope_type", 1), ("scope_entity_ids", 1)],
            name="world_rules_novel_scope_entities",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
            name="world_rules_creation_idempotency_unique",
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
        ),
    ],
    "locations": [
        IndexModel(
            [("novel_id", 1), ("location_id", 1)],
            name="locations_novel_location_unique",
            unique=True,
        ),
        IndexModel(
            [("novel_id", 1), ("parent_location_id", 1), ("normalized_name", 1)],
            name="locations_active_parent_normalized_name_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False},
        ),
        IndexModel(
            [("novel_id", 1), ("parent_location_id", 1), ("order_index", 1)],
            name="locations_active_parent_order_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False},
        ),
        IndexModel(
            [
                ("novel_id", 1),
                ("is_deleted", 1),
                ("status", 1),
                ("location_type", 1),
                ("parent_location_id", 1),
                ("order_index", 1),
            ],
            name="locations_novel_filter_order",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("associated_faction_ids", 1), ("is_deleted", 1)],
            name="locations_novel_faction_references",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("applicable_rule_ids", 1), ("is_deleted", 1)],
            name="locations_novel_rule_references",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
            name="locations_creation_idempotency_unique",
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
        ),
    ],
    "items": [
        IndexModel(
            [("novel_id", 1), ("item_id", 1)],
            name="items_novel_item_unique",
            unique=True,
        ),
        IndexModel(
            [("novel_id", 1), ("normalized_name", 1)],
            name="items_active_name_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False},
        ),
        IndexModel(
            [("novel_id", 1), ("order_index", 1)],
            name="items_active_order_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False},
        ),
        IndexModel(
            [
                ("novel_id", 1),
                ("is_deleted", 1),
                ("lifecycle_status", 1),
                ("item_type", 1),
                ("order_index", 1),
            ],
            name="items_novel_filter_order",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("owner_character_id", 1), ("is_deleted", 1)],
            name="items_novel_owner_references",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("controlling_faction_id", 1), ("is_deleted", 1)],
            name="items_novel_faction_references",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("current_location_id", 1), ("is_deleted", 1)],
            name="items_novel_location_references",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
            name="items_creation_idempotency_unique",
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
        ),
    ],
    "character_volume_states": [
        IndexModel(
            [("novel_id", 1), ("state_id", 1)],
            name="character_volume_states_novel_state_unique",
            unique=True,
        ),
        IndexModel(
            [("novel_id", 1), ("volume_id", 1), ("character_id", 1)],
            name="character_volume_states_active_pair_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False},
        ),
        IndexModel(
            [
                ("novel_id", 1),
                ("volume_id", 1),
                ("is_deleted", 1),
                ("participation_scope", 1),
                ("character_id", 1),
            ],
            name="character_volume_states_volume_list",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("character_id", 1), ("created_at", 1), ("state_id", 1)],
            name="character_volume_states_character_history",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("source_state_id", 1)],
            name="character_volume_states_source_reference",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("relationship_focus_ids", 1)],
            name="character_volume_states_relation_focus_reference",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
            name="character_volume_states_creation_idempotency_unique",
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
        ),
        IndexModel(
            [("novel_id", 1), ("initialization_idempotency_key_hash", 1), ("character_id", 1)],
            name="character_volume_states_initialization_member_unique",
            unique=True,
            partialFilterExpression={"initialization_idempotency_key_hash": {"$type": "string"}},
        ),
    ],
    "faction_volume_states": [
        IndexModel(
            [("novel_id", 1), ("state_id", 1)],
            name="faction_volume_states_novel_state_unique",
            unique=True,
        ),
        IndexModel(
            [("novel_id", 1), ("volume_id", 1), ("faction_id", 1)],
            name="faction_volume_states_active_pair_unique",
            unique=True,
            partialFilterExpression={"is_deleted": False},
        ),
        IndexModel(
            [
                ("novel_id", 1),
                ("volume_id", 1),
                ("is_deleted", 1),
                ("participation_scope", 1),
                ("faction_id", 1),
            ],
            name="faction_volume_states_volume_list",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("faction_id", 1), ("created_at", 1), ("state_id", 1)],
            name="faction_volume_states_faction_history",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("source_state_id", 1)],
            name="faction_volume_states_source_reference",
            unique=False,
        ),
        IndexModel(
            [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
            name="faction_volume_states_creation_idempotency_unique",
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
        ),
        IndexModel(
            [("novel_id", 1), ("initialization_idempotency_key_hash", 1), ("faction_id", 1)],
            name="faction_volume_states_initialization_member_unique",
            unique=True,
            partialFilterExpression={"initialization_idempotency_key_hash": {"$type": "string"}},
        ),
    ],
    "id_sequences": [
        IndexModel(
            [("novel_id", 1), ("entity_type", 1)],
            name="id_sequences_novel_entity_unique",
            unique=True,
        ),
    ],
    "volume_command_receipts": [
        IndexModel(
            [("novel_id", 1), ("idempotency_key_hash", 1)],
            name="volume_command_receipts_novel_key_unique",
            unique=True,
        ),
    ],
    "character_volume_state_initialization_receipts": [
        IndexModel(
            [("novel_id", 1), ("idempotency_key_hash", 1)],
            name="character_volume_state_init_receipts_novel_key_unique",
            unique=True,
        ),
        IndexModel(
            [("novel_id", 1), ("target_volume_id", 1), ("created_at", 1)],
            name="character_volume_state_init_receipts_target_audit",
            unique=False,
        ),
    ],
    "faction_volume_state_initialization_receipts": [
        IndexModel(
            [("novel_id", 1), ("idempotency_key_hash", 1)],
            name="faction_volume_state_init_receipts_novel_key_unique",
            unique=True,
        ),
        IndexModel(
            [("novel_id", 1), ("target_volume_id", 1), ("created_at", 1)],
            name="faction_volume_state_init_receipts_target_audit",
            unique=False,
        ),
    ],
    "world_rule_core_confirmation_receipts": [
        IndexModel(
            [("novel_id", 1), ("idempotency_key_hash", 1)],
            name="world_rule_core_receipts_novel_key_unique",
            unique=True,
        ),
    ],
    "location_generation_confirmation_receipts": [
        IndexModel(
            [("novel_id", 1), ("idempotency_key_hash", 1)],
            name="location_confirmation_receipts_novel_key_unique",
            unique=True,
        ),
    ],
    "item_generation_confirmation_receipts": [
        IndexModel(
            [("novel_id", 1), ("idempotency_key_hash", 1)],
            name="item_confirmation_receipts_novel_key_unique",
            unique=True,
        ),
    ],
    "writing_confirmation_receipts": [
        IndexModel(
            [("novel_id", 1), ("operation", 1), ("idempotency_key_hash", 1)],
            name="writing_confirmation_idempotency",
            unique=True,
        ),
    ],
}


# 已发布 v4 的恢复回执绑定此目录；只读重入不得把旧目录升级成新目录。
V4_BOOK_INDEXES = deepcopy(BOOK_INDEXES)
BOOK_INDEXES = {
    **deepcopy(V4_BOOK_INDEXES),
    "events": [
        IndexModel([("novel_id", 1), ("chapter_id", 1), ("confirmed_at", -1)], unique=False, name="chapter_event_book"),
        IndexModel([("novel_id", 1), ("evidence.revision_id", 1), ("confirmed_at", -1)], unique=False, name="chapter_event_revision"),
    ],
    "chapter_reports": [
        IndexModel([("novel_id", 1), ("chapter_id", 1), ("report_version", 1)], unique=True, name="chapter_report_version"),
        IndexModel([("novel_id", 1), ("evidence.revision_id", 1), ("confirmed_at", -1)], unique=False, name="chapter_report_revision"),
    ],
    "entity_state_history": [
        IndexModel([("novel_id", 1), ("entity_type", 1), ("entity_id", 1), ("after_version", 1)], unique=True, name="entity_state_history_version"),
        IndexModel([("novel_id", 1), ("chapter_id", 1)], unique=False, name="entity_state_history_source"),
        IndexModel([("novel_id", 1), ("evidence.revision_id", 1), ("confirmed_at", -1)], unique=False, name="entity_state_history_revision"),
    ],
    "chapter_record_confirmation_receipts": [
        IndexModel([("novel_id", 1), ("idempotency_key_hash", 1)], unique=True, name="chapter_record_confirmation_key"),
        IndexModel([("novel_id", 1), ("chapter_id", 1)], unique=False, name="chapter_record_confirmation_source"),
    ],
}


# v7 回执已经绑定原 30 集合索引摘要；复制各新增列表，绝不就地扩松旧目录。
V7_BOOK_INDEXES = deepcopy(BOOK_INDEXES)
BOOK_INDEXES = {
    **deepcopy(V7_BOOK_INDEXES),
    "entity_state_history": [
        *deepcopy(V7_BOOK_INDEXES["entity_state_history"]),
        IndexModel([("novel_id", 1), ("schema_id", 1), ("schema_version", 1), ("entity_id", 1)],
                   name="character_fact_entity"),
        IndexModel([("novel_id", 1), ("protected_sources.id", 1)], name="character_fact_protected_source"),
    ],
    "chapter_record_confirmation_receipts": [
        *deepcopy(V7_BOOK_INDEXES["chapter_record_confirmation_receipts"]),
        IndexModel([("novel_id", 1), ("protected_sources.id", 1)], name="character_fact_receipt_protected_source"),
    ],
}


# v9 复用这些键和名称；独立保存 v8 对象，防止后续列表或 IndexModel 原地修改旧目录。
V8_BOOK_INDEXES = deepcopy(BOOK_INDEXES)
V10_BOOK_INDEXES = deepcopy(BOOK_INDEXES)
# 势力事实复用 v10 索引；v11 恢复目录仍只有原 30 个集合。
V11_BOOK_INDEXES = deepcopy(BOOK_INDEXES)

# 整批创建的回执随 v12 归档；旧恢复目录保持原摘要。
BOOK_INDEXES["character_creation_batch_receipts"] = [
    IndexModel([("novel_id", 1), ("operation", 1), ("idempotency_key_hash", 1)],
               unique=True, name="character_creation_batch_novel_operation_key_unique"),
]


# v13 沿用 v12 的 31 集合索引，单独冻结历史对象。
V12_BOOK_INDEXES = deepcopy(BOOK_INDEXES)
V13_BOOK_INDEXES = deepcopy(BOOK_INDEXES)

# v14 才加入势力批次；v11/v12/v13 的集合、字段顺序和索引摘要不变。
BOOK_INDEXES["faction_creation_batch_receipts"] = [
    IndexModel([("novel_id", 1), ("operation", 1), ("idempotency_key_hash", 1)],
               unique=True, name="faction_creation_batch_novel_operation_key_unique"),
]


def index_catalog_digest(catalog: dict[str, list[IndexModel]] | None = None) -> str:
    """计算恢复索引定义的固定摘要，保留复合索引的字段顺序。

    Args:
        catalog: 明确选择的恢复目录；省略时使用当前目录。

    Returns:
        名称、有序字段、唯一约束和条件索引定义的 SHA256。
    """
    definitions = {
        name: [
            {**index.document, "key": list(index.document["key"].items())}
            for index in sorted(indexes, key=lambda item: item.document["name"])
        ]
        for name, indexes in (BOOK_INDEXES if catalog is None else catalog).items()
    }
    # 字段顺序影响复合索引含义，不能直接对 key 对象排序后再计算摘要。
    content = json.dumps(definitions, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(content).hexdigest()
