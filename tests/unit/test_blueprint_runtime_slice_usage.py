from __future__ import annotations

from pathlib import Path
from typing import Any

from novel_generator.blueprint import StrictChapterGenerator


class _DummyComplianceChecker:
    def __init__(self, _filepath: str, novel_corpus_name: str = "") -> None:
        self.novel_corpus_name = novel_corpus_name

    def generate_report_file(self) -> str:
        return "dummy_report.md"

    def check_compliance_result(self) -> dict[str, Any]:
        return {"passed": True, "hard_fail_reasons": []}


def _create_generator(monkeypatch) -> StrictChapterGenerator:
    monkeypatch.setattr(
        "novel_generator.blueprint.create_llm_adapter",
        lambda **kwargs: object(),
    )
    return StrictChapterGenerator(
        interface_format="test",
        api_key="test",
        base_url="http://test.local",
        llm_model="test-model",
        timeout=1,
    )


def test_blueprint_generation_uses_runtime_sliced_architecture(monkeypatch, tmp_path: Path):
    architecture_file = tmp_path / "Novel_architecture.txt"
    architecture_file.write_text(
        """
## 0. Meta
keep-0

## 13. Archive
drop-13

## 88. Runtime
keep-88
""".strip(),
        encoding="utf-8",
    )

    captured: dict[str, str] = {}
    generator = _create_generator(monkeypatch)

    def fake_generate_batch(_start, _end, architecture_text, _final, _filepath, *_extra):
        captured["architecture_text"] = architecture_text
        return "第1章 - 标题\n## 1. 基础元信息\n- 完成"

    monkeypatch.setattr(
        generator,
        "_generate_batch_with_retry",
        fake_generate_batch,
    )
    monkeypatch.setattr(
        generator,
        "_strict_validation",
        lambda _content, _start, _end: {"is_valid": True, "errors": []},
    )
    monkeypatch.setattr(
        generator,
        "_run_directory_quality_gate",
        lambda _filepath, _filename: (True, {"summary": {}, "hard_fail_reasons": [], "rewrite_hints": []}),
    )
    monkeypatch.setattr(generator, "_format_cleanup", lambda _filepath: None)
    monkeypatch.setattr(
        generator,
        "_format_cleanup_content",
        lambda content: (
            content,
            {"separator_fixes": 0, "refs_fixed": 0, "chapter_count": 1, "removed": 0},
        ),
    )
    monkeypatch.setattr(
        "novel_generator.architecture_compliance.ArchitectureComplianceChecker",
        _DummyComplianceChecker,
    )

    result = generator.generate_complete_directory_strict(
        filepath=str(tmp_path),
        number_of_chapters=1,
        user_guidance="",
        auto_optimize=False,
        optimize_per_batch=False,
        target_score=80.0,
    )

    assert result is True
    runtime_text = captured["architecture_text"]
    assert "## 0." in runtime_text
    assert "## 88." in runtime_text
    assert "## 13." not in runtime_text
