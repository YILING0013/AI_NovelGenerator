from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorCollection
from application.db.mongo import get_database
from application.db.utils import get_utc_now, to_object_id
from application.db.errors import NotFoundError

class BaseRepository:
    """
    封装通用CRUD操作和审计逻辑的通用基础仓储。
    """
    def __init__(self, collection_name: str):
        """初始化基础仓储类，指定集合名称。"""
        self.collection_name = collection_name

    @property
    def collection(self) -> AsyncIOMotorCollection:
        """获取当前仓储对应的MongoDB异步集合实例。"""
        return get_database()[self.collection_name]

    def _prepare_audit_fields_for_insert(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """为插入操作准备审计字段（创建时间、更新时间、删除状态等）。"""
        now = get_utc_now()
        data.setdefault("created_at", now)
        data.setdefault("updated_at", now)
        data.setdefault("is_deleted", False)
        data.setdefault("deleted_at", None)
        return data

    def _prepare_audit_fields_for_update(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """为更新操作准备审计字段（更新时间）。"""
        data["updated_at"] = get_utc_now()
        return data

    async def insert_one(self, document: Dict[str, Any]) -> str:
        """插入单条文档记录，并返回插入的ID。"""
        document = self._prepare_audit_fields_for_insert(document)
        result = await self.collection.insert_one(document)
        return str(result.inserted_id)

    async def insert_many(self, documents: List[Dict[str, Any]]) -> List[str]:
        """插入多条文档记录，并返回插入的ID列表。"""
        if not documents:
            return []
        prepared_docs = [self._prepare_audit_fields_for_insert(doc) for doc in documents]
        result = await self.collection.insert_many(prepared_docs)
        return [str(gid) for gid in result.inserted_ids]

    async def find_one(self, query: Dict[str, Any], include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        """查找单条文档，默认不包含已软删除的记录。"""
        # Default query filters out soft-deleted items
        q = dict(query)
        if not include_deleted:
            q["is_deleted"] = False
            
        return await self.collection.find_one(q)

    async def find_many(self, query: Dict[str, Any], include_deleted: bool = False, limit: int = 0, skip: int = 0, sort=None) -> List[Dict[str, Any]]:
        """查找多条文档，支持分页和排序，默认不包含已软删除的记录。"""
        q = dict(query)
        if not include_deleted:
            q["is_deleted"] = False
            
        cursor = self.collection.find(q)
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
            
        return await cursor.to_list(length=None)

    async def update_one(self, query: Dict[str, Any], update_data: Dict[str, Any], include_deleted: bool = False) -> bool:
        """更新单条匹配的文档记录，返回是否更新成功。"""
        q = dict(query)
        if not include_deleted:
            q["is_deleted"] = False
            
        update_doc = {"$set": self._prepare_audit_fields_for_update(update_data)}
        result = await self.collection.update_one(q, update_doc)
        return result.modified_count > 0

    async def increment_one(self, query: Dict[str, Any], increments: Dict[str, int], include_deleted: bool = False) -> bool:
        """对单条文档的数值字段进行原子增减（$inc），同时更新updated_at。"""
        q = dict(query)
        if not include_deleted:
            q["is_deleted"] = False

        update_doc = {
            "$inc": increments,
            "$set": {"updated_at": get_utc_now()}
        }
        result = await self.collection.update_one(q, update_doc)
        return result.modified_count > 0

    async def update_many(self, query: Dict[str, Any], update_data: Dict[str, Any], include_deleted: bool = False) -> int:
        """更新多条匹配的文档记录，返回更新影响的行数。"""
        q = dict(query)
        if not include_deleted:
            q["is_deleted"] = False
            
        update_doc = {"$set": self._prepare_audit_fields_for_update(update_data)}
        result = await self.collection.update_many(q, update_doc)
        return result.modified_count

    async def soft_delete_one(self, query: Dict[str, Any]) -> bool:
        """软删除单条匹配的记录（将is_deleted标记为True）。"""
        q = dict(query)
        q["is_deleted"] = False
        update_doc = {
            "$set": {
                "is_deleted": True,
                "deleted_at": get_utc_now(),
                "updated_at": get_utc_now()
            }
        }
        result = await self.collection.update_one(q, update_doc)
        return result.modified_count > 0

    async def restore_one(self, query: Dict[str, Any]) -> bool:
        """恢复单条已软删除的记录。"""
        q = dict(query)
        q["is_deleted"] = True

        update_data = {
            "is_deleted": False,
            "deleted_at": None
        }
        
        update_doc = {"$set": self._prepare_audit_fields_for_update(update_data)}
        
        result = await self.collection.update_one(q, update_doc)
        return result.modified_count > 0

    async def hard_delete_one(self, query: Dict[str, Any]) -> bool:
        """物理删除单条匹配的记录（不可恢复）。"""
        result = await self.collection.delete_one(query)
        return result.deleted_count > 0

    async def hard_delete_many(self, query: Dict[str, Any]) -> int:
        """物理删除多条匹配的记录（不可恢复），返回删除的数量。"""
        result = await self.collection.delete_many(query)
        return result.deleted_count

    async def count_documents(self, query: Dict[str, Any], include_deleted: bool = False) -> int:
        """计算匹配查询的文档总数。"""
        q = dict(query)
        if not include_deleted:
            q["is_deleted"] = False
        return await self.collection.count_documents(q)

    async def exists(self, query: Dict[str, Any], include_deleted: bool = False) -> bool:
        """检查是否存在匹配查询的文档。"""
        count = await self.count_documents(query, include_deleted)
        return count > 0

    async def paginate(self, query: Dict[str, Any], page: int = 1, page_size: int = 10, include_deleted: bool = False, sort=None) -> Dict[str, Any]:
        """分页工具。"""
        skip = (page - 1) * page_size
        items = await self.find_many(query, include_deleted=include_deleted, limit=page_size, skip=skip, sort=sort)
        total = await self.count_documents(query, include_deleted=include_deleted)
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0
        }
