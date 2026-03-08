#!/usr/bin/env python3
"""
Headless strict verifier for UI blueprint generation path.

This script executes the real UI handler `generate_chapter_blueprint_ui`
non-interactively, captures artifacts, and performs strict structural checks.

It is designed as an operator tool (idempotent on unique run dirs) and avoids
hardcoded machine-specific paths by defaulting to config values.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config_manager import load_config
from scripts.audit_prompt_runtime_architecture import audit_project_logs
from scripts.check_architecture_prompt_leakage import check_runtime_architecture
from utils import resolve_architecture_file


REQUIRED_SECTIONS: list[tuple[int, str]] = [
    (1, "基础元信息"),
    (2, "张力与冲突"),
    (3, "匠心思维应用"),
    (4, "伏笔与信息差"),
    (5, "暧昧与修罗场"),
    (6, "剧情精要"),
    (7, "衔接设计"),
]


CHAPTER_HEADER_PATTERN = re.compile(
    r"(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章"
    r"(?:\s*[-–—:：]\s*[^\n]*)?\s*(?:\*\*)?\s*$"
)


class _ImmediateThread:
    def __init__(
        self,
        group: Any = None,
        target: Callable[..., Any] | None = None,
        name: str | None = None,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        daemon: bool | None = None,
    ) -> None:
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}
        self._running = False

    def start(self) -> None:
        if self._target is not None:
            self._running = True
            try:
                self._target(*self._args, **self._kwargs)
            finally:
                self._running = False

    def is_alive(self) -> bool:
        return self._running

    def join(self, timeout: float | None = None) -> None:
        _ = timeout
        return None


class _Var:
    def __init__(self, value: str) -> None:
        self._value = value

    def get(self) -> str:
        return self._value

    def set(self, value: str) -> None:
        self._value = value


class _Text:
    def __init__(self, value: str) -> None:
        self._value = value

    def get(self, _start: str, _end: str) -> str:
        return self._value


class _Master:
    def after(self, _delay_ms: int, callback: Callable[..., Any], *args: Any) -> None:
        callback(*args)


@dataclass
class _Decision:
    kind: str
    title: str
    decision: bool | None


class _MessageBoxController:
    def __init__(self) -> None:
        self.decisions: list[_Decision] = []
        self.warnings: list[dict[str, str]] = []

    def askyesno(self, title: str, _message: str) -> bool:
        decision = title == "确认"
        self.decisions.append(_Decision("askyesno", title, decision))
        return decision

    def askyesnocancel(self, title: str, _message: str) -> bool | None:
        decision: bool | None = None
        self.decisions.append(_Decision("askyesnocancel", title, decision))
        return decision

    def showwarning(self, title: str, message: str) -> None:
        self.warnings.append({"title": title, "message": message})


class _DummyUI:
    def __init__(
        self,
        filepath: str,
        number_of_chapters: int,
        llm_key: str,
        config: dict[str, Any],
        user_guidance: str,
    ) -> None:
        self.filepath_var = _Var(filepath)
        self.num_chapters_var = _Var(str(number_of_chapters))
        self.chapter_outline_llm_var = _Var(llm_key)
        self.user_guide_text = _Text(user_guidance)
        self.loaded_config = config
        self.master = _Master()
        self.btn_generate_directory = "btn_generate_directory"

        self.logs: list[str] = []
        self.exceptions: list[str] = []

    def safe_get_int(self, var: _Var, default: int) -> int:
        try:
            return int(var.get())
        except Exception:
            return default

    def safe_log(self, message: str) -> None:
        self.logs.append(str(message))

    def disable_button_safe(self, _button: Any) -> None:
        self.logs.append("[BUTTON] disable")

    def enable_button_safe(self, _button: Any) -> None:
        self.logs.append("[BUTTON] enable")

    def handle_exception(self, context: str) -> None:
        self.exceptions.append(f"{context}: {traceback.format_exc()}")
        self.logs.append(f"[EXCEPTION] {context}")


def _pick_llm_key(config: dict[str, Any], preferred: str | None) -> str:
    llm_configs = config.get("llm_configs", {})
    if not isinstance(llm_configs, dict) or not llm_configs:
        raise RuntimeError("No llm_configs found in config.json")

    if preferred and preferred in llm_configs:
        return preferred

    choose_configs = config.get("choose_configs", {})
    if isinstance(choose_configs, dict):
        key = str(choose_configs.get("chapter_outline_llm", "")).strip()
        if key and key in llm_configs:
            return key

    return next(iter(llm_configs.keys()))


def _default_source_dir(config: dict[str, Any]) -> str:
    other = config.get("other_params", {})
    if isinstance(other, dict):
        filepath = str(other.get("filepath", "")).strip()
        if filepath:
            return filepath
    return "wxhyj"


def _prepare_run_dir(source_dir: str, run_dir: str) -> dict[str, str]:
    src = Path(source_dir).resolve()
    dst = Path(run_dir).resolve()

    if not src.exists() or not src.is_dir():
        raise RuntimeError(f"Source dir not found: {src}")
    if dst.exists() and any(dst.iterdir()):
        raise RuntimeError(f"Run dir already exists and is not empty: {dst}")
    dst.mkdir(parents=True, exist_ok=True)

    copied: dict[str, str] = {}

    for name in ("Novel_architecture.txt", "novel_architecture.txt"):
        src_file = src / name
        if src_file.exists() and src_file.is_file():
            shutil.copy2(src_file, dst / name)
            copied[name] = str(dst / name)

    arch_path = resolve_architecture_file(str(dst))
    if not Path(arch_path).exists():
        raise RuntimeError(f"No architecture file copied from source dir: {src}")

    for src_csv in src.glob("*逐章任务卡*.csv"):
        target = dst / src_csv.name
        shutil.copy2(src_csv, target)
        copied[src_csv.name] = str(target)

    return copied


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _collect_llm_logs(run_dir: Path) -> list[str]:
    log_dir = run_dir / "llm_conversation_logs"
    if not log_dir.exists():
        return []
    return sorted(str(p) for p in log_dir.glob("llm_log_chapters_*.md"))


def _contains_false_retry_signature(log_text: str) -> bool:
    for match in re.finditer(r"第\s*(\d+)\s*章到第\s*(\d+)\s*章\s*，\s*共\s*(\d+)\s*章", log_text):
        start = int(match.group(1))
        end = int(match.group(2))
        total = int(match.group(3))
        if total != (end - start + 1):
            return True
    return False


def _split_chapter_blocks(content: str) -> dict[int, str]:
    matches = list(CHAPTER_HEADER_PATTERN.finditer(content))
    blocks: dict[int, str] = {}
    for idx, match in enumerate(matches):
        chapter_num = int(match.group(1))
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        blocks[chapter_num] = content[start:end]
    return blocks


def _check_directory_structure(content: str, expected_chapters: int) -> dict[str, Any]:
    chapter_headers = [int(x) for x in CHAPTER_HEADER_PATTERN.findall(content)]
    section_heading_count = len(re.findall(r"(?m)^\s*##\s*[1-7]\.\s*", content))
    chapter_seq_marker_count = len(re.findall(r"章节序号", content))

    blocks = _split_chapter_blocks(content)
    chapter_header_counts: dict[int, int] = {}
    section_presence: dict[int, dict[str, bool]] = {}

    for chapter in range(1, expected_chapters + 1):
        chapter_header_counts[chapter] = chapter_headers.count(chapter)
        block = blocks.get(chapter, "")
        section_presence[chapter] = {}
        for sec_num, sec_name in REQUIRED_SECTIONS:
            pattern = rf"(?m)^\s*##\s*{sec_num}\.\s*{re.escape(sec_name)}\s*$"
            section_presence[chapter][f"{sec_num}.{sec_name}"] = bool(re.search(pattern, block))

    strict_ok = True
    if len(chapter_headers) != expected_chapters:
        strict_ok = False
    if sorted(chapter_headers) != list(range(1, expected_chapters + 1)):
        strict_ok = False
    if section_heading_count != expected_chapters * 7:
        strict_ok = False
    if chapter_seq_marker_count < expected_chapters:
        strict_ok = False
    for chapter in range(1, expected_chapters + 1):
        if chapter_header_counts[chapter] != 1:
            strict_ok = False
        if not all(section_presence[chapter].values()):
            strict_ok = False

    return {
        "strict_ok": strict_ok,
        "chapter_headers": chapter_headers,
        "chapter_header_count": len(chapter_headers),
        "section_heading_count": section_heading_count,
        "chapter_seq_marker_count": chapter_seq_marker_count,
        "chapter_header_counts": chapter_header_counts,
        "section_presence": section_presence,
    }


def _run_runtime_prompt_guards(run_dir: Path, sample_size: int) -> dict[str, Any]:
    architecture_path = Path(resolve_architecture_file(str(run_dir), prefer_active=False))
    architecture_issues: list[str] = []
    if not architecture_path.exists():
        architecture_issues = [f"架构文件不存在: {architecture_path}"]
    else:
        architecture_text = architecture_path.read_text(encoding="utf-8")
        architecture_issues = check_runtime_architecture(architecture_text)

    audit_error: str | None = None
    try:
        audit_report = audit_project_logs(run_dir, sample_size=sample_size)
    except Exception as exc:
        audit_error = str(exc)
        audit_report = {
            "project_dir": str(run_dir),
            "files_scanned": 0,
            "prompt_blocks_scanned": 0,
            "violations": [],
        }

    raw_violations = audit_report.get("violations", []) if isinstance(audit_report, dict) else []
    violations = raw_violations if isinstance(raw_violations, list) else []
    return {
        "architecture_path": str(architecture_path),
        "architecture_issues": architecture_issues,
        "architecture_issue_count": len(architecture_issues),
        "log_audit_report": audit_report,
        "log_violation_count": len(violations),
        "audit_error": audit_error,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Headless strict UI blueprint path verifier")
    parser.add_argument("--source-dir", default=None, help="Source novel directory (defaults to config other_params.filepath)")
    parser.add_argument("--run-dir", default=None, help="Clean run directory (default: /tmp/wxhyj_ui_path_clean_<timestamp>)")
    parser.add_argument("--result-path", default=None, help="Result JSON path (default: /tmp/wxhyj_ui_path_result_clean_<timestamp>.json)")
    parser.add_argument("--chapters", type=int, default=3, help="Target chapter count for strict run")
    parser.add_argument("--llm-key", default=None, help="LLM key from config llm_configs (defaults to choose_configs.chapter_outline_llm)")
    parser.add_argument("--user-guidance", default="", help="User guidance passed to UI handler")
    parser.add_argument(
        "--audit-sample-size",
        type=int,
        default=20,
        help="Runtime prompt leakage audit sample size (<=0 means all logs)",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    started_at = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    config = load_config("config.json")
    source_dir = args.source_dir or _default_source_dir(config)
    run_dir = args.run_dir or f"/tmp/wxhyj_ui_path_clean_{timestamp}"
    result_path = args.result_path or f"/tmp/wxhyj_ui_path_result_clean_{timestamp}.json"

    llm_key = _pick_llm_key(config, args.llm_key)

    copied_files: dict[str, str] = {}
    result: dict[str, Any] = {
        "run_dir": str(Path(run_dir).resolve()),
        "source_dir": str(Path(source_dir).resolve()),
        "elapsed_seconds": 0.0,
        "llm_key": llm_key,
        "exceptions": [],
        "warnings": [],
        "infos": [],
        "messagebox_decisions": [],
        "copied_files": copied_files,
    }

    try:
        copied_files.update(_prepare_run_dir(source_dir, run_dir))

        import ui.generation_handlers as handlers

        messagebox_controller = _MessageBoxController()
        patched_config = copy.deepcopy(config)

        patched_other = patched_config.setdefault("other_params", {})
        if isinstance(patched_other, dict):
            patched_other["num_chapters"] = int(args.chapters)
            patched_other["blueprint_enable_critic"] = False
            patched_other["blueprint_optimize_per_batch"] = False

        ui = _DummyUI(
            filepath=str(Path(run_dir).resolve()),
            number_of_chapters=int(args.chapters),
            llm_key=llm_key,
            config=patched_config,
            user_guidance=args.user_guidance,
        )

        original_thread_cls = handlers.threading.Thread
        original_askyesno = handlers.messagebox.askyesno
        original_askyesnocancel = handlers.messagebox.askyesnocancel
        original_showwarning = handlers.messagebox.showwarning
        original_chapter_blueprint_generate = handlers.Chapter_blueprint_generate

        def _chapter_blueprint_generate_without_auto_optimize(*a: Any, **kw: Any) -> Any:
            kw["auto_optimize"] = False
            return original_chapter_blueprint_generate(*a, **kw)

        handlers.threading.Thread = _ImmediateThread
        handlers.messagebox.askyesno = messagebox_controller.askyesno
        handlers.messagebox.askyesnocancel = messagebox_controller.askyesnocancel
        handlers.messagebox.showwarning = messagebox_controller.showwarning
        handlers.Chapter_blueprint_generate = _chapter_blueprint_generate_without_auto_optimize

        try:
            handlers.generate_chapter_blueprint_ui(ui)
        finally:
            handlers.threading.Thread = original_thread_cls
            handlers.messagebox.askyesno = original_askyesno
            handlers.messagebox.askyesnocancel = original_askyesnocancel
            handlers.messagebox.showwarning = original_showwarning
            handlers.Chapter_blueprint_generate = original_chapter_blueprint_generate

        result["exceptions"] = list(ui.exceptions)
        result["warnings"] = list(messagebox_controller.warnings)
        result["messagebox_decisions"] = [
            {"kind": d.kind, "title": d.title, "decision": d.decision}
            for d in messagebox_controller.decisions
        ]

        run_dir_path = Path(run_dir)
        state_path = run_dir_path / ".blueprint_state.json"
        state = _load_json(state_path)
        state_exists = state is not None

        result["state_exists"] = state_exists
        result["state_last_batch_telemetry"] = state.get("last_batch_telemetry") if state else None
        result["state_completed"] = bool(state.get("completed", False)) if state else False
        result["state_last_generated_chapter"] = int(state.get("last_generated_chapter", 0)) if state else 0
        result["state_target_chapters"] = int(state.get("target_chapters", 0)) if state else 0

        llm_log_files = _collect_llm_logs(run_dir_path)
        latest_llm_log = llm_log_files[-1] if llm_log_files else None
        latest_log_text = Path(latest_llm_log).read_text(encoding="utf-8") if latest_llm_log else ""

        result["llm_log_files"] = llm_log_files
        result["latest_llm_log"] = latest_llm_log
        result["contains_prompt_title_benshu"] = "为《本书》" in latest_log_text
        result["contains_prompt_title_guimizhizhu"] = "闺蜜之主" in latest_log_text
        result["contains_false_retry_signature"] = _contains_false_retry_signature(latest_log_text)

        novel_directory_path = run_dir_path / "Novel_directory.txt"
        directory_exists = novel_directory_path.exists()
        directory_content = novel_directory_path.read_text(encoding="utf-8") if directory_exists else ""
        directory_checks = _check_directory_structure(directory_content, int(args.chapters)) if directory_exists else {
            "strict_ok": False,
            "chapter_headers": [],
            "chapter_header_count": 0,
            "section_heading_count": 0,
            "chapter_seq_marker_count": 0,
            "chapter_header_counts": {},
            "section_presence": {},
        }

        result["novel_directory_exists"] = directory_exists
        result["novel_directory_has_expected_chapters"] = directory_checks["chapter_headers"] == list(
            range(1, int(args.chapters) + 1)
        )
        result["novel_directory_header_count"] = directory_checks["chapter_header_count"]
        result["novel_directory_section_header_count"] = directory_checks["section_heading_count"]
        result["chapter_seq_marker_count"] = directory_checks["chapter_seq_marker_count"]
        result["directory_checks"] = directory_checks

        runtime_prompt_guards = _run_runtime_prompt_guards(
            run_dir_path,
            sample_size=int(args.audit_sample_size),
        )
        result["runtime_prompt_guards"] = runtime_prompt_guards

        postcheck_report = run_dir_path / "postcheck_repair_report.json"
        result["postcheck_repair_report"] = str(postcheck_report) if postcheck_report.exists() else None

        result["log_tail"] = ui.logs[-25:]

        strict_checks = {
            "exceptions_empty": len(result["exceptions"]) == 0,
            "state_completed": bool(result["state_completed"]),
            "state_last_generated_matches_target": (
                result["state_last_generated_chapter"] == int(args.chapters)
            ),
            "contains_prompt_title_guimizhizhu": bool(result["contains_prompt_title_guimizhizhu"]),
            "contains_false_retry_signature": bool(result["contains_false_retry_signature"]),
            "directory_structure_ok": bool(directory_checks["strict_ok"]),
            "runtime_architecture_prompt_clean": runtime_prompt_guards["architecture_issue_count"] == 0,
            "runtime_prompt_audit_clean": (
                runtime_prompt_guards["log_violation_count"] == 0
                and runtime_prompt_guards["audit_error"] is None
            ),
        }
        result["strict_checks"] = strict_checks
        result["strict_passed"] = (
            strict_checks["exceptions_empty"]
            and strict_checks["state_completed"]
            and strict_checks["state_last_generated_matches_target"]
            and not strict_checks["contains_prompt_title_guimizhizhu"]
            and not strict_checks["contains_false_retry_signature"]
            and strict_checks["directory_structure_ok"]
            and strict_checks["runtime_architecture_prompt_clean"]
            and strict_checks["runtime_prompt_audit_clean"]
        )

    except Exception as exc:
        result["exceptions"].append(f"runtime_exception: {exc}\n{traceback.format_exc()}")
        result["strict_passed"] = False
    finally:
        result["elapsed_seconds"] = round(time.time() - started_at, 3)
        result_file = Path(result_path)
        result_file.parent.mkdir(parents=True, exist_ok=True)
        result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Result JSON: {result_path}")
    print(f"Run dir: {run_dir}")
    print(f"Strict passed: {result.get('strict_passed', False)}")
    return 0 if result.get("strict_passed", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
