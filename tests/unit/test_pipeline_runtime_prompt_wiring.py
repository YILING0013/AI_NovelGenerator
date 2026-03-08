from __future__ import annotations

from novel_generator import chapter as chapter_module
from novel_generator.pipeline import RuntimeChapterGenerator
from novel_generator.pipeline_interfaces import GenerationContext, PromptData


def test_runtime_chapter_generator_marks_prebuilt_prompt_as_complete(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_generate_chapter_draft(**kwargs):
        captured.update(kwargs)
        return "第1章 标题\n正文"

    monkeypatch.setattr(chapter_module, "generate_chapter_draft", fake_generate_chapter_draft)

    generator = RuntimeChapterGenerator({"word_number": 1800})
    context = GenerationContext(
        project_path="/tmp/project",
        chapter_number=1,
        total_chapters=10,
        interface_format="openai",
        api_key="",
        base_url="",
        model_name="dummy-model",
        temperature=0.7,
        max_tokens=256,
        timeout=5,
        user_guidance="用户指导",
        characters_involved=["主角", "师父"],
        scene_location="山门",
    )
    prompt = PromptData(prompt_type="draft", content="已构建完整提示词")

    chapter = generator.generate(context, prompt)

    assert captured["custom_prompt_text"] == "已构建完整提示词"
    assert captured["custom_prompt_is_complete"] is True
    assert chapter.chapter_title == "标题"
