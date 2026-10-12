"""阵营关系直接生成候选预览服务。"""

from __future__ import annotations

import math
from typing import Any

from backend.db.errors import DuplicateKeyError, NotFoundError
from backend.db.repositories.faction_relation_repository import faction_relation_repo
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.llm.schemas.faction_relation_pydantic import (
    FactionRelationsGenerateRequestV1,
    FactionRelationsResultSchemaV1,
)
from backend.services.llm.candidate_contract import MAX_CANDIDATE_SOURCE_REFS, CandidateSourceRefV1
from backend.services.llm.workflow_service import ensure_text_budget
from backend.services.novel.errors import GenerationDomainError
from backend.services.novel.request_fingerprint import canonical_json
from backend.services.novel.faction_relation_service import FactionRelationService


FACTION_RELATION_WORKFLOW_NAME = "create_faction_relations_by_ai"
FACTION_RELATION_STEP = "create_faction_relations"
FACTION_RELATION_COUNT_DEFAULT = 20
FACTION_RELATION_INPUT_MAX_CHARS = 180_000

NOVEL_PROFILE_FIELDS = (
    "title",
    "genre",
    "tone",
    "target_audience",
    "core_idea",
    "core_seed",
    "plot",
    "summary",
    "worldview",
    "number_of_chapters",
    "words_per_chapter",
    "writing_style",
    "narrative_pov",
    "era_background",
    "tags",
)
FACTION_PROMPT_FIELDS = (
    "faction_id",
    "name",
    "faction_type",
    "positioning",
    "public_stance",
    "core_goal",
    "hidden_goal",
    "resources_and_advantages",
    "organization_style",
    "core_values",
    "conflict_with_mainline",
    "is_public",
    "influence_scope",
    "expandability",
    "tags",
    "active_status",
    "level_type",
    "version",
)
RELATION_PROMPT_FIELDS = (
    "relation_id",
    "source_faction_id",
    "target_faction_id",
    "relation_type",
    "current_state",
    "core_conflict",
    "hidden_tension",
    "possible_change",
    "intensity",
    "is_active",
    "version",
)

def _project(document: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """从数据库文档提取允许进入 Prompt 的稳定字段。

    Args:
        document: Repository 返回的原始文档。
        fields: 允许进入 Prompt 的字段白名单。

    Returns:
        仅包含白名单字段的独立字典。
    """
    projected = {field: document.get(field) for field in fields}
    if "version" in fields and projected.get("version") is None:
        projected["version"] = document["version"]
    return projected


class FactionRelationGenerationService:
    """读取当前小说事实并直接生成阵营关系候选预览。"""

    @staticmethod
    async def load_context(
        request: FactionRelationsGenerateRequestV1,
    ) -> dict[str, Any]:
        """读取阵营关系追加生成所需的当前小说事实。

        Args:
            request: 已校验的阵营关系直接生成请求。

        Returns:
            Prompt 输入、最终数量上限和关系业务校验上下文。
        """
        novel_id = request.novel_id
        novel = await novel_repo.get_novel_by_id(novel_id)
        factions_by_id: dict[str, dict[str, Any]] = {}
        for faction_id in request.faction_ids:
            try:
                faction = await faction_repo.get_faction(
                    novel_id,
                    faction_id,
                    include_deleted=True,
                )
            except NotFoundError as exc:
                raise GenerationDomainError(
                    "FACTION_RELATION_ENDPOINT_INVALID",
                    f"阵营不存在或不属于当前小说: {faction_id}",
                ) from exc
            if (
                faction.get("is_deleted") is True
                or faction.get("active_status") != "active"
            ):
                raise GenerationDomainError(
                    "FACTION_RELATION_ENDPOINT_INVALID",
                    f"阵营 {faction_id} 必须处于 active 状态",
                )
            factions_by_id[faction_id] = faction

        selected_ids = set(request.faction_ids)
        relations = [
            item
            for item in await faction_relation_repo.get_relations_by_novel(
                novel_id,
                active_only=True,
            )
            if item.get("source_faction_id") in selected_ids
            and item.get("target_faction_id") in selected_ids
        ]
        if len(relations) > 1000:
            raise GenerationDomainError(
                "FACTION_RELATION_INPUT_BUDGET_EXCEEDED",
                "所选阵营的既有活动关系超过工作流预算，禁止静默截断",
            )

        faction_projections = [
            _project(factions_by_id[faction_id], FACTION_PROMPT_FIELDS)
            for faction_id in request.faction_ids
        ]
        relation_projections = [
            _project(item, RELATION_PROMPT_FIELDS) for item in relations
        ]
        for index, projection in enumerate(
            (*faction_projections, *relation_projections)
        ):
            if len(canonical_json(projection)) > 4000:
                raise GenerationDomainError(
                    "FACTION_RELATION_INPUT_BUDGET_EXCEEDED",
                    f"阵营或关系摘要第 {index + 1} 项超过 4000 字符",
                )

        faction_count = len(request.faction_ids)
        maximum_edge_count = faction_count * (faction_count - 1)
        minimum_cover_count = math.ceil(faction_count / 2)
        normalized_limit = (
            request.relation_count_limit
            if request.relation_count_limit is not None
            else min(
                maximum_edge_count,
                max(FACTION_RELATION_COUNT_DEFAULT, minimum_cover_count),
            )
        )
        novel_profile = _project(novel, NOVEL_PROFILE_FIELDS)
        for field in ("plot", "core_seed"):
            value = novel_profile.get(field)
            if isinstance(value, str) and len(value) > 8000:
                raise GenerationDomainError(
                    "FACTION_RELATION_INPUT_BUDGET_EXCEEDED",
                    f"小说字段 {field} 超过 8000 字符",
                )

        prompt_input = {
            "novel_profile": novel_profile,
            "factions": faction_projections,
            "existing_relations": relation_projections,
            "allow_isolated_factions": request.allow_isolated_factions,
            "relation_count_limit": normalized_limit,
            "user_guidance": request.user_guidance,
        }
        ensure_text_budget(
            prompt_input,
            max_chars=FACTION_RELATION_INPUT_MAX_CHARS,
            code="FACTION_RELATION_INPUT_BUDGET_EXCEEDED",
            label="阵营关系生成输入",
        )
        source_refs = [
            CandidateSourceRefV1(
                resource_type="novel",
                id=request.novel_id,
                version=int(novel["version"]),
            ),
            *[
                CandidateSourceRefV1(
                    resource_type="faction",
                    id=faction_id,
                    version=int(factions_by_id[faction_id]["version"]),
                )
                for faction_id in request.faction_ids
            ],
            *[
                CandidateSourceRefV1(
                    resource_type="faction_relation",
                    id=str(relation["relation_id"]),
                    version=int(relation["version"]),
                )
                for relation in relations
            ],
        ]
        if len(source_refs) > MAX_CANDIDATE_SOURCE_REFS:
            raise GenerationDomainError(
                "FACTION_RELATION_SOURCE_BUDGET_EXCEEDED",
                "势力关系生成正式来源版本超过 2000 项，禁止静默截断",
                status_code=422,
            )
        return {
            "prompt_input": prompt_input,
            "relation_count_limit": normalized_limit,
            "faction_ids": list(request.faction_ids),
            "allow_isolated_factions": request.allow_isolated_factions,
            "source_refs": source_refs,
        }


    @staticmethod
    async def validate_result(
        novel_id: str,
        result: FactionRelationsResultSchemaV1,
        context: dict[str, Any],
    ) -> None:
        """校验候选数量、端点白名单、覆盖范围和既有语义冲突。

        Args:
            novel_id: 当前小说公开 ID。
            result: 已通过结构 Schema 的阵营关系候选。
            context: 当前阵营关系生成事实上下文。

        Returns:
            校验通过时不返回内容。
        """
        errors: list[str] = []
        if len(result.relations) > context["relation_count_limit"]:
            errors.append("阵营关系候选数量超过本次请求上限")

        selected_ids = set(context["faction_ids"])
        for relation in result.relations:
            if (
                relation.source_faction_id not in selected_ids
                or relation.target_faction_id not in selected_ids
            ):
                errors.append(
                    f"{relation.relation_ref}: 关系端点必须来自本次锁定的阵营白名单"
                )

        if not errors:
            try:
                # 输出返回前重新读取当前事实，拒绝生成期间被停用或已产生冲突的端点。
                await FactionRelationService.validate_relation_payloads(
                    novel_id,
                    result.relations,
                    require_active_endpoints=True,
                )
            except (DuplicateKeyError, ValueError) as exc:
                errors.append(str(exc))

        if not context["allow_isolated_factions"]:
            covered = {
                endpoint
                for relation in result.relations
                for endpoint in (
                    relation.source_faction_id,
                    relation.target_faction_id,
                )
            }
            missing = sorted(selected_ids - covered)
            if missing:
                errors.append(f"以下阵营未参与任何候选关系: {', '.join(missing)}")

        if errors:
            raise GenerationDomainError(
                "FACTION_RELATION_OUTPUT_INVALID",
                "; ".join(errors),
                status_code=502,
            )


__all__ = [
    "FACTION_RELATION_STEP",
    "FACTION_RELATION_WORKFLOW_NAME",
    "FactionRelationGenerationService",
]
