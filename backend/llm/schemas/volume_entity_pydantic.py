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
    """两个卷内实体任务共用的作者选择。"""

    new_count: int = Field(default=2, ge=0, le=20)
    selection_mode: Literal["manual", "auto"] = "manual"
    selected_existing_ids: list[EntityId] = Field(default_factory=list, max_length=20)
    user_guidance: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_selection(self) -> "VolumeEntityParametersV1":
        """限制本批总量并拒绝重复选择已有档案。"""
        if len(self.selected_existing_ids) != len(set(self.selected_existing_ids)):
            raise ValueError("已有档案不能重复选择")
        minimum = 0 if self.selection_mode == "auto" else 1
        if not minimum <= self.new_count + len(self.selected_existing_ids) <= 20:
            raise ValueError("新建数量与已有档案数量合计必须为 1..20")
        return self


class VolumeEntityGenerateRequestV1(ReasoningOptions, VolumeEntityParametersV1):
    """普通请求及任务图使用的卷内实体生成参数。"""

    volume_expected_version: int = Field(ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    system_prompt: str | None = Field(default=None, max_length=40000)
    use_stream: bool = True


class VolumeEntityGenerationInputV1(VolumeEntityParametersV1):
    """确认时重新读取当前卷和所选档案的原始输入。"""

    novel_id: ObjectIdString
    volume_id: ObjectIdString
    volume_expected_version: int = Field(ge=1)


class VolumeCharacterProfileV1(CharacterCreateRequestV1):
    """本卷新增人物沿用档案字段，始终为非核心人物。"""

    is_core_character: Literal[False] = False


class VolumeFactionProfileV1(FactionCreateRequestV1):
    """本卷新增势力只允许 volume 或 local，父势力可选。"""

    level_type: Literal["volume", "local"] = "volume"
    first_appearance_volume_id: None = None
    first_appearance_chapter_id: None = None

    @model_validator(mode="after")
    def validate_scope_fields(self) -> "VolumeFactionProfileV1":
        """候选可省略归属卷；确认时只能使用路径指定的当前卷。"""
        return self


class VolumeCharacterCandidateV1(StrictRequestModel):
    """一条新人物或已有档案的当前卷状态候选。"""

    candidate_ref: CandidateRef
    character_id: CharacterId | None = None
    profile: VolumeCharacterProfileV1 | None = None
    state: CharacterVolumeStateFieldsV1
    state_expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_target(self) -> "VolumeCharacterCandidateV1":
        """新人物需提供档案；已有人物只接受卷状态。"""
        if (self.character_id is None) == (self.profile is None):
            raise ValueError("新人物必须提供 profile，已有角色只能提供 character_id")
        if self.character_id is None and self.state_expected_version is not None:
            raise ValueError("新人物不能指定已有卷状态版本")
        return self


class VolumeFactionCandidateV1(StrictRequestModel):
    """一条新势力或已有档案的当前卷状态候选。"""

    candidate_ref: CandidateRef
    faction_id: EntityId | None = None
    profile: VolumeFactionProfileV1 | None = None
    state: FactionVolumeStateFieldsV1
    state_expected_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_target(self) -> "VolumeFactionCandidateV1":
        """新势力需提供档案；已有势力只接受卷状态。"""
        if (self.faction_id is None) == (self.profile is None):
            raise ValueError("新势力必须提供 profile，已有势力只能提供 faction_id")
        if self.faction_id is None and self.state_expected_version is not None:
            raise ValueError("新势力不能指定已有卷状态版本")
        return self


class GeneratedVolumeFactionCandidateV1(VolumeFactionCandidateV1):
    """新生成候选只传出模型明确给出的实际值；旧确认模型保持不变。"""

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
    """模型返回的卷内势力候选。"""

    factions: list[GeneratedVolumeFactionCandidateV1] = Field(max_length=20)


class VolumeEntityBasisV1(CandidateBasisV1):
    """保留原图、当前卷和所用档案／卷状态版本的依据。"""

    generation_input: VolumeEntityGenerationInputV1
    content_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_volume_basis(self) -> "VolumeEntityBasisV1":
        """确保原图、小说、卷及版本属于同一个卷内任务。"""
        kind = VOLUME_ENTITY_TASKS.get(self.workflow)
        if kind is None or self.step != f"create_{kind}_for_volume" or self.schema_id != f"volume_{kind}_result" or self.schema_version != 1:
            raise ValueError("卷内实体候选任务不一致")
        if self.novel_id != self.generation_input.novel_id or self.flow_snapshot is None:
            raise ValueError("卷内实体候选缺少原始流程或小说不一致")
        if self.flow_snapshot["scope"].get("volume_id") != self.generation_input.volume_id:
            raise ValueError("原始流程与候选的目标卷不一致")
        refs = {(ref.resource_type, ref.id): ref.version for ref in self.source_refs}
        volume_version = refs.get(("volume", self.generation_input.volume_id))
        if ("novel", self.novel_id) not in refs or volume_version is None or (self.generation_input.selection_mode != "auto" and volume_version != self.generation_input.volume_expected_version):
            raise ValueError("卷内实体候选缺少当前小说或目标卷版本")
        return self


class VolumeFactionsPreviewV1(StrictResponseModel):
    """普通响应与 SSE 完成事件使用的卷内势力信封。"""

    workflow: Literal["create_factions_for_volume_by_ai"]
    step: Literal["create_factions_for_volume"]
    schema_id: Literal["volume_factions_result"]
    schema_version: Literal[1]
    candidate: VolumeFactionsResultV1
    basis: VolumeEntityBasisV1


class VolumeCharactersLegacyResultV1(StrictRequestModel):
    """旧确认入口的完整候选结构；不用于当前生成或预览。"""

    characters: list[VolumeCharacterCandidateV1] = Field(max_length=20)


class VolumeCharactersConfirmV1(StrictRequestModel):
    """作者审核后确认的当前卷人物列表和原始依据。"""

    candidates: list[VolumeCharacterCandidateV1] = Field(max_length=20)
    basis: VolumeEntityBasisV1


class VolumeCharacterPlanProfileV1(CharacterFactCreateDataV1):
    """新卷人物的设计资料；实际事实仅由 initial_facts 提交。"""

    is_core_character: Literal[False] = False

    @model_serializer(mode="wrap")
    def serialize_present_values(self, handler):
        """预览补齐非事实设计字段；实际事实仍只存在于独立的稀疏对象。"""
        return handler(self)


class VolumeCharacterPlanCandidateV1(VolumeCharacterCandidateV1):
    """采用本卷计划；新人物的明确初始状态单独保存。"""

    state: CharacterVolumePlanFieldsV1
    initial_facts: CharacterFactValuesV1 | None = None

    @model_validator(mode="after")
    def new_character_only(self) -> "VolumeCharacterPlanCandidateV1":
        """已有角色的计划不能顺便覆盖事实。"""
        if self.character_id is not None and self.initial_facts is not None:
            raise ValueError("已有角色的本卷计划不接受实际状态修改")
        return self


class VolumeCharactersPlanResultV1(StrictRequestModel):
    """六字段计划确认的候选集合。"""

    characters: list[VolumeCharacterPlanCandidateV1] = Field(max_length=20)


class VolumeCharacterInitialFactsCandidateV1(VolumeCharacterPlanCandidateV1):
    """独立的新合同：设计档案与明确初始事实分开，不改变旧计划请求。"""

    profile: VolumeCharacterPlanProfileV1 | None = None

    @model_validator(mode="after")
    def require_initial_facts(self):
        if self.profile is not None and (self.initial_facts is None or not self.initial_facts.model_dump()):
            raise ValueError("新角色至少需要一项明确的初始事实；未知事实不能用空值补齐")
        return self


class VolumeCharactersInitialFactsResultV1(StrictRequestModel):
    characters: list[VolumeCharacterInitialFactsCandidateV1] = Field(max_length=20)


class VolumeCharactersPreviewV1(StrictResponseModel):
    """普通响应与 SSE 完成事件使用的卷内人物信封。"""

    workflow: Literal["create_characters_for_volume_by_ai"]
    step: Literal["create_characters_for_volume"]
    schema_id: Literal["volume_characters_result"]
    schema_version: Literal[1]
    contract: Literal["character_plan_initial_facts_v1"]
    candidate: VolumeCharactersInitialFactsResultV1
    basis: VolumeEntityBasisV1


class _GeneratedCharacterInitialFacts(StrictRequestModel):
    """模型传输专用：null 表示未知，预览和确认只保留明确的事实值。"""

    @model_serializer(mode="wrap")
    def serialize_known_values(self, handler):
        return {field: value for field, value in handler(self).items() if value is not None}


# 复用事实字段的类型与长度约束，但不把禁止显式 null 的确认合同用作模型协议。
GeneratedCharacterInitialFactsV1 = create_model(
    "GeneratedCharacterInitialFactsV1", __base__=_GeneratedCharacterInitialFacts,
    **{name: (field.annotation, deepcopy(field)) for name, field in CharacterFactValuesV1.model_fields.items()},
)


class GeneratedVolumeCharacterPlanCandidateV1(VolumeCharacterInitialFactsCandidateV1):
    """仅在模型响应边界接收未知标记，不接收旧 state 事实字段。"""

    initial_facts: GeneratedCharacterInitialFactsV1 | None = None


class VolumeCharactersResultV1(StrictRequestModel):
    """人物生成采用卷计划语义，未知初始事实在序列化时保持省略。"""

    characters: list[GeneratedVolumeCharacterPlanCandidateV1] = Field(max_length=20)


class VolumeCharactersPlanConfirmV1(StrictRequestModel):
    """新保存显式采用计划合同，旧九字段原请求仍独立处理。"""

    contract: Literal["participation_plan_v1"]
    candidates: list[VolumeCharacterPlanCandidateV1] = Field(max_length=20)
    basis: VolumeEntityBasisV1


class VolumeCharactersInitialFactsConfirmV1(StrictRequestModel):
    """新生成合同有独立身份；原 v1 的输入、摘要及执行保持原样。"""

    contract: Literal["character_plan_initial_facts_v1"]
    candidates: list[VolumeCharacterInitialFactsCandidateV1] = Field(max_length=20)
    basis: VolumeEntityBasisV1

    @model_validator(mode="after")
    def require_generation_contract(self):
        if self.basis.flow_snapshot["execution"].get("character_candidate_contract") != CHARACTER_PLAN_CONTRACT:
            raise ValueError("新人物计划需要同合同的原始生成依据")
        return self


class VolumeFactionsConfirmV1(StrictRequestModel):
    """作者审核后确认的当前卷势力列表和原始依据。"""

    candidates: list[VolumeFactionCandidateV1] = Field(max_length=20)
    basis: VolumeEntityBasisV1


class VolumeFactionPlanCandidateV1(VolumeFactionCandidateV1):
    """卷内新势力的明确事实与参与计划分别保存。"""

    state: FactionVolumePlanFieldsV1
    initial_facts: FactionFactValuesV1 | None = None

    @model_validator(mode="after")
    def new_faction_only(self) -> "VolumeFactionPlanCandidateV1":
        """已有势力只改卷计划，不借计划确认覆盖当前事实。"""
        if self.faction_id is not None and self.initial_facts is not None:
            raise ValueError("已有势力的参与计划不接受实际剧情状态修改")
        return self


class VolumeFactionsPlanResultV1(StrictRequestModel):
    """卷内势力参与计划候选。"""

    factions: list[VolumeFactionPlanCandidateV1] = Field(max_length=20)


class VolumeFactionsPlanConfirmV1(StrictRequestModel):
    """新保存采用计划合同；旧未知请求不得偷偷升级。"""

    contract: Literal["participation_plan_v1"]
    candidates: list[VolumeFactionPlanCandidateV1] = Field(max_length=20)
    basis: VolumeEntityBasisV1


class VolumeCharactersConfirmedV1(StrictResponseModel):
    """已保存人物卷状态及候选到正式人物 ID 的映射。"""

    novel_id: ObjectIdString
    volume_id: ObjectIdString
    data: list[CharacterVolumeStateReadV1]
    mapping: dict[str, str]


class VolumeFactionsConfirmedV1(StrictResponseModel):
    """已保存势力卷状态及候选到正式势力 ID 的映射。"""

    novel_id: ObjectIdString
    volume_id: ObjectIdString
    data: list[FactionVolumeReadV1]
    mapping: dict[str, str]
