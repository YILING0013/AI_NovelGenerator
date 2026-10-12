from typing import Any, Dict, List, Optional

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.collection import AsyncCollection

from backend.db.mongo import get_database
from backend.db.utils import get_utc_now

class BaseRepository:
    """
    封装通用CRUD操作和审计逻辑的通用基础仓储。
    """
    def __init__(self, collection_name: str):
        """初始化基础仓储类，指定集合名称。"""
        self.collection_name = collection_name

    @property
    def collection(self) -> AsyncCollection:
        """获取当前仓储对应的MongoDB异步集合实例。"""
        return get_database()[self.collection_name]

    def _prepare_audit_fields_for_insert(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """为插入操作准备审计字段（创建时间、更新时间、删除状态等）。"""
        prepared = dict(data)
        now = get_utc_now()
        prepared.setdefault("created_at", now)
        prepared.setdefault("updated_at", now)
        prepared.setdefault("is_deleted", False)
        prepared.setdefault("deleted_at", None)
        return prepared

    def _prepare_audit_fields_for_update(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """为更新操作准备审计字段（更新时间）。"""
        prepared = dict(data)
        prepared["updated_at"] = get_utc_now()
        return prepared

    async def insert_one(self, document: Dict[str, Any], session: AsyncClientSession | None = None) -> str:
        """插入单条文档记录，并返回插入的ID。

        Args:
            document: 待插入的文档。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            新文档的 ObjectId 字符串。
        """
        document = self._prepare_audit_fields_for_insert(document)
        result = await self.collection.insert_one(document, session=session)
        return str(result.inserted_id)

    async def insert_many(
        self,
        documents: List[Dict[str, Any]],
        session: AsyncClientSession | None = None,
    ) -> List[str]:
        """插入多条文档记录，并返回插入的ID列表。

        Args:
            documents: 待插入的文档列表。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            新文档的 ObjectId 字符串列表。
        """
        if not documents:
            return []
        prepared_docs = [self._prepare_audit_fields_for_insert(doc) for doc in documents]
        result = await self.collection.insert_many(prepared_docs, session=session)
        return [str(gid) for gid in result.inserted_ids]

    async def find_one(
        self,
        query: Dict[str, Any],
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> Optional[Dict[str, Any]]:
        """查找单条文档，默认不包含已软删除的记录。

        Args:
            query: MongoDB 查询条件。
            include_deleted: 是否包含软删除记录。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            命中的单个文档，不存在时返回 None。
        """
        q = dict(query)
        if not include_deleted:
            q["is_deleted"] = False
            
        return await self.collection.find_one(q, session=session)

    async def find_many(
        self,
        query: Dict[str, Any],
        include_deleted: bool = False,
        limit: int = 0,
        skip: int = 0,
        sort=None,
        session: AsyncClientSession | None = None,
    ) -> List[Dict[str, Any]]:
        """查找多条文档，支持分页和排序，默认不包含已软删除的记录。

        Args:
            query: MongoDB 查询条件。
            include_deleted: 是否包含软删除记录。
            limit: 返回数量限制，0 表示不限制。
            skip: 跳过的记录数。
            sort: MongoDB 排序定义。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            文档列表。
        """
        q = dict(query)
        if not include_deleted:
            q["is_deleted"] = False
            
        cursor = self.collection.find(q, session=session)
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
            
        return await cursor.to_list(length=None)

    async def update_one(
        self,
        query: Dict[str, Any],
        update_data: Dict[str, Any],
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> bool:
        """更新单条匹配的文档记录，返回是否更新成功。

        Args:
            query: MongoDB 查询条件。
            update_data: 需要写入 $set 的字段。
            include_deleted: 是否允许更新软删除记录。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            实际修改了文档时返回 True。
        """
        q = dict(query)
        if not include_deleted:
            q["is_deleted"] = False
            
        update_doc = {"$set": self._prepare_audit_fields_for_update(update_data)}
        result = await self.collection.update_one(q, update_doc, session=session)
        return result.modified_count > 0

    async def update_many(
        self,
        query: Dict[str, Any],
        update_data: Dict[str, Any],
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> int:
        """更新多条匹配的文档记录，返回更新影响的行数。

        Args:
            query: MongoDB 查询条件。
            update_data: 需要写入 $set 的字段。
            include_deleted: 是否允许更新软删除记录。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            被实际修改的文档数量。
        """
        q = dict(query)
        if not include_deleted:
            q["is_deleted"] = False
            
        update_doc = {"$set": self._prepare_audit_fields_for_update(update_data)}
        result = await self.collection.update_many(q, update_doc, session=session)
        return result.modified_count

    async def hard_delete_many(
        self,
        query: Dict[str, Any],
        session: AsyncClientSession | None = None,
    ) -> int:
        """物理删除多条匹配的记录（不可恢复），返回删除的数量。

        Args:
            query: MongoDB 查询条件。
            session: 可选 MongoDB 会话，用于事务写入。

        Returns:
            被物理删除的文档数量。
        """
        result = await self.collection.delete_many(query, session=session)
        return result.deleted_count

    async def count_documents(
        self,
        query: Dict[str, Any],
        include_deleted: bool = False,
        session: AsyncClientSession | None = None,
    ) -> int:
        """计算匹配查询的文档总数。

        Args:
            query: MongoDB 查询条件。
            include_deleted: 是否包含软删除记录。
            session: 可选 MongoDB 会话，用于事务读取。

        Returns:
            匹配文档数量。
        """
        q = dict(query)
        if not include_deleted:
            q["is_deleted"] = False
        return await self.collection.count_documents(q, session=session)
