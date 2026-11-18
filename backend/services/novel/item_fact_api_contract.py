"""物品页面的读取及整批起点准备；持久记录和回执仍用原合同。"""

from pydantic import Field, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.llm.schemas.item_pydantic import ItemId, ItemCandidateRef, ItemBulkGeneratedRequestV1
from backend.services.novel.item_fact_contract import (
    FactPositionV1, FactReadPositionV1, FactConfirmed, ItemFactsAtPositionV1, ItemFactReadV1,
    ItemFactPreviewV1, ItemFactCreateConfirmV1, ItemFactValuesV1,
)


class ItemFactQueryV1(StrictRequestModel):
    "Khi lược bỏ vị trí, bộ phân giải vị trí gốc sẽ xác định vị trí mới nhất."

    item_ids: list[ItemId] = Field(max_length=200)
    position: FactPositionV1 | None = None


class ItemFactReadResultV1(StrictResponseModel):
    "Kết quả đọc toàn nhóm dùng chung cho trang và bước kiểm tra."

    novel_id: ObjectIdString
    position: FactReadPositionV1
    items: list[ItemFactsAtPositionV1]
    missing_item_ids: list[ItemId]
    read: ItemFactReadV1


class ItemFactBatchPreviewInputV1(StrictRequestModel):
    "Cùng một loạt ứng viên áp dụng chung điểm khởi đầu do tác giả chọn, chưa được lưu."

    generation: ItemBulkGeneratedRequestV1
    position: FactPositionV1
    note: str = Field(default="", max_length=2000)


class ItemFactBatchPreviewEntryV1(StrictResponseModel):
    "Danh tính ứng viên và bản xem trước thủ công đầy đủ được giữ tương ứng một-một."

    candidate_ref: ItemCandidateRef
    preview: ItemFactPreviewV1
    after: ItemFactValuesV1


class ItemFactBatchPreviewV1(StrictResponseModel):
    "Kết quả chuẩn bị cho phép đóng băng cả lô vào bảng nháp gốc."

    generation: ItemBulkGeneratedRequestV1
    entries: list[ItemFactBatchPreviewEntryV1] = Field(min_length=1, max_length=20)


class ItemFactBatchConfirmEntryV1(StrictRequestModel):
    "Một yêu cầu tạo gốc trong lô, không được phân phối riêng lẻ."

    candidate_ref: ItemCandidateRef
    command: ItemFactCreateConfirmV1


class ItemFactBatchConfirmV1(StrictRequestModel):
    "Một khóa xác nhận ràng buộc cả loạt yêu cầu, chỉ cần một mục lỗi là rollback toàn bộ."

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
            raise ValueError("Hãy giữ nguyên toàn bộ ứng viên và thứ tự của lô, không được tách ra để xác nhận")
        return self
