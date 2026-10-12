"""人物和关系的整批新建；字段缺项保持未知，原请求可直接重试。"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.llm.schemas.character_pydantic import CoreCharactersGenerationInputV1
from backend.llm.schemas.character_relation_pydantic import CharacterRelationsGenerationInputV1
from backend.services.llm.candidate_contract import CandidateBasisV1
from backend.services.novel.character_fact_contract import (
    CharacterFactCreateDataV1, CharacterFactPositionV1, CharacterFactValuesV1,
    CharacterId, FactConfirmed, FactVersion,
)
from backend.services.novel.character_relation_fact_contract import (
    CharacterRelationFactCreateDataV1, CharacterRelationFactValuesV1, CharacterRelationId,
)

CandidateRef = Annotated[str, Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,79}$")]


class CharacterBatchGenerationV1(StrictRequestModel):
    """保留原人物生成输入，不能用当前配置替换旧依据。"""

    basis: CandidateBasisV1
    generation_input: CoreCharactersGenerationInputV1


class CharacterRelationBatchGenerationV1(StrictRequestModel):
    """保留原关系生成输入及所选人物。"""

    basis: CandidateBasisV1
    generation_input: CharacterRelationsGenerationInputV1


class CharacterBatchBindingV1(StrictRequestModel):
    """新人物的初始归属；已有主归属切换仍使用原专用接口。"""

    faction_id: str = Field(pattern=r"^fac_[0-9]{6,19}$")
    faction_version: FactVersion
    membership_type: Literal["primary", "secondary", "covert"]
    role_title: str | None = Field(default=None, max_length=100)
    public_status: str | None = Field(default=None, max_length=200)
    loyalty_level: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=1000)


class CharacterBatchCandidateV1(StrictRequestModel):
    """每个人物始终按稳定引用保存，不依赖页面当前选中索引。"""

    candidate_ref: CandidateRef
    profile: CharacterFactCreateDataV1
    facts: CharacterFactValuesV1
    bindings: list[CharacterBatchBindingV1] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_actual_fields(self) -> "CharacterBatchCandidateV1":
        """不替缺失资料编造起点值。"""
        if not self.facts.model_fields_set:
            raise ValueError("请至少保留一项实际填写的人物资料")
        return self


class CharacterRelationBatchCandidateV1(StrictRequestModel):
    """关系设计和已明确的起点状态分别提交。"""

    candidate_ref: CandidateRef
    profile: CharacterRelationFactCreateDataV1
    facts: CharacterRelationFactValuesV1

    @model_validator(mode="after")
    def require_actual_state(self) -> "CharacterRelationBatchCandidateV1":
        """没有关系状态时保留原稿，不补造文字。"""
        if "current_state" not in self.facts.model_fields_set:
            raise ValueError("请填写这段关系开始时的状态")
        return self


class CharacterFactBatchCreateV1(StrictRequestModel):
    """一次采用整批人物；内部预览不需要作者逐人操作。"""

    position: CharacterFactPositionV1
    candidates: list[CharacterBatchCandidateV1] = Field(min_length=1, max_length=50)
    generation: CharacterBatchGenerationV1 | None = None
    confirmed: FactConfirmed

    @model_validator(mode="after")
    def unique_candidates(self) -> "CharacterFactBatchCreateV1":
        """重复引用无法准确恢复原请求，进入事务前即拒绝。"""
        refs = [row.candidate_ref for row in self.candidates]
        if len(refs) != len(set(refs)):
            raise ValueError("人物候选引用不能重复")
        return self


class CharacterRelationFactBatchCreateV1(StrictRequestModel):
    """一次采用整批关系，已有内容覆盖仍走原比较确认接口。"""

    position: CharacterFactPositionV1
    candidates: list[CharacterRelationBatchCandidateV1] = Field(min_length=1, max_length=500)
    generation: CharacterRelationBatchGenerationV1 | None = None
    confirmed: FactConfirmed

    @model_validator(mode="after")
    def unique_candidates(self) -> "CharacterRelationFactBatchCreateV1":
        """整批关系保留一一对应的身份。"""
        refs = [row.candidate_ref for row in self.candidates]
        if len(refs) != len(set(refs)):
            raise ValueError("关系候选引用不能重复")
        return self


class CharacterBatchSavedV1(StrictResponseModel):
    """保存结果只返回刷新与定位需要的身份和版本。"""

    candidate_ref: CandidateRef
    entity_id: ObjectIdString
    character_id: CharacterId
    version: FactVersion
    history_id: ObjectIdString


class CharacterBatchBindingSavedV1(StrictResponseModel):
    """绑定结果通过人物候选引用回到原列表。"""

    candidate_ref: CandidateRef
    binding_id: str = Field(pattern=r"^cfb_[0-9]{6,19}$")
    version: FactVersion


class CharacterFactBatchResultV1(StrictResponseModel):
    """整批人物首次保存的不可变结果。"""

    novel_id: ObjectIdString
    characters: list[CharacterBatchSavedV1] = Field(min_length=1, max_length=50)
    bindings: list[CharacterBatchBindingSavedV1] = Field(max_length=1000)


class CharacterRelationBatchSavedV1(StrictResponseModel):
    """关系的稳定身份与起点记录。"""

    candidate_ref: CandidateRef
    entity_id: ObjectIdString
    relation_id: CharacterRelationId
    version: FactVersion
    history_id: ObjectIdString


class CharacterRelationFactBatchResultV1(StrictResponseModel):
    """整批关系首次保存的不可变结果。"""

    novel_id: ObjectIdString
    relations: list[CharacterRelationBatchSavedV1] = Field(min_length=1, max_length=500)
