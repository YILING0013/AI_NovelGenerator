"""原 AI 任务的工具入口；保留原方案、提示、候选依据和确认服务。"""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from bson import ObjectId

from backend.api.error_protocol import DomainApiError
from backend.db.base import BaseRepository
from backend.db.utils import get_utc_now
from backend.db.write_contracts import canonical_request_hash
from backend.services.task_flows.contracts import FlowRef, GraphRunRequest
from backend.services.task_flows.graph import port_schema
from backend.services.task_flows.integration import generate_task_flow
from backend.services.task_flows.registry import TASKS, CONTENT_TASKS
from backend.services.task_flows.store import flow_store
from backend.llm.schemas.writing_pydantic import WRITING_TASKS, WritingGenerateInputV1
from backend.services.novel.plot_contract import PLOT_TASKS
from .contracts import ResourceRef, WritingAnswerReview
from .models import structured_advice
from .resources import RESOURCES, content_fingerprint, get_resource, public_content


GENERATION_KINDS = {
    "rewrite_novel_field_by_ai": ["novel"],
    "create_factions_by_ai": ["faction", "faction_relation"],
    "create_characters_by_ai": ["character", "character_faction_binding"],
    "create_character_relations_by_ai": ["character_relation"],
    "create_faction_relations_by_ai": ["faction_relation"],
    "create_world_rules_by_ai": ["world_rule"],
    "create_volume_skeleton_by_ai": ["volume"],
    "plan_volume_launch_by_ai": ["volume"],
    "create_locations_for_volume_by_ai": ["location", "volume"],
    "create_characters_for_volume_by_ai": ["character", "character_faction_binding", "character_volume_state", "volume"],
    "create_factions_for_volume_by_ai": ["faction", "faction_volume_state", "volume"],
    "create_items_by_ai": ["item"],
    "generate_volume_plot_by_ai": ["volume"], "generate_arc_plot_by_ai": ["arc"],
    "plan_arcs_by_ai": ["arc"], "plan_scenes_by_ai": ["scene"],
    "plan_chapters_by_ai": ["chapter"], "write_chapter_by_ai": ["chapter"],
}

# 只限定候选审核和确认；卷任务仍保留原全书管理的作者输入合同。
POSITION_REVIEW_TASKS = CONTENT_TASKS | {
    "plan_volume_launch_by_ai", "create_characters_for_volume_by_ai",
    "create_factions_for_volume_by_ai", "create_locations_for_volume_by_ai",
}

FACT_GENERATION_CONTRACTS = {
    "create_characters_by_ai": "character_fact_batch_v1",
    "create_character_relations_by_ai": "character_relation_fact_batch_v1",
    "create_characters_for_volume_by_ai": "participation_plan_v1",
}


WRITING_ANSWER_ACTIONS = {
    "continue_request": "继续完成作者原请求。",
    "preserve_plot": "保留当前位置已有剧情，只调整表达。",
    "preserve_ending": "保留当前位置原文的结局，不引入其它位置的结局。",
    "rewrite_expression": "调整当前位置的表达方式。",
    "expand_detail": "扩写当前位置已有内容的细节。",
    "condense": "精简当前位置的表达。",
    "more_subtle": "表达更含蓄。",
    "more_direct": "表达更直接。",
    "more_dialogue": "增加当前位置的对话。",
    "less_dialogue": "减少当前位置的对话。",
    "preserve_viewpoint": "保留当前位置已有的叙述视角。",
}


def author_guidance(run: dict, answer_ids: list[str], *, meanings: list[dict] | None = None) -> str:
    """按固定回答前缀保留作者真实原文，不把模型提问写成作者要求。

    Args:
        run: 不可变原请求及原问题的真实作者回答。
        answer_ids: 此候选生成时固定的回答顺序；旧候选为空。
        meanings: 外层按实际位置核实的固定动作；不含提问或模型自由文本。
    Returns:
        原消息和真实补充，标识不匹配时拒绝编造来源。
    """
    answers = run.get("answers", [])[:len(answer_ids)]
    if [answer["id"] for answer in answers] != answer_ids:
        raise DomainApiError("ASSISTANT_CREATION_REQUEST_EXPIRED", "原问题回答记录不完整，请保留原稿并核对", status_code=409)
    message = run["request"]["message"]
    message += "".join("\n\n作者补充：\n" + answer["message"] for answer in answers)
    if meanings is not None:
        reviewed = WritingAnswerReview(answers=meanings).answers
        if [item.answer_id for item in reviewed] != answer_ids:
            raise DomainApiError("ASSISTANT_WRITING_ANSWER_NEEDS_DETAIL", "请说明希望怎样修改当前位置；目前的简短回答还不能安全确定创作要求")
        explanations = []
        for index, item in enumerate(reviewed):
            if item.supported and item.actions and item.resolved_by_answer_id is None:
                explanation = "".join(WRITING_ANSWER_ACTIONS[action] for action in item.actions)
            else:
                at = answer_ids.index(item.resolved_by_answer_id) if item.resolved_by_answer_id in answer_ids else -1
                later = reviewed[at] if at > index else None
                # 只允许引用确实在后的、已核实的回答；旧歧义不能互相引用或夹带动作蒙混通过。
                if item.supported or item.actions or not later or not later.supported or not later.actions or later.resolved_by_answer_id is not None:
                    raise DomainApiError("ASSISTANT_WRITING_ANSWER_NEEDS_DETAIL", "请说明希望怎样修改当前位置；目前的简短回答还不能安全确定创作要求")
                explanation = f"这次简答已由第{at + 1}次作者补充明确，请按那条作者原文理解。"
            explanations.append(f"第{index + 1}次补充：" + explanation)
        message += "\n\n已结合原问题和当前位置核对的回答含义：\n" + "\n".join(explanations)
    return message


async def validate_creation(change: dict, *, session=None) -> None:
    """核对按位置候选绑定的原作者请求；旧成功回执由调用者优先回放。

    Args:
        change: 保存的原任务候选或续跑记录。
        session: 可选确认事务。
    Returns:
        来源一致时正常返回，否则保留旧记录并拒绝继续。
    """
    task = change.get("generation_task")
    if task not in CONTENT_TASKS and task not in FACT_GENERATION_CONTRACTS:
        return
    context = change.get("creation_context", {})
    run = await BaseRepository("assistant_runs").collection.find_one(
        {"_id": change["run_id"], "novel_id": change["novel_id"]}, session=session)
    request = deepcopy(change.get("generation_request", {}))
    request.pop("agent_continuation", None)
    if task in FACT_GENERATION_CONTRACTS:
        policy = change.get("generation_policy", {})
        answers = policy.get("author_answers", [])
        position = {"version": 1, "intent": "volume_start", "target_type": "volume", "target_id": request.get("scope", {}).get("volume_id")} if task == "create_characters_for_volume_by_ai" else {
            "version": 1, "intent": "book_start", "target_type": "novel", "target_id": str(change["novel_id"])}
        if (not run or policy.get("contract") != FACT_GENERATION_CONTRACTS[task]
                or policy.get("request_hash") != run.get("request_hash")
                or canonical_request_hash(run["request"]) != run.get("request_hash")
                or policy.get("author_location") != run["request"].get("location")
                or run.get("answers", [])[:len(answers)] != answers
                or policy.get("author_request") != "\n".join([run["request"]["message"], *(answer["message"] for answer in answers)])
                or policy.get("position") != position or not position["target_id"]
                or context.get("generation_request_hash") != canonical_request_hash(request)):
            raise DomainApiError("ASSISTANT_CREATION_REQUEST_EXPIRED", "这批候选缺少原作者要求或明确起点，请保留原稿并另发请求；已保存回执仍可重放", status_code=409)
        if change.get("candidate"):
            field, keys = {"create_characters_by_ai": ("core_characters", ("character_ref",)),
                           "create_character_relations_by_ai": ("relations", ("relation_ref", "source_character_id", "target_character_id")),
                           "create_characters_for_volume_by_ai": ("characters", ("candidate_ref", "character_id"))}[task]
            original = change["envelope"]["candidate"][field]
            if [tuple(row.get(key) for key in keys) for row in change["candidate"][field]] != [tuple(row.get(key) for key in keys) for row in original]:
                raise DomainApiError("ASSISTANT_CHANGE_SCOPE", "这批人物或关系的对应位置已变化，请保留原稿并另发请求", status_code=409)
        return
    if (context.get("contract_version") != 1 or context.get("semantics") != "position_writing"
            or not run or run.get("creation_contract_version") != 1
            or context.get("author_request_hash") != run.get("request_hash")
            or canonical_request_hash(run["request"]) != run.get("request_hash")
            # 旧版把问题全文写入创作输入；保留可读，但不能续跑或保存未成功候选。
            or context.get("author_dialogue_version") not in {None, 2}
            or (context.get("author_dialogue_version") == 2 and (
                context.get("author_answers_hash") != canonical_request_hash(run.get("answers", [])[:len(context.get("author_answer_ids", []))])
                or context.get("author_answer_meanings") is None))
            or context.get("message_hash") != canonical_request_hash(author_guidance(run, context.get("author_answer_ids", []), meanings=context.get("author_answer_meanings")))
            or context.get("target") != run["request"].get("writing_target")
            or context.get("generation_request_hash") != canonical_request_hash(request)):
        raise DomainApiError("ASSISTANT_CREATION_REQUEST_EXPIRED", "旧候选或续跑缺少可靠的创作来源，请保留记录并另发新请求；已保存回执仍可重放", status_code=409)


def describe_generation(task: str, flow_ref: FlowRef | None = None) -> dict:
    """返回所选原方案的真实开始表单及不可变修订。

    Args:
        task: 当前小说支持的原 AI 任务。
        flow_ref: 可选的作者自定义方案修订。
    Returns:
        开始表单 Schema、默认值、原结果 Schema 及位置要求。
    """
    if task not in GENERATION_KINDS:
        raise DomainApiError("ASSISTANT_TASK_UNKNOWN", "此处不支持该生成任务")
    store = flow_store()
    flow = store.get(flow_ref.id, flow_ref.revision) if flow_ref else store.get_default(task)
    if flow.task != task:
        raise DomainApiError("ASSISTANT_FLOW_MISMATCH", "所选方案不属于这个任务")
    start = next(node for node in flow.nodes if node.type == "input")
    return {"task": task, "label": TASKS[task].label, "flow_ref": {"id": flow.id, "revision": flow.revision},
            "flow_name": flow.name, "inputs": port_schema(start, output=True), "defaults": start.values,
            "result_schema": TASKS[task].result_model.model_json_schema(), "available_flows": store.list_flows(task)["flows"],
            "semantics": "position_writing" if task in CONTENT_TASKS else "book_management",
            "instructions": ("按位置创作必须匹配作者本轮 writing_target。作者要求取原消息、真实回答和服务端按位置核实的回答动作，最多 5000 字；inputs 只采用原表单数量、字数和枚举，不采用模型提问全文、补写的要求、搜索词、摘要或资料选择。"
                             if task in CONTENT_TASKS else "全书设计任务会读取全书资料，不能声称按章安全。保持原方案和开始表单。")
                            + ("人物/关系批量及卷人物计划只取作者原话作为要求，保存前核对作者意图；全书核心人物和关系从书初建立，卷人物使用本卷六字段参与计划，不覆盖已有事实。位置不明先提问。" if task in FACT_GENERATION_CONTRACTS else "")
                            + "target 指定原按钮的位置；字段改写另指定 target_field。依赖前组修改时先保存该组，再调用生成。结果为独立审核组。"}


async def run_generation(novel_id: str, session_id: str, run_id: str, *, task: str, inputs: dict, target: ResourceRef | None, target_field: str | None, flow_ref: FlowRef | None, key: str, emit, additional_rounds: int = 0) -> dict:
    """执行原图并立即保存候选；未完成的子流程只在明确继续时重试。

    Args:
        novel_id: 当前小说。
        session_id: 当前会话。
        run_id: 当前轮次。
        task: 原任务名。
        inputs: 原开始表单值。
        target: 原业务按钮的位置。
        target_field: 小说字段改写的目标字段。
        flow_ref: 已选的不可变方案；省略时固定当前默认方案。
        key: 当前工具调用的稳定键。
        emit: 保存可公开的子任务进度。
        additional_rounds: 作者此次明确继续时追加的预算，模型不能自行提供。
    Returns:
        保存原候选依据的独立修改组。
    """
    from .changes import get_change, public_change

    collection = BaseRepository("assistant_changes").collection
    identity = ObjectId(canonical_request_hash({"run": run_id, "key": key})[:24])
    existing = await collection.find_one({"_id": identity, "novel_id": ObjectId(novel_id)})
    if existing and existing["status"] == "applied":
        return existing
    if existing:
        await validate_creation(existing)
        if existing["status"] in {"draft", "reviewed"}:
            return existing
        if existing.get("apply_attempt", {}).get("revision") != existing["revision"] or existing.get("apply_attempt", {}).get("outcome") not in {"not_sent", "not_committed"}:
            raise DomainApiError("ASSISTANT_SAVE_UNKNOWN", "原保存结果仍待核对，请先恢复原请求，不能重新生成", status_code=409)
        task = existing["generation_task"]
        flow_ref = FlowRef.model_validate(existing["generation_request"]["flow_ref"])
        if task in CONTENT_TASKS:
            target = ResourceRef.model_validate(existing["creation_context"]["target"])
            inputs = existing["generation_request"]["flow_inputs"]
    description = describe_generation(task, flow_ref)
    creation_context = {"contract_version": 1, "semantics": "book_management"}
    generation_policy = None
    if task in FACT_GENERATION_CONTRACTS and not existing:
        run = await BaseRepository("assistant_runs").collection.find_one({"_id": ObjectId(run_id), "novel_id": ObjectId(novel_id)})
        if not run or run.get("creation_contract_version") != 1 or canonical_request_hash(run["request"]) != run.get("request_hash"):
            raise DomainApiError("ASSISTANT_CREATION_REQUEST_EXPIRED", "此轮缺少原作者要求，请由作者另发新请求", status_code=409)
        if task != "create_characters_for_volume_by_ai" and target is not None and target.model_dump() != {"resource_type": "novel", "id": novel_id}:
            raise DomainApiError("ASSISTANT_FACT_POSITION_REQUIRED", "全书核心人物和关系从书初建立；其它起点请使用明确位置的事实工具", status_code=409)
        author_request = "\n".join([run["request"]["message"], *(answer["message"] for answer in run.get("answers", []))])
        if len(author_request) > 2000:
            raise DomainApiError("ASSISTANT_FACT_SOURCE_REQUIRED", "请作者用不超过 2000 字说明这批要求，助手不会代写或截断原文", status_code=409)
        inputs = {**inputs, "user_guidance": author_request}
        generation_policy = {"contract": FACT_GENERATION_CONTRACTS[task], "author_request": author_request,
                             "author_answers": deepcopy(run.get("answers", [])), "author_location": deepcopy(run["request"].get("location")),
                             "request_hash": run["request_hash"]}
    if task in CONTENT_TASKS and not existing:
        # 外层模型读过全书，只有发送时固定的作者原话可以成为子任务自由文本。
        run = await BaseRepository("assistant_runs").collection.find_one({"_id": ObjectId(run_id), "novel_id": ObjectId(novel_id)})
        if not run or run.get("creation_contract_version") != 1 or canonical_request_hash(run["request"]) != run.get("request_hash"):
            raise DomainApiError("ASSISTANT_CREATION_REQUEST_EXPIRED", "此轮缺少创作来源，请由作者另发新请求", status_code=409)
        selected = run["request"].get("writing_target")
        if not selected:
            raise DomainApiError("ASSISTANT_WRITING_TARGET_REQUIRED", "请由作者在发送消息时明确选择按位置创作目标")
        if target is None or target.model_dump() != selected:
            raise DomainApiError("ASSISTANT_WRITING_TARGET_MISMATCH", "生成目标必须与作者本轮明确选择的位置一致")
        answer_ids = [answer["id"] for answer in run.get("answers", [])]
        message = author_guidance(run, answer_ids)
        if len(message) > 5000:
            raise DomainApiError("ASSISTANT_WRITING_MESSAGE_TOO_LONG", "按位置创作的作者要求最多 5000 字；请保留原文并缩短后另发，助手不会代为截断")
        allowed = {"count_mode", "count", "target_word_count", "search_scope"} if task in WRITING_TASKS else set()
        selected_inputs = {field: value for field, value in inputs.items() if field in allowed}
        properties = description["inputs"].get("properties", {})
        if set(properties) - allowed - {"user_guidance", "search_text"}:
            raise DomainApiError("ASSISTANT_WRITING_FLOW_INPUTS", "这个方案包含额外开始字段，请从原创作入口明确填写后运行")
        inputs = {**selected_inputs, "user_guidance": message}
        if "search_text" in properties:
            inputs["search_text"] = ""
        creation_context = {"contract_version": 1, "semantics": "position_writing", "target": selected,
                            "author_request_hash": run["request_hash"], "message_hash": canonical_request_hash(message)}
        if answer_ids:
            creation_context["author_answer_ids"] = answer_ids
    scope = {"novel_id": novel_id}
    if target:
        document = await get_resource(novel_id, target)
        if task in CONTENT_TASKS:
            required = PLOT_TASKS.get(task) or WRITING_TASKS[task][0]
            if target.resource_type != required:
                raise DomainApiError("ASSISTANT_TASK_TARGET", f"此任务需要 {required} 位置")
            scope.update(target_type=required, target_id=target.id)
            if task in PLOT_TASKS or task == "write_chapter_by_ai":
                scope["expected_version"] = document["version"]
        elif task in {"plan_volume_launch_by_ai", "create_locations_for_volume_by_ai", "create_characters_for_volume_by_ai", "create_factions_for_volume_by_ai"}:
            if target.resource_type != "volume":
                raise DomainApiError("ASSISTANT_TASK_TARGET", "此任务需要卷位置")
            scope.update(volume_id=target.id, volume_expected_version=document["version"])
    if task in CONTENT_TASKS or task in {"plan_volume_launch_by_ai", "create_locations_for_volume_by_ai", "create_characters_for_volume_by_ai", "create_factions_for_volume_by_ai"}:
        if target is None:
            raise DomainApiError("ASSISTANT_TASK_TARGET", "请选择原任务所在的卷、篇章、场景或章节")
    if task == "rewrite_novel_field_by_ai":
        if not target_field:
            raise DomainApiError("ASSISTANT_TASK_TARGET", "请选择要改写的小说字段")
        scope["target_field"] = target_field
    if task in CONTENT_TASKS:
        from backend.services.task_flows.book_tools import normalize_agent_scope
        scope.update(normalize_agent_scope(scope, task=task))
    if task in WRITING_TASKS and not existing:
        # 数量和枚举仍由原业务合同校验，不允许在这些字段里夹带自由文本。
        WritingGenerateInputV1.model_validate({**scope, **inputs})
    if generation_policy is not None:
        position = {"version": 1, "intent": "volume_start", "target_type": "volume", "target_id": scope["volume_id"]} if task == "create_characters_for_volume_by_ai" else {
            "version": 1, "intent": "book_start", "target_type": "novel", "target_id": novel_id}
        selected_position = next((answer["selected_position"] for answer in reversed(run.get("answers", [])) if answer.get("selected_position")), None)
        if selected_position and selected_position != position:
            raise DomainApiError("ASSISTANT_FACT_POSITION_REQUIRED", "这批资料的起点与作者已经选择的位置不一致，请保留选择并核对", status_code=409)
        generation_policy["position"] = position
    answer_review_usage = None
    if task in CONTENT_TASKS and not existing and answer_ids:
        from backend.services.task_flows.domain import load_task_context

        # 外层解释完整问答，子图只能接收固定动作。候选前后文及问题中的未来资料不能穿过此处。
        loaded = await load_task_context(task, inputs, scope, {})
        material = {"task": task, "target": selected, "author_request": run["request"]["message"],
                    "author_answers": run["answers"], "position_context": json.loads(loaded.ports["writing_context"])}
        interpretation, answer_review_usage = await structured_advice(run["settings"],
            "解释作者对助手原问题的真实回答，包括‘是’‘第二个’的指代。完整问题仅用于意图核对，不是作者要求。"
            "按给出的实际 position_context 判断选择是否适用于当前位置。未选择的选项、问题中的未来正文、候选前后值都不能成为创作要求。"
            "每条回答按原顺序保留 answer_id；只用 schema 中的固定动作准确表达已核实的含义，不输出或夹带剧情。"
            "preserve_ending 只指当前位置原文结局；不能代表问题里另一个未来结局。continue_request 仅用于单纯同意继续原要求或已完成的确认。"
            "若作者已经写出完整明确的新要求，可用 continue_request 让子任务读取作者原文。"
            "结合全部问答判断现在仍未解决的歧义，不能因旧简答曾不明确就永久拒绝。若后来作者自己的完整原文已经明确消解某条简答，"
            "旧简答保持 supported=false、actions=[]，resolved_by_answer_id 指向那条后来已核实的明确回答；后者 supported=true 并给出适当动作。"
            "只消解该条歧义，其它已明确的旧意图仍保留。再次回答‘是’、‘第二个’或补充无关要求不能消解；不能用助手的新问题代替作者原文。"
            "简短回答选择了具体剧情、新人物、不同位置或其它无法用这些动作准确表达的内容，且未被后来明确作者原文消解时，"
            "supported=false、actions=[]、resolved_by_answer_id=null，不能用近似动作代替。",
            material, WritingAnswerReview)
        meanings = interpretation.model_dump(mode="json")["answers"]
        message = author_guidance(run, answer_ids, meanings=meanings)
        if len(message) > 5000:
            raise DomainApiError("ASSISTANT_WRITING_MESSAGE_TOO_LONG", "按位置创作的作者要求最多 5000 字；请保留原文并缩短后另发，助手不会代为截断")
        inputs["user_guidance"] = message
        creation_context.update(author_dialogue_version=2, author_answer_meanings=meanings,
                                author_answers_hash=canonical_request_hash(run["answers"]), message_hash=canonical_request_hash(message))
    request = GraphRunRequest(flow_ref=FlowRef.model_validate(description["flow_ref"]), flow_inputs=inputs, scope=scope, use_stream=False)
    clean_request = request.model_dump(mode="json", exclude={"agent_continuation"})
    creation_context["generation_request_hash"] = canonical_request_hash(clean_request)
    now = get_utc_now()
    child_usage = dict(existing.get("child_usage", {})) if existing else {}
    if answer_review_usage:
        child_usage["author_answer_review"] = {"node_id": "author_answer_review", **answer_review_usage, "model_calls": 1, "usage_complete": True}
    attempt = existing.get("generation_attempt", 1) if existing else 1
    if existing:
        request = GraphRunRequest.model_validate(existing["generation_request"])
        continuation = existing.get("child_continuation")
        if existing.get("child_paused") and not additional_rounds:
            raise DomainApiError("ASSISTANT_CHILD_PAUSED", "原任务已暂停，请由作者明确继续", status_code=409)
        if continuation:
            from backend.services.task_flows.agent_continuation import AgentContinuation
            prior = request.agent_continuation
            request.agent_continuation = AgentContinuation(token=continuation["token"], additional_rounds=prior.additional_rounds if prior and prior.token == continuation["token"] else additional_rounds)
            await collection.update_one({"_id": identity}, {"$set": {"generation_request": request.model_dump(mode="json"), "child_paused": False}})
            await emit("tool_progress", {"task": task, "message": "继续原资料整理，复用仍有效的已完成节点。"})
        else:
            request.agent_continuation = None
            attempt += 1
            await emit("tool_progress", {"task": task, "message": "从已保存的原任务入口重试；先前未完成的模型步骤可能重新调用。"})
    else:
        await collection.insert_one({"_id": identity, "schema_version": 1, "novel_id": ObjectId(novel_id), "session_id": ObjectId(session_id), "run_id": ObjectId(run_id),
                                     "kind": "generation", "revision": 1, "status": "generating", "generation_task": task,
                                     "apply_attempt": {"revision": 1, "outcome": "not_sent"},
                                     "generation_request": request.model_dump(mode="json"), "creation_context": creation_context,
                                     **({"generation_policy": generation_policy} if generation_policy is not None else {}), "created_at": now, "updated_at": now})
    await collection.update_one({"_id": identity}, {"$set": {
        "status": "generating", "generation_attempt": attempt, "child_usage": child_usage, "updated_at": get_utc_now()},
        "$unset": {"program_error": ""}})

    async def progress(event):
        data = event.get("data", {})
        if "usage" in data:
            usage_key = canonical_request_hash({"attempt": attempt, "node": data.get("instance_path", data.get("node_id", "task"))})
            child_usage[usage_key] = {field: data[field] for field in ("node_id", "instance_path", "usage", "model_calls", "usage_complete") if field in data}
            await collection.update_one({"_id": identity}, {"$set": {"child_usage": child_usage}})
        if event["event"] == "done":
            envelope = data["result"]
            basis = envelope["basis"]
            candidate = deepcopy(envelope["candidate"])
            policy = existing.get("generation_policy") if existing else generation_policy
            if task == "create_characters_for_volume_by_ai" and policy and policy["contract"] == "participation_plan_v1":
                from backend.llm.schemas.character_volume_state_pydantic import CharacterVolumePlanFieldsV1
                # 只为本次明确的计划请求取六字段；原九字段输出完整留在 envelope，旧候选不升级。
                for row in candidate["characters"]:
                    row["state"] = {field: value for field, value in row["state"].items() if field in CharacterVolumePlanFieldsV1.model_fields}
            sources, before = [], {}
            if task in POSITION_REVIEW_TASKS:
                # 原任务已固定按位置读取依据，不能再用整实体的统计版本替代它。
                sources = deepcopy(basis.get("source_refs", []))
            else:
                for value in basis.get("source_refs", []):
                    ref = ResourceRef(resource_type=value["resource_type"], id=value["id"])
                    content = public_content(ref.resource_type, await get_resource(novel_id, ref))
                    if content["version"] != value["version"]:
                        raise DomainApiError("ASSISTANT_SOURCE_CHANGED", "原任务完成时资料已修改，请重新生成", status_code=409)
                    sources.append({**ref.model_dump(), "version": content["version"], "fingerprint": content_fingerprint(content)})
                    if ref == target or (task == "rewrite_novel_field_by_ai" and ref.resource_type == "novel"):
                        before[f"{ref.resource_type}:{ref.id}"] = content
            await collection.update_one({"_id": identity, "status": "generating"}, {"$set": {
                "status": "draft", "candidate": candidate, "envelope": envelope, "sources": sources, "source_refs": sources,
                "before": before, "queries": [], "review": None, "child_paused": False, "updated_at": get_utc_now()}, "$unset": {"child_continuation": "", "program_error": ""}})
        elif event["event"] == "error":
            editable = data.get("details", {}).get("editable_candidate")
            if editable:
                await progress({"event": "done", "data": {"result": editable}})
                await collection.update_one({"_id": identity}, {"$set": {"program_error": {"code": data.get("code"), "message": data.get("message", "请修改候选后重新审核")}}})
            await emit("tool_progress", {"task": task, "state": "error", "message": data.get("message", "原任务未完成")})
        else:
            # 原图的模型签名、提示和节点输出只保留在其候选依据中，不当成公开进度。
            await emit("tool_progress", {"task": task, **{field: data[field] for field in ("node_id", "instance_path", "state", "status", "message", "usage", "model_calls", "usage_complete", "characters", "round", "tool_calls", "call_count") if field in data}})
    try:
        await generate_task_flow(task, request, scope=request.scope, stream=False, on_event=progress)
    except DomainApiError as exc:
        saved = await get_change(novel_id, str(identity))
        if saved["status"] == "draft":
            return saved
        continuation = exc.details.get("agent_continuation")
        if continuation or exc.code in {"AGENT_ROUND_BUDGET_EXCEEDED", "AGENT_TOOL_BUDGET_EXCEEDED", "AGENT_CONTINUATION_EXPIRED", "AGENT_CONTINUATION_CHANGED"}:
            message = "原资料整理已达到预算，请明确继续。" if continuation else "原任务的续跑记录不可用。再次继续会从已保存的原任务入口重新执行，未完成步骤可能重新调用模型。"
            await collection.update_one({"_id": identity}, {"$set": {"child_paused": True, "child_continuation": continuation, "program_error": {"code": exc.code, "message": message}, "updated_at": get_utc_now()}})
            await emit("change", public_change(await get_change(novel_id, str(identity))))
            raise DomainApiError("ASSISTANT_CHILD_PAUSED", message, status_code=409) from exc
        raise
    return await get_change(novel_id, str(identity))


async def confirm_generation(change: dict, *, session) -> dict:
    """把未改动的原依据和审核候选交给原确认服务。

    Args:
        change: 原生成任务的独立修改组。
        session: 外层保存或预演事务。
    Returns:
        业务资料的实际变化和原确认结果，不返回内部回执字段。
    """
    await validate_creation(change, session=session)
    from backend.api.default_routers.novel_router import NovelAIFieldConfirmationRequestV1
    from backend.llm.schemas.character_pydantic import CoreCharactersAIConfirmationRequestV1
    from backend.llm.schemas.novel_pydantic import CoreFactionsAIConfirmationRequestV2
    from backend.llm.schemas.character_relation_pydantic import CharacterRelationsAIConfirmationRequestV1
    from backend.llm.schemas.faction_relation_pydantic import FactionRelationsAIConfirmationRequestV1
    from backend.llm.schemas.world_rule_pydantic import CoreWorldRulesConfirmV1
    from backend.llm.schemas.location_pydantic import LocationBulkGeneratedRequestV1
    from backend.llm.schemas.item_pydantic import ItemBulkGeneratedRequestV1
    from backend.llm.schemas.volume_planning_pydantic import VolumeBulkPlanRequestV1, VolumeLaunchConfirmV1
    from backend.llm.schemas.volume_entity_pydantic import VolumeCharactersPlanConfirmV1, VolumeCharactersPlanResultV1, VolumeFactionsConfirmV1
    from backend.services.novel.writing_contract import WritingConfirmV1
    from backend.services.novel.plot_contract import PlotConfirmV1
    from backend.services.novel.writing_generation import confirm_writing
    from backend.services.novel.plot_service import confirm_plot
    from backend.services.llm.volume_entity_generation_service import confirm_volume_entities
    from .domain import NovelService, VolumeService, FactionService, FactionRelationService, WorldRuleService, LocationService, ItemService

    task, novel_id = change["generation_task"], str(change["novel_id"])
    result_model = VolumeCharactersPlanResultV1 if task == "create_characters_for_volume_by_ai" else TASKS[task].result_model
    candidate = result_model.model_validate(change["candidate"]).model_dump(mode="json")
    basis = deepcopy(change["envelope"]["basis"])
    inputs = basis["generation_input"] if "generation_input" in basis else basis["flow_snapshot"]["business_input"]
    expected = {f"{ref['resource_type']}:{ref['id']}": ref["version"] for ref in basis["source_refs"]}
    payload = {"candidate": candidate, "basis": basis, "generation_input": inputs, "expected_versions": expected, "request_type": "ai_confirmation"}
    key = f"assistant:{change['_id']}:{change['revision']}"
    # 只比较原任务会写的业务类型；内部保护计数和统计不构造撤销内容。
    before = {}
    for kind in GENERATION_KINDS[task]:
        spec = RESOURCES[kind]
        query = {"_id": ObjectId(novel_id)} if kind == "novel" else {"novel_id": ObjectId(novel_id)}
        async for document in BaseRepository(spec.collection).collection.find(query, session=session):
            content = public_content(kind, document)
            before[(kind, content["id"])] = content
    common = {"idempotency_key": key, "session": session}
    saved_batch, identities = None, {}
    if task == "rewrite_novel_field_by_ai":
        payload["request_type"] = "ai_field_confirmation"
        await NovelService.confirm_ai_field(novel_id, NovelAIFieldConfirmationRequestV1.model_validate(payload), **common)
    elif task == "create_factions_by_ai":
        payload.update(selected_faction_refs=[row["faction_ref"] for row in candidate["core_factions"]], selected_relation_refs=[row["relation_ref"] for row in candidate["faction_relations"]])
        await FactionService.bulk_create_core_factions_with_relations(novel_id, CoreFactionsAIConfirmationRequestV2.model_validate(payload), **common)
    elif task == "create_characters_by_ai":
        from backend.services.novel.character_fact_batch_service import create_character_fact_batch
        from backend.services.novel.character_fact_contract import CharacterFactCreateDataV1, CHARACTER_FACT_PROFILE_FIELDS
        payload["selected_character_refs"] = [row["character_ref"] for row in candidate["core_characters"]]
        CoreCharactersAIConfirmationRequestV1.model_validate(payload)
        rows = []
        for row in candidate["core_characters"]:
            bindings = []
            for binding in candidate["binding_candidates"]:
                if binding["character_ref"] == row["character_ref"] and binding["faction_id"] is not None:
                    bindings.append({"faction_id": binding["faction_id"], "faction_version": expected[f"faction:{binding['faction_id']}"],
                        **{field: binding[field] for field in ("membership_type", "role_title", "public_status", "loyalty_level")}, "notes": binding["reason"]})
            rows.append({"candidate_ref": row["character_ref"], "profile": {**{field: value for field, value in row.items() if field in CharacterFactCreateDataV1.model_fields}, "is_core_character": True},
                         "facts": {field: value for field, value in row.items() if field in CHARACTER_FACT_PROFILE_FIELDS}, "bindings": bindings})
        saved_batch = await create_character_fact_batch(novel_id, {"position": change["generation_policy"]["position"], "candidates": rows,
            "generation": {"basis": basis, "generation_input": inputs}, "confirmed": True}, **common)
        identities = {row["candidate_ref"]: row["character_id"] for row in saved_batch["characters"]}
    elif task == "create_character_relations_by_ai":
        from backend.services.novel.character_fact_batch_service import create_character_relation_fact_batch
        from backend.services.novel.character_relation_fact_contract import CharacterRelationFactCreateDataV1
        payload.update(selected_character_refs=inputs["character_ids"], selected_relation_refs=[row["relation_ref"] for row in candidate["relations"]])
        CharacterRelationsAIConfirmationRequestV1.model_validate(payload)
        saved_batch = await create_character_relation_fact_batch(novel_id, {"position": change["generation_policy"]["position"],
            "candidates": [{"candidate_ref": row["relation_ref"], "profile": {field: value for field, value in row.items() if field in CharacterRelationFactCreateDataV1.model_fields},
                            "facts": {"current_state": row["current_state"]}} for row in candidate["relations"]],
            "generation": {"basis": basis, "generation_input": inputs}, "confirmed": True}, **common)
        identities = {row["candidate_ref"]: row["relation_id"] for row in saved_batch["relations"]}
    elif task == "create_faction_relations_by_ai":
        entity = "faction"
        payload[f"selected_{entity}_refs"] = inputs[f"{entity}_ids"]
        payload["selected_relation_refs"] = [row["relation_ref"] for row in candidate["relations"]]
        await FactionRelationService.bulk_append_relations(novel_id, FactionRelationsAIConfirmationRequestV1.model_validate(payload), **common)
    elif task in {"create_world_rules_by_ai", "create_locations_for_volume_by_ai", "create_items_by_ai", "create_volume_skeleton_by_ai"}:
        model, field, service = {
            "create_world_rules_by_ai": (CoreWorldRulesConfirmV1, "core_world_rules", WorldRuleService.bulk_create_core_world_rules),
            "create_locations_for_volume_by_ai": (LocationBulkGeneratedRequestV1, "locations", LocationService.bulk_create_generated_locations),
            "create_items_by_ai": (ItemBulkGeneratedRequestV1, "items", ItemService.bulk_create_generated_items),
            "create_volume_skeleton_by_ai": (VolumeBulkPlanRequestV1, "volumes", VolumeService.bulk_plan_volumes),
        }[task]
        await service(novel_id, model.model_validate({"candidates": candidate[field], "basis": basis, "expected_versions": expected}), **common)
    elif task == "plan_volume_launch_by_ai":
        await VolumeService.confirm_launch_package(inputs["volume_id"], VolumeLaunchConfirmV1.model_validate({**candidate["launch_package"], "basis": basis, "expected_version": inputs["volume_expected_version"]}), **common)
    elif task in {"create_characters_for_volume_by_ai", "create_factions_for_volume_by_ai"}:
        field, model = ("characters", VolumeCharactersPlanConfirmV1) if task == "create_characters_for_volume_by_ai" else ("factions", VolumeFactionsConfirmV1)
        request = {"candidates": candidate[field], "basis": basis}
        if task == "create_characters_for_volume_by_ai":
            request["contract"] = "participation_plan_v1"
        result = await confirm_volume_entities(task, novel_id, inputs["volume_id"], model.model_validate(request), **common)
        if task == "create_characters_for_volume_by_ai":
            saved_batch, identities = result, result["mapping"]
    elif task in PLOT_TASKS:
        await confirm_plot(task, inputs["target_id"], PlotConfirmV1.model_validate({"candidate": candidate, "basis": basis, "expected_version": inputs["expected_version"]}), **common)
    else:
        await confirm_writing(task, inputs["target_id"], WritingConfirmV1.model_validate({"candidate": candidate, "basis": basis, "expected_version": inputs.get("expected_version")}), **common)
    operations, resources = [], []
    for kind in GENERATION_KINDS[task]:
        spec = RESOURCES[kind]
        query = {"_id": ObjectId(novel_id)} if kind == "novel" else {"novel_id": ObjectId(novel_id)}
        async for document in BaseRepository(spec.collection).collection.find(query, session=session):
            after = public_content(kind, document)
            original = before.get((kind, after["id"]))
            if original and content_fingerprint(original) == content_fingerprint(after):
                continue
            resources.append(after)
            fields = {field: value for field, value in after.items() if field in spec.update.model_fields and (original is None or original.get(field) != value)}
            if original and kind == "volume" and "plot" not in fields:
                from backend.services.novel.plot_service import plot_hash
                for stage in reversed(("factions", "characters", "locations")):
                    if original.get("preparation", {}).get(stage) != after.get("preparation", {}).get(stage):
                        operations.append({"operation": {"action": "preparation", "resource_type": kind, "id": after["id"], "fields": {"kind": stage, "confirmed": after.get("preparation", {}).get(stage) == plot_hash(after.get("plot", ""))}, "reason": TASKS[task].label}, "before": [original], "after": [after]})
            if original and not fields:
                continue
            operations.append({"operation": {"action": "create" if original is None else "update", "resource_type": kind, "id": after["id"], "fields": fields, "reason": TASKS[task].label},
                               "before": [original] if original else [], "after": [after]})
    return {"operations": operations, "identities": identities, "resources": resources, "generation_task": task,
            **({"generation_result": saved_batch} if saved_batch is not None else {})}
