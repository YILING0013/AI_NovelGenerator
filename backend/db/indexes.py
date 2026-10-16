"""建立当前数据结构使用的 MongoDB 索引。"""

import logging
from typing import Any

import pymongo

from backend.db.mongo import get_database

logger = logging.getLogger(__name__)

CHARACTER_NORMALIZED_NAME_INDEX = "characters_active_novel_normalized_name_unique"
FACTION_NORMALIZED_NAME_INDEX = "factions_active_core_normalized_name_unique"
LOCATION_NORMALIZED_NAME_INDEX = "locations_active_parent_normalized_name_unique"
CHARACTER_FACTION_PRIMARY_INDEX = (
    "character_faction_bindings_active_membership_primary_unique"
)


async def init_novel_indexes(db=None):
    """功能：初始化 novels 集合的当前索引。

    Args:
        无。

    Returns:
        无。
    """
    try:
        db = db if db is not None else get_database()
        novels_collection = db["novels"]

        logger.info("正在初始化'novels'集合的索引...")

        indexes = [
            # 单字段索引
            pymongo.IndexModel([("title", pymongo.ASCENDING)]),
            pymongo.IndexModel([("status", pymongo.ASCENDING)]),
            pymongo.IndexModel([("tags", pymongo.ASCENDING)]),
            pymongo.IndexModel([("updated_at", pymongo.DESCENDING)]),
            pymongo.IndexModel([("is_deleted", pymongo.ASCENDING)]),

            # 书架列表：按is_deleted过滤，按updated_at降序排序
            pymongo.IndexModel([
                ("is_deleted", pymongo.ASCENDING),
                ("updated_at", pymongo.DESCENDING)
            ]),

            # 标题搜索：按is_deleted过滤，按标题排序或查询
            pymongo.IndexModel([
                ("is_deleted", pymongo.ASCENDING),
                ("title", pymongo.ASCENDING)
            ]),
            pymongo.IndexModel(
                [("creation_idempotency_key_hash", pymongo.ASCENDING)],
                unique=True,
                name="novels_creation_idempotency_unique",
                partialFilterExpression={
                    "creation_idempotency_key_hash": {"$type": "string"}
                },
            ),
        ]

        await novels_collection.create_indexes(indexes)
        logger.info("成功初始化'novels'集合的索引。")
    except Exception as e:
        logger.error(f"初始化novel索引失败：{e}")
        raise


async def init_volume_indexes(db=None):
    """功能：初始化 volumes 集合的当前索引。

    Args:
        无。

    Returns:
        无。
    """
    try:
        db = db if db is not None else get_database()
        volumes_collection = db["volumes"]

        logger.info("正在初始化'volumes'集合的索引...")

        indexes = [
            # 单字段索引：按小说过滤拉取全书卷列表
            pymongo.IndexModel([("novel_id", pymongo.ASCENDING)]),

            # 只约束未软删除卷，允许回收站里保留历史序号。
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("order_index", pymongo.ASCENDING)],
                unique=True,
                partialFilterExpression={"is_deleted": False},
                name="volumes_active_novel_order_unique",
            ),

            # 读优化组合索引：未删除卷按序号排列的常用查询
            pymongo.IndexModel([
                ("novel_id", pymongo.ASCENDING),
                ("is_deleted", pymongo.ASCENDING),
                ("order_index", pymongo.ASCENDING)
            ]),

            pymongo.IndexModel(
                [
                    ("novel_id", pymongo.ASCENDING),
                    ("status", pymongo.ASCENDING),
                    ("order_index", pymongo.ASCENDING),
                ],
                name="volumes_novel_status_order",
            ),

            pymongo.IndexModel(
                [
                    ("novel_id", pymongo.ASCENDING),
                    ("is_deleted", pymongo.ASCENDING),
                    ("deleted_at", pymongo.DESCENDING),
                ],
                name="volumes_novel_trash_recent",
            ),

            # 按最近更新时间检索
            pymongo.IndexModel([("updated_at", pymongo.DESCENDING)]),
        ]

        await volumes_collection.create_indexes(indexes)
        logger.info("成功初始化'volumes'集合的索引。")
    except Exception as e:
        logger.error(f"初始化volume索引失败：{e}")
        raise


async def init_faction_indexes(db=None):
    """功能：初始化 factions 集合的当前索引。

    Args:
        无。

    Returns:
        无。
    """
    try:
        db = db if db is not None else get_database()
        factions_collection = db["factions"]

        logger.info("正在初始化'factions'集合的索引...")

        indexes = [
            pymongo.IndexModel(
                [("novel_id", 1), ("normalized_name", 1)],
                unique=True,
                partialFilterExpression={
                    "is_deleted": False,
                    "level_type": "core",
                    "active_status": "active",
                },
                name=FACTION_NORMALIZED_NAME_INDEX,
            ),
            # 业务 ID 在同一小说全历史中唯一，软删除后也禁止复用。
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("faction_id", pymongo.ASCENDING)],
                unique=True,
                name="factions_novel_faction_unique",
            ),

            # 按层级类型过滤（用于按 core / major_volume 等召回）
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("level_type", pymongo.ASCENDING)],
            ),

            # 按父级阵营查子阵营
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("parent_faction_id", pymongo.ASCENDING)],
            ),

            # 按名称检索阵营
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("name", pymongo.ASCENDING)],
            ),

            pymongo.IndexModel(
                [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
                unique=True,
                partialFilterExpression={
                    "creation_idempotency_key_hash": {"$type": "string"},
                },
                name="factions_creation_idempotency_unique",
            ),

            pymongo.IndexModel(
                [("novel_id", 1), ("core_batch_idempotency_key_hash", 1)],
                unique=True,
                partialFilterExpression={"core_batch_command_marker": True},
                name="factions_core_batch_command_unique",
            ),

            pymongo.IndexModel(
                [
                    ("novel_id", 1),
                    ("core_batch_idempotency_key_hash", 1),
                    ("core_batch_local_ref", 1),
                ],
                unique=True,
                partialFilterExpression={
                    "core_batch_idempotency_key_hash": {"$type": "string"},
                    "core_batch_local_ref": {"$type": "string"},
                },
                name="factions_core_batch_local_ref_unique",
            ),

            # 读优化：未删除阵营按排序权重排列
            pymongo.IndexModel([
                ("novel_id", pymongo.ASCENDING),
                ("is_deleted", pymongo.ASCENDING),
                ("sort_order", pymongo.ASCENDING)
            ]),

            # 按最近更新时间检索
            pymongo.IndexModel([("updated_at", pymongo.DESCENDING)]),
        ]

        await factions_collection.create_indexes(indexes)
        logger.info("成功初始化'factions'集合的索引。")
    except Exception as exc:
        logger.error("初始化faction索引失败：%s", exc)
        raise


async def init_faction_relation_indexes(db=None):
    """功能：初始化 faction_relations 集合的当前索引。

    Args:
        无。

    Returns:
        无。
    """
    try:
        db = db if db is not None else get_database()
        relations_collection = db["faction_relations"]

        logger.info("正在初始化'faction_relations'集合的索引...")

        indexes = [
            # 稳定关系 ID 在同一小说全历史中唯一，软删除后不可复用。
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("relation_id", pymongo.ASCENDING)],
                unique=True,
                name="faction_relations_novel_relation_unique",
            ),

            pymongo.IndexModel(
                [
                    ("novel_id", pymongo.ASCENDING),
                    ("normalized_source_faction_id", pymongo.ASCENDING),
                    ("normalized_target_faction_id", pymongo.ASCENDING),
                    ("relation_type", pymongo.ASCENDING),
                ],
                unique=True,
                partialFilterExpression={"is_deleted": False, "is_active": True},
                name="faction_relations_active_semantic_unique",
            ),

            # 按来源阵营召回关系
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("source_faction_id", pymongo.ASCENDING)],
            ),

            # 按目标阵营召回关系
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("target_faction_id", pymongo.ASCENDING)],
            ),

            # 常用列表读取：只读未删除、启用关系，并按强度排序
            pymongo.IndexModel([
                ("novel_id", pymongo.ASCENDING),
                ("is_deleted", pymongo.ASCENDING),
                ("is_active", pymongo.ASCENDING),
                ("intensity", pymongo.DESCENDING),
            ]),

            # 按最近更新时间检索
            pymongo.IndexModel([("updated_at", pymongo.DESCENDING)]),

            pymongo.IndexModel(
                [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
                unique=True,
                partialFilterExpression={
                    "creation_idempotency_key_hash": {"$type": "string"},
                },
                name="faction_relations_creation_idempotency_unique",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("batch_idempotency_key_hash", 1)],
                unique=True,
                partialFilterExpression={"batch_command_marker": True},
                name="faction_relations_batch_command_unique",
            ),
            pymongo.IndexModel(
                [
                    ("novel_id", 1),
                    ("batch_idempotency_key_hash", 1),
                    ("batch_local_ref", 1),
                ],
                unique=True,
                partialFilterExpression={
                    "batch_idempotency_key_hash": {"$type": "string"},
                    "batch_local_ref": {"$type": "string"},
                },
                name="faction_relations_batch_local_ref_unique",
            ),
        ]

        await relations_collection.create_indexes(indexes)
        logger.info("成功初始化'faction_relations'集合的索引。")
    except Exception as exc:
        logger.error("初始化faction_relations索引失败：%s", exc)
        raise


async def init_character_indexes(db=None) -> None:
    """初始化全书级角色集合索引。

    Args:
        无。

    Returns:
        无。
    """
    try:
        collection = (db if db is not None else get_database())["characters"]
        indexes = [
            # 业务 ID 终身唯一，软删除后也不得复用。
            pymongo.IndexModel(
                [("novel_id", 1), ("character_id", 1)],
                unique=True,
                name="characters_novel_character_unique",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("normalized_name", 1)],
                unique=True,
                partialFilterExpression={"is_deleted": False},
                name=CHARACTER_NORMALIZED_NAME_INDEX,
            ),
            pymongo.IndexModel(
                [
                    ("novel_id", 1),
                    ("is_deleted", 1),
                    ("is_core_character", 1),
                    ("status", 1),
                    ("sort_order", 1),
                    ("character_id", 1),
                ],
                name="characters_novel_core_sort",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("role_type", 1), ("importance_level", 1)],
                name="characters_novel_role_importance",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
                unique=True,
                partialFilterExpression={
                    "creation_idempotency_key_hash": {"$type": "string"},
                },
                name="characters_creation_idempotency_unique",
            ),
        ]
        await collection.create_indexes(indexes)
        logger.info("成功初始化'characters'集合的索引。")
    except Exception as exc:
        logger.error("初始化characters索引失败：%s", exc)
        raise


async def init_character_relation_indexes(db=None) -> None:
    """初始化全书级角色关系索引。

    Args:
        无。

    Returns:
        无。
    """
    try:
        collection = (db if db is not None else get_database())["character_relations"]
        indexes = [
            pymongo.IndexModel(
                [("novel_id", 1), ("relation_id", 1)],
                unique=True,
                name="character_relations_novel_relation_unique",
            ),
            # 同一小说内只允许一条活动语义边，追加生成不能覆盖既有关系。
            pymongo.IndexModel(
                [
                    ("novel_id", 1),
                    ("normalized_source_character_id", 1),
                    ("normalized_target_character_id", 1),
                    ("relation_type", 1),
                ],
                unique=True,
                partialFilterExpression={"is_deleted": False, "is_active": True},
                name="character_relations_active_semantic_unique",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("source_character_id", 1), ("is_active", 1)],
                name="character_relations_source_lookup",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("target_character_id", 1), ("is_active", 1)],
                name="character_relations_target_lookup",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
                unique=True,
                partialFilterExpression={
                    "creation_idempotency_key_hash": {"$type": "string"},
                },
                name="character_relations_creation_idempotency_unique",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("batch_idempotency_key_hash", 1)],
                unique=True,
                partialFilterExpression={"batch_command_marker": True},
                name="character_relations_batch_command_unique",
            ),
            pymongo.IndexModel(
                [
                    ("novel_id", 1),
                    ("batch_idempotency_key_hash", 1),
                    ("batch_local_ref", 1),
                ],
                unique=True,
                partialFilterExpression={
                    "batch_idempotency_key_hash": {"$type": "string"},
                    "batch_local_ref": {"$type": "string"},
                },
                name="character_relations_batch_local_ref_unique",
            ),
        ]
        await collection.create_indexes(indexes)
        logger.info("成功初始化'character_relations'集合的索引。")
    except Exception as exc:
        logger.error("初始化character_relations索引失败：%s", exc)
        raise


async def init_character_faction_binding_indexes(db=None) -> None:
    """初始化全书级角色势力绑定索引。

    Args:
        无。

    Returns:
        无。
    """
    try:
        collection = (db if db is not None else get_database())["character_faction_bindings"]
        indexes = [
            pymongo.IndexModel(
                [("novel_id", 1), ("binding_id", 1)],
                unique=True,
                name="character_faction_bindings_novel_binding_unique",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("character_id", 1)],
                unique=True,
                partialFilterExpression={
                    "membership_type": "primary",
                    "is_active": True,
                    "is_deleted": False,
                },
                name=CHARACTER_FACTION_PRIMARY_INDEX,
            ),
            # 防止并发创建 secondary/covert 时绕过 service 的先查后写校验。
            pymongo.IndexModel(
                [
                    ("novel_id", 1),
                    ("character_id", 1),
                    ("faction_id", 1),
                    ("membership_type", 1),
                ],
                unique=True,
                partialFilterExpression={"is_deleted": False, "is_active": True},
                name="character_faction_bindings_active_semantic_unique",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("character_id", 1), ("is_active", 1)],
                name="character_faction_bindings_character_lookup",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("faction_id", 1), ("is_active", 1)],
                name="character_faction_bindings_faction_lookup",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
                unique=True,
                partialFilterExpression={
                    "creation_idempotency_key_hash": {"$type": "string"},
                },
                name="character_faction_bindings_creation_idempotency_unique",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("primary_switch_idempotency_key_hash", 1)],
                unique=True,
                partialFilterExpression={
                    "primary_switch_idempotency_key_hash": {"$type": "string"},
                },
                name="character_faction_bindings_primary_switch_idempotency_unique",
            ),
        ]
        await collection.create_indexes(indexes)
        logger.info("成功初始化'character_faction_bindings'集合的索引。")
    except Exception as exc:
        logger.error("初始化character_faction_bindings索引失败：%s", exc)
        raise


async def init_world_rule_indexes(db=None) -> None:
    """初始化正式世界规则集合索引。

    Args:
        无。

    Returns:
        无。

    Raises:
        Exception: MongoDB 索引创建或核对失败。
    """
    try:
        collection = (db if db is not None else get_database())["world_rules"]
        await collection.create_indexes(
            [
                # 业务 ID 在同一小说全历史唯一，软删除后也不得复用。
                pymongo.IndexModel(
                    [("novel_id", 1), ("rule_id", 1)],
                    unique=True,
                    name="world_rules_novel_rule_unique",
                ),
                # 回收站记录不占用显示名称，恢复时再由 Service 做冲突校验。
                pymongo.IndexModel(
                    [("novel_id", 1), ("normalized_name", 1)],
                    unique=True,
                    partialFilterExpression={"is_deleted": False},
                    name="world_rules_active_novel_normalized_name_unique",
                ),
                # 所有未删除状态共用同分类的连续 1-based 顺序。
                pymongo.IndexModel(
                    [
                        ("novel_id", 1),
                        ("category", 1),
                        ("order_index", 1),
                    ],
                    unique=True,
                    partialFilterExpression={"is_deleted": False},
                    name="world_rules_active_novel_category_order_unique",
                ),
                pymongo.IndexModel(
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
                ),
                pymongo.IndexModel(
                    [
                        ("novel_id", 1),
                        ("is_deleted", 1),
                        ("scope_type", 1),
                        ("scope_entity_ids", 1),
                    ],
                    name="world_rules_novel_scope_entities",
                ),
                pymongo.IndexModel(
                    [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
                    unique=True,
                    partialFilterExpression={
                        "creation_idempotency_key_hash": {"$type": "string"},
                    },
                    name="world_rules_creation_idempotency_unique",
                ),
            ]
        )
        logger.info("成功初始化'world_rules'集合的索引。")
    except Exception as exc:
        logger.error("初始化world_rules索引失败：%s", exc)
        raise


async def init_world_rule_confirmation_receipt_indexes(db=None) -> None:
    """初始化核心世界规则确认命令的不可变幂等回执索引。

    Args:
        无。

    Returns:
        无。
    """
    try:
        collection = (db if db is not None else get_database())["world_rule_core_confirmation_receipts"]
        await collection.create_indexes(
            [
                pymongo.IndexModel(
                    [("novel_id", 1), ("idempotency_key_hash", 1)],
                    unique=True,
                    name="world_rule_core_receipts_novel_key_unique",
                )
            ]
        )
        logger.info("成功初始化核心世界规则确认回执索引。")
    except Exception as exc:
        logger.error("初始化核心世界规则确认回执索引失败：%s", exc)
        raise


async def init_volume_command_receipt_indexes(db=None) -> None:
    """初始化卷创建与批量规划确认的不可变幂等收据索引。

    Args:
        无。

    Returns:
        无。
    """
    try:
        collection = (db if db is not None else get_database())["volume_command_receipts"]
        await collection.create_indexes(
            [
                pymongo.IndexModel(
                    [("novel_id", 1), ("idempotency_key_hash", 1)],
                    unique=True,
                    name="volume_command_receipts_novel_key_unique",
                )
            ]
        )
        logger.info("成功初始化卷命令不可变收据索引。")
    except Exception as exc:
        logger.error("初始化卷命令收据索引失败：%s", exc)
        raise


async def init_location_indexes(db=None) -> None:
    """初始化正式地点集合索引。

    Args:
        无。

    Returns:
        无。

    Raises:
        Exception: MongoDB 索引创建失败。
    """
    try:
        collection = (db if db is not None else get_database())["locations"]
        await collection.create_indexes(
            [
                pymongo.IndexModel(
                    [("novel_id", 1), ("location_id", 1)],
                    unique=True,
                    name="locations_novel_location_unique",
                ),
                pymongo.IndexModel(
                    [
                        ("novel_id", 1),
                        ("parent_location_id", 1),
                        ("normalized_name", 1),
                    ],
                    unique=True,
                    partialFilterExpression={"is_deleted": False},
                    name=LOCATION_NORMALIZED_NAME_INDEX,
                ),
                pymongo.IndexModel(
                    [
                        ("novel_id", 1),
                        ("parent_location_id", 1),
                        ("order_index", 1),
                    ],
                    unique=True,
                    partialFilterExpression={"is_deleted": False},
                    name="locations_active_parent_order_unique",
                ),
                pymongo.IndexModel(
                    [
                        ("novel_id", 1),
                        ("is_deleted", 1),
                        ("status", 1),
                        ("location_type", 1),
                        ("parent_location_id", 1),
                        ("order_index", 1),
                    ],
                    name="locations_novel_filter_order",
                ),
                # 势力硬删会使用该索引核对真实地点消费者。
                pymongo.IndexModel(
                    [
                        ("novel_id", 1),
                        ("associated_faction_ids", 1),
                        ("is_deleted", 1),
                    ],
                    name="locations_novel_faction_references",
                ),
                pymongo.IndexModel(
                    [
                        ("novel_id", 1),
                        ("applicable_rule_ids", 1),
                        ("is_deleted", 1),
                    ],
                    name="locations_novel_rule_references",
                ),
                pymongo.IndexModel(
                    [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
                    unique=True,
                    partialFilterExpression={
                        "creation_idempotency_key_hash": {"$type": "string"},
                    },
                    name="locations_creation_idempotency_unique",
                ),
            ]
        )
        logger.info("成功初始化'locations'集合的索引。")
    except Exception as exc:
        logger.error("初始化locations索引失败：%s", exc)
        raise


async def init_location_confirmation_receipt_indexes(db=None) -> None:
    """初始化地点批量确认不可变回执索引。

    Args:
        无。

    Returns:
        无。
    """
    try:
        collection = (db if db is not None else get_database())["location_generation_confirmation_receipts"]
        await collection.create_indexes(
            [
                pymongo.IndexModel(
                    [("novel_id", 1), ("idempotency_key_hash", 1)],
                    unique=True,
                    name="location_confirmation_receipts_novel_key_unique",
                )
            ]
        )
        logger.info("成功初始化地点批量确认不可变回执索引。")
    except Exception as exc:
        logger.error("初始化地点批量确认回执索引失败：%s", exc)
        raise


async def init_item_indexes(db=None) -> None:
    """初始化正式物品集合索引。

    Args:
        无。

    Returns:
        无。

    Raises:
        Exception: MongoDB 索引创建失败。
    """
    try:
        collection = (db if db is not None else get_database())["items"]
        await collection.create_indexes(
            [
                pymongo.IndexModel(
                    [("novel_id", 1), ("item_id", 1)],
                    unique=True,
                    name="items_novel_item_unique",
                ),
                pymongo.IndexModel(
                    [("novel_id", 1), ("normalized_name", 1)],
                    unique=True,
                    partialFilterExpression={"is_deleted": False},
                    name="items_active_name_unique",
                ),
                pymongo.IndexModel(
                    [("novel_id", 1), ("order_index", 1)],
                    unique=True,
                    partialFilterExpression={"is_deleted": False},
                    name="items_active_order_unique",
                ),
                pymongo.IndexModel(
                    [
                        ("novel_id", 1),
                        ("is_deleted", 1),
                        ("lifecycle_status", 1),
                        ("item_type", 1),
                        ("order_index", 1),
                    ],
                    name="items_novel_filter_order",
                ),
                pymongo.IndexModel(
                    [("novel_id", 1), ("owner_character_id", 1), ("is_deleted", 1)],
                    name="items_novel_owner_references",
                ),
                pymongo.IndexModel(
                    [
                        ("novel_id", 1),
                        ("controlling_faction_id", 1),
                        ("is_deleted", 1),
                    ],
                    name="items_novel_faction_references",
                ),
                pymongo.IndexModel(
                    [
                        ("novel_id", 1),
                        ("current_location_id", 1),
                        ("is_deleted", 1),
                    ],
                    name="items_novel_location_references",
                ),
                pymongo.IndexModel(
                    [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
                    unique=True,
                    partialFilterExpression={
                        "creation_idempotency_key_hash": {"$type": "string"},
                    },
                    name="items_creation_idempotency_unique",
                ),
            ]
        )
        logger.info("成功初始化'items'集合的索引。")
    except Exception as exc:
        logger.error("初始化items索引失败：%s", exc)
        raise


async def init_item_confirmation_receipt_indexes(db=None) -> None:
    """初始化物品批量确认不可变回执索引。

    Args:
        无。

    Returns:
        无。
    """
    try:
        collection = (db if db is not None else get_database())["item_generation_confirmation_receipts"]
        await collection.create_indexes(
            [
                pymongo.IndexModel(
                    [("novel_id", 1), ("idempotency_key_hash", 1)],
                    unique=True,
                    name="item_confirmation_receipts_novel_key_unique",
                )
            ]
        )
        logger.info("成功初始化物品批量确认不可变回执索引。")
    except Exception as exc:
        logger.error("初始化物品批量确认回执索引失败：%s", exc)
        raise


async def init_character_volume_state_indexes(db=None) -> None:
    """初始化角色卷级参与状态索引。

    Args:
        无。

    Returns:
        无。
    """
    collection = (db if db is not None else get_database())["character_volume_states"]
    await collection.create_indexes(
        [
            pymongo.IndexModel(
                [("novel_id", 1), ("state_id", 1)],
                unique=True,
                name="character_volume_states_novel_state_unique",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("volume_id", 1), ("character_id", 1)],
                unique=True,
                partialFilterExpression={"is_deleted": False},
                name="character_volume_states_active_pair_unique",
            ),
            pymongo.IndexModel(
                [
                    ("novel_id", 1),
                    ("volume_id", 1),
                    ("is_deleted", 1),
                    ("participation_scope", 1),
                    ("character_id", 1),
                ],
                name="character_volume_states_volume_list",
            ),
            pymongo.IndexModel(
                [
                    ("novel_id", 1),
                    ("character_id", 1),
                    ("created_at", 1),
                    ("state_id", 1),
                ],
                name="character_volume_states_character_history",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("source_state_id", 1)],
                name="character_volume_states_source_reference",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("relationship_focus_ids", 1)],
                name="character_volume_states_relation_focus_reference",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
                unique=True,
                partialFilterExpression={
                    "creation_idempotency_key_hash": {"$type": "string"},
                },
                name="character_volume_states_creation_idempotency_unique",
            ),
            pymongo.IndexModel(
                [
                    ("novel_id", 1),
                    ("initialization_idempotency_key_hash", 1),
                    ("character_id", 1),
                ],
                unique=True,
                partialFilterExpression={
                    "initialization_idempotency_key_hash": {"$type": "string"},
                },
                name="character_volume_states_initialization_member_unique",
            ),
        ]
    )
    logger.info("成功初始化 character_volume_states 索引。")


async def init_character_volume_state_initialization_receipt_indexes(db=None) -> None:
    """初始化角色卷状态批量初始化不可变回执索引。

    Args:
        无。

    Returns:
        无。
    """
    collection = (db if db is not None else get_database())[
        "character_volume_state_initialization_receipts"
    ]
    await collection.create_indexes(
        [
            pymongo.IndexModel(
                [("novel_id", 1), ("idempotency_key_hash", 1)],
                unique=True,
                name="character_volume_state_init_receipts_novel_key_unique",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("target_volume_id", 1), ("created_at", 1)],
                name="character_volume_state_init_receipts_target_audit",
            ),
        ]
    )
    logger.info("成功初始化角色卷状态初始化回执索引。")


async def init_faction_scope_indexes(db=None) -> None:
    """初始化势力归属卷查询和活动作用域名称唯一索引。

    Args:
        无。

    Returns:
        无。
    """
    collection = (db if db is not None else get_database())["factions"]
    await collection.create_indexes(
        [
            pymongo.IndexModel(
                [
                    ("novel_id", 1),
                    ("level_type", 1),
                    ("volume_id", 1),
                    ("parent_faction_id", 1),
                    ("is_deleted", 1),
                    ("sort_order", 1),
                ],
                name="factions_scope_parent_order",
            ),
            pymongo.IndexModel(
                [
                    ("novel_id", 1),
                    ("level_type", 1),
                    ("volume_id", 1),
                    ("normalized_name", 1),
                ],
                unique=True,
                partialFilterExpression={
                    "is_deleted": False,
                    "active_status": "active",
                },
                name="factions_active_scope_normalized_name_unique",
            ),
        ]
    )
    logger.info("成功初始化 factions 归属卷作用域索引。")


async def init_faction_volume_state_indexes(db=None) -> None:
    """初始化势力卷级参与状态索引。

    Args:
        无。

    Returns:
        无。
    """
    collection = (db if db is not None else get_database())["faction_volume_states"]
    await collection.create_indexes(
        [
            pymongo.IndexModel(
                [("novel_id", 1), ("state_id", 1)],
                unique=True,
                name="faction_volume_states_novel_state_unique",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("volume_id", 1), ("faction_id", 1)],
                unique=True,
                partialFilterExpression={"is_deleted": False},
                name="faction_volume_states_active_pair_unique",
            ),
            pymongo.IndexModel(
                [
                    ("novel_id", 1),
                    ("volume_id", 1),
                    ("is_deleted", 1),
                    ("participation_scope", 1),
                    ("faction_id", 1),
                ],
                name="faction_volume_states_volume_list",
            ),
            pymongo.IndexModel(
                [
                    ("novel_id", 1),
                    ("faction_id", 1),
                    ("created_at", 1),
                    ("state_id", 1),
                ],
                name="faction_volume_states_faction_history",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("source_state_id", 1)],
                name="faction_volume_states_source_reference",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("creation_idempotency_key_hash", 1)],
                unique=True,
                partialFilterExpression={
                    "creation_idempotency_key_hash": {"$type": "string"},
                },
                name="faction_volume_states_creation_idempotency_unique",
            ),
            pymongo.IndexModel(
                [
                    ("novel_id", 1),
                    ("initialization_idempotency_key_hash", 1),
                    ("faction_id", 1),
                ],
                unique=True,
                partialFilterExpression={
                    "initialization_idempotency_key_hash": {"$type": "string"},
                },
                name="faction_volume_states_initialization_member_unique",
            ),
        ]
    )
    logger.info("成功初始化 faction_volume_states 索引。")


async def init_faction_volume_state_initialization_receipt_indexes(db=None) -> None:
    """初始化势力卷状态批量初始化不可变回执索引。

    Args:
        无。

    Returns:
        无。
    """
    collection = (db if db is not None else get_database())[
        "faction_volume_state_initialization_receipts"
    ]
    await collection.create_indexes(
        [
            pymongo.IndexModel(
                [("novel_id", 1), ("idempotency_key_hash", 1)],
                unique=True,
                name="faction_volume_state_init_receipts_novel_key_unique",
            ),
            pymongo.IndexModel(
                [("novel_id", 1), ("target_volume_id", 1), ("created_at", 1)],
                name="faction_volume_state_init_receipts_target_audit",
            ),
        ]
    )
    logger.info("成功初始化势力卷状态初始化回执索引。")


async def init_id_sequence_indexes(db=None) -> None:
    """初始化小说内业务 ID 序列索引。

    Args:
        无。

    Returns:
        无。
    """
    try:
        db = db if db is not None else get_database()
        await db["id_sequences"].create_indexes(
            [
                pymongo.IndexModel(
                    [("novel_id", 1), ("entity_type", 1)],
                    unique=True,
                    name="id_sequences_novel_entity_unique",
                )
            ]
        )
        logger.info("成功初始化'id_sequences'集合的索引。")
    except Exception as exc:
        logger.error("初始化id_sequences索引失败：%s", exc)
        raise


async def init_arc_indexes(db: Any) -> None:
    """建立篇章的顺序、目录和创建幂等索引。

    Args:
        db: 当前 MongoDB 数据库。

    Returns:
        无。
    """
    await db["arcs"].create_indexes([
        pymongo.IndexModel(
            [("volume_id", 1), ("order_index", 1)],
            unique=True,
            partialFilterExpression={"is_deleted": False},
            name="arc_active_volume_order",
        ),
        pymongo.IndexModel(
            [("novel_id", 1), ("volume_id", 1), ("is_deleted", 1), ("order_index", 1)],
            name="arc_novel_directory",
        ),
        pymongo.IndexModel(
            [("volume_id", 1), ("creation_idempotency_key_hash", 1)],
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
            name="arc_creation_idempotency",
        ),
    ])


async def init_hierarchy_indexes(db: Any) -> None:
    """建立场景、章节和写作审核回执索引。

    Args:
        db: 当前 MongoDB 数据库。

    Returns:
        无。
    """
    await db["scenes"].create_indexes([
        pymongo.IndexModel(
            [("arc_id", 1), ("order_index", 1)],
            unique=True,
            partialFilterExpression={"is_deleted": False},
            name="scene_active_arc_order",
        ),
        pymongo.IndexModel(
            [("novel_id", 1), ("volume_id", 1), ("arc_id", 1), ("is_deleted", 1), ("order_index", 1)],
            name="scene_novel_directory",
        ),
        pymongo.IndexModel(
            [("arc_id", 1), ("creation_idempotency_key_hash", 1)],
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
            name="scene_creation_idempotency",
        ),
    ])
    await db["chapters"].create_indexes([
        pymongo.IndexModel(
            [("scene_id", 1), ("order_index", 1)],
            unique=True,
            partialFilterExpression={"is_deleted": False},
            name="chapter_active_scene_order",
        ),
        pymongo.IndexModel(
            [("novel_id", 1), ("volume_id", 1), ("arc_id", 1), ("scene_id", 1), ("is_deleted", 1), ("order_index", 1)],
            name="chapter_novel_directory",
        ),
        pymongo.IndexModel(
            [("scene_id", 1), ("creation_idempotency_key_hash", 1)],
            unique=True,
            partialFilterExpression={"creation_idempotency_key_hash": {"$type": "string"}},
            name="chapter_creation_idempotency",
        ),
    ])
    await db["chapter_revisions"].create_indexes([
        pymongo.IndexModel([("chapter_id", 1), ("version", 1)], unique=True, name="chapter_revision_version"),
        pymongo.IndexModel([("novel_id", 1), ("chapter_id", 1)], name="chapter_revision_book"),
    ])
    await db["writing_confirmation_receipts"].create_indexes([
        pymongo.IndexModel(
            [("novel_id", 1), ("operation", 1), ("idempotency_key_hash", 1)],
            unique=True,
            name="writing_confirmation_idempotency",
        ),
    ])


async def init_foreshadowing_indexes(db: Any) -> None:
    """建立伏笔业务 ID、筛选、来源引用及创建回执索引。

    Args:
        db: 当前数据库或隔离测试库。
    Returns:
        无。
    """
    from backend.ops.book_archive_indexes import BOOK_INDEXES
    for name in ("foreshadowings", "foreshadowing_creation_receipts"):
        await db[name].create_indexes(BOOK_INDEXES[name])


async def init_chapter_record_indexes(db: Any) -> None:
    """建立章后记录、报告版本、真实状态历史和确认回执索引。

    Args:
        db: 当前数据库或隔离测试库。
    Returns:
        无。
    """
    from backend.ops.book_archive_indexes import BOOK_INDEXES
    for name in ("events", "chapter_reports", "entity_state_history", "chapter_record_confirmation_receipts", "character_creation_batch_receipts", "faction_creation_batch_receipts"):
        await db[name].create_indexes(BOOK_INDEXES[name])


async def init_all_indexes(db=None) -> None:
    """为当前数据结构创建全部业务索引。

    Args:
        无。

    Returns:
        无。
    """
    db = db if db is not None else get_database()
    await init_novel_indexes(db)
    await init_volume_indexes(db)
    await init_faction_indexes(db)
    await init_faction_relation_indexes(db)
    await init_character_indexes(db)
    await init_character_relation_indexes(db)
    await init_character_faction_binding_indexes(db)
    await init_world_rule_indexes(db)
    await init_world_rule_confirmation_receipt_indexes(db)
    await init_volume_command_receipt_indexes(db)
    await init_id_sequence_indexes(db)
    await init_location_indexes(db)
    await init_location_confirmation_receipt_indexes(db)
    await init_item_indexes(db)
    await init_item_confirmation_receipt_indexes(db)
    await init_character_volume_state_indexes(db)
    await init_character_volume_state_initialization_receipt_indexes(db)
    await init_faction_scope_indexes(db)
    await init_faction_volume_state_indexes(db)
    await init_faction_volume_state_initialization_receipt_indexes(db)
    await init_arc_indexes(db)
    await init_hierarchy_indexes(db)
    await init_foreshadowing_indexes(db)
    await init_chapter_record_indexes(db)
    from backend.services.assistant.resources import init_assistant_indexes
    await init_assistant_indexes(db)
