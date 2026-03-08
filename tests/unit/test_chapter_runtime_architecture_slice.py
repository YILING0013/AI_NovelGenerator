from __future__ import annotations

from pathlib import Path

from novel_generator import chapter as chapter_module


class _NoopArchitectureReader:
    def __init__(self, _text: str) -> None:
        pass

    def get_dynamic_guidelines(self) -> str:
        return ""


def test_build_chapter_prompt_uses_runtime_architecture_view(monkeypatch, tmp_path: Path):
    architecture_path = tmp_path / "Novel_architecture.txt"

    architecture_text = """
## 0. Meta
keep-0

## 13. Archive
drop-13

## 88. Runtime
keep-88
""".strip()

    def fake_read_file(path: str) -> str:
        if path.endswith("Novel_architecture.txt"):
            return architecture_text
        return ""

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
    monkeypatch.setattr(chapter_module, "first_chapter_draft_prompt", "{novel_setting}")

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

    assert "## 0." in prompt
    assert "## 88." in prompt
    assert "## 13." not in prompt
