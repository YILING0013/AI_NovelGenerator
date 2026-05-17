import pymongo
import logging
from pymongo.asynchronous.collection import AsyncCollection
from backend.db.mongo import get_database

logger = logging.getLogger(__name__)


async def _drop_legacy_unique_index(
    collection: AsyncCollection,
    expected_key: dict[str, int],
    new_index_name: str,
) -> None:
    """删除软删除改造前遗留的全量唯一索引。

    Args:
        collection: 需要检查的 MongoDB 集合。
        expected_key: 旧索引的 key 定义。
        new_index_name: 新 partial unique 索引名称，用于避免误删。

    Returns:
        无。
    """
    # PyMongo Async 的 list_indexes() 是协程，必须先 await 得到异步游标。
    async with await collection.list_indexes() as cursor:
        async for index in cursor:
            index_name = index.get("name")
            if index_name in {"_id_", new_index_name}:
                continue

            # 只删除 key 完全一致、unique=true 且没有 partialFilterExpression 的旧索引。
            if (
                dict(index.get("key", {})) == expected_key
                and index.get("unique") is True
                and "partialFilterExpression" not in index
            ):
                await collection.drop_index(index_name)
                logger.info("已删除旧全量唯一索引 %s.%s", collection.name, index_name)


async def init_novel_indexes():
    """初始化novels集合的索引。"""
    try:
        db = get_database()
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
        ]
        
        await novels_collection.create_indexes(indexes)
        logger.info("成功初始化'novels'集合的索引。")
    except Exception as e:
        logger.error(f"初始化novel索引失败：{e}")


async def init_volume_indexes():
    """初始化volumes集合的索引。"""
    try:
        db = get_database()
        volumes_collection = db["volumes"]

        logger.info("正在初始化'volumes'集合的索引...")

        await _drop_legacy_unique_index(
            volumes_collection,
            {"novel_id": 1, "order_index": 1},
            "volumes_active_novel_order_unique",
        )

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

            # 按最近更新时间检索
            pymongo.IndexModel([("updated_at", pymongo.DESCENDING)]),
        ]

        await volumes_collection.create_indexes(indexes)
        logger.info("成功初始化'volumes'集合的索引。")
    except Exception as e:
        logger.error(f"初始化volume索引失败：{e}")


async def init_faction_indexes():
    """初始化factions集合的索引。"""
    try:
        db = get_database()
        factions_collection = db["factions"]

        logger.info("正在初始化'factions'集合的索引...")

        await _drop_legacy_unique_index(
            factions_collection,
            {"novel_id": 1, "faction_id": 1},
            "factions_active_novel_faction_unique",
        )

        indexes = [
            # 只约束未软删除阵营，允许回收站保留历史业务ID。
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("faction_id", pymongo.ASCENDING)],
                unique=True,
                partialFilterExpression={"is_deleted": False},
                name="factions_active_novel_faction_unique",
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
    except Exception as e:
        logger.error(f"初始化faction索引失败：{e}")


async def init_faction_relation_indexes():
    """初始化faction_relations集合的索引。"""
    try:
        db = get_database()
        relations_collection = db["faction_relations"]

        logger.info("正在初始化'faction_relations'集合的索引...")

        indexes = [
            # 只约束未软删除关系，方便未来保留历史关系记录。
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("relation_id", pymongo.ASCENDING)],
                unique=True,
                partialFilterExpression={"is_deleted": False},
                name="faction_relations_active_novel_relation_unique",
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
        ]

        await relations_collection.create_indexes(indexes)
        logger.info("成功初始化'faction_relations'集合的索引。")
    except Exception as e:
        logger.error(f"初始化faction_relations索引失败：{e}")


async def init_all_indexes():
    """初始化所有数据库索引。"""
    await init_novel_indexes()
    await init_volume_indexes()
    await init_faction_indexes()
    await init_faction_relation_indexes()
    # 在这里添加其他集合的索引初始化
