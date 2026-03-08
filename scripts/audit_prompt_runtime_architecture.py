from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from novel_generator.architecture_runtime_slice import split_top_sections


PROMPT_BLOCK_RE = re.compile(
    r"(?:^##\s*Prompt\s*$|^###\s*📝\s*Prompt[^\n]*$)\s*\n```(?:[^\n]*)\n(.*?)\n```",
    re.MULTILINE | re.DOTALL,
)


@dataclass
class CliArgs(argparse.Namespace):
    project_dir: str = "wxhyj"
    sample_size: int = 20
    strict: bool = False


def parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(description="审计生成日志中的运行时架构泄漏痕迹")
    _ = parser.add_argument("--project-dir", default="wxhyj", help="小说目录")
    _ = parser.add_argument("--sample-size", type=int, default=20, help="按最新日志抽样数量（<=0 表示全量）")
    _ = parser.add_argument("--strict", action="store_true", help="发现泄漏即非0退出")
    return parser.parse_args(namespace=CliArgs())


def collect_log_files(project_dir: Path) -> list[Path]:
    patterns = [
        "llm_logs/chapter_*/gen_*.md",
        "llm_conversation_logs/llm_log_chapters_*.md",
    ]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(project_dir.glob(pattern))
    files = [path for path in files if path.is_file()]
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return files


def extract_prompt_blocks(log_text: str) -> list[str]:
    blocks = [match.group(1).strip() for match in PROMPT_BLOCK_RE.finditer(log_text or "")]
    return [block for block in blocks if block]


def find_archive_sections(prompt_text: str) -> list[int]:
    section_numbers = [section_num for section_num, _ in split_top_sections(prompt_text or "")]
    archive_nums = sorted({num for num in section_numbers if 13 <= num <= 87})
    return archive_nums


def audit_project_logs(project_dir: Path, sample_size: int = 20) -> dict[str, Any]:
    files = collect_log_files(project_dir)
    selected = files if sample_size <= 0 else files[:sample_size]

    violations: list[dict[str, Any]] = []
    prompt_blocks = 0
    for log_path in selected:
        try:
            log_text = log_path.read_text(encoding="utf-8")
        except Exception:
            continue
        blocks = extract_prompt_blocks(log_text)
        prompt_blocks += len(blocks)
        for idx, block in enumerate(blocks, start=1):
            archive_nums = find_archive_sections(block)
            if not archive_nums:
                continue
            violations.append(
                {
                    "file": str(log_path),
                    "block_index": idx,
                    "archive_sections": archive_nums,
                }
            )

    return {
        "project_dir": str(project_dir),
        "files_scanned": len(selected),
        "prompt_blocks_scanned": prompt_blocks,
        "violations": violations,
    }


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project_dir)
    if not project_dir.exists() or not project_dir.is_dir():
        print(f"[FAIL] 无效目录: {project_dir}")
        return 1

    report = audit_project_logs(project_dir, sample_size=int(args.sample_size))
    violations = report.get("violations", [])

    print(f"项目目录: {report['project_dir']}")
    print(f"日志文件扫描数: {report['files_scanned']}")
    print(f"Prompt块扫描数: {report['prompt_blocks_scanned']}")
    print(f"泄漏命中数: {len(violations)}")

    for item in violations[:20]:
        sections = ",".join(str(num) for num in item.get("archive_sections", []))
        print(f"- {item.get('file')} [block #{item.get('block_index')}] -> sections: {sections}")

    if args.strict and violations:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
