from __future__ import annotations

import json
from pathlib import Path

from novel_generator.generation_state_facade import GenerationStateFacade
from novel_generator.story_ledger import PromptMemoryContext
from novel_generator import chapter as chapter_module
from novel_generator import finalization as finalization_module


def test_generation_state_facade_exports_legacy_views_and_memory_guidance(tmp_path: Path):
    facade = GenerationStateFacade(str(tmp_path), chapters_per_volume=2)
    facade.commit_chapter_state(
        chapter_number=1,
        chapter_text="第一章正文",
        global_summary_text="全局摘要1",
        character_state_text="角色状态1",
        chapter_summary="第一章摘要",
    )
    facade.commit_chapter_state(
        chapter_number=2,
        chapter_text="第二章正文",
        global_summary_text="全局摘要2",
        character_state_text="角色状态2",
        chapter_summary="第二章摘要",
    )

    context = facade.load_prompt_memory_context(current_chapter_num=3)

    assert context.global_summary_text == "全局摘要2"
    assert context.character_state_text == "角色状态2"
    assert "卷级记忆" in context.memory_guidance
    assert "第二章摘要" in context.memory_guidance
    assert (tmp_path / "global_summary.txt").read_text(encoding="utf-8") == "全局摘要2"


class _NoopArchitectureReader:
    def __init__(self, _text: str) -> None:
        pass

    def get_dynamic_guidelines(self) -> str:
        return ""


def test_build_chapter_prompt_injects_story_ledger_guidance(monkeypatch, tmp_path: Path):
    architecture_path = tmp_path / "Novel_architecture.txt"

    def fake_read_file(path: str) -> str:
        if path.endswith("Novel_architecture.txt"):
            return "## 0. Meta\nkeep-0\n\n## 88. Runtime\nkeep-88"
        return ""

    class _DummyFacade:
        def __init__(self, _project_root: str, chapters_per_volume: int = 50) -> None:
            self.project_root = _project_root

        def load_prompt_memory_context(self, current_chapter_num: int) -> PromptMemoryContext:
            return PromptMemoryContext(
                global_summary_text="全局摘要",
                character_state_text="角色状态",
                volume_summary_text="第一卷推进至关键冲突",
                hook_summary_text="未回收伏笔：青铜门",
                thread_summary_text="主线：复仇", 
                memory_guidance="【长期记忆账本】\n卷级记忆：第一卷推进至关键冲突",
            )

    monkeypatch.setattr(chapter_module, "GenerationStateFacade", _DummyFacade)
    monkeypatch.setattr(chapter_module, "resolve_architecture_file", lambda *_args, **_kwargs: str(architecture_path))
    monkeypatch.setattr(chapter_module, "read_file", fake_read_file)
    monkeypatch.setattr(chapter_module, "get_chapter_info_from_blueprint", lambda _bp, _num: {})
    monkeypatch.setattr(
        chapter_module,
        "extract_protagonist_info",
        lambda _filepath: {
            "protagonist_name": "主角",
            "system_name": "天书",
            "core_abilities": "改命",
            "protagonist_identity": "测试身份",
        },
    )
    monkeypatch.setattr(chapter_module, "ArchitectureReader", _NoopArchitectureReader)
    monkeypatch.setattr(chapter_module, "first_chapter_draft_prompt", "{user_guidance}")

    prompt = chapter_module.build_chapter_prompt(
        api_key="",
        base_url="",
        model_name="",
        filepath=str(tmp_path),
        novel_number=1,
        word_number=1000,
        temperature=0.7,
        user_guidance="",
        characters_involved="",
        key_items="",
        scene_location="",
        time_constraint="",
        embedding_api_key="",
        embedding_url="",
        embedding_interface_format="",
        embedding_model_name="",
        embedding_retrieval_k=2,
        interface_format="openai",
        max_tokens=128,
        timeout=5,
    )

    assert "【长期记忆账本】" in prompt


def test_build_chapter_prompt_injects_filtered_context_into_user_guidance(
    monkeypatch,
    tmp_path: Path,
):
    architecture_path = tmp_path / "Novel_architecture.txt"
    architecture_path.write_text("## 0. Meta\nkeep-0\n\n## 88. Runtime\nkeep-88", encoding="utf-8")

    class _DummyFacade:
        def __init__(self, _project_root: str, chapters_per_volume: int = 50) -> None:
            self.project_root = _project_root

        def load_prompt_memory_context(self, current_chapter_num: int) -> PromptMemoryContext:
            return PromptMemoryContext(
                global_summary_text="全局摘要",
                character_state_text="角色状态",
                volume_summary_text="卷级记忆",
                hook_summary_text="未回收伏笔：青铜门",
                thread_summary_text="主线：复仇",
                memory_guidance="【长期记忆账本】\n卷级记忆：关键冲突正在升温",
            )

    monkeypatch.setattr(chapter_module, "GenerationStateFacade", _DummyFacade)
    monkeypatch.setattr(chapter_module, "resolve_architecture_file", lambda *_args, **_kwargs: str(architecture_path))
    monkeypatch.setattr(chapter_module, "read_file", lambda _path: architecture_path.read_text(encoding="utf-8"))
    monkeypatch.setattr(chapter_module, "build_runtime_architecture_context", lambda text, **_kwargs: text)
    monkeypatch.setattr(chapter_module, "contains_archive_sections", lambda _text: False)
    monkeypatch.setattr(chapter_module, "build_runtime_guardrail_brief", lambda _text: "")
    monkeypatch.setattr(chapter_module, "get_chapter_info_from_blueprint", lambda _bp, _num: {})
    monkeypatch.setattr(
        chapter_module,
        "load_chapter_info",
        lambda _filepath, chapter_num, blueprint_text_fallback=None: {
            "chapter_title": f"第{chapter_num}章",
            "chapter_role": "推进章节",
            "chapter_purpose": "推进主线",
            "suspense_level": "中",
            "foreshadowing": "青铜门",
            "plot_twist_level": "★★☆☆☆",
            "chapter_summary": "主角追查青铜门线索",
            "characters_involved": "主角",
            "key_items": "青铜门钥匙",
            "scene_location": "北境",
            "time_constraint": "月蚀夜前",
        },
    )
    monkeypatch.setattr(chapter_module, "get_last_n_chapters_text", lambda *_args, **_kwargs: ["前章结尾：主角握紧青铜门钥匙。"])
    monkeypatch.setattr(chapter_module, "summarize_recent_chapters", lambda **_kwargs: "前情摘要：青铜门即将开启。")
    monkeypatch.setattr(chapter_module, "create_llm_adapter", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(chapter_module, "invoke_with_cleaning", lambda *_args, **_kwargs: "青铜门, 月蚀")
    monkeypatch.setattr(chapter_module, "parse_search_keywords", lambda _response: ["青铜门 月蚀"])
    monkeypatch.setattr(chapter_module, "apply_content_rules", lambda contexts, _novel_number: contexts)
    monkeypatch.setattr(
        chapter_module,
        "get_filtered_knowledge_context",
        lambda **_kwargs: "【检索知识】青铜门只有在月蚀夜才能开启。",
    )
    monkeypatch.setattr(chapter_module, "extract_chapter_openings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(chapter_module, "get_cultivation_constraint", lambda _novel_number: {})
    monkeypatch.setattr(chapter_module, "build_chapter_contract", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(chapter_module, "build_chapter_contract_prompt", lambda _contract: "")
    monkeypatch.setattr(chapter_module, "ArchitectureReader", _NoopArchitectureReader)
    monkeypatch.setattr(
        chapter_module,
        "extract_protagonist_info",
        lambda _filepath: {
            "protagonist_name": "主角",
            "system_name": "天书",
            "core_abilities": "改命",
            "protagonist_identity": "测试身份",
        },
    )
    monkeypatch.setattr(chapter_module, "next_chapter_draft_prompt", "{user_guidance}")

    prompt = chapter_module.build_chapter_prompt(
        api_key="",
        base_url="",
        model_name="",
        filepath=str(tmp_path),
        novel_number=2,
        word_number=1200,
        temperature=0.7,
        user_guidance="原始指导",
        characters_involved="主角",
        key_items="青铜门钥匙",
        scene_location="北境",
        time_constraint="月蚀夜前",
        embedding_api_key="",
        embedding_url="",
        embedding_interface_format="",
        embedding_model_name="",
        embedding_retrieval_k=2,
        interface_format="openai",
        max_tokens=128,
        timeout=5,
    )

    assert "【检索知识】青铜门只有在月蚀夜才能开启。" in prompt


def test_finalize_chapter_commits_story_ledger_and_exports_legacy_views(monkeypatch, tmp_path: Path):
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    (chapters_dir / "chapter_1.txt").write_text("第1章 正文", encoding="utf-8")
    (tmp_path / "global_summary.txt").write_text("旧摘要", encoding="utf-8")
    (tmp_path / "character_state.txt").write_text("旧状态", encoding="utf-8")

    class _DummyAdapter:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                return "秦昭野在本章中推进了关键冲突，并且局势仍在升级。"
            return "秦昭野：状态稳定，目标未变。"

    dummy_adapter = _DummyAdapter()

    monkeypatch.setattr(finalization_module, "create_llm_adapter", lambda *_args, **_kwargs: dummy_adapter)
    monkeypatch.setattr(finalization_module, "invoke_with_cleaning", lambda adapter, prompt: adapter.invoke(prompt))
    monkeypatch.setattr(finalization_module, "update_vector_store", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(finalization_module, "_summary_is_valid", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(finalization_module, "_character_state_is_valid", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        "novel_generator.chapter.extract_protagonist_info",
        lambda _filepath: {"protagonist_name": "秦昭野"},
        raising=False,
    )

    finalization_module.finalize_chapter(
        novel_number=1,
        word_number=3000,
        api_key="",
        base_url="",
        model_name="",
        temperature=0.7,
        filepath=str(tmp_path),
        embedding_api_key="",
        embedding_url="",
        embedding_interface_format="openai",
        embedding_model_name="dummy",
        interface_format="openai",
        max_tokens=128,
        timeout=5,
    )

    assert (tmp_path / "global_summary.txt").read_text(encoding="utf-8") == "秦昭野在本章中推进了关键冲突，并且局势仍在升级。"
    assert (tmp_path / "character_state.txt").read_text(encoding="utf-8") == "秦昭野：状态稳定，目标未变。"
    assert (tmp_path / "story_ledger" / "chapters" / "chapter_000001.json").exists()


def test_finalize_chapter_refreshes_runtime_state_artifacts_and_exports_world_state(
    monkeypatch,
    tmp_path: Path,
):
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    chapter_text = "第1章 正文\n秦昭野在月蚀夜拿到青铜门钥匙，并决定三天后进入遗迹。"
    (chapters_dir / "chapter_1.txt").write_text(chapter_text, encoding="utf-8")
    (tmp_path / "global_summary.txt").write_text("旧摘要", encoding="utf-8")
    (tmp_path / "character_state.txt").write_text("旧状态", encoding="utf-8")

    class _DummyAdapter:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                return "秦昭野在本章拿到青铜门钥匙，并确认遗迹探索将于三天后开始。"
            return "秦昭野：状态稳定，生死状态：存活。"

    class _DummyWorldStateManager:
        def __init__(self, output_dir: str) -> None:
            self.state_path = Path(output_dir) / "world_state.json"
            self.state = {
                "world_flags": {"遗迹探索已立项": True},
                "protagonist": {"inventory": ["青铜门钥匙"]},
            }

        def update_state_from_chapter(self, content: str, llm_adapter) -> None:
            assert content == chapter_text
            assert llm_adapter is dummy_adapter
            self.state_path.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")

    class _DummyHookTracker:
        def __init__(self, novel_path: str) -> None:
            self.registry_file = Path(novel_path) / "hook_registry.json"

        def check_resolutions(self, content: str, chapter_num: int):
            assert content == chapter_text
            assert chapter_num == 1
            self.registry_file.write_text(json.dumps({"hooks": [{"status": "resolved"}]}, ensure_ascii=False), encoding="utf-8")
            return 1

        def register_hooks(self, content: str, chapter_num: int):
            assert content == chapter_text
            assert chapter_num == 1
            self.registry_file.write_text(json.dumps({"hooks": [{"status": "open", "hook_text": "青铜门"}]}, ensure_ascii=False), encoding="utf-8")

    class _DummyNarrativeThreadTracker:
        def __init__(self, novel_path: str) -> None:
            self.threads_file = Path(novel_path) / ".narrative_threads.json"

        def update_threads(self, content: str, chapter_num: int):
            assert content == chapter_text
            assert chapter_num == 1
            self.threads_file.write_text(
                json.dumps({"threads": {"探索线": {"last_active": 1}}}, ensure_ascii=False),
                encoding="utf-8",
            )

    class _DummyTimelineManager:
        def __init__(self, novel_path: str) -> None:
            self.state_path = Path(novel_path) / "timeline_state.json"

        def update_timeline(self, chapter_text_value: str, chapter_num: int) -> None:
            assert chapter_text_value == chapter_text
            assert chapter_num == 1
            self.state_path.write_text(
                json.dumps({"current_day": 3, "chapters": {"1": {"day": 3, "source": "relative"}}}, ensure_ascii=False),
                encoding="utf-8",
            )

    dummy_adapter = _DummyAdapter()

    monkeypatch.setattr(finalization_module, "create_llm_adapter", lambda *_args, **_kwargs: dummy_adapter)
    monkeypatch.setattr(finalization_module, "invoke_with_cleaning", lambda adapter, prompt: adapter.invoke(prompt))
    monkeypatch.setattr(finalization_module, "update_vector_store", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(finalization_module, "_summary_is_valid", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(finalization_module, "_character_state_is_valid", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(finalization_module, "WorldStateManager", _DummyWorldStateManager, raising=False)
    monkeypatch.setattr(finalization_module, "HookTracker", _DummyHookTracker, raising=False)
    monkeypatch.setattr(finalization_module, "NarrativeThreadTracker", _DummyNarrativeThreadTracker, raising=False)
    monkeypatch.setattr(finalization_module, "TimelineManager", _DummyTimelineManager, raising=False)
    monkeypatch.setattr(
        "novel_generator.chapter.extract_protagonist_info",
        lambda _filepath: {"protagonist_name": "秦昭野"},
        raising=False,
    )

    finalization_module.finalize_chapter(
        novel_number=1,
        word_number=3000,
        api_key="",
        base_url="",
        model_name="",
        temperature=0.7,
        filepath=str(tmp_path),
        embedding_api_key="",
        embedding_url="",
        embedding_interface_format="openai",
        embedding_model_name="dummy",
        interface_format="openai",
        max_tokens=128,
        timeout=5,
    )

    legacy_views = json.loads((tmp_path / "story_ledger" / "legacy_views.json").read_text(encoding="utf-8"))

    assert json.loads((tmp_path / "world_state.json").read_text(encoding="utf-8")) == {
        "world_flags": {"遗迹探索已立项": True},
        "protagonist": {"inventory": ["青铜门钥匙"]},
    }
    assert legacy_views["world_state"] == {
        "world_flags": {"遗迹探索已立项": True},
        "protagonist": {"inventory": ["青铜门钥匙"]},
    }
    assert json.loads((tmp_path / "hook_registry.json").read_text(encoding="utf-8"))["hooks"]
    assert json.loads((tmp_path / ".narrative_threads.json").read_text(encoding="utf-8"))["threads"]
    assert json.loads((tmp_path / "timeline_state.json").read_text(encoding="utf-8"))["current_day"] == 3
