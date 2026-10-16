"""全书级核心角色与人物关系的直接生成预览服务。"""

from __future__ import annotations

import math
from typing import Any

from backend.services.novel.writing_context import faction_design_content
from backend.db.repositories.faction_repository import faction_repo
from backend.db.repositories.novel_repository import novel_repo
from backend.llm.schemas.character_pydantic import (
    CoreCharactersGenerateRequestV1,
    CoreCharactersResultSchemaV1,
)
from backend.llm.schemas.character_relation_pydantic import (
    CharacterRelationsGenerateRequestV1,
    CharacterRelationsResultSchemaV1,
)
from backend.services.llm.candidate_contract import MAX_CANDIDATE_SOURCE_REFS
from backend.services.llm.character_generation_contract import CHARACTER_RELATION_GENERATION_STEP, CHARACTER_RELATION_WORKFLOW, CORE_CHARACTER_GENERATION_STEP, CORE_CHARACTER_WORKFLOW, build_character_relation_source_refs, build_core_character_source_refs
from backend.services.novel.errors import GenerationDomainError
from backend.services.novel.request_fingerprint import canonical_json
from backend.services.novel.character_name import normalize_character_name
from backend.services.llm.workflow_service import ensure_text_budget
from backend.services.novel.character_faction_binding_service import (
    CharacterFactionBindingService,
)
from backend.services.novel.character_relation_service import CharacterRelationService
from backend.services.novel.character_service import CharacterService
from backend.services.novel.writing_context import character_design_content, character_relation_design_content


CORE_CHARACTER_WORKFLOW_NAME = CORE_CHARACTER_WORKFLOW
CORE_CHARACTER_STEP = CORE_CHARACTER_GENERATION_STEP
CHARACTER_RELATION_WORKFLOW_NAME = CHARACTER_RELATION_WORKFLOW
CHARACTER_RELATION_STEP = CHARACTER_RELATION_GENERATION_STEP

CHARACTER_RELATION_COUNT_DEFAULT = 20
CORE_CHARACTER_INPUT_MAX_CHARS = 120_000
CHARACTER_RELATION_INPUT_MAX_CHARS = 180_000

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
    "positioning",
    "core_goal",
    "conflict_with_mainline",
    "active_status",
    "level_type",
    "version",
)
CHARACTER_PROMPT_FIELDS = (
    "character_id",
    "name",
    "identity",
    "core_desire",
    "core_fear",
    "story_function",
    "arc_seed",
    "status",
    "is_core_character",
    "version",
)
RELATION_PROMPT_FIELDS = (
    "relation_id",
    "source_character_id",
    "target_character_id",
    "relation_type",
    "current_state",
    "core_conflict",
    "hidden_tension",
    "possible_change",
    "story_value",
    "intensity",
    "is_active",
    "version",
)
BINDING_PROMPT_FIELDS = (
    "binding_id",
    "character_id",
    "faction_id",
    "membership_type",
    "role_title",
    "public_status",
    "loyalty_level",
    "notes",
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


class CharacterGenerationService:
    """读取当前小说事实并直接生成角色或关系候选预览。"""

    @staticmethod
    async def load_core_context(
        request: CoreCharactersGenerateRequestV1,
        *,
        require_readiness: bool = True,
    ) -> dict[str, Any]:
        """读取核心角色生成所需的当前小说事实。

        Args:
            request: 已校验的直接生成请求。
            require_readiness: 正式生成要求已有核心势力，流程查看允许显示缺项。

        Returns:
            Prompt 输入、允许引用的势力 ID 和已占用角色名称。
        """
        novel_id = request.novel_id
        novel = await novel_repo.get_novel_by_id(novel_id)
        factions = [
            item
            for item in await faction_repo.get_factions_by_level_type(novel_id, "core")
            if item.get("active_status") == "active"
        ]
        if require_readiness and not factions:
            raise GenerationDomainError(
                "CORE_FACTION_REQUIRED",
                "生成核心角色前至少需要一个活动核心势力",
                status_code=422,
            )
        all_characters = await CharacterService.get_characters_by_novel(novel_id)
        core_characters = [
            item
            for item in all_characters
            if item.get("is_core_character") is True and item.get("status") == "active"
        ]
        if len(factions) > 100:
            raise GenerationDomainError(
                "CHARACTER_GENERATION_INPUT_BUDGET_EXCEEDED",
                "核心势力数量超过 100，无法在不截断事实的情况下生成角色",
            )
        if len(core_characters) > 200:
            raise GenerationDomainError(
                "CHARACTER_GENERATION_INPUT_BUDGET_EXCEEDED",
                "已有核心角色数量超过 200，无法在不截断事实的情况下继续生成",
            )
        if len(all_characters) > 1000:
            raise GenerationDomainError(
                "CHARACTER_GENERATION_INPUT_BUDGET_EXCEEDED",
                "已有正式角色数量超过 1000，无法在不截断名称占用事实的情况下继续生成",
            )

        novel_profile = _project(novel, NOVEL_PROFILE_FIELDS)
        for field, value in novel_profile.items():
            if isinstance(value, str) and len(value) > 8000:
                raise GenerationDomainError(
                    "CHARACTER_GENERATION_INPUT_BUDGET_EXCEEDED",
                    f"小说字段 {field} 超过 8000 字符",
                )

        faction_projections = [faction_design_content(item, FACTION_PROMPT_FIELDS) for item in factions]
        character_projections = [
            character_design_content(item, CHARACTER_PROMPT_FIELDS) for item in core_characters
        ]
        for index, projection in enumerate(
            (*faction_projections, *character_projections)
        ):
            if len(canonical_json(projection)) > 2000:
                raise GenerationDomainError(
                    "CHARACTER_GENERATION_INPUT_BUDGET_EXCEEDED",
                    f"核心势力或角色摘要第 {index + 1} 项超过 2000 字符",
                )

        prompt_input = {
            "novel_profile": novel_profile,
            "core_factions": faction_projections,
            "existing_core_characters": character_projections,
            "character_count": request.character_count,
            "user_guidance": request.user_guidance,
        }
        ensure_text_budget(
            prompt_input,
            max_chars=CORE_CHARACTER_INPUT_MAX_CHARS,
            code="CHARACTER_GENERATION_INPUT_BUDGET_EXCEEDED",
            label="核心角色生成输入",
        )
        source_refs = build_core_character_source_refs(
            novel,
            factions,
            all_characters,
        )
        if len(source_refs) > MAX_CANDIDATE_SOURCE_REFS:
            raise GenerationDomainError(
                "CHARACTER_GENERATION_SOURCE_BUDGET_EXCEEDED",
                "核心角色生成正式来源版本超过 2000 项，禁止静默截断",
                status_code=422,
            )
        return {
            "prompt_input": prompt_input,
            "allowed_faction_ids": {
                str(item["faction_id"]) for item in faction_projections
            },
            "reserved_character_names": {
                normalize_character_name(str(item.get("name") or ""))[1]
                for item in all_characters
                if str(item.get("name") or "").strip()
            },
            "source_refs": source_refs,
        }

    @staticmethod
    async def load_relation_context(
        request: CharacterRelationsGenerateRequestV1,
    ) -> dict[str, Any]:
        """读取关系追加生成所需的全书设计和未定位原文。

        Args:
            request: 已校验的关系直接生成请求。

        Returns:
            Prompt 输入、最终数量上限和关系业务校验上下文。
        """
        novel_id = request.novel_id
        novel = await novel_repo.get_novel_by_id(novel_id)
        characters = await CharacterService.get_characters_by_ids(
            novel_id,
            request.character_ids,
        )
        characters_by_id = {
            str(item["character_id"]): item for item in characters
        }
        missing_ids = [
            character_id
            for character_id in request.character_ids
            if character_id not in characters_by_id
        ]
        if missing_ids:
            raise GenerationDomainError(
                "CHARACTER_RELATION_ENDPOINT_INVALID",
                f"角色不存在或不属于当前小说: {', '.join(missing_ids)}",
            )
        for character in characters:
            if (
                character.get("status") != "active"
                or character.get("is_core_character") is not True
            ):
                raise GenerationDomainError(
                    "CHARACTER_RELATION_ENDPOINT_INVALID",
                    f"角色 {character['character_id']} 必须是 active 核心角色",
                )

        selected_ids = set(request.character_ids)
        bindings = [
            item
            for item in await CharacterFactionBindingService.list_bindings(
                novel_id,
                is_active=True,
            )
            if item.get("character_id") in selected_ids
        ]
        relations = [
            item
            for item in await CharacterRelationService.list_relations(
                novel_id,
                is_active=True,
            )
            if item.get("source_character_id") in selected_ids
            and item.get("target_character_id") in selected_ids
        ]
        if len(bindings) > 300 or len(relations) > 1000:
            raise GenerationDomainError(
                "CHARACTER_RELATION_INPUT_BUDGET_EXCEEDED",
                "角色绑定或既有活动关系超过工作流预算，禁止静默截断",
            )

        character_projections = [
            character_design_content(characters_by_id[item], CHARACTER_PROMPT_FIELDS)
            for item in request.character_ids
        ]
        binding_projections = [
            _project(item, BINDING_PROMPT_FIELDS) for item in bindings
        ]
        relation_projections = [
            character_relation_design_content(item, RELATION_PROMPT_FIELDS) for item in relations
        ]
        for index, projection in enumerate(
            (*character_projections, *relation_projections)
        ):
            if len(canonical_json(projection)) > 2000:
                raise GenerationDomainError(
                    "CHARACTER_RELATION_INPUT_BUDGET_EXCEEDED",
                    f"角色或关系摘要第 {index + 1} 项超过 2000 字符",
                )

        character_count = len(request.character_ids)
        maximum_edge_count = character_count * (character_count - 1)
        minimum_cover_count = math.ceil(character_count / 2)
        normalized_limit = (
            request.relation_count_limit
            if request.relation_count_limit is not None
            else min(
                maximum_edge_count,
                max(CHARACTER_RELATION_COUNT_DEFAULT, minimum_cover_count),
            )
        )
        novel_profile = _project(novel, NOVEL_PROFILE_FIELDS)
        for field in ("plot", "core_seed"):
            value = novel_profile.get(field)
            if isinstance(value, str) and len(value) > 8000:
                raise GenerationDomainError(
                    "CHARACTER_RELATION_INPUT_BUDGET_EXCEEDED",
                    f"小说字段 {field} 超过 8000 字符",
                )

        prompt_input = {
            "novel_profile": novel_profile,
            "characters": character_projections,
            "faction_bindings": binding_projections,
            "existing_relations": relation_projections,
            "allow_isolated_characters": request.allow_isolated_characters,
            "relation_count_limit": normalized_limit,
            "user_guidance": request.user_guidance,
        }
        ensure_text_budget(
            prompt_input,
            max_chars=CHARACTER_RELATION_INPUT_MAX_CHARS,
            code="CHARACTER_RELATION_INPUT_BUDGET_EXCEEDED",
            label="角色关系生成输入",
        )
        source_refs = build_character_relation_source_refs(
            novel,
            characters,
            bindings,
            relations,
        )
        if len(source_refs) > MAX_CANDIDATE_SOURCE_REFS:
            raise GenerationDomainError(
                "CHARACTER_RELATION_SOURCE_BUDGET_EXCEEDED",
                "角色关系生成正式来源版本超过 2000 项，禁止静默截断",
                status_code=422,
            )
        return {
            "prompt_input": prompt_input,
            "relation_count_limit": normalized_limit,
            "character_ids": list(request.character_ids),
            "allow_isolated_characters": request.allow_isolated_characters,
            "source_refs": source_refs,
        }


    @staticmethod
    def validate_core_result(
        result: CoreCharactersResultSchemaV1,
        request: CoreCharactersGenerateRequestV1,
        context: dict[str, Any],
    ) -> None:
        """校验角色数量、名称和势力引用是否符合当前请求事实。

        Args:
            result: 已通过结构 Schema 的角色候选。
            request: 当前直接生成请求。
            context: 当前小说事实上下文。

        Returns:
            校验通过时不返回内容。
        """
        errors: list[str] = []
        if request.character_count is not None and len(result.core_characters) != request.character_count:
            errors.append(
                f"候选数量必须严格等于 {request.character_count}"
            )
        normalized_names = [
            normalize_character_name(item.name)[1]
            for item in result.core_characters
        ]
        if len(normalized_names) != len(set(normalized_names)):
            errors.append("候选角色名称在 Unicode 规范化后重复")
        if set(normalized_names) & context["reserved_character_names"]:
            errors.append("候选角色与已有角色重名")

        allowed_faction_ids = context["allowed_faction_ids"]
        for binding in result.binding_candidates:
            if (
                binding.faction_id is not None
                and binding.faction_id not in allowed_faction_ids
            ):
                errors.append(f"势力 {binding.faction_id} 不在当前核心势力中")
        if errors:
            raise GenerationDomainError(
                "CHARACTER_GENERATION_OUTPUT_INVALID",
                "; ".join(errors),
                status_code=502,
            )

    @staticmethod
    async def validate_relation_result(
        novel_id: str,
        result: CharacterRelationsResultSchemaV1,
        context: dict[str, Any],
    ) -> None:
        """校验关系数量、端点覆盖和仅追加语义冲突。

        Args:
            novel_id: 当前小说公开 ID。
            result: 已通过结构 Schema 的关系候选。
            context: 当前关系生成事实上下文。

        Returns:
            校验通过时不返回内容。
        """
        errors: list[str] = []
        if len(result.relations) > context["relation_count_limit"]:
            errors.append("关系候选数量超过本次请求上限")

        service_errors = await CharacterRelationService.validate_generation_candidates(
            novel_id,
            result.relations,
            context["character_ids"],
            require_core_endpoints=True,
        )
        errors.extend(service_errors)
        if not context["allow_isolated_characters"]:
            covered = {
                endpoint
                for relation in result.relations
                for endpoint in (
                    relation.source_character_id,
                    relation.target_character_id,
                )
            }
            missing = sorted(set(context["character_ids"]) - covered)
            if missing:
                errors.append(
                    f"以下角色未参与任何候选关系: {', '.join(missing)}"
                )
        if errors:
            raise GenerationDomainError(
                "CHARACTER_RELATION_OUTPUT_INVALID",
                "; ".join(errors),
                status_code=502,
            )


__all__ = [
    "CHARACTER_RELATION_STEP",
    "CHARACTER_RELATION_WORKFLOW_NAME",
    "CORE_CHARACTER_STEP",
    "CORE_CHARACTER_WORKFLOW_NAME",
    "CharacterGenerationService",
]
