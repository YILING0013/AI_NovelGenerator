# -*- coding: utf-8 -*-
"""Prompt contract tests: placeholder compatibility and canonical source alignment."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import prompt_definitions
import prompts


REPO_ROOT = Path(__file__).resolve().parents[2]
FIELD_RE = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")


def _extract_string_fields(file_path: Path) -> dict[str, set[str]]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    fields: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            fields[target.id] = set(FIELD_RE.findall(value.value))
    return fields


def _extract_format_calls(file_path: Path) -> dict[str, set[str]]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    calls: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "format":
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        prompt_name = node.func.value.id
        kwargs = {kw.arg for kw in node.keywords if kw.arg}
        calls[prompt_name] = kwargs
    return calls


def test_prompt_definitions_uses_prompts_as_runtime_source() -> None:
    canonical_names = [
        "first_chapter_draft_prompt",
        "next_chapter_draft_prompt",
        "summarize_recent_chapters_prompt",
        "knowledge_search_prompt",
        "knowledge_filter_prompt",
        "summary_prompt",
        "core_seed_prompt",
        "character_dynamics_prompt",
        "world_building_prompt",
        "plot_architecture_prompt",
        "create_character_state_prompt",
        "update_character_state_prompt",
    ]
    for name in canonical_names:
        assert getattr(prompt_definitions, name) == getattr(prompts, name)


def test_chapter_prompt_format_contracts() -> None:
    prompt_fields = _extract_string_fields(REPO_ROOT / "prompts/chapter_prompts.py")
    call_fields = _extract_format_calls(REPO_ROOT / "novel_generator/chapter.py")

    for prompt_name in ("first_chapter_draft_prompt", "next_chapter_draft_prompt"):
        assert prompt_name in prompt_fields
        assert prompt_name in call_fields
        assert prompt_fields[prompt_name] == call_fields[prompt_name]


def test_blueprint_prompt_required_fields_are_provided() -> None:
    prompt_fields = _extract_string_fields(REPO_ROOT / "prompt_definitions.py")
    required = prompt_fields["chunked_chapter_blueprint_prompt"]

    for rel in (
        "strict_blueprint_generator.py",
        "scripts/chapter_directory_fix.py",
        "scripts/blueprint_optimized.py",
    ):
        call_fields = _extract_format_calls(REPO_ROOT / rel)
        assert "chunked_chapter_blueprint_prompt" in call_fields
        assert required.issubset(call_fields["chunked_chapter_blueprint_prompt"])
