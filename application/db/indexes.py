import pymongo
import logging
from application.db.mongo import get_database

logger = logging.getLogger(__name__)

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

        indexes = [
            # 单字段索引：按小说过滤拉取全书卷列表
            pymongo.IndexModel([("novel_id", pymongo.ASCENDING)]),

            # 唯一组合索引：保证同一小说内卷序号不重复
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("order_index", pymongo.ASCENDING)],
                unique=True
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

        indexes = [
            # 唯一组合索引：保证同一小说内 faction_id 不重复
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("faction_id", pymongo.ASCENDING)],
                unique=True
            ),

            # 按层级类型过滤（用于按 core / major_volume 等召回）
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("level_type", pymongo.ASCENDING)]
            ),

            # 按父级阵营查子阵营
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("parent_faction_id", pymongo.ASCENDING)]
            ),

            # 按名称检索阵营
            pymongo.IndexModel(
                [("novel_id", pymongo.ASCENDING), ("name", pymongo.ASCENDING)]
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


async def init_all_indexes():
    """初始化所有数据库索引。"""
    await init_novel_indexes()
    await init_volume_indexes()
    await init_faction_indexes()
    # 在这里添加其他集合的索引初始化
