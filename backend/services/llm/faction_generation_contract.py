"""核心势力 AI 候选的来源版本、指纹与统一响应契约。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.llm.generation_options import REASONING_FIELDS
from backend.llm.schemas.novel_pydantic import GenerateCoreFactionsRequestV2, ExistingFactionRelationTargetV2
from backend.services.llm.candidate_contract import CandidateSourceRefV1
from backend.services.novel.writing_context import faction_design_content


CORE_FACTIONS_WORKFLOW = "create_factions_by_ai"
CORE_FACTIONS_STEP = "create_core_factions"
_GENERATION_PARAMETER_FIELDS = (
    "temperature",
    "top_p",
    "max_tokens",
    "presence_penalty",
    "frequency_penalty",
    *REASONING_FIELDS,
    "system_prompt",
)
_UNSET = object()


def format_faction_novel_text(novel: dict[str, Any], field: str, fallback: str = "未提供") -> str:
    """读取小说字段并转换为适合提示词的文本。

    Args:
        novel: 已落库小说文档。
        field: 字段名。
        fallback: 字段为空时使用的占位文本。

    Returns:
        可放入提示词的字符串。
    """
    value = novel.get(field)
    if isinstance(value, list):
        return "、".join(str(item).strip() for item in value if str(item).strip()) or fallback
    text = str(value or "").strip()
    return text or fallback


def compact_existing_core_factions(factions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """压缩已有核心阵营为提示词可读的低噪声结构。

    Args:
        factions: 数据库中已保存且未删除的核心阵营列表。

    Returns:
        只保留名称、类型和主线相关信息的阵营摘要列表。
    """
    compacted: list[dict[str, Any]] = []
    for faction in factions:
        compacted.append(
            {
                "faction_id": faction.get("faction_id", ""),
                "name": faction.get("name", ""),
                "faction_type": faction.get("faction_type", ""),
                "positioning": faction.get("positioning", ""),
                "public_stance": faction.get("public_stance", ""),
                "core_goal": faction.get("core_goal", ""),
                "hidden_goal": faction.get("hidden_goal", ""),
                "influence_scope": faction.get("influence_scope", ""),
                "tags": faction.get("tags", []),
                "version": int(faction["version"]),
            }
        )
    return [faction_design_content(row, tuple(row)) for row in compacted]


def _describe_integrity_score(score: int) -> str:
    """解释单个阵营正直度滑块的生成含义。

    Args:
        score: 0 到 10 的正直度分值。

    Returns:
        可直接放入提示词的正直度说明。
    """
    negative_feature_count = max(0, 10 - score)
    if score == 0:
        stance = "绝对负面，可设计为扁平化反派势力，核心特征全部服务压迫、掠夺或破坏。"
    elif score == 10:
        stance = "绝对正面，可设计为扁平化正派势力，不安排明显负面特征。"
    elif score < 5:
        stance = "整体偏负面，但需要保留少量可理解动机或秩序逻辑。"
    elif score > 5:
        stance = "整体偏正面，但需要安排相对负面的代价、盲区或内部问题。"
    else:
        stance = "正负面相对均衡，需要同时具备建设性目标和明显问题。"
    return f"正直度为 {score}/10。{stance} 相对负面特征数量参考 {negative_feature_count} 项。"


def _describe_relation_score(score: int) -> str:
    """解释单个阵营与已有阵营关系滑块的生成含义。

    Args:
        score: 0 到 10 的关系量化分值。

    Returns:
        可直接放入提示词的关系倾向说明。
    """
    if score == 0:
        return "关系量化为 0/10：应设计为绝对决裂或不可调和敌对。"
    if score == 10:
        return "关系量化为 10/10：应设计为高度互信、稳定伙伴或同盟。"
    if score < 5:
        return f"关系量化为 {score}/10：关系偏差，越接近 0 越应体现敌意、竞争、背叛风险或旧怨。"
    if score > 5:
        return f"关系量化为 {score}/10：关系偏好，越接近 10 越应体现合作、利益绑定或共同目标。"
    return "关系量化为 5/10：关系中性或摇摆，合作与冲突并存。"


def _format_existing_relation_targets(targets: list[ExistingFactionRelationTargetV2]) -> str:
    """格式化用户手动选择的已有阵营关系目标。

    Args:
        targets: 已有阵营正式 ID 与独立关系分值配置列表。

    Returns:
        可放入提示词的多行目标说明。
    """
    lines: list[str] = []
    for target in targets:
        lines.append(
            f"{target.faction_id}: {_describe_relation_score(target.relation_score)}"
        )
    return "\n".join(lines)


def build_core_factions_generation_strategy(
    req: GenerateCoreFactionsRequestV2,
    existing_core_factions: list[dict[str, Any]],
) -> str:
    """构造核心阵营追加生成策略说明。

    Args:
        req: 前端提交的核心阵营生成参数。
        existing_core_factions: 数据库中已保存且未删除的核心阵营列表。

    Returns:
        可拼接进提示词的生成约束说明。
    """
    independent_count = req.independent_faction_count
    user_guidance = req.user_guidance.strip() or "无"
    has_existing = len(existing_core_factions) > 0
    lines = [
        ("根据故事需要自行决定新增核心阵营数量，至少 1 个、最多 6 个，同时满足下面的独立数量和关系约束。" if req.faction_count is None else f"本次必须只生成 {req.faction_count} 个全新的核心阵营。"),
        "已有核心阵营只作为上下文和关系端点参考，禁止把已有阵营重复放入 core_factions。",
        "新阵营名称不得与已有核心阵营重复。",
        "每条新关系至少要连接一个本次生成的新阵营；可以连接新阵营和已有阵营，也可以连接两个本次新阵营。",
        f"本批必须恰有 {independent_count} 个新阵营不建立直接关系，即不出现在本批 faction_relations 的 source 或 target 中；与新阵营或已有阵营的关系都计入。",
        "这里只限制本批关系输出，不代表势力永久独立、不隶属其他势力或隐藏存在。",
        f"用户指导: {user_guidance}",
    ]

    if req.faction_count == 1:
        integrity_score = req.single_faction_integrity_score if req.single_faction_integrity_score is not None else 5
        lines.append(_describe_integrity_score(integrity_score))
        can_connect_to_existing = independent_count == 0 and req.connect_to_existing and has_existing
        if can_connect_to_existing:
            formatted_targets = _format_existing_relation_targets(req.existing_relation_targets)
            if formatted_targets:
                lines.append("这个单个新阵营需要分别与以下用户选定的已有核心阵营产生关系，并按每个阵营的独立分值设计关系。")
                lines.append(formatted_targets)
            else:
                relation_score = req.existing_relation_score if req.existing_relation_score is not None else 5
                lines.append("这个单个新阵营需要与至少一个已有核心阵营产生关系。")
                lines.append(_describe_relation_score(relation_score))
        else:
            lines.append("这个单个新阵营是否建立关系，仍须满足上述本批不建立直接关系的数量。")
    elif has_existing:
        lines.append("已有核心阵营存在时，本批需要建立关系的新阵营可以优先与已有核心阵营建立关系，补足追加生成的连贯性。")
    else:
        lines.append("当前没有已有核心阵营，关系只能在本次新生成阵营之间建立。")

    return "\n".join(f"- {line}" for line in lines)


def extract_core_factions_generation_input(
    request: GenerateCoreFactionsRequestV2 | Mapping[str, Any],
) -> dict[str, Any]:
    """提取确认阶段允许回传并参与指纹计算的严格生成输入。

    Args:
        request: 生成请求模型或已校验映射。

    Returns:
        去除传输态 ``use_stream`` 的业务输入白名单。
    """
    model = (
        request
        if isinstance(request, GenerateCoreFactionsRequestV2)
        else GenerateCoreFactionsRequestV2.model_validate(request)
    )
    return model.model_dump(mode="json", exclude={"use_stream"})


def build_core_factions_source_refs(
    novel: Mapping[str, Any],
    factions: Sequence[Mapping[str, Any]],
    relations: Sequence[Mapping[str, Any]],
) -> list[CandidateSourceRefV1]:
    """把生成时读取的正式事实转换为版本依据。

    Args:
        novel: 本次读取的小说正式快照。
        factions: 全部活动核心势力快照。
        relations: 活动核心势力之间的既有关系快照。

    Returns:
        可直接写入 CandidateBasisV1 的完整来源引用。
    """
    refs = [
        CandidateSourceRefV1(
            resource_type="novel",
            id=str(novel.get("id") or novel.get("_id")),
            version=int(novel["version"]),
        )
    ]
    refs.extend(
        CandidateSourceRefV1(
            resource_type="faction",
            id=str(faction["faction_id"]),
            version=int(faction["version"]),
        )
        for faction in factions
    )
    refs.extend(
        CandidateSourceRefV1(
            resource_type="faction_relation",
            id=str(relation["relation_id"]),
            version=int(relation["version"]),
        )
        for relation in relations
    )
    return refs


def compute_core_factions_input_fingerprint(
    request: GenerateCoreFactionsRequestV2 | Mapping[str, Any],
    source_refs: Sequence[CandidateSourceRefV1 | Mapping[str, Any]],
    *, flow_snapshot: Mapping[str, Any],
) -> str:
    """按生成时方案重算核心势力候选输入指纹。

    Args:
        request: 确认阶段回传的严格生成输入。
        source_refs: 生成时读取并在确认时重读的正式来源版本。

        flow_snapshot: 生成时的方案与非敏感配置。

    Returns:
        绑定输入、来源和执行契约的 SHA-256 十六进制摘要。
    """
    from backend.services.task_flows.candidate import compute_flow_candidate_fingerprint
    return compute_flow_candidate_fingerprint('create_factions_by_ai', request, source_refs, flow_snapshot)


__all__ = [
    "CORE_FACTIONS_STEP",
    "CORE_FACTIONS_WORKFLOW",
    "build_core_factions_generation_strategy",
    "compact_existing_core_factions",
    "format_faction_novel_text",
    "build_core_factions_source_refs",
    "compute_core_factions_input_fingerprint",
    "extract_core_factions_generation_input",
]
