from __future__ import annotations

from pathlib import Path

from scripts.verify_ui_blueprint_path_strict import _run_runtime_prompt_guards


def _write_prompt_log(path: Path, prompt_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"## Prompt\n\n```\n{prompt_text}\n```\n",
        encoding="utf-8",
    )


def test_run_runtime_prompt_guards_passes_for_clean_runtime(tmp_path: Path):
    (tmp_path / "Novel_architecture.txt").write_text(
        """
## 0. Meta
keep-0

## 13. Archive
drop-13

## 88. Runtime
keep-88

## 136. Gate
keep-136
""".strip(),
        encoding="utf-8",
    )
    _write_prompt_log(
        tmp_path / "llm_logs" / "chapter_1" / "gen_initial.md",
        """
## 0. Meta
keep-0

## 88. Runtime
keep-88
""".strip(),
    )

    report = _run_runtime_prompt_guards(tmp_path, sample_size=20)

    assert report["architecture_issue_count"] == 0
    assert report["log_violation_count"] == 0
    assert report["audit_error"] is None


def test_run_runtime_prompt_guards_detects_architecture_and_log_leak(tmp_path: Path):
    (tmp_path / "Novel_architecture.txt").write_text(
        """
## 0. Meta
keep-0

## 13. Archive
drop-13
""".strip(),
        encoding="utf-8",
    )
    _write_prompt_log(
        tmp_path / "llm_logs" / "chapter_1" / "gen_initial.md",
        """
## 0. Meta
keep-0

## 13. Archive
drop-13
""".strip(),
    )

    report = _run_runtime_prompt_guards(tmp_path, sample_size=20)

    assert report["architecture_issue_count"] > 0
    assert any("关键节：88" in issue for issue in report["architecture_issues"])
    assert any("关键节：136" in issue for issue in report["architecture_issues"])
    assert report["log_violation_count"] == 1
