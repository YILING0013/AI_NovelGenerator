from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.check_architecture_prompt_leakage import check_runtime_architecture


def test_check_runtime_architecture_passes_for_valid_runtime_ranges():
    text = """
## 0. Meta
keep-0

## 13. Archive
drop-13

## 88. Runtime
keep-88

## 136. Gate
keep-136
""".strip()

    issues = check_runtime_architecture(text)

    assert issues == []


def test_check_runtime_architecture_fails_when_required_sections_missing():
    text = """
## 0. Meta
keep-0

## 13. Archive
drop-13
""".strip()

    issues = check_runtime_architecture(text)

    assert any("关键节：88" in issue for issue in issues)
    assert any("关键节：136" in issue for issue in issues)


def test_cli_strict_returns_nonzero_on_invalid_runtime(tmp_path: Path):
    architecture_file = tmp_path / "Novel_architecture.txt"
    architecture_file.write_text(
        """
## 0. Meta
keep-0

## 13. Archive
drop-13
""".strip(),
        encoding="utf-8",
    )

    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_architecture_prompt_leakage.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--architecture",
            str(architecture_file),
            "--strict",
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
