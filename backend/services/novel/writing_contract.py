"""层级生成候选的内容依据与审核确认契约。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from backend.api.contracts import ObjectIdString, StrictRequestModel, StrictResponseModel
from backend.llm.schemas.writing_pydantic import WritingGenerateInputV1
from backend.services.llm.candidate_contract import CandidateBasisV1
from backend.services.novel.character_fact_contract import CharacterFactReadV1
from backend.services.novel.character_relation_fact_contract import CharacterRelationFactReadV1
from backend.services.novel.item_fact_contract import ItemFactReadV1
from backend.services.novel.faction_fact_contract import FactionFactReadV1


class WritingReadV1(StrictRequestModel):
    """一种固定语义的内容读取，包括空查询。"""

    kind: Literal["parent_chain", "children", "neighbors", "previous_written", "selected_entities", "selected_relations", "volume_states", "literal_search", "edit_target", "plot_sources", "volume_participants", "reading_position"]
    scope: dict[str, Any]
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class WritingContextBasisV1(StrictRequestModel):
    """仅散列实际业务内容，不使用祖先统计版本。"""

    version: Literal[1] = 1
    reads: list[WritingReadV1 | CharacterFactReadV1 | CharacterRelationFactReadV1 | ItemFactReadV1 | FactionFactReadV1] = Field(min_length=1, max_length=200)


class WritingCandidateBasisV1(CandidateBasisV1):
    """四类写作任务专用依据，旧任务继续使用原版本契约。"""

    generation_input: WritingGenerateInputV1
    context_basis: WritingContextBasisV1


class WritingGenerationEnvelopeV1(StrictResponseModel):
    """普通响应和 SSE done.result 使用相同结果。"""

    workflow: str
    step: str
    schema_id: str
    schema_version: int
    candidate: dict[str, Any]
    basis: WritingCandidateBasisV1
    context: dict[str, Any]
    prepared_context: dict[str, Any] | None = None
    coverage_review: dict[str, Any] | None = None


class WritingConfirmV1(StrictRequestModel):
    """只提交作者审核后的内容和生成依据；追加不要求祖先旧版本。"""

    candidate: dict[str, Any] = Field(min_length=1)
    basis: WritingCandidateBasisV1
    expected_version: int | None = Field(default=None, ge=1)


class WritingConfirmResultV1(StrictResponseModel):
    """同一次确认的正式对象和稳定 ID，供前端定位当前分支。"""

    operation: str
    ids: list[ObjectIdString]
    data: list[dict[str, Any]]


class WritingMissingV1(StrictResponseModel):
    """当前对象需要补齐的字段。"""

    field: str
    message: str


class WritingReadinessV1(StrictResponseModel):
    """当前部分的可执行状态，不持久保存进度。"""

    target_type: Literal["volume", "arc", "scene", "chapter"]
    target_id: ObjectIdString
    novel_id: ObjectIdString
    can_create_child: bool
    create_missing_fields: list[WritingMissingV1]
    can_refine: bool
    can_write: bool
    can_generate_plot: bool = False
    plot_status: Literal["missing", "stale", "ready"] = "missing"
    preparation: dict[str, bool] = Field(default_factory=dict)
    missing_fields: list[WritingMissingV1]
    blockers: list[dict[str, str]]
    parent_chain: list[dict[str, str]]
    expected_version: int
