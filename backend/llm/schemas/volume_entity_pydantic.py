"""卷内人物、势力的新档案和参与状态候选契约。"""

from __future__ import annotations

from copy import deepcopy
from typing import Annotated, Literal

from pydantic import Field, create_model, model_validator, model_serializer

from backend.llm.generation_options import ReasoningOptions
from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.llm.schemas.character_pydantic import CharacterCreateRequestV1
from backend.llm.schemas.character_volume_state_pydantic import CharacterId, CharacterVolumePlanFieldsV1, CharacterVolumeStateFieldsV1, CharacterVolumeStateReadV1
from backend.services.novel.character_fact_contract import CharacterFactCreateDataV1, CharacterFactValuesV1
from backend.llm.schemas.faction_creation_pydantic import FactionCreateRequestV1
from backend.llm.schemas.faction_volume_state_pydantic import FactionVolumeStateFieldsV1, FactionVolumePlanFieldsV1, FactionVolumeReadV1
from backend.services.novel.faction_fact_contract import FactionFactValuesV1
from backend.services.llm.candidate_contract import CandidateBasisV1


VOLUME_ENTITY_TASKS = {
    "create_characters_for_volume_by_ai": "characters",
    "create_factions_for_volume_by_ai": "factions",
}
CandidateRef = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
EntityId = Annotated[str, Field(min_length=5, max_length=100)]
CHARACTER_PLAN_CONTRACT = "character_plan_initial_facts_v1"


class VolumeEntityParametersV1(StrictRequestModel):
    "Lựa chọn của tác giả dùng chung cho hai nhiệm vụ thực thể trong quyển."

    new_count: int = Field(default=2, ge=0, le=20)
    selection_mode: Literal["manual", "auto"] = "manual"
    selected_existing_ids: list[EntityId] = Field(default_factory=list, max_length=20)
    user_guidance: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_selection(self) -> "VolumeEntityParametersV1":
        """限制本批总量并拒绝重复选择已有档案。"""
        if len(self.selected_existing_ids) != len(set(self.selected_existing_ids)):
            raise ValueError("Hồ sơ đã có không được chọn lặp")
        minimum = 0 if self.selection_mode == "auto" else 1
        if not minimum <= self.new_count + len(self.selected_existing_ids) <= 20:
            raise ValueError("Tổng số lượng tạo mới và số hồ sơ đã có phải nằm trong 1..20")
        return self


class VolumeEntityGenerateRequestV1(ReasoningOptions, VolumeEntityParametersV1):
    "Tham số sinh thực thể trong quyển dùng cho yêu cầu thường và đồ thị tác vụ."

    volume_expected_version: int = Field(ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40000)
    use_stream: bool = True


class VolumeEntityGenerationInputV1(VolumeEntityParametersV1):
    "Đầu vào gốc đọc lại quyển hiện tại và hồ sơ đã chọn vào lúc xác nhận."

    novel_id: ObjectIdString
    volume_id: ObjectIdString
    volume_expected_version: int = Field(ge=1)


class VolumeCharacterProfileV1(CharacterCreateRequestV1):
    "Nhân vật mới trong tập dùng lại trường hồ sơ, luôn là nhân vật không lõi."

    is_core_character: Literal[False] = False


class VolumeFactionProfileV1(FactionCreateRequestV1):
    "Thế lực mới trong tập chỉ cho phép volume hoặc local, thế lực cha là tùy chọn."

    level_type: Literal["volume", "local"] = "volume"
    first_appearance_volume_id: None = None
    first_appearance_chapter_id: None = None

    @model_validator(mode="after")
    def validate_scope_fields(self) -> "VolumeFactionProfileV1":
        """候选可省略归属卷；确认时只能使用路径指定的当前卷。"""
        return self


class VolumeCharacterCandidateV1(StrictRequestModel):
    "Một ứng viên trạng thái quyển hiện tại cho nhân vật mới hoặc hồ sơ đã có."

    candidate_ref: CandidateRef
    character_id: CharacterId | None = None
    profile: VolumeCharacterProfileV1 | None = None
    state: CharacterVolumeStateFieldsV1
    state_expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_target(self) -> "VolumeCharacterCandidateV1":
        """新人物需提供档案；已有人物只接受卷状态。"""
        if (self.character_id is None) == (self.profile is None):
            raise ValueError("Nhân vật mới phải cung cấp profile, nhân vật đã có chỉ được cung cấp character_id")
        if self.character_id is None and self.state_expected_version is not None:
            raise ValueError("Nhân vật mới không được chỉ định phiên bản trạng thái quyển đã có")
        return self


class VolumeFactionCandidateV1(StrictRequestModel):
    "Một ứng viên trạng thái quyển hiện tại cho thế lực mới hoặc hồ sơ đã có."

    candidate_ref: CandidateRef
    faction_id: EntityId | None = None
    profile: VolumeFactionProfileV1 | None = None
    state: FactionVolumeStateFieldsV1
    state_expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_target(self) -> "VolumeFactionCandidateV1":
        """新势力需提供档案；已有势力只接受卷状态。"""
        if (self.faction_id is None) == (self.profile is None):
            raise ValueError("Thế lực mới phải cung cấp profile, thế lực đã có chỉ được cung cấp faction_id")
        if self.faction_id is None and self.state_expected_version is not None:
            raise ValueError("Thế lực mới không được chỉ định phiên bản trạng thái quyển đã có")
        return self


class GeneratedVolumeFactionCandidateV1(VolumeFactionCandidateV1):
    "Ứng viên mới sinh chỉ truyền ra giá trị thực mà mô hình đưa rõ; mô hình xác nhận cũ giữ nguyên."

    @model_serializer(mode="wrap")
    def preserve_explicit_facts(self, handler):
        """跨预览、修复与助手序列化保留字段是否提供，不把默认空值登记为事实。"""
        from backend.services.novel.faction_fact_contract import FACTION_FACT_FIELDS
        result = handler(self)
        for field in ("power_level", "resources", "public_stance", "influence_scope", "active_status"):
            if field not in self.state.model_fields_set:
                result["state"].pop(field, None)
        if self.profile is not None:
            for field in FACTION_FACT_FIELDS:
                if field not in self.profile.model_fields_set:
                    result["profile"].pop(field, None)
        return result


class VolumeFactionsResultV1(StrictRequestModel):
    "Ứng viên thế lực trong quyển do mô hình trả về."

    factions: list[GeneratedVolumeFactionCandidateV1] = Field(max_length=20)


class VolumeEntityBasisV1(CandidateBasisV1):
    "Căn cứ giữ lại đồ thị gốc, quyển hiện tại cùng phiên bản hồ sơ/trạng thái quyển đã dùng."

    generation_input: VolumeEntityGenerationInputV1
    content_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_volume_basis(self) -> "VolumeEntityBasisV1":
        """确保原图、小说、卷及版本属于同一个卷内任务。"""
        kind = VOLUME_ENTITY_TASKS.get(self.workflow)
        if kind is None or self.step != f"create_{kind}_for_volume" or self.schema_id != f"volume_{kind}_result" or self.schema_version != 1:
            raise ValueError("Tác vụ ứng viên thực thể trong quyển không nhất quán")
        if self.novel_id != self.generation_input.novel_id or self.flow_snapshot is None:
            raise ValueError("Ứng viên thực thể trong quyển thiếu luồng gốc hoặc tiểu thuyết không nhất quán")
        if self.flow_snapshot["scope"].get("volume_id") != self.generation_input.volume_id:
            raise ValueError("Quyển đích của luồng gốc và của ứng viên không nhất quán")
        refs = {(ref.resource_type, ref.id): ref.version for ref in self.source_refs}
        volume_version = refs.get(("volume", self.generation_input.volume_id))
        if ("novel", self.novel_id) not in refs or volume_version is None or (self.generation_input.selection_mode != "auto" and volume_version != self.generation_input.volume_expected_version):
            raise ValueError("Ứng viên thực thể trong quyển thiếu tiểu thuyết hiện tại hoặc phiên bản quyển đích")
        return self


class VolumeFactionsPreviewV1(StrictResponseModel):
    "Bao thế lực trong quyển, dùng chung cho phản hồi thường và sự kiện hoàn tất SSE."

    workflow: Literal["create_factions_for_volume_by_ai"]
    step: Literal["create_factions_for_volume"]
    schema_id: Literal["volume_factions_result"]
    schema_version: Literal[1]
    candidate: VolumeFactionsResultV1
    basis: VolumeEntityBasisV1


class VolumeCharactersLegacyResultV1(StrictRequestModel):
    "Cấu trúc ứng viên đầy đủ của cửa xác nhận cũ; không dùng cho tạo sinh hay xem trước hiện tại."

    characters: list[VolumeCharacterCandidateV1] = Field(max_length=20)


class VolumeCharactersConfirmV1(StrictRequestModel):
    "Danh sách nhân vật và căn cứ gốc của quyển hiện tại đã được tác giả duyệt rồi xác nhận."

    candidates: list[VolumeCharacterCandidateV1] = Field(max_length=20)
    basis: VolumeEntityBasisV1


class VolumeCharacterPlanProfileV1(CharacterFactCreateDataV1):
    "Tư liệu thiết kế nhân vật của tập mới; dữ kiện thực tế chỉ được gửi qua initial_facts."

    is_core_character: Literal[False] = False

    @model_serializer(mode="wrap")
    def serialize_present_values(self, handler):
        """预览补齐非事实设计字段；实际事实仍只存在于独立的稀疏对象。"""
        return handler(self)


class VolumeCharacterPlanCandidateV1(VolumeCharacterCandidateV1):
    "Áp dụng kế hoạch của tập; trạng thái ban đầu rõ ràng của nhân vật mới lưu riêng."

    state: CharacterVolumePlanFieldsV1
    initial_facts: CharacterFactValuesV1 | None = None

    @model_validator(mode="after")
    def new_character_only(self) -> "VolumeCharacterPlanCandidateV1":
        """已有角色的计划不能顺便覆盖事实。"""
        if self.character_id is not None and self.initial_facts is not None:
            raise ValueError("Kế hoạch quyển này của nhân vật đã có không chấp nhận sửa trạng thái thực tế")
        return self


class VolumeCharactersPlanResultV1(StrictRequestModel):
    "Tập hợp ứng viên cho xác nhận kế hoạch sáu trường."

    characters: list[VolumeCharacterPlanCandidateV1] = Field(max_length=20)


class VolumeCharacterInitialFactsCandidateV1(VolumeCharacterPlanCandidateV1):
    "Hợp đồng mới độc lập: tách hồ sơ thiết kế khỏi dữ kiện ban đầu rõ ràng, không thay đổi request kế hoạch cũ."

    profile: VolumeCharacterPlanProfileV1 | None = None

    @model_validator(mode="after")
    def require_initial_facts(self):
        if self.profile is not None and (self.initial_facts is None or not self.initial_facts.model_dump()):
            raise ValueError("Nhân vật mới cần ít nhất một dữ kiện khởi tạo rõ ràng; dữ kiện chưa biết không được điền giá trị rỗng")
        return self


class VolumeCharactersInitialFactsResultV1(StrictRequestModel):
    characters: list[VolumeCharacterInitialFactsCandidateV1] = Field(max_length=20)


class VolumeCharactersPreviewV1(StrictResponseModel):
    "Bao nhân vật trong quyển, dùng chung cho phản hồi thường và sự kiện hoàn tất SSE."

    workflow: Literal["create_characters_for_volume_by_ai"]
    step: Literal["create_characters_for_volume"]
    schema_id: Literal["volume_characters_result"]
    schema_version: Literal[1]
    contract: Literal["character_plan_initial_facts_v1"]
    candidate: VolumeCharactersInitialFactsResultV1
    basis: VolumeEntityBasisV1


class _GeneratedCharacterInitialFacts(StrictRequestModel):
    "Dùng riêng cho kênh truyền tới mô hình: null biểu thị chưa biết; bản xem trước và xác nhận chỉ giữ giá trị sự kiện minh thị."

    @model_serializer(mode="wrap")
    def serialize_known_values(self, handler):
        return {field: value for field, value in handler(self).items() if value is not None}


# 复用事实字段的类型与长度约束，但不把禁止显式 null 的确认合同用作模型协议。
GeneratedCharacterInitialFactsV1 = create_model(
    "GeneratedCharacterInitialFactsV1", __base__=_GeneratedCharacterInitialFacts,
    **{name: (field.annotation, deepcopy(field)) for name, field in CharacterFactValuesV1.model_fields.items()},
)


class GeneratedVolumeCharacterPlanCandidateV1(VolumeCharacterInitialFactsCandidateV1):
    "Chỉ nhận ký hiệu chưa xác định ở ranh giới phản hồi của mô hình, không nhận trường dữ kiện state cũ."

    initial_facts: GeneratedCharacterInitialFactsV1 | None = None


class VolumeCharactersResultV1(StrictRequestModel):
    "Tạo nhân vật áp dụng ngữ nghĩa kế hoạch quyển; sự kiện ban đầu chưa biết vẫn để lược khi tuần tự hóa."

    characters: list[GeneratedVolumeCharacterPlanCandidateV1] = Field(max_length=20)


class VolumeCharactersPlanConfirmV1(StrictRequestModel):
    "Bản lưu mới minh thị áp dụng hợp đồng kế hoạch; yêu cầu gốc chín trường kiểu cũ vẫn xử lý riêng."

    contract: Literal["participation_plan_v1"]
    candidates: list[VolumeCharacterPlanCandidateV1] = Field(max_length=20)
    basis: VolumeEntityBasisV1


class VolumeCharactersInitialFactsConfirmV1(StrictRequestModel):
    "Hợp đồng tạo sinh mới có định danh riêng; đầu vào, tóm tắt và cách thực thi của bản v1 gốc giữ nguyên."

    contract: Literal["character_plan_initial_facts_v1"]
    candidates: list[VolumeCharacterInitialFactsCandidateV1] = Field(max_length=20)
    basis: VolumeEntityBasisV1

    @model_validator(mode="after")
    def require_generation_contract(self):
        if self.basis.flow_snapshot["execution"].get("character_candidate_contract") != CHARACTER_PLAN_CONTRACT:
            raise ValueError("Kế hoạch nhân vật mới cần căn cứ tạo gốc cùng hợp đồng")
        return self


class VolumeFactionsConfirmV1(StrictRequestModel):
    "Danh sách thế lực và căn cứ gốc của quyển hiện tại đã được tác giả duyệt rồi xác nhận."

    candidates: list[VolumeFactionCandidateV1] = Field(max_length=20)
    basis: VolumeEntityBasisV1


class VolumeFactionPlanCandidateV1(VolumeFactionCandidateV1):
    "Dữ kiện rõ ràng và kế hoạch tham gia của thế lực mới trong tập lưu riêng biệt."

    state: FactionVolumePlanFieldsV1
    initial_facts: FactionFactValuesV1 | None = None

    @model_validator(mode="after")
    def new_faction_only(self) -> "VolumeFactionPlanCandidateV1":
        """已有势力只改卷计划，不借计划确认覆盖当前事实。"""
        if self.faction_id is not None and self.initial_facts is not None:
            raise ValueError("Kế hoạch tham gia của thế lực đã có không chấp nhận sửa trạng thái cốt truyện thực tế")
        return self


class VolumeFactionsPlanResultV1(StrictRequestModel):
    "Ứng viên thế lực trong quyển tham gia kế hoạch."

    factions: list[VolumeFactionPlanCandidateV1] = Field(max_length=20)


class VolumeFactionsPlanConfirmV1(StrictRequestModel):
    "Bản lưu mới dùng hợp đồng kế hoạch; yêu cầu cũ không rõ ràng không được âm thầm nâng cấp."

    contract: Literal["participation_plan_v1"]
    candidates: list[VolumeFactionPlanCandidateV1] = Field(max_length=20)
    basis: VolumeEntityBasisV1


class VolumeCharactersConfirmedV1(StrictResponseModel):
    "Trạng thái quyển của nhân vật đã lưu cùng ánh xạ từ ứng viên sang ID nhân vật chính thức."

    novel_id: ObjectIdString
    volume_id: ObjectIdString
    data: list[CharacterVolumeStateReadV1]
    mapping: dict[str, str]


class VolumeFactionsConfirmedV1(StrictResponseModel):
    "Trạng thái quyển của thế lực đã lưu cùng ánh xạ từ ứng viên sang ID thế lực chính thức."

    novel_id: ObjectIdString
    volume_id: ObjectIdString
    data: list[FactionVolumeReadV1]
    mapping: dict[str, str]
