"""世界规则、地点和物品的不可变 AI 确认回执。"""

from collections.abc import Mapping
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError as MongoDuplicateKeyError

from backend.db.base import BaseRepository
from backend.db.errors import DuplicateKeyError
from backend.db.utils import get_utc_now, to_object_id


class ConfirmationReceiptRepository(BaseRepository):
    """按小说和幂等键保存成功确认的原始响应，不更新已保存的回执。"""

    def __init__(self, collection_name: str, conflict_message: str) -> None:
        """绑定领域使用的集合和重复确认错误消息。

        Args:
            collection_name: 已有的确认回执集合名称。
            conflict_message: 幂等键被占用时返回的领域消息。
        """
        super().__init__(collection_name)
        self.conflict_message = conflict_message

    async def find_receipt(
        self,
        novel_id: str,
        key_hash: str,
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any] | None:
        """读取该小说已经成功执行的确认命令。

        Args:
            novel_id: 小说 ObjectId 字符串。
            key_hash: Idempotency-Key 的 SHA-256。
            session: 可选 MongoDB 会话。

        Returns:
            原始成功回执；尚未成功时返回 None。
        """
        return await self.find_one(
            {"novel_id": to_object_id(novel_id), "idempotency_key_hash": key_hash},
            include_deleted=True,
            session=session,
        )

    async def create_receipt(
        self,
        data: Mapping[str, Any],
        *,
        session: AsyncClientSession | None = None,
    ) -> dict[str, Any]:
        """保存本次确认的请求哈希、正式 ID 映射和响应快照。

        Args:
            data: 已完成领域校验的完整回执数据。
            session: 可选 MongoDB 会话。

        Returns:
            已写入的完整回执文档。
        """
        document = {
            **dict(data),
            "_id": ObjectId(),
            "novel_id": to_object_id(data["novel_id"]),
            "created_at": get_utc_now(),
        }
        try:
            await self.collection.insert_one(document, session=session)
        except MongoDuplicateKeyError as exc:
            raise DuplicateKeyError(self.conflict_message) from exc
        return document


world_rule_confirmation_receipt_repo = ConfirmationReceiptRepository(
    "world_rule_core_confirmation_receipts", "核心世界规则确认幂等键已被占用",
)
location_confirmation_receipt_repo = ConfirmationReceiptRepository(
    "location_generation_confirmation_receipts", "地点批量确认幂等键已被占用",
)
item_confirmation_receipt_repo = ConfirmationReceiptRepository(
    "item_generation_confirmation_receipts", "物品批量确认幂等键已被占用",
)
