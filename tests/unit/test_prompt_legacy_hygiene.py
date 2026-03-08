# -*- coding: utf-8 -*-
"""Prevent legacy prompt artifacts from returning to runtime paths."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

LEGACY_FILES = (
    "prompt_definitions_example.py",
    "prompt_definitions.py.backup_7section_fix",
    "prompt_definitions.py.broken",
)

LEGACY_FIX_SCRIPTS = (
    "add_chunked_prompt.py",
    "fix_chunked_prompt.py",
    "fix_prompt_add_fewshot.py",
    "fix_template_sections.py",
    "fix_orphaned_template.py",
    "repair_prompt_file.py",
    "fix_sections_8_to_13.py",
)

ONE_OFF_ROOT_SCRIPTS = (
    "analyze_10_chapters_text.py",
    "analyze_10_new.py",
    "analyze_56_chapters.py",
    "analyze_new_5.py",
    "apply_auto_fix.py",
    "apply_section_fix.py",
    "apply_validation_fix.py",
    "auto_fix_chapter_directory.py",
    "auto_fix_sections.py",
    "batch_quality_check.py",
    "blueprint_format_fix.py",
    "blueprint_strict_requirements_fix.py",
    "capture_generation_error.py",
    "check_10_chapters.py",
    "check_consistency.py",
    "check_llm_response.py",
    "comprehensive_check.py",
    "debug_generation.py",
    "debug_regex_failure.py",
    "debug_v2.py",
    "diagnose_batch_failure.py",
    "diagnose_generation.py",
    "enhanced_auto_fix.py",
    "extract_report.py",
    "extract_report_v2.py",
    "final_root_cause_check.py",
    "fix_blueprint_debug.py",
    "fix_blueprint_format.py",
    "fix_chapter_directory.py",
    "fix_chapter_directory_v2.py",
    "fix_chapter_list_format.py",
    "fix_chapter_list_format_v2.py",
    "fix_double_quotes.py",
    "fix_progressive_generator.py",
    "fix_return_statement.py",
    "generate_one_by_one.py",
    "gui_integration_patch.py",
    "insert_fix_method.py",
    "integration_example.py",
    "manual_test_gen.py",
    "post_generation_fixer.py",
    "read_log.py",
    "run_batch_generation.py",
    "run_progressive_generation.py",
    "show_validation_errors.py",
    "simple_test.py",
    "simulate_gui_blueprint_generation.py",
    "validation_debug_helper.py",
)


def test_legacy_prompt_files_are_archived() -> None:
    for name in LEGACY_FILES:
        assert not (REPO_ROOT / name).exists(), f"{name} should be archived, not kept at repo root"
        assert (REPO_ROOT / "docs/archive/legacy_prompts" / name).exists()


def test_legacy_fix_scripts_are_archived() -> None:
    for name in LEGACY_FIX_SCRIPTS:
        assert not (REPO_ROOT / name).exists(), f"{name} should be archived, not kept at repo root"
        assert (REPO_ROOT / "docs/archive/scripts/legacy_fixes" / name).exists()


def test_one_off_root_scripts_are_archived() -> None:
    for name in ONE_OFF_ROOT_SCRIPTS:
        assert not (REPO_ROOT / name).exists(), f"{name} should be archived, not kept at repo root"
        assert (REPO_ROOT / "docs/archive/scripts/one_off_root" / name).exists()


def test_runtime_source_does_not_import_legacy_archive() -> None:
    runtime_targets = [
        REPO_ROOT / "main.py",
        REPO_ROOT / "llm_adapters.py",
    ]
    runtime_targets.extend((REPO_ROOT / "novel_generator").rglob("*.py"))
    runtime_targets.extend((REPO_ROOT / "ui").rglob("*.py"))
    runtime_targets.extend((REPO_ROOT / "prompts").rglob("*.py"))

    py_files = [
        p for p in runtime_targets
        if p.exists() and ".venv" not in p.parts and "__pycache__" not in p.parts
    ]
    for py_file in py_files:
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        assert "docs/archive/legacy_prompts" not in text, f"legacy archive referenced in {py_file}"
