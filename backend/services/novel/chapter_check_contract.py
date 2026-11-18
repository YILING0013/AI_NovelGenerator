"""章后检查的固定来源、有限选择与严格结果，不接收任意实体修改。"""

from typing import Annotated

from pydantic import ConfigDict, Field, field_validator, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel


CHAPTER_CHECK_TASK = "check_chapter_psychological_state_by_ai"
CHAPTER_CHECK_SCOPE_FIELDS = {"novel_id", "source", "state_id", "expected_version"}
CHAPTER_ITEM_OWNER_CHECK_TASK = "check_chapter_item_owner_by_ai"
CHAPTER_ITEM_OWNER_FACTS_CHECK_TASK = "check_chapter_item_owner_facts_by_ai"
CHAPTER_ITEM_OWNER_CHECK_SCOPE_FIELDS = {
    "novel_id", "source", "item_id", "expected_version", "from_character_id", "to_character_id",
}
CHAPTER_CHARACTER_RELATION_STATE_CHECK_TASK = "check_chapter_character_relation_state_by_ai"
# 迁移期间明确区分章前事实检查；旧任务仍供原页面及成功回执回放使用。
CHAPTER_CHARACTER_RELATION_FACTS_CHECK_TASK = "check_chapter_character_relation_facts_by_ai"
CHAPTER_CHARACTER_RELATION_STATE_CHECK_SCOPE_FIELDS = {
    "novel_id", "source", "relation_id", "expected_version",
}
CHAPTER_WORLD_RULES_CHECK_TASK = "check_chapter_world_rules_by_ai"
CHAPTER_WORLD_RULES_CHECK_SCOPE_FIELDS = {"novel_id", "source", "rules"}


class ChapterCheckSourceV1(StrictRequestModel):
    "Bản chỉnh sửa chương bất biến đầy đủ do tác giả chọn; không cần chọn trích dẫn trước khi kiểm tra."

    chapter_id: ObjectIdString
    revision_id: ObjectIdString
    version: int = Field(ge=1, le=2**63 - 1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ChapterCheckInputV1(StrictRequestModel):
    "Bản chỉnh sửa của một chương do máy chủ cố định cùng trạng thái hiện có trong cùng quyển."

    novel_id: ObjectIdString
    source: ChapterCheckSourceV1
    state_id: ObjectIdString
    expected_version: int = Field(ge=1, le=2**63 - 2)


class ChapterCheckSuggestionV1(StrictResponseModel):
    "Mô hình chỉ được đề xuất giá trị tâm lý kèm trích dẫn nguyên văn, không tạo định danh hay phiên bản."

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    psychological_state: str = Field(max_length=1000)
    start: int = Field(ge=0, le=2**31 - 1, description="Vị trí code point Unicode tính từ 0, không phải chỉ số UTF-16.")
    quote: str = Field(min_length=1, max_length=10000)


class ChapterCheckResultV1(StrictResponseModel):
    "Câu hỏi chỉ để đọc; không có đề xuất đáng tin thì minh thị trả null."

    issues: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(max_length=50)
    suggestion: ChapterCheckSuggestionV1 | None


class ChapterItemOwnerCheckInputV1(StrictRequestModel):
    "Cố định vật phẩm và người giữ A→B; mô hình không thể thay mục tiêu hay chiều chuyển giao."

    novel_id: ObjectIdString
    source: ChapterCheckSourceV1
    item_id: str = Field(pattern=r"^item_[0-9]{6,19}$")
    expected_version: int = Field(ge=1, le=2**63 - 2)
    from_character_id: str = Field(pattern=r"^char_[0-9]{6,19}$")
    to_character_id: str = Field(pattern=r"^char_[0-9]{6,19}$")

    @model_validator(mode="after")
    def require_different_holders(self) -> "ChapterItemOwnerCheckInputV1":
        """拒绝持有人未改变的请求。

        Args:
            无。
        Returns:
            两个持有人不同的固定输入。
        """
        if self.from_character_id == self.to_character_id:
            raise ValueError("Hãy chọn một người sở hữu mới khác")
        return self


class ChapterItemOwnerCheckSuggestionV1(StrictResponseModel):
    "Đề xuất vật phẩm chỉ kèm vị trí nguyên văn; mô hình không được chỉ định định danh, phiên bản hay trường sửa đổi."

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    start: int = Field(ge=0, le=2**31 - 1, description="Vị trí code point Unicode tính từ 0.")
    quote: str = Field(min_length=1, max_length=10000)


class ChapterItemOwnerCheckResultV1(StrictResponseModel):
    "Mô hình chỉ kiểm tra lượt chuyển giao đã cố định; trả null khi không có nguyên văn minh thị."

    issues: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(max_length=50)
    suggestion: ChapterItemOwnerCheckSuggestionV1 | None


class ChapterCharacterRelationStateCheckInputV1(StrictRequestModel):
    "Cố định một quan hệ toàn sách và phiên bản gốc của tác giả; đầu cuối do server đọc."

    novel_id: ObjectIdString
    source: ChapterCheckSourceV1
    relation_id: str = Field(pattern=r"^cr_[0-9]{6,19}$")
    expected_version: int = Field(ge=1, le=2**63 - 2)


class ChapterCharacterRelationStateCheckSuggestionV1(StrictResponseModel):
    "Chỉ đề xuất trạng thái quan hệ hiện tại và nguyên văn; mô hình không được quyết định định danh hay các trường khác."

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    current_state: str = Field(min_length=1, max_length=2000)
    start: int = Field(ge=0, le=2**31 - 1, description="Vị trí code point Unicode tính từ 0.")
    quote: str = Field(min_length=1, max_length=10000)

    @field_validator("current_state", mode="before")
    @classmethod
    def validate_current_state(cls, value):
        """只清理关系值的首尾空白，保留原文引文。

        Args:
            value: 模型建议的关系当前状态。
        Returns:
            首尾去空白后的字符串；其他类型交由严格字段检查拒绝。
        """
        return value.strip() if isinstance(value, str) else value


class ChapterCharacterRelationStateCheckResultV1(StrictResponseModel):
    "Câu hỏi dành cho tác giả đọc; không có thay đổi đáng tin thì đề xuất là null."

    issues: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(max_length=50)
    suggestion: ChapterCharacterRelationStateCheckSuggestionV1 | None


class ChapterCharacterRelationStateCheckSuggestionV2(ChapterCharacterRelationStateCheckSuggestionV1):
    """新版建议交给作者准备事实时，关系值和引文都原样保留。"""

    @field_validator("current_state", mode="before")
    @classmethod
    def validate_current_state(cls, value):
        """仅拒绝空白关系值，不改写建议中的任何字符。

        Args:
            value: 模型建议的关系当前状态。
        Returns:
            原样建议；非字符串由严格字段检查拒绝。
        """
        if isinstance(value, str) and not value.strip():
            raise ValueError("Gợi ý quan hệ không được để trống")
        return value


class ChapterCharacterRelationStateCheckResultV2(ChapterCharacterRelationStateCheckResultV1):
    "Kiểm tra quan hệ bản mới giữ nguyên định dạng câu hỏi và trích dẫn, chỉ thay đổi cách xử lý khoảng trắng của giá trị đề xuất."

    suggestion: ChapterCharacterRelationStateCheckSuggestionV2 | None


class ChapterWorldRuleSelectionV1(StrictRequestModel):
    "Một quy tắc thế giới do tác giả chọn rõ cùng phiên bản gốc của nó."

    rule_id: str = Field(pattern=r"^rule_[0-9]{6,}$")
    expected_version: int = Field(ge=1, le=2**63 - 2)


class ChapterWorldRulesCheckInputV1(StrictRequestModel):
    "Cố định một bản chỉnh sửa chương cùng một đến năm quy tắc; không nhận nội dung quy tắc hay sửa đổi thực thể."

    novel_id: ObjectIdString
    source: ChapterCheckSourceV1
    rules: list[ChapterWorldRuleSelectionV1] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def require_unique_rules(self) -> "ChapterWorldRulesCheckInputV1":
        """拒绝重复选定同一规则。

        Args:
            无。
        Returns:
            规则身份唯一的固定输入。
        """
        if len({rule.rule_id for rule in self.rules}) != len(self.rules):
            raise ValueError("Các quy tắc thế giới đã chọn không được trùng lặp")
        return self


class ChapterWorldRulesCheckIssueV1(StrictResponseModel):
    "Mô hình chỉ cung cấp các điểm nghi vấn, số quy tắc đã chọn và trích dẫn chương gốc."

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    text: str = Field(min_length=1, max_length=2000)
    rule_ids: list[Annotated[str, Field(pattern=r"^rule_[0-9]{6,}$")]] = Field(min_length=1, max_length=5)
    start: int = Field(ge=0, le=2**31 - 1, description="Vị trí code point Unicode tính từ 0, không phải chỉ số UTF-16.")
    quote: str = Field(min_length=1, max_length=10000)

    @field_validator("text", mode="before")
    @classmethod
    def trim_text(cls, value):
        """只清理疑点文字的首尾空白，引文保持原样。

        Args:
            value: 模型返回的疑点文字。
        Returns:
            首尾去空白后的字符串；非字符串由严格字段校验拒绝。
        """
        return value.strip() if isinstance(value, str) else value

    @field_validator("rule_ids")
    @classmethod
    def require_unique_rule_ids(cls, value):
        """拒绝疑点内重复的规则编号。

        Args:
            value: 当前疑点引用的规则编号。
        Returns:
            不重复的规则编号。
        """
        if len(set(value)) != len(value):
            raise ValueError("Các quy tắc thế giới dẫn chiếu trong nghi vấn không được trùng lặp")
        return value


class ChapterWorldRulesCheckResultV1(StrictResponseModel):
    "Mảng rỗng chỉ có nghĩa trong phạm vi các quy tắc đã chọn không có điểm nghi vấn nào được báo cáo."

    issues: list[ChapterWorldRulesCheckIssueV1] = Field(max_length=10)
