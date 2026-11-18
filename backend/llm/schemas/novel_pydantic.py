from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from backend.llm.generation_options import ReasoningOptions
from backend.llm.schemas.character_pydantic import FACTION_BUSINESS_ID_PATTERN
from backend.services.llm.candidate_contract import (
    MAX_CANDIDATE_SOURCE_REFS,
    CandidateBasisV1,
)


CORE_FACTIONS_RESULT_SCHEMA_ID = "faction.core_generation.result"
CORE_FACTIONS_RESULT_SCHEMA_VERSION = 2
CORE_FACTION_REF_PATTERN = r"^faction_[0-9]{3}$"
CORE_FACTION_RELATION_REF_PATTERN = r"^relation_[0-9]{3}$"


class ExpandIdeaSchema(BaseModel):
    """
    将用户创意扩写为完整长篇小说压缩故事
    """
    model_config = ConfigDict(extra="forbid")

    plot: str = Field(
        ...,
        min_length=200,
        max_length=5000,
        description="Toàn bộ văn bản chính của câu chuyện dạng dài được rút gọn, khoảng 3000 chữ"
    )


class ExtractIdeaSchema(BaseModel):
    """
    从扩展剧情中提炼出的故事构思要素
    """
    model_config = ConfigDict(extra="forbid")

    genre: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="Thể loại tiểu thuyết, ví dụ huyền huyễn, khoa học viễn tưởng, đô thị, huyền nghi, lịch sử, tiên hiệp, v.v."
    )
    tone: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="Giọng điệu tổng thể, ví dụ nhiệt huyết, dark, nhẹ nhàng, hài hước, chữa lành, u ám, v.v."
    )
    target_audience: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="Nhóm độc giả mục tiêu, ví dụ dành cho nam, dành cho nữ, thanh thiếu niên, độc giả fantasy đại chúng, v.v."
    )
    core_idea: str = Field(
        ...,
        min_length=10,
        max_length=300,
        description="Mô tả ý tưởng cốt lõi của câu chuyện bằng 1-2 câu"
    )


class CoreSeedSchema(BaseModel):
    """
    雪花写作法第一步生成的故事核心公式
    """
    model_config = ConfigDict(extra="forbid")

    core_seed: str = Field(
        ...,
        min_length=30,
        max_length=150,
        description="Công thức cốt lõi của câu chuyện, cần gồm xung đột hiển tính, khủng hoảng tiềm ẩn, động lực cốt lõi của nhân vật và gợi ý mâu thuẫn then chốt của thế giới quan, dài 30-100 chữ"
    )


class NovelMetaSchema(BaseModel):
    """
    小说整体设定
    """
    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="Tên chính của tiểu thuyết, có sức hút và dễ lan truyền, hợp thị hiếu độc giả thể loại"
    )
    subtitle: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Phụ đề, bổ trợ xung đột cốt lõi hoặc chủ đề, có chất văn chương hoặc thương mại"
    )
    introduction: str = Field(
        ...,
        min_length=100,
        max_length=300,
        description="Lời dẫn của tiểu thuyết, 100-300 chữ, dẫn nhập câu chuyện, khơi gợi hứng thú đọc"
    )
    summary: str = Field(
        ...,
        min_length=100,
        max_length=500,
        description="Giới thiệu tiểu thuyết, 100-500 chữ, cần thể hiện rõ xung đột tuyến chính và tình tiết treo"
    )
    worldview: str = Field(
        ...,
        min_length=100,
        max_length=800,
        description="Thiết lập thế giới quan, giải thích quy tắc thế giới, hệ thống sức mạnh, cấu trúc xã hội, v.v., tối thiểu 100 chữ"
    )
    writing_style: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Phong cách sáng tác, ví dụ dark hiện thực, nhẹ nhàng hài hước, sử thi hoành tráng, v.v."
    )
    narrative_pov: Literal["第一人称", "第三人称有限视角", "全知视角"] = Field(
        ...,
        description="Góc nhìn kể chuyện, chỉ được là một trong: ngôi thứ nhất, góc nhìn hạn tri ngôi thứ ba, góc nhìn toàn tri"
    )
    era_background: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Bối cảnh thời đại, ví dụ cổ đại hư cấu, tương lai liên sao, đô thị hiện đại, hậu tận thế hoang vu, v.v."
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Thẻ của tiểu thuyết, 3-5 thẻ, tóm tắt các nguyên tố cốt lõi, ví dụ khoa học viễn tưởng nặng, phiêu lưu, tình cảm, v.v."
    )


FactionRelationType = Literal[
    "hostile",
    "allied",
    "cold_war",
    "dependent",
    "subordinate",
    "trade_partner",
    "secret_cooperation",
    "historical_enemy",
]


class CoreFactionSchema(BaseModel):
    """
    全书级核心阵营生成结果。
    """
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    faction_ref: str = Field(
        ...,
        pattern=CORE_FACTION_REF_PATTERN,
        description="Tham chiếu ổn định trong lô ứng viên lần này, ví dụ faction_001",
    )
    name: str = Field(..., min_length=1, max_length=80, description="Tên thế lực")
    faction_type: str = Field(..., min_length=1, max_length=80, description="Loại thế lực")
    positioning: str = Field(..., min_length=10, max_length=500, description="Vị trí của thế lực trong cấu trúc thế giới")
    public_stance: str = Field(..., min_length=5, max_length=500, description="Lập trường công khai của thế lực với bên ngoài")
    core_goal: str = Field(..., min_length=5, max_length=500, description="Mục tiêu cốt lõi thực sự của thế lực")
    hidden_goal: str = Field(default="", max_length=500, description="Mục tiêu ẩn của thế lực")
    resources_and_advantages: list[
        Annotated[str, Field(min_length=1, max_length=80)]
    ] = Field(
        ...,
        min_length=1,
        max_length=6,
        description="Nguồn tài nguyên hoặc lợi thế chính của thế lực",
    )
    organization_style: str = Field(..., min_length=5, max_length=300, description="Khí chất hoặc phong cách hành động của tổ chức")
    core_values: list[
        Annotated[str, Field(min_length=1, max_length=80)]
    ] = Field(..., min_length=1, max_length=6, description="Giá trị cốt lõi")
    conflict_with_mainline: str = Field(..., min_length=10, max_length=600, description="Quan hệ xung đột với tuyến truyện chính")
    is_public: bool = Field(default=True, description="Thế lực có tồn tại công khai hay không")
    influence_scope: str = Field(..., min_length=2, max_length=80, description="Phạm vi ảnh hưởng")
    expandability: str = Field(..., min_length=5, max_length=500, description="Hướng mở rộng về sau")
    tags: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list,
        max_length=8,
        description="Thẻ của thế lực",
    )


class CandidateFactionEndpointV2(BaseModel):
    """引用本次尚未落库势力的关系端点。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["candidate"]
    faction_ref: str = Field(pattern=CORE_FACTION_REF_PATTERN)


class ExistingFactionEndpointV2(BaseModel):
    """引用已有正式势力的关系端点。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: Literal["existing"]
    faction_id: str = Field(pattern=FACTION_BUSINESS_ID_PATTERN)


CoreFactionRelationEndpointV2: TypeAlias = Annotated[
    CandidateFactionEndpointV2 | ExistingFactionEndpointV2,
    Field(discriminator="kind"),
]


class CoreFactionRelationSchema(BaseModel):
    """
    AI 生成阶段只使用候选 ref 或正式 ID 引用端点的阵营关系。
    """
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    relation_ref: str = Field(pattern=CORE_FACTION_RELATION_REF_PATTERN)
    source: CoreFactionRelationEndpointV2
    target: CoreFactionRelationEndpointV2
    relation_type: FactionRelationType = Field(..., description="Loại quan hệ thế lực")
    current_state: str = Field(..., min_length=5, max_length=500, description="Trạng thái quan hệ hiện tại")
    core_conflict: str = Field(..., min_length=5, max_length=600, description="Mâu thuẫn cốt lõi trong quan hệ")
    hidden_tension: str = Field(default="", max_length=500, description="Căng thẳng sâu xa chưa bùng nổ")
    possible_change: str = Field(..., min_length=5, max_length=500, description="Có thể thay đổi về sau")
    intensity: int = Field(..., ge=1, le=5, description="Cường độ quan hệ, từ 1 đến 5")
    is_active: bool = Field(default=True, description="Quan hệ có đang hiệu lực hay không")

    @model_validator(mode="after")
    def validate_distinct_endpoints(self) -> "CoreFactionRelationSchema":
        """拒绝候选 ref 或正式 ID 的自引用关系。"""
        source_identity = (
            f"candidate:{self.source.faction_ref}"
            if self.source.kind == "candidate"
            else f"existing:{self.source.faction_id}"
        )
        target_identity = (
            f"candidate:{self.target.faction_ref}"
            if self.target.kind == "candidate"
            else f"existing:{self.target.faction_id}"
        )
        if source_identity == target_identity:
            raise ValueError("Quan hệ thế lực không được chỉ đến chính nó")
        return self


class CoreFactionsResultSchema(BaseModel):
    """
    全书核心阵营和阵营关系的完整生成结果。
    """
    model_config = ConfigDict(extra="forbid", strict=True)

    core_factions: list[CoreFactionSchema] = Field(
        ...,
        min_length=1,
        max_length=6,
        description="Danh sách thế lực cốt lõi cấp toàn sách",
    )
    faction_relations: list[CoreFactionRelationSchema] = Field(
        default_factory=list,
        max_length=20,
        description="Danh sách quan hệ giữa các thế lực cốt lõi",
    )

    @model_validator(mode="after")
    def validate_faction_relation_references(self) -> "CoreFactionsResultSchema":
        """校验阵营数量、名称唯一性和关系引用。

        Args:
            无。

        Returns:
            校验通过后的当前模型。

        Raises:
            ValueError: 阵营名称重复或关系自引用时抛出。
        """
        faction_refs = [faction.faction_ref for faction in self.core_factions]
        if len(faction_refs) != len(set(faction_refs)):
            raise ValueError("faction_ref của thế lực cốt lõi không được trùng lặp")

        faction_names = [faction.name for faction in self.core_factions]
        if len(faction_names) != len(set(faction_names)):
            raise ValueError("Tên thế lực cốt lõi không được trùng lặp")

        relation_refs = [relation.relation_ref for relation in self.faction_relations]
        if len(relation_refs) != len(set(relation_refs)):
            raise ValueError("relation_ref của quan hệ thế lực không được trùng lặp")

        candidate_ref_set = set(faction_refs)
        semantic_keys: list[tuple[str, str, str]] = []
        for relation in self.faction_relations:
            endpoints = (relation.source, relation.target)
            for endpoint in endpoints:
                if (
                    endpoint.kind == "candidate"
                    and endpoint.faction_ref not in candidate_ref_set
                ):
                    raise ValueError("Quan hệ thế lực tham chiếu faction_ref không tồn tại")
            source_identity = (
                f"candidate:{relation.source.faction_ref}"
                if relation.source.kind == "candidate"
                else f"existing:{relation.source.faction_id}"
            )
            target_identity = (
                f"candidate:{relation.target.faction_ref}"
                if relation.target.kind == "candidate"
                else f"existing:{relation.target.faction_id}"
            )
            if relation.relation_type in {
                "hostile",
                "allied",
                "cold_war",
                "trade_partner",
                "secret_cooperation",
                "historical_enemy",
            }:
                source_identity, target_identity = sorted(
                    (source_identity, target_identity)
                )
            semantic_keys.append(
                (source_identity, target_identity, relation.relation_type)
            )

        if len(semantic_keys) != len(set(semantic_keys)):
            raise ValueError("Quan hệ thế lực không được chứa cạnh ngữ nghĩa cùng loại bị trùng hoặc trùng ngược chiều")

        return self


class ExistingFactionRelationTargetV2(BaseModel):
    """核心势力生成时用户指定的已有正式关系端点。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    faction_id: str = Field(pattern=FACTION_BUSINESS_ID_PATTERN)
    relation_score: int = Field(ge=0, le=10)


class CoreFactionsGenerationInputV2(ReasoningOptions, BaseModel):
    """确认阶段允许回传并重算指纹的核心势力生成输入。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    novel_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    faction_count: int | None = Field(default=3, ge=1, le=6)
    independent_faction_count: int = Field(default=0, ge=0, le=6)
    user_guidance: str = Field(default="", max_length=2000)
    single_faction_integrity_score: int | None = Field(default=None, ge=0, le=10)
    connect_to_existing: bool = False
    existing_relation_targets: list[ExistingFactionRelationTargetV2] = Field(
        default_factory=list,
        max_length=12,
    )
    existing_relation_score: int | None = Field(default=None, ge=0, le=10)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40_000)

    @model_validator(mode="after")
    def validate_generation_counts(self) -> "CoreFactionsGenerationInputV2":
        """校验数量约束并拒绝重复的正式关系目标。"""
        if self.faction_count is not None and self.independent_faction_count > self.faction_count:
            raise ValueError("Số thế lực trong lô này không tạo quan hệ trực tiếp không được lớn hơn số thế lực được tạo mới lần này")
        target_ids = [target.faction_id for target in self.existing_relation_targets]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("Các thế lực hiện hữu cần tạo liên kết không được trùng lặp")
        return self


class GenerateCoreFactionsRequestV2(CoreFactionsGenerationInputV2):
    """核心势力生成 HTTP 请求，在业务输入外增加传输模式。"""

    use_stream: bool = True


class CoreFactionsAIConfirmationRequestV2(BaseModel):
    """核心势力及关系候选显式确认的严格请求。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    request_type: Literal["ai_confirmation"]
    candidate: CoreFactionsResultSchema
    selected_faction_refs: list[str] = Field(min_length=1, max_length=6)
    selected_relation_refs: list[str] = Field(default_factory=list, max_length=20)
    basis: CandidateBasisV1
    generation_input: CoreFactionsGenerationInputV2
    expected_versions: dict[str, int] = Field(
        min_length=1,
        max_length=MAX_CANDIDATE_SOURCE_REFS,
    )

    @field_validator(
        "selected_faction_refs",
        "selected_relation_refs",
        mode="before",
    )
    @classmethod
    def normalize_selected_refs(cls, value: object) -> object:
        """清理并按首次出现顺序去重候选选择引用。"""
        if not isinstance(value, list):
            return value
        normalized: list[object] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                normalized.append(item)
                continue
            cleaned = item.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                normalized.append(cleaned)
        return normalized

    @model_validator(mode="after")
    def validate_confirmation_selection(self) -> "CoreFactionsAIConfirmationRequestV2":
        """校验候选选择、依据契约和精确版本映射。"""
        if (
            self.basis.novel_id != self.generation_input.novel_id
            or self.basis.workflow != "create_factions_by_ai"
            or self.basis.step != "create_core_factions"
            or self.basis.schema_id != CORE_FACTIONS_RESULT_SCHEMA_ID
            or self.basis.schema_version != CORE_FACTIONS_RESULT_SCHEMA_VERSION
        ):
            raise ValueError("Hợp đồng basis của việc xác nhận thế lực cốt lõi không khớp")

        candidate_faction_refs = {
            faction.faction_ref for faction in self.candidate.core_factions
        }
        if any(ref not in candidate_faction_refs for ref in self.selected_faction_refs):
            raise ValueError("selected_faction_refs chứa tham chiếu không có trong các ứng viên")

        relation_by_ref = {
            relation.relation_ref: relation
            for relation in self.candidate.faction_relations
        }
        if any(ref not in relation_by_ref for ref in self.selected_relation_refs):
            raise ValueError("selected_relation_refs chứa tham chiếu không có trong các ứng viên")
        selected_factions = set(self.selected_faction_refs)
        for relation_ref in self.selected_relation_refs:
            relation = relation_by_ref[relation_ref]
            for endpoint in (relation.source, relation.target):
                if (
                    endpoint.kind == "candidate"
                    and endpoint.faction_ref not in selected_factions
                ):
                    raise ValueError("Quan hệ đã chọn tham chiếu một thế lực mới chưa được chọn")

        expected_from_basis = {
            f"{source.resource_type}:{source.id}": source.version
            for source in self.basis.source_refs
        }
        if self.expected_versions != expected_from_basis:
            raise ValueError("expected_versions phải khớp chính xác với basis.source_refs")
        return self


__all__ = [
    "CORE_FACTIONS_RESULT_SCHEMA_ID",
    "CORE_FACTIONS_RESULT_SCHEMA_VERSION",
    "CandidateFactionEndpointV2",
    "CoreFactionRelationEndpointV2",
    "CoreFactionRelationSchema",
    "CoreFactionSchema",
    "CoreFactionsGenerationInputV2",
    "CoreFactionsAIConfirmationRequestV2",
    "CoreFactionsResultSchema",
    "ExistingFactionEndpointV2",
    "ExistingFactionRelationTargetV2",
    "GenerateCoreFactionsRequestV2",
]
