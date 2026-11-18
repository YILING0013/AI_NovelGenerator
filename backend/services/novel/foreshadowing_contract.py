"""伏笔计划、作者确认的章节证据和回收站接口。"""

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel


ForeshadowingStatus = Literal["planned", "planted", "resolved", "abandoned"]
FORESHADOWING_ID_PATTERN = r"^fo_[0-9]{6,}$"


class ForeshadowingPositionV1(StrictRequestModel):
    "Kế hoạch chỉ trỏ tới vị trí ổn định; quyển chưa chi tiết hóa vẫn có thể dùng."

    kind: Literal["volume", "arc", "scene"]
    id: ObjectIdString


class ForeshadowingEvidenceInputV1(StrictRequestModel):
    "Tham chiếu nguyên văn trong một bản chỉnh sửa đã lưu, start tính từ 0 theo mã Unicode code point."

    # 原文空白也是证据，不能沿用普通表单的首尾清理。
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    chapter_id: ObjectIdString
    version: int = Field(ge=1, le=2**63 - 1)
    start: int = Field(ge=0, le=2**31 - 1, description="Vị trí code point Unicode tính từ 0; phía JS cần dùng Array.from(content) để chuyển thành mảng code point trước.")
    quote: str = Field(min_length=1, max_length=10000)


class ForeshadowingEvidenceV1(ForeshadowingEvidenceInputV1):
    "Server ràng buộc bản chỉnh sửa cùng bản tóm tắt văn bản, không thay đổi theo văn bản hiện tại."

    revision_id: ObjectIdString
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ForeshadowingCreateV1(StrictRequestModel):
    "Kế hoạch tạo thủ công, trạng thái cố định là chưa được gài."

    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=12000)
    target_effect: str = Field(default="", max_length=12000)
    planting_position: ForeshadowingPositionV1 | None = None
    resolution_position: ForeshadowingPositionV1 | None = None


class ForeshadowingUpdateV1(StrictRequestModel):
    "Sửa kế hoạch cục bộ; trạng thái và bằng chứng thực tế chỉ đi qua API xác nhận của tác giả."

    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    content: str | None = Field(default=None, min_length=1, max_length=12000)
    target_effect: str | None = Field(default=None, max_length=12000)
    planting_position: ForeshadowingPositionV1 | None = None
    resolution_position: ForeshadowingPositionV1 | None = None

    @model_validator(mode="after")
    def validate_fields(self) -> "ForeshadowingUpdateV1":
        """拒绝空更新和文本 null，位置 null 表示明确清除。

        Args:
            无。
        Returns:
            校验通过的局部计划。
        """
        fields = self.model_fields_set - {"expected_version"}
        if not fields or any(getattr(self, name) is None for name in fields & {"title", "content", "target_effect"}):
            raise ValueError("Cần sửa ít nhất một trường của kế hoạch, không được đặt phần văn bản thành null")
        return self


class ForeshadowingRecordV1(StrictRequestModel):
    "Tác giả chọn rõ trạng thái, có thể thay thế hoặc xóa đồng thời hai bằng chứng thực tế."

    expected_version: int = Field(ge=1)
    status: ForeshadowingStatus
    planted_evidence: ForeshadowingEvidenceInputV1 | None = None
    resolved_evidence: ForeshadowingEvidenceInputV1 | None = None


class ForeshadowingVersionV1(StrictRequestModel):
    "Thu hồi, khôi phục và xóa vĩnh viễn dùng phiên bản mà tác giả đã đọc."

    expected_version: int = Field(ge=1)


class ForeshadowingReadV1(StrictResponseModel):
    "Chi tiết phục bút và trạng thái đối chiếu của phép tính chỉ đọc lần này."

    foreshadowing_id: str = Field(pattern=FORESHADOWING_ID_PATTERN)
    novel_id: ObjectIdString
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=12000)
    target_effect: str = Field(max_length=12000)
    planting_position: ForeshadowingPositionV1 | None
    resolution_position: ForeshadowingPositionV1 | None
    status: ForeshadowingStatus
    planted_evidence: ForeshadowingEvidenceV1 | None
    resolved_evidence: ForeshadowingEvidenceV1 | None
    planted_needs_review: bool
    resolved_needs_review: bool
    version: int = Field(ge=1)
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


def serialize_foreshadowing(document: dict) -> dict:
    """只公开伏笔字段，不公开幂等键和数据库内部标记。

    Args:
        document: 已计算复核标记的伏笔文档。
    Returns:
        可由严格响应模型校验的数据。
    """
    result = {name: document[name] for name in ForeshadowingReadV1.model_fields}
    result["novel_id"] = str(result["novel_id"])
    return result
