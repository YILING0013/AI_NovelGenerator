"""势力及关联关系一次采用的合同，保留原请求和首次完整结果。"""

from typing import Annotated

from pydantic import Field, model_validator

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.llm.schemas.novel_pydantic import CoreFactionsGenerationInputV2, CoreFactionRelationSchema
from backend.llm.schemas.faction_relation_pydantic import FactionRelationResponseV1
from backend.services.llm.candidate_contract import CandidateBasisV1
from backend.services.novel.faction_fact_contract import (
    FactConfirmed, FactPositionV1, FactionFactCreateDataV1, FactionFactValuesV1, FactionFactResultV1,
)


class FactionBatchGenerationV1(StrictRequestModel):
    """冻结生成时的输入及读取依据，确认时不用今天的配置替换。"""

    basis: CandidateBasisV1
    generation_input: CoreFactionsGenerationInputV2


class FactionBatchCandidateV1(StrictRequestModel):
    """设计与实际事实分开；旧目标、优势和计划不自动映射成事实。"""

    candidate_ref: Annotated[str, Field(pattern=r"^faction_[0-9]{3}$")]
    profile: FactionFactCreateDataV1
    facts: FactionFactValuesV1

    @model_validator(mode="after")
    def require_actual_fields(self) -> "FactionBatchCandidateV1":
        """缺项保持未知，不替作者填入默认事实。"""
        if not self.facts.model_fields_set:
            raise ValueError("Hãy nhập ít nhất một mục tư liệu thế lực tại đây")
        return self


class FactionFactBatchCreateV1(StrictRequestModel):
    """一次确认整批新势力及其关系，共享明确剧情位置。"""

    position: FactPositionV1
    candidates: list[FactionBatchCandidateV1] = Field(min_length=1, max_length=50)
    relations: list[CoreFactionRelationSchema] = Field(default_factory=list, max_length=20)
    generation: FactionBatchGenerationV1 | None = None
    confirmed: FactConfirmed

    @model_validator(mode="after")
    def validate_selection(self) -> "FactionFactBatchCreateV1":
        """检查稳定引用及端点，不允许把已有势力关系伪装成本批新建。"""
        refs = [row.candidate_ref for row in self.candidates]
        relations = [row.relation_ref for row in self.relations]
        if len(refs) != len(set(refs)) or len(relations) != len(set(relations)):
            raise ValueError("Tham chiếu ứng viên của thế lực hoặc quan hệ không được trùng lặp")
        for row in self.relations:
            endpoints = [row.source, row.target]
            if all(endpoint.kind == "existing" for endpoint in endpoints):
                raise ValueError("Đợt quan hệ này cần ít nhất một thế lực mới")
            if any(endpoint.faction_ref not in refs for endpoint in endpoints if endpoint.kind == "candidate"):
                raise ValueError("Quan hệ tham chiếu thế lực mới chưa được chấp nhận")
        if self.generation is not None and (
            len(self.candidates) > (self.generation.generation_input.faction_count or 6)
            or any(row.profile.level_type != "core" for row in self.candidates)
        ):
            raise ValueError("Việc tạo thế lực cốt lõi không được thêm ứng viên ngoài yêu cầu gốc hoặc đổi thành thế lực trong quyển")
        return self


class FactionBatchSavedV1(StrictResponseModel):
    """每个候选首次保存的完整事实结果，包含当时的内容与来源。"""

    candidate_ref: Annotated[str, Field(pattern=r"^faction_[0-9]{3}$")]
    result: FactionFactResultV1


class FactionBatchRelationSavedV1(StrictResponseModel):
    """关系首次完整公开结果，不从后来的关系文档重组。"""

    relation_ref: Annotated[str, Field(pattern=r"^relation_[0-9]{3}$")]
    result: FactionRelationResponseV1


class FactionFactBatchResultV1(StrictResponseModel):
    """原顺序、原引用映射和首次完整保存结果。"""

    novel_id: ObjectIdString
    factions: list[FactionBatchSavedV1] = Field(min_length=1, max_length=50)
    relations: list[FactionBatchRelationSavedV1] = Field(default_factory=list, max_length=20)
    faction_ref_map: dict[str, str]
    relation_ref_map: dict[str, str]
