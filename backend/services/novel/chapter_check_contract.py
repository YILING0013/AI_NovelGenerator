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
    """作者选定的完整不可变章修订；检查前无需先选择引文。"""

    chapter_id: ObjectIdString
    revision_id: ObjectIdString
    version: int = Field(ge=1, le=2**63 - 1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ChapterCheckInputV1(StrictRequestModel):
    """服务器固定的单章修订和同卷已有状态。"""

    novel_id: ObjectIdString
    source: ChapterCheckSourceV1
    state_id: ObjectIdString
    expected_version: int = Field(ge=1, le=2**63 - 2)


class ChapterCheckSuggestionV1(StrictResponseModel):
    """模型只能建议心理值并给出原样引文，不产生身份或版本。"""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    psychological_state: str = Field(max_length=1000)
    start: int = Field(ge=0, le=2**31 - 1, description="从零开始的 Unicode 码点位置，不是 UTF-16 下标。")
    quote: str = Field(min_length=1, max_length=10000)


class ChapterCheckResultV1(StrictResponseModel):
    """问题只供阅读；没有可靠建议时明确返回 null。"""

    issues: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(max_length=50)
    suggestion: ChapterCheckSuggestionV1 | None


class ChapterItemOwnerCheckInputV1(StrictRequestModel):
    """固定物品及持有人 A→B；模型不能改变目标或方向。"""

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
            raise ValueError("请选择不同的新持有人")
        return self


class ChapterItemOwnerCheckSuggestionV1(StrictResponseModel):
    """物品建议只带原文位置，不允许模型指定身份、版本或修改字段。"""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    start: int = Field(ge=0, le=2**31 - 1, description="从零开始的 Unicode 码点位置。")
    quote: str = Field(min_length=1, max_length=10000)


class ChapterItemOwnerCheckResultV1(StrictResponseModel):
    """模型只检查固定转交；没有明确原文时返回 null。"""

    issues: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(max_length=50)
    suggestion: ChapterItemOwnerCheckSuggestionV1 | None


class ChapterCharacterRelationStateCheckInputV1(StrictRequestModel):
    """固定一条全书关系和作者原版本，端点由服务器读取。"""

    novel_id: ObjectIdString
    source: ChapterCheckSourceV1
    relation_id: str = Field(pattern=r"^cr_[0-9]{6,19}$")
    expected_version: int = Field(ge=1, le=2**63 - 2)


class ChapterCharacterRelationStateCheckSuggestionV1(StrictResponseModel):
    """只建议当前关系状态和原文，不允许模型决定身份或其他字段。"""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    current_state: str = Field(min_length=1, max_length=2000)
    start: int = Field(ge=0, le=2**31 - 1, description="从零开始的 Unicode 码点位置。")
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
    """问题供作者阅读，没有可靠变化时建议为 null。"""

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
            raise ValueError("关系建议不能为空")
        return value


class ChapterCharacterRelationStateCheckResultV2(ChapterCharacterRelationStateCheckResultV1):
    """新版关系检查沿用问题和引文格式，只改变建议值的空白处理。"""

    suggestion: ChapterCharacterRelationStateCheckSuggestionV2 | None


class ChapterWorldRuleSelectionV1(StrictRequestModel):
    """作者明确选定的一条世界规则及其原版本。"""

    rule_id: str = Field(pattern=r"^rule_[0-9]{6,}$")
    expected_version: int = Field(ge=1, le=2**63 - 2)


class ChapterWorldRulesCheckInputV1(StrictRequestModel):
    """固定一个章修订和一至五条规则，不接受规则正文或实体修改。"""

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
            raise ValueError("所选世界规则不能重复")
        return self


class ChapterWorldRulesCheckIssueV1(StrictResponseModel):
    """模型只提供疑点、所选规则编号和原章引文。"""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=False)
    text: str = Field(min_length=1, max_length=2000)
    rule_ids: list[Annotated[str, Field(pattern=r"^rule_[0-9]{6,}$")]] = Field(min_length=1, max_length=5)
    start: int = Field(ge=0, le=2**31 - 1, description="从零开始的 Unicode 码点位置，不是 UTF-16 下标。")
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
            raise ValueError("疑点引用的世界规则不能重复")
        return value


class ChapterWorldRulesCheckResultV1(StrictResponseModel):
    """空数组仅表示所选规则范围内没有报告疑点。"""

    issues: list[ChapterWorldRulesCheckIssueV1] = Field(max_length=10)
