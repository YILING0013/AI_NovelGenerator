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

async def init_all_indexes():
    """初始化所有数据库索引。"""
    await init_novel_indexes()
    # 在这里添加其他集合的索引初始化
