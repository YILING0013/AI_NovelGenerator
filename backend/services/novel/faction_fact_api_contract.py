"""势力产品接口的准备合同；不改变内部记录、回执或归档格式。"""

from pydantic import Field, model_validator

from backend.api.contracts import StrictRequestModel, StrictResponseModel
from backend.llm.schemas.faction_volume_state_pydantic import FactionId
from backend.services.novel.faction_fact_contract import (
    FactPositionV1, FactionFactBasisV1, FactionFactBeforeV1,
    FactionFactPreviewInputV1,
)


class FactionFactQueryV1(StrictRequestModel):
    "Minh thị chọn mã số thế lực ổn định; nếu lược vị trí, dịch vụ sẽ phân giải vị trí mới nhất."

    faction_ids: list[FactionId] = Field(max_length=200)
    position: FactPositionV1 | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> "FactionFactQueryV1":
        """拒绝重复选择，不在接口中悄悄去重或扩大范围。"""
        if len(self.faction_ids) != len(set(self.faction_ids)):
            raise ValueError("Mã thế lực không được trùng")
        return self


# 产品请求沿用原内部严格合同；卷首已通过势力合同及独立 v14 归档门控。
FactionFactPreviewRequestV1 = FactionFactPreviewInputV1


class FactionFactPreviewV1(StrictResponseModel):
    "Trả về bản xem trước nội bộ gốc; mục thiếu của giá trị trước và giá trị rỗng rõ ràng được giữ tách biệt."

    basis: FactionFactBasisV1
    values: FactionFactBeforeV1
