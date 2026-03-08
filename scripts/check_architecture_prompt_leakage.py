from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from novel_generator.architecture_runtime_slice import (
    build_runtime_architecture_view,
    collect_runtime_architecture_issues,
)
from utils import read_file, resolve_architecture_file


@dataclass
class CliArgs(argparse.Namespace):
    architecture: str | None = None
    project_dir: str = "wxhyj"
    strict: bool = False


def parse_args() -> CliArgs:
    parser = argparse.ArgumentParser(description="检查运行时架构提示词是否泄漏归档节（13-87）")
    _ = parser.add_argument("--architecture", default=None, help="架构文件路径")
    _ = parser.add_argument("--project-dir", default="wxhyj", help="小说目录（用于默认解析架构路径）")
    _ = parser.add_argument("--strict", action="store_true", help="发现问题即非0退出")
    args = parser.parse_args(namespace=CliArgs())
    if args.architecture is None:
        args.architecture = resolve_architecture_file(args.project_dir, prefer_active=False)
    return args


def check_runtime_architecture(architecture_text: str) -> list[str]:
    return collect_runtime_architecture_issues(architecture_text, required_sections=(0, 88, 136))


def main() -> int:
    args = parse_args()
    architecture_path = Path(args.architecture or "")
    if not architecture_path.exists():
        print(f"[FAIL] 架构文件不存在: {architecture_path}")
        return 1

    architecture_text = read_file(str(architecture_path))
    issues = check_runtime_architecture(architecture_text)

    runtime_text = build_runtime_architecture_view(architecture_text)
    print(f"架构文件: {architecture_path}")
    print(f"运行时文本长度: {len(runtime_text)}")

    if not issues:
        print("[PASS] 未检测到归档泄漏，且关键节完整")
        return 0

    print("[WARN] 发现以下问题:")
    for issue in issues:
        print(f"- {issue}")

    if args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
