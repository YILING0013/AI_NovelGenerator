from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.audit_prompt_runtime_architecture import audit_project_logs


def _write_prompt_log(path: Path, prompt_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"## Prompt\n\n```\n{prompt_text}\n```\n",
        encoding="utf-8",
    )


def test_audit_project_logs_detects_archive_section_leak(tmp_path: Path):
    _write_prompt_log(
        tmp_path / "llm_logs" / "chapter_1" / "gen_initial.md",
        """
## 0. Meta
keep-0

## 13. Archive
drop-13
""".strip(),
    )

    report = audit_project_logs(tmp_path, sample_size=20)

    violations = report["violations"]
    assert len(violations) == 1
    assert violations[0]["archive_sections"] == [13]


def test_audit_project_logs_passes_clean_runtime_prompt(tmp_path: Path):
    _write_prompt_log(
        tmp_path / "llm_logs" / "chapter_1" / "gen_initial.md",
        """
## 0. Meta
keep-0

## 88. Runtime
keep-88
""".strip(),
    )

    report = audit_project_logs(tmp_path, sample_size=20)

    assert report["violations"] == []


def test_audit_cli_strict_returns_nonzero_when_violation_exists(tmp_path: Path):
    _write_prompt_log(
        tmp_path / "llm_logs" / "chapter_1" / "gen_initial.md",
        """
## 0. Meta
keep-0

## 13. Archive
drop-13
""".strip(),
    )

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "audit_prompt_runtime_architecture.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--project-dir",
            str(tmp_path),
            "--strict",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
