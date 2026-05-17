from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.llm_routers import create_novel_router
from backend.llm.schemas.novel_pydantic import (
    CoreSeedSchema,
    ExpandIdeaSchema,
    ExtractIdeaSchema,
    NovelMetaSchema,
)


PLOT_TEXT = "少年在废土边城发现失落文明遗迹，并被迫卷入多方势力争夺。" * 12
INTRO_TEXT = "这是一段用于测试的小说引言，描写主角在危机中踏入更广阔世界，并让读者快速理解故事张力。" * 3
SUMMARY_TEXT = "这是一段用于测试的小说简介，概括主线冲突、人物目标以及后续冒险方向，确保满足模型字段长度。" * 3
WORLDVIEW_TEXT = "世界由旧文明残骸、流浪城邦和失控能源构成，各方势力围绕遗迹技术展开长期争夺。" * 4


def _expand_payload() -> dict[str, Any]:
    """构造合法的扩写剧情缓存。

    Args:
        None.

    Returns:
        可通过 ExpandIdeaSchema 校验的字典。
    """
    return ExpandIdeaSchema(plot=PLOT_TEXT).model_dump()


def _extract_payload() -> dict[str, Any]:
    """构造合法的提炼创意缓存。

    Args:
        None.

    Returns:
        可通过 ExtractIdeaSchema 校验的字典。
    """
    return ExtractIdeaSchema(
        genre="科幻",
        tone="热血",
        target_audience="男频",
        core_idea="废土少年依靠失落文明遗产改变自身命运，并重塑旧世界秩序。",
    ).model_dump()


def _seed_payload() -> dict[str, Any]:
    """构造合法的故事核心缓存。

    Args:
        None.

    Returns:
        可通过 CoreSeedSchema 校验的字典。
    """
    return CoreSeedSchema(core_seed="废土少年发现遗迹能源，却必须在城邦追杀与文明真相之间做出选择。").model_dump()


def _meta_payload() -> dict[str, Any]:
    """构造合法的小说设定结果。

    Args:
        None.

    Returns:
        可通过 NovelMetaSchema 校验的字典。
    """
    return NovelMetaSchema(
        title="废土星火",
        subtitle="失落文明的继承者",
        introduction=INTRO_TEXT,
        summary=SUMMARY_TEXT,
        worldview=WORLDVIEW_TEXT,
        writing_style="热血冒险",
        narrative_pov="第三人称有限视角",
        era_background="废土未来",
        tags=["废土", "遗迹", "成长"],
    ).model_dump()


def _prompts() -> dict[str, dict[str, str]]:
    """构造测试用 prompt 模板，避免读取真实提示词文件。

    Args:
        None.

    Returns:
        create_novel_by_ai 工作流所需的最小模板集合。
    """
    return {
        "create_novel_by_ai": {
            "expand_idea_to_full_novel_story_prompt_base": "{user_idea}",
            "expand_idea_to_full_novel_story_prompt_with_schema_suffix": "",
            "expand_idea_to_full_novel_story_prompt_without_schema_suffix": "",
            "extract_idea_prompt_base": "{plot}",
            "extract_idea_prompt_with_schema_suffix": "",
            "extract_idea_prompt_without_schema_suffix": "",
            "core_seed_prompt_base": (
                "{plot}{genre}{tone}{target_audience}{core_idea}"
                "{number_of_chapters}{words_per_chapter}"
            ),
            "core_seed_prompt_with_schema_suffix": "",
            "core_seed_prompt_without_schema_suffix": "",
            "novel_meta_prompt_base": (
                "{plot}{genre}{tone}{target_audience}{core_idea}"
                "{number_of_chapters}{words_per_chapter}{core_seed}"
            ),
            "novel_meta_prompt_with_schema_suffix": "",
            "novel_meta_prompt_without_schema_suffix": "",
        }
    }


def _parse_sse_events(text: str) -> list[dict[str, Any]]:
    """解析测试响应中的 SSE 事件。

    Args:
        text: TestClient 返回的完整 SSE 文本。

    Returns:
        按顺序排列的事件字典，每项包含 event 与 data。
    """
    events: list[dict[str, Any]] = []
    for part in text.strip().split("\n\n"):
        event_type = "message"
        event_data = ""
        for line in part.splitlines():
            if line.startswith("event: "):
                event_type = line.removeprefix("event: ")
            elif line.startswith("data: "):
                event_data = line.removeprefix("data: ")
        if event_data:
            events.append({"event": event_type, "data": json.loads(event_data)})
    return events


def _install_fake_workflow(monkeypatch: pytest.MonkeyPatch, calls: list[str], fail_step: str | None = None) -> None:
    """替换创建小说流程依赖的 LLM 与配置读取函数。

    Args:
        monkeypatch: pytest monkeypatch 实例。
        calls: 用于记录实际调用的工作流步骤。
        fail_step: 需要模拟失败的工作流步骤名。

    Returns:
        无返回值。
    """

    class FakeService:
        def __init__(self, step_name: str) -> None:
            self.step_name = step_name

        async def generate_structured(self, prompt: str, schema: type[Any], **kwargs: Any):
            if self.step_name == fail_step:
                raise RuntimeError(f"{self.step_name} failed")
            if schema is ExpandIdeaSchema:
                return ExpandIdeaSchema.model_validate(_expand_payload())
            if schema is ExtractIdeaSchema:
                return ExtractIdeaSchema.model_validate(_extract_payload())
            if schema is CoreSeedSchema:
                return CoreSeedSchema.model_validate(_seed_payload())
            if schema is NovelMetaSchema:
                return NovelMetaSchema.model_validate(_meta_payload())
            raise AssertionError(f"unexpected schema: {schema}")

    def fake_get_service(workflow_name: str, step_name: str) -> FakeService:
        # 记录实际生成步骤；缓存步骤不应创建 LLMService。
        calls.append(step_name)
        return FakeService(step_name)

    monkeypatch.setattr(create_novel_router, "_load_prompts", _prompts)
    monkeypatch.setattr(create_novel_router, "_check_json_schema_support", lambda step_name: True)
    monkeypatch.setattr(create_novel_router, "resolve_provider_for_step", lambda workflow_name, step_name: "fake")
    monkeypatch.setattr(create_novel_router, "resolve_timeout_for_step", lambda workflow_name, step_name: None)
    monkeypatch.setattr(create_novel_router, "get_llm_service_for_step", fake_get_service)


def test_create_novel_resume_uses_cached_prefix_for_novel_meta_only(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _install_fake_workflow(monkeypatch, calls)

    response = client.post(
        "/api/llm/create-novel-by-ai",
        json={
            "user_idea": "一个废土少年寻找失落文明的故事",
            "number_of_chapters": 120,
            "words_per_chapter": 3000,
            "cached_steps": {
                "expand_idea": _expand_payload(),
                "extract_idea": _extract_payload(),
                "core_seed": _seed_payload(),
            },
        },
    )

    assert response.status_code == 200, response.text
    events = _parse_sse_events(response.text)
    step_events = [event["data"] for event in events if event["event"] == "step"]
    done_event = next(event["data"] for event in events if event["event"] == "done")

    assert calls == ["novel_meta"]
    assert [event["step"] for event in step_events if event.get("cached")] == [
        "expand_idea",
        "extract_idea",
        "core_seed",
    ]
    assert done_event["success"] is True
    assert done_event["result"]["novel_meta"]["title"] == "废土星火"


def test_create_novel_failure_returns_partial_result(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _install_fake_workflow(monkeypatch, calls, fail_step="extract_idea")

    response = client.post(
        "/api/llm/create-novel-by-ai",
        json={
            "user_idea": "一个废土少年寻找失落文明的故事",
            "number_of_chapters": 120,
            "words_per_chapter": 3000,
        },
    )

    assert response.status_code == 200, response.text
    events = _parse_sse_events(response.text)
    done_event = next(event["data"] for event in events if event["event"] == "done")

    assert calls == ["expand_idea_to_full_novel_story", "extract_idea"]
    assert done_event["success"] is False
    assert done_event["failed_step"] == "extract_idea"
    assert done_event["partial_result"] == {"expand_idea": _expand_payload()}


def test_create_novel_ignores_non_contiguous_cached_steps(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _install_fake_workflow(monkeypatch, calls)

    response = client.post(
        "/api/llm/create-novel-by-ai",
        json={
            "user_idea": "一个废土少年寻找失落文明的故事",
            "number_of_chapters": 120,
            "words_per_chapter": 3000,
            "cached_steps": {
                "core_seed": _seed_payload(),
            },
        },
    )

    assert response.status_code == 200, response.text
    events = _parse_sse_events(response.text)
    step_events = [event["data"] for event in events if event["event"] == "step"]

    assert calls == [
        "expand_idea_to_full_novel_story",
        "extract_idea",
        "core_seed",
        "novel_meta",
    ]
    assert not any(event.get("cached") for event in step_events)
