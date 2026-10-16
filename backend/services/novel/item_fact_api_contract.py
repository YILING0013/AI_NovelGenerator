"""物品页面的读取及整批起点准备；持久记录和回执仍用原合同。"""

from pydantic import Field, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.llm.schemas.item_pydantic import ItemId, ItemCandidateRef, ItemBulkGeneratedRequestV1
from backend.services.novel.item_fact_contract import (
    FactPositionV1, FactReadPositionV1, FactConfirmed, ItemFactsAtPositionV1, ItemFactReadV1,
    ItemFactPreviewV1, ItemFactCreateConfirmV1, ItemFactValuesV1,
)


class ItemFactQueryV1(StrictRequestModel):
    """省略位置时由原位置解析器确定最新位置。"""

    item_ids: list[ItemId] = Field(max_length=200)
    position: FactPositionV1 | None = None


class ItemFactReadResultV1(StrictResponseModel):
    """页面与检查共用的整组读取结果。"""

    novel_id: ObjectIdString
    position: FactReadPositionV1
    items: list[ItemFactsAtPositionV1]
    missing_item_ids: list[ItemId]
    read: ItemFactReadV1


class ItemFactBatchPreviewInputV1(StrictRequestModel):
    """同一批候选共同采用作者选定的起点，尚不保存。"""

    generation: ItemBulkGeneratedRequestV1
    position: FactPositionV1
    note: str = Field(default="", max_length=2000)


class ItemFactBatchPreviewEntryV1(StrictResponseModel):
    """候选身份与完整人工预览保持一一对应。"""

    candidate_ref: ItemCandidateRef
    preview: ItemFactPreviewV1
    after: ItemFactValuesV1


class ItemFactBatchPreviewV1(StrictResponseModel):
    """整批可冻结到原草稿表的准备结果。"""

    generation: ItemBulkGeneratedRequestV1
    entries: list[ItemFactBatchPreviewEntryV1] = Field(min_length=1, max_length=20)


class ItemFactBatchConfirmEntryV1(StrictRequestModel):
    """批次内的一条原创建请求，不单独派发。"""

    candidate_ref: ItemCandidateRef
    command: ItemFactCreateConfirmV1


class ItemFactBatchConfirmV1(StrictRequestModel):
    """一个确认键绑定整批请求，任一条失败则全部回滚。"""

    generation: ItemBulkGeneratedRequestV1
    entries: list[ItemFactBatchConfirmEntryV1] = Field(min_length=1, max_length=20)
    confirmed: FactConfirmed

    @model_validator(mode="after")
    def require_original_batch(self) -> "ItemFactBatchConfirmV1":
        """保持原候选顺序和完整批次，不能漏项或重复采用。

        Args:
            无。
        Returns:
            对应原完整候选的请求。
        """
        if [row.candidate_ref for row in self.entries] != [row.candidate_ref for row in self.generation.candidates]:
            raise ValueError("请保留原整批候选及顺序，不能拆开确认")
        return self
