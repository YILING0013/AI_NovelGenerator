# ui/generation_handlers.py
# -*- coding: utf-8 -*-
"""
集成优化系统的生成处理器
已集成：情绪工程、动态知识库、极限性能优化
"""

import os
import builtins
import threading
import json
import tkinter as tk
import tkinter.filedialog as filedialog
from tkinter import messagebox
import customtkinter as ctk
import traceback
import glob
import time
import asyncio
import re
import hashlib
import shutil
from typing import Any, Callable, Protocol
from utils import read_file, save_string_to_txt, clear_file_content, resolve_architecture_file
from novel_generator import (
    Novel_architecture_generate,
    Chapter_blueprint_generate,
    generate_chapter_draft,
    finalize_chapter,
    import_knowledge_file,
    clear_vector_store,
    enrich_chapter_text,
    build_chapter_prompt,
    invoke_text_generation,
    build_llm_adapter,
)
from novel_generator.consistency_review import (
    build_ledger_backed_review_inputs,
    check_consistency,
    has_obvious_conflict,
    extract_conflict_items,
)
from novel_generator.common import (
    set_llm_log_context,
    clear_llm_log_context,
    set_runtime_log_stage,
    clear_runtime_log_stage,
    clean_llm_output,
    extract_revised_text_payload,
)
from novel_generator.architecture_runtime_slice import (
    build_runtime_architecture_context,
    collect_runtime_architecture_issues,
)
from novel_generator.chapter_contract_guard import (
    build_chapter_contract,
    detect_chapter_contract_drift,
    detect_paragraph_contract_drift,
    split_chapter_paragraphs,
    merge_chapter_paragraphs,
)




# ======== 集成优化的批量生成函数 ========


# ==================== 终极解决方案已集成 ====================
# 现在使用严格生成模式：
# - 零容忍省略策略（任何省略都视为失败）
# - 分批次生成（每批50章）
# - 强制架构一致性检查
# - 每章最少20行内容要求
# - 最多5次重试机制
# ==================== 终极解决方案已集成 ====================

def _log_directory_gate_summary(self, filepath: str):
    """将目录最终闸门结果写入 UI 日志；找不到报告时静默返回。"""
    report_candidates = [
        os.path.join(filepath, "autogen", "examples", "directory.report.json"),
        os.path.join(filepath, "directory.report.json"),
    ]

    report = None
    for candidate in report_candidates:
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and loaded:
                report = loaded
                break
        except (OSError, json.JSONDecodeError, TypeError):
            continue

    if not report:
        return

    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    passed = bool(report.get("passed", False))
    hard_fail_reasons = report.get("hard_fail_reasons", [])
    rewrite_hints = report.get("rewrite_hints", [])

    self.safe_log("")
    _stage_log(self, "S2", "🔒 目录最终闸门报告：")
    self.safe_log(f"  - 状态: {'✅ 通过' if passed else '❌ 未通过'}")
    self.safe_log(
        f"  - 摘要: 章节{summary.get('total_chapters', 0)} | "
        f"占位符{summary.get('placeholder_count', 0)} | "
        f"缺节章{summary.get('missing_section_chapter_count', 0)} | "
        f"缺4节{summary.get('missing_section4_chapters', 0)} | "
        f"缺5节{summary.get('missing_section5_chapters', 0)} | "
        f"模板泄漏{summary.get('template_leak_count', 0)} | "
        f"定位占位章{summary.get('location_placeholder_chapter_count', 0)} | "
        f"重复标题组{summary.get('duplicate_title_group_count', 0)} | "
        f"衔接风险{summary.get('transition_violation_count', 0)} | "
        f"实体偏移{summary.get('entity_violation_count', 0)}"
    )
    if hard_fail_reasons:
        self.safe_log(f"  - 硬失败原因: {', '.join(str(x) for x in hard_fail_reasons)}")
    if rewrite_hints:
        self.safe_log(f"  - 回炉建议: {'；'.join(str(x) for x in rewrite_hints[:3])}")


_BLUEPRINT_RETRY_REASON_LABELS = {
    "empty_result": "空响应",
    "validation_failed": "结构验证失败",
    "architecture_consistency_failed": "架构一致性失败",
    "mapping_gap": "架构映射缺失",
    "timeout": "超时",
    "rate_limited": "限流/配额",
    "exception": "运行异常",
}

_STAGE_LOG_PREFIX = {
    "S1": "🔵 [S1架构]",
    "S2": "🟣 [S2目录]",
    "S3": "🟢 [S3章节]",
}


def _stage_log(self, stage: str, message: str) -> None:
    prefix = _STAGE_LOG_PREFIX.get(str(stage), "⚪ [阶段]")
    self.safe_log(f"{prefix} {message}")


_BLUEPRINT_BATCH_STATUS_LABELS = {
    "success": "✅ 成功",
    "failed": "❌ 失败",
    "running": "⏳ 进行中",
}


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on", "enabled", "t"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", "disabled", "f", ""}:
            return False
    return default


def _normalize_chapter_title_text(chapter_num: int, chapter_title: str) -> str:
    """规范化章节标题，仅保留标题正文（去除重复的“第X章”前缀）。"""
    raw = str(chapter_title or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(rf"^第\s*{int(chapter_num)}\s*章[\s:：、.．\-—]*", "", raw).strip()
    return cleaned or raw


def _clean_generated_chapter_text(text: str) -> str:
    """对章节正文做结构化残留清理（JSON外壳/编辑批注/转义污染）。"""
    content = str(text or "").replace("\r\n", "\n").strip()
    if not content:
        return content

    extracted = extract_revised_text_payload(content)
    if extracted:
        content = extracted

    content = clean_llm_output(content)

    lines = content.splitlines()
    cleaned_lines: list[str] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if idx < 12 and re.search(r"(金牌编辑|编辑手记|本项目)", stripped):
            continue
        if idx < 20 and re.match(r'^"?(?:change_log|self_check|revised_text)"?\s*:', stripped):
            continue
        cleaned_lines.append(line)
    content = "\n".join(cleaned_lines).strip()

    # 移除尾部“编辑修改精评”等附录区块
    appendix_markers = (
        "\n编辑修改精评",
        "\n### 编辑修改精评",
        "\n#### 编辑修改精评",
        "\n修改精评",
    )
    for marker in appendix_markers:
        marker_idx = content.find(marker)
        if marker_idx > max(120, len(content) // 3):
            content = content[:marker_idx].rstrip()
            break

    content = re.sub(r"(?im)^\s*[\[\]\{\},]+\s*$", "", content)
    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    return content


def _collect_chapter_text_integrity_issues(chapter_text: str, chapter_num: int) -> list[str]:
    """检测章节文本结构污染（用于最终保存前硬闸）。"""
    text = str(chapter_text or "")
    issues: list[str] = []
    if not text.strip():
        return ["文本为空"]

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    first_line = lines[0] if lines else ""
    if not re.match(rf"^第\s*{int(chapter_num)}\s*章", first_line):
        issues.append("章节标题缺失或未位于首行")

    if re.search(r'(?im)^\s*"?(change_log|self_check|revised_text)"?\s*:', text):
        issues.append("结构化回包残留（change_log/self_check/revised_text）")

    if re.search(r"(金牌编辑|编辑手记|编辑修改精评)", text):
        issues.append("编辑元信息串入正文")

    escaped_newline_count = text.count("\\n")
    real_newline_count = text.count("\n")
    if escaped_newline_count >= 8 and real_newline_count <= 4:
        issues.append("正文疑似仍为转义字符串（\\\\n 未还原）")

    return issues


def _ensure_chapter_title_line(chapter_text: str, chapter_num: int, chapter_title: str) -> str:
    """保证章节首行存在唯一标题。"""
    normalized_title = _normalize_chapter_title_text(chapter_num, chapter_title)
    text = str(chapter_text or "").strip()
    if not text:
        if normalized_title:
            return f"第{chapter_num}章 {normalized_title}"
        return f"第{chapter_num}章"

    if not normalized_title:
        if re.match(rf"^第\s*{int(chapter_num)}\s*章", text):
            return text
        return f"第{chapter_num}章\n\n{text}"

    try:
        from fix_chapter_title_duplication import ensure_single_title
        return ensure_single_title(text, chapter_num, normalized_title)
    except (RuntimeError, ValueError, TypeError, OSError, ImportError):
        if re.match(rf"^第\s*{int(chapter_num)}\s*章", text):
            return text
        return f"第{chapter_num}章 {normalized_title}\n\n{text}"


def _set_step2_runtime_status(
    self,
    text: str,
    progress: float | None = None,
    *,
    text_color: str = "gray",
) -> None:
    """线程安全更新 Step2 状态条。"""
    if hasattr(self, "safe_update_step2_repair_status"):
        self.safe_update_step2_repair_status(text=text, progress=progress, text_color=text_color)
        return

    def _update():
        if hasattr(self, "step2_repair_status_label"):
            self.step2_repair_status_label.configure(text=text, text_color=text_color)
        if progress is not None and hasattr(self, "step2_repair_progressbar"):
            try:
                value = float(progress)
            except (TypeError, ValueError):
                value = 0.0
            value = max(0.0, min(1.0, value))
            self.step2_repair_progressbar.set(value)

    if hasattr(self, "master"):
        self.master.after(0, _update)


def _format_eta_duration(seconds: float | int | None) -> str:
    """将 ETA 秒数格式化为友好字符串。"""
    if seconds is None:
        return "计算中"
    try:
        total_seconds = int(max(0, round(float(seconds))))
    except (TypeError, ValueError):
        return "计算中"

    if total_seconds <= 0:
        return "即将完成"

    hours, rem = divmod(total_seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}h{minutes:02d}m"
    if minutes > 0:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def _estimate_step2_repair_eta_seconds(state: dict[str, Any], completed: int, total: int) -> float | None:
    """基于本轮已完成量估算剩余时间（ETA）。"""
    if total <= 0 or completed <= 0:
        return None
    started_at = state.get("round_started_at")
    if not isinstance(started_at, (int, float)):
        return None
    elapsed = max(0.0, float(time.time() - started_at))
    if elapsed <= 0.0:
        return None

    unit_cost = elapsed / max(1, int(completed))
    remaining = max(0, int(total) - int(completed))
    return unit_cost * remaining


def _parse_step2_repair_progress_line(line: str, state: dict[str, Any]) -> dict[str, Any] | None:
    """
    解析 Step2 自动修复日志行，输出标准事件，供 UI 进度显示。
    """
    text = str(line or "").strip()
    if not text:
        return None

    round_start = re.search(r"断点续传自动修复第(\d+)轮：尝试修复(\d+)个问题章节", text)
    if round_start:
        round_idx = int(round_start.group(1))
        total = max(0, int(round_start.group(2)))
        state["round"] = round_idx
        state["total"] = total
        state["completed"] = 0
        state["completed_chapters"] = set()
        state["failed_chapters"] = set()
        state["round_started_at"] = time.time()
        return {
            "event": "round_start",
            "round": round_idx,
            "total": total,
            "completed": 0,
        }

    round_done = re.search(r"断点续传自动修复第(\d+)轮完成：成功(\d+)章，失败(\d+)章", text)
    if round_done:
        round_idx = int(round_done.group(1))
        success_count = max(0, int(round_done.group(2)))
        failed_count = max(0, int(round_done.group(3)))
        total = max(state.get("total", 0), success_count + failed_count)
        completed = min(total, success_count + failed_count)
        state["round"] = round_idx
        state["total"] = total
        state["completed"] = completed
        return {
            "event": "round_done",
            "round": round_idx,
            "total": total,
            "completed": completed,
            "success": success_count,
            "failed": failed_count,
        }

    chapter_success = re.search(r"第(\d+)章修复成功", text)
    if chapter_success:
        chapter_num = int(chapter_success.group(1))
        completed_chapters = state.setdefault("completed_chapters", set())
        if chapter_num not in completed_chapters:
            completed_chapters.add(chapter_num)
        state["completed"] = len(completed_chapters) + len(state.setdefault("failed_chapters", set()))
        return {
            "event": "chapter_done",
            "chapter": chapter_num,
            "total": max(0, int(state.get("total", 0))),
            "completed": max(0, int(state.get("completed", 0))),
            "round": max(0, int(state.get("round", 0))),
        }

    chapter_failed = re.search(r"第(\d+)章修复失败", text)
    if chapter_failed:
        chapter_num = int(chapter_failed.group(1))
        failed_chapters = state.setdefault("failed_chapters", set())
        if chapter_num not in failed_chapters:
            failed_chapters.add(chapter_num)
        state["completed"] = len(state.setdefault("completed_chapters", set())) + len(failed_chapters)
        return {
            "event": "chapter_failed",
            "chapter": chapter_num,
            "total": max(0, int(state.get("total", 0))),
            "completed": max(0, int(state.get("completed", 0))),
            "round": max(0, int(state.get("round", 0))),
        }

    repair_finished = re.search(r"断点续传自动修复成功：修复(\d+)章，轮次(\d+)", text)
    if repair_finished:
        repaired = max(0, int(repair_finished.group(1)))
        round_idx = max(0, int(repair_finished.group(2)))
        state["round"] = round_idx
        if state.get("total", 0) <= 0:
            state["total"] = repaired
        state["completed"] = max(state.get("completed", 0), repaired)
        return {
            "event": "repair_finished",
            "round": round_idx,
            "repaired": repaired,
            "total": max(0, int(state.get("total", 0))),
            "completed": max(0, int(state.get("completed", 0))),
        }

    return None


def _watch_step2_repair_progress_from_app_log(self, stop_event: threading.Event, start_offset: int) -> None:
    """监听 app.log 中的 Step2 自动修复进度，并同步到 UI。"""
    log_path = os.path.join(os.getcwd(), "app.log")
    state: dict[str, Any] = {
        "round": 0,
        "total": 0,
        "completed": 0,
        "completed_chapters": set(),
        "failed_chapters": set(),
    }
    last_logged_completed = -1

    while not stop_event.is_set():
        if not os.path.exists(log_path):
            time.sleep(0.25)
            continue

        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as fp:
                try:
                    fp.seek(max(0, int(start_offset)), os.SEEK_SET)
                except (OSError, ValueError):
                    fp.seek(0, os.SEEK_END)

                while not stop_event.is_set():
                    line = fp.readline()
                    if not line:
                        time.sleep(0.25)
                        continue

                    event = _parse_step2_repair_progress_line(line, state)
                    if not isinstance(event, dict):
                        continue

                    event_name = str(event.get("event", ""))
                    total = max(0, int(event.get("total", state.get("total", 0) or 0)))
                    completed = max(0, int(event.get("completed", state.get("completed", 0) or 0)))
                    progress_value = float(completed / total) if total > 0 else 0.0
                    eta_seconds = _estimate_step2_repair_eta_seconds(state, completed, total)
                    eta_text = _format_eta_duration(eta_seconds)

                    if event_name == "round_start":
                        round_idx = int(event.get("round", 0))
                        self.safe_log(f"🧩 Step2自动修复进度：第{round_idx}轮，待修复 {total} 章")
                        _set_step2_runtime_status(
                            self,
                            f"Step2自动修复：第{round_idx}轮 {completed}/{total} | ETA {eta_text}",
                            progress_value,
                            text_color="#B8860B",
                        )
                        last_logged_completed = completed
                        continue

                    if event_name in {"chapter_done", "chapter_failed"}:
                        chapter_num = int(event.get("chapter", 0))
                        round_idx = int(event.get("round", 0))
                        if completed != last_logged_completed and (
                            completed <= 3 or completed % 5 == 0 or (total > 0 and completed >= total)
                        ):
                            status_text = "完成" if event_name == "chapter_done" else "失败"
                            self.safe_log(
                                f"🧩 Step2自动修复进度：第{round_idx}轮 {completed}/{total}（第{chapter_num}章{status_text}，ETA {eta_text}）"
                            )
                            last_logged_completed = completed
                        _set_step2_runtime_status(
                            self,
                            f"Step2自动修复：第{round_idx}轮 {completed}/{total}（最新第{chapter_num}章） | ETA {eta_text}",
                            progress_value,
                            text_color="#B8860B",
                        )
                        continue

                    if event_name == "round_done":
                        round_idx = int(event.get("round", 0))
                        success_count = int(event.get("success", 0))
                        failed_count = int(event.get("failed", 0))
                        self.safe_log(
                            f"🧩 Step2自动修复第{round_idx}轮完成：成功{success_count}章，失败{failed_count}章"
                        )
                        _set_step2_runtime_status(
                            self,
                            f"Step2自动修复：第{round_idx}轮完成（成功{success_count}/失败{failed_count}） | ETA 0s",
                            1.0 if total > 0 else progress_value,
                            text_color="#B8860B",
                        )
                        last_logged_completed = completed
                        continue

                    if event_name == "repair_finished":
                        round_idx = int(event.get("round", 0))
                        repaired = int(event.get("repaired", 0))
                        self.safe_log(f"✅ Step2自动修复完成：累计修复 {repaired} 章（{round_idx}轮）")
                        _set_step2_runtime_status(
                            self,
                            f"Step2自动修复完成：已修复{repaired}章，准备继续生成目录…",
                            1.0,
                            text_color="#2E8B57",
                        )
        except OSError:
            time.sleep(0.25)
            continue


def _start_step2_repair_progress_monitor(self) -> None:
    """启动 Step2 自动修复进度监听线程。"""
    _stop_step2_repair_progress_monitor(self)
    log_path = os.path.join(os.getcwd(), "app.log")
    start_offset = os.path.getsize(log_path) if os.path.exists(log_path) else 0
    stop_event = threading.Event()
    monitor_thread = threading.Thread(
        target=_watch_step2_repair_progress_from_app_log,
        args=(self, stop_event, start_offset),
        daemon=True,
    )
    self._step2_repair_monitor_stop_event = stop_event
    self._step2_repair_monitor_thread = monitor_thread
    monitor_thread.start()


def _stop_step2_repair_progress_monitor(self) -> None:
    stop_event = getattr(self, "_step2_repair_monitor_stop_event", None)
    if isinstance(stop_event, threading.Event):
        stop_event.set()
    self._step2_repair_monitor_stop_event = None
    self._step2_repair_monitor_thread = None


def _format_blueprint_retry_reasons(retry_reasons: object) -> str:
    if not isinstance(retry_reasons, list) or not retry_reasons:
        return "无"

    normalized: list[str] = []
    for item in retry_reasons:
        key = str(item).strip()
        if not key:
            continue
        normalized.append(_BLUEPRINT_RETRY_REASON_LABELS.get(key, key))

    if not normalized:
        return "无"

    deduped = list(dict.fromkeys(normalized))
    return "、".join(deduped)


def _apply_hard_gate_repairs(
    chapter_text: str,
    issues: list[str] | None,
    auto_fix_fn,
    llm_fix_fn,
    collect_issues_fn,
) -> tuple[str, list[str], bool]:
    normalized_issues = [str(item).strip() for item in (issues or []) if str(item).strip()]
    if not normalized_issues:
        return chapter_text, [], False

    fixed_text = auto_fix_fn(chapter_text, normalized_issues)
    used_llm_fix = any("LLM深度一致性冲突" in item for item in normalized_issues)
    if used_llm_fix:
        fixed_text = llm_fix_fn(fixed_text)
        fixed_text = auto_fix_fn(fixed_text, normalized_issues)

    remaining = collect_issues_fn(fixed_text)
    if not isinstance(remaining, list):
        remaining = []
    return fixed_text, remaining, used_llm_fix


def _should_raise_hard_gate_after_repair(
    stop_batch_on_hard_gate: bool,
    unresolved_hard_gate_issues: list[str] | None,
) -> bool:
    return bool(stop_batch_on_hard_gate and unresolved_hard_gate_issues)


def _log_blueprint_runtime_telemetry(self, filepath: str, max_recent: int = 3) -> None:
    state_path = os.path.join(filepath, ".blueprint_state.json")
    if not os.path.exists(state_path):
        return

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return

    if not isinstance(state, dict):
        return

    last_batch_raw = state.get("last_batch_telemetry")
    history_raw = state.get("batch_telemetry_history")
    last_batch: dict[str, object] = last_batch_raw if isinstance(last_batch_raw, dict) else {}
    history: list[dict[str, object]] = (
        [item for item in history_raw if isinstance(item, dict)] if isinstance(history_raw, list) else []
    )
    elapsed_seconds = _safe_float(state.get("last_run_elapsed_seconds"))
    target_chapters = _safe_int(state.get("target_chapters"))
    last_generated_chapter = _safe_int(state.get("last_generated_chapter"))

    has_last_batch = bool(last_batch)
    has_history = bool(history)
    if elapsed_seconds is None and not has_last_batch and not has_history:
        return

    self.safe_log("")
    _stage_log(self, "S2", "运行遥测：")

    if last_generated_chapter is not None and target_chapters is not None and target_chapters > 0:
        self.safe_log(f"  - 目录进度: 第{last_generated_chapter}章 / 目标{target_chapters}章")
    elif last_generated_chapter is not None:
        self.safe_log(f"  - 目录进度: 已生成到第{last_generated_chapter}章")

    if elapsed_seconds is not None and elapsed_seconds >= 0:
        self.safe_log(f"  - 最近一次总耗时: {elapsed_seconds:.1f}s")

    if last_batch:
        chapter_range = str(last_batch.get("chapter_range", "?")).strip() or "?"
        status_key = str(last_batch.get("status", "")).strip().lower()
        status_label = _BLUEPRINT_BATCH_STATUS_LABELS.get(status_key, status_key or "unknown")
        attempt_count = _safe_int(last_batch.get("attempt_count")) or 0
        success_attempt = _safe_int(last_batch.get("success_attempt"))
        total_seconds = _safe_float(last_batch.get("total_seconds"))

        summary_parts = [f"  - 最近批次: 第{chapter_range}章", status_label]
        if attempt_count > 0:
            if success_attempt is not None and success_attempt > 0:
                summary_parts.append(f"尝试{attempt_count}次(第{success_attempt}次成功)")
            else:
                summary_parts.append(f"尝试{attempt_count}次")
        if total_seconds is not None and total_seconds >= 0:
            summary_parts.append(f"耗时{total_seconds:.1f}s")
        self.safe_log(" | ".join(summary_parts))

        retry_reasons = last_batch.get("retry_reasons", [])
        if isinstance(retry_reasons, list) and retry_reasons:
            self.safe_log(f"  - 最近批次重试原因: {_format_blueprint_retry_reasons(retry_reasons)}")

    if history:
        history_limit = max(1, int(max_recent))
        recent_items = history[-history_limit:]
        retry_items: list[str] = []
        reason_counts: dict[str, int] = {}

        for item in recent_items:
            chapter_range = str(item.get("chapter_range", "?")).strip() or "?"
            attempt_count = _safe_int(item.get("attempt_count")) or 0
            retry_reasons = item.get("retry_reasons", [])
            has_retry = attempt_count > 1 or (isinstance(retry_reasons, list) and bool(retry_reasons))
            if not has_retry:
                continue

            reason_text = _format_blueprint_retry_reasons(retry_reasons)
            retry_items.append(f"第{chapter_range}章({attempt_count}次, {reason_text})")

            if isinstance(retry_reasons, list):
                for reason in retry_reasons:
                    key = str(reason).strip()
                    if not key:
                        continue
                    label = _BLUEPRINT_RETRY_REASON_LABELS.get(key, key)
                    reason_counts[label] = reason_counts.get(label, 0) + 1

        if retry_items:
            self.safe_log(f"  - 最近{len(recent_items)}批重试批次: {'；'.join(retry_items[:3])}")

        if reason_counts:
            top_reasons = sorted(reason_counts.items(), key=lambda item: item[1], reverse=True)[:3]
            top_summary = "，".join(f"{name}({count})" for name, count in top_reasons)
            self.safe_log(f"  - 高频重试原因: {top_summary}")


def _write_batch_guard_report(filepath: str, report: dict[str, Any]) -> str:
    """写入批量硬阻断报告，返回文件路径。"""
    report_path = os.path.join(filepath, "batch_guard_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report_path


def _write_batch_precheck_report(filepath: str, report: dict[str, Any]) -> str:
    """写入批量预检查报告，返回文件路径。"""
    report_path = os.path.join(filepath, "batch_precheck_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report_path


def _blueprint_state_path(filepath: str) -> str:
    return os.path.join(filepath, ".blueprint_state.json")


def _load_blueprint_state_file(filepath: str) -> dict[str, Any]:
    state_path = _blueprint_state_path(filepath)
    if not os.path.exists(state_path):
        return {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def _sync_blueprint_state_for_resume(
    filepath: str,
    *,
    current_arch_hash: str,
    existing_end: int,
    target_chapters: int,
    base_state: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """
    当用户选择“继续生成”且架构哈希不一致时，修正运行状态避免误判为“必须重开”。
    """
    arch_hash = str(current_arch_hash or "").strip()
    if not arch_hash:
        return False, "当前架构哈希为空，无法同步续写状态"

    state = dict(base_state) if isinstance(base_state, dict) else _load_blueprint_state_file(filepath)
    state["architecture_hash"] = arch_hash
    state["last_generated_chapter"] = max(0, int(existing_end))
    state["target_chapters"] = max(1, int(target_chapters))
    state["completed_target_chapters"] = max(1, int(target_chapters))
    state["completed"] = False
    state["completed_content_hash"] = ""
    state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    state_path = _blueprint_state_path(filepath)
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return True, f"已同步续写状态（last_generated={int(existing_end)}）"
    except (OSError, TypeError, ValueError) as sync_error:
        return False, f"续写状态同步失败: {sync_error}"


def _extract_directory_chapter_numbers(directory_text: str) -> list[int]:
    text = str(directory_text or "").strip()
    if not text:
        return []
    chapter_pattern = r"(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*[^\n]*)?\s*(?:\*\*)?\s*$"
    numbers = [int(num) for num in re.findall(chapter_pattern, text)]
    if numbers:
        return numbers
    fallback_pattern = r"(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章\s*(?:\*\*)?\s*$"
    return [int(num) for num in re.findall(fallback_pattern, text)]


def _inspect_existing_blueprint_progress(chapter_dir_path: str) -> dict[str, int]:
    """
    检测 Step2 已有进度，兼容整文件+拆分目录双来源。

    返回字段：
    - main_max: Novel_directory.txt 识别到的最大章号
    - split_contiguous_end: chapter_blueprints 连续前缀终点
    - split_max: chapter_blueprints 最大章号
    - split_count: chapter_blueprints 章节文件数量
    - detected_end: 续传实际采用的章号（max(main_max, split_contiguous_end)）
    """
    chapter_dir = str(chapter_dir_path or "").strip()
    if not chapter_dir:
        return {
            "main_max": 0,
            "split_contiguous_end": 0,
            "split_max": 0,
            "split_count": 0,
            "detected_end": 0,
        }

    main_max = 0
    filename_dir = os.path.join(chapter_dir, "Novel_directory.txt")
    if os.path.exists(filename_dir):
        try:
            existing_content = read_file(filename_dir).strip()
        except OSError:
            existing_content = ""
        main_numbers = _extract_directory_chapter_numbers(existing_content)
        main_max = max(main_numbers) if main_numbers else 0

    split_dir = os.path.join(chapter_dir, "chapter_blueprints")
    split_contiguous_end = 0
    split_max = 0
    split_count = 0
    if os.path.isdir(split_dir):
        split_numbers: list[int] = []
        try:
            for fname in os.listdir(split_dir):
                match = re.match(r"^chapter_(\d+)\.txt$", str(fname))
                if match:
                    split_numbers.append(int(match.group(1)))
        except OSError:
            split_numbers = []

        if split_numbers:
            unique_sorted = sorted(set(split_numbers))
            split_count = len(unique_sorted)
            split_max = int(unique_sorted[-1])
            expected = 1
            for chapter_num in unique_sorted:
                if chapter_num != expected:
                    break
                split_contiguous_end = chapter_num
                expected += 1

    detected_end = max(main_max, split_contiguous_end)
    return {
        "main_max": int(main_max),
        "split_contiguous_end": int(split_contiguous_end),
        "split_max": int(split_max),
        "split_count": int(split_count),
        "detected_end": int(detected_end),
    }


def _detect_existing_blueprint_end(chapter_dir_path: str) -> int:
    """
    检测 Step2 已有进度，优先保障“断点续传”对拆分目录兼容：
    - Novel_directory.txt（传统整文件）
    - chapter_blueprints/chapter_X.txt（拆分目录）
    返回两者中更可靠的连续章节终点。
    """
    return int(_inspect_existing_blueprint_progress(chapter_dir_path).get("detected_end", 0))


def _sanitize_report_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", str(name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:120] if cleaned else "未命名章节"


def _resolve_chapter_report_name(filepath: str, chapter_num: int) -> str:
    chapter_label = f"第{chapter_num}章"
    chapter_title = ""
    directory_path = os.path.join(filepath, "Novel_directory.txt")
    if os.path.exists(directory_path):
        try:
            from chapter_directory_parser import load_chapter_info

            chapter_info = load_chapter_info(filepath, chapter_num)
            if isinstance(chapter_info, dict):
                chapter_title = str(chapter_info.get("chapter_title", "")).strip()
        except (RuntimeError, ValueError, TypeError, OSError, ImportError):
            chapter_title = ""

    if chapter_title:
        return _sanitize_report_filename(f"{chapter_label} {chapter_title}")
    return _sanitize_report_filename(chapter_label)


def _extract_hard_gate_issue_items(error_text: str, limit: int = 12) -> list[str]:
    text = str(error_text or "").strip()
    if not text:
        return []

    detail = text
    if "->" in detail:
        detail = detail.split("->", 1)[1].strip()
    elif ":" in detail:
        detail = detail.split(":", 1)[1].strip()

    parts = [part.strip(" -") for part in re.split(r"[；;\n]+", detail) if part.strip(" -")]
    deduped = list(dict.fromkeys(parts))
    return deduped[: max(1, int(limit))]


def _write_chapter_hard_gate_report(
    filepath: str,
    chapter_num: int,
    error_text: str,
    timestamp: str,
    traceback_text: str = "",
    stop_on_hard_gate: bool = False,
) -> str:
    report_dir = os.path.join(filepath, "hard_gate_reports")
    os.makedirs(report_dir, exist_ok=True)
    chapter_name = _resolve_chapter_report_name(filepath, chapter_num)
    report_path = os.path.join(report_dir, f"{chapter_name}.md")

    issues = _extract_hard_gate_issue_items(error_text, limit=12)
    chapter_path = os.path.join(filepath, "chapters", f"chapter_{chapter_num}.txt")
    chapter_exists = os.path.exists(chapter_path)
    chapter_size = 0
    if chapter_exists:
        try:
            chapter_size = int(os.path.getsize(chapter_path))
        except OSError:
            chapter_size = 0

    policy_line = (
        "- 批量策略: 命中硬阻断后终止当前批次"
        if bool(stop_on_hard_gate)
        else "- 批量策略: 命中硬阻断后不中断，继续后续章节"
    )
    batch_effect_line = (
        "- 批量任务已停止（命中硬阻断即停策略）。"
        if bool(stop_on_hard_gate)
        else "- 批量任务未停止，继续执行后续章节。"
    )

    lines = [
        f"# {chapter_name} - 硬阻断详细报告",
        "",
        "## 基本信息",
        f"- 生成时间: {timestamp}",
        f"- 章节序号: {chapter_num}",
        policy_line,
        f"- 章节文件存在: {'是' if chapter_exists else '否'}",
        f"- 章节文件路径: {chapter_path}",
        f"- 章节文件大小(字节): {chapter_size}",
        "",
        "## 具体问题",
    ]
    if issues:
        lines.extend([f"{idx}. {item}" for idx, item in enumerate(issues, 1)])
    else:
        lines.append("1. 未解析到结构化问题条目，请查看原始异常。")

    lines.extend(
        [
            "",
            "## 现象",
            "- 本章在质量闭环/硬闸复核阶段触发硬阻断。",
            "- 本章生成被判定为失败。",
            batch_effect_line,
            "",
            "## 原始异常",
            "```text",
            str(error_text or ""),
            "```",
        ]
    )

    traceback_clean = str(traceback_text or "").strip()
    if traceback_clean:
        lines.extend(
            [
                "",
                "## 异常堆栈",
                "```text",
                traceback_clean,
                "```",
            ]
        )

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
    return report_path


_DRIFT_STATE_LEDGER_FILENAME = "chapter_drift_ledger.json"
_OPENING_TRANSITION_MARKERS = (
    "片刻后",
    "不久后",
    "次日",
    "翌日",
    "随后",
    "与此同时",
    "离开",
    "回到",
    "走出",
    "想到",
    "不知过了多久",
)
_ANCHOR_TERM_TOKEN_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff·_-]{2,12}")
_ANCHOR_TERM_STOP_WORDS = {
    "本章",
    "章节",
    "内容",
    "角色",
    "人物",
    "场景",
    "地点",
    "剧情",
    "系统",
    "提示",
    "然后",
    "这个",
    "那个",
}


def _drift_state_ledger_path(filepath: str) -> str:
    return os.path.join(filepath, _DRIFT_STATE_LEDGER_FILENAME)


def _default_drift_state_ledger() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": "",
        "chapters": [],
    }


def _normalize_anchor_terms(raw_terms: Any, limit: int = 8) -> list[str]:
    items = raw_terms if isinstance(raw_terms, list) else []
    normalized: list[str] = []
    for item in items:
        term = str(item or "").strip()
        if (
            not term
            or term in _ANCHOR_TERM_STOP_WORDS
            or len(term) < 2
            or len(term) > 20
            or term in normalized
        ):
            continue
        normalized.append(term)
        if len(normalized) >= max(1, int(limit)):
            break
    return normalized


def _collect_contract_anchor_terms(chapter_contract: dict[str, Any] | None) -> dict[str, list[str]]:
    contract = chapter_contract if isinstance(chapter_contract, dict) else {}
    required = contract.get("required_terms", {}) if isinstance(contract.get("required_terms"), dict) else {}
    return {
        "characters": _normalize_anchor_terms(required.get("characters", []), limit=6),
        "key_items": _normalize_anchor_terms(required.get("key_items", []), limit=6),
        "locations": _normalize_anchor_terms(required.get("locations", []), limit=4),
        "time_constraints": _normalize_anchor_terms(required.get("time_constraints", []), limit=4),
    }


def _load_drift_state_ledger(filepath: str) -> dict[str, Any]:
    ledger_path = _drift_state_ledger_path(filepath)
    if not os.path.exists(ledger_path):
        return _default_drift_state_ledger()
    try:
        with open(ledger_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return _default_drift_state_ledger()

    if not isinstance(loaded, dict):
        return _default_drift_state_ledger()
    chapters_raw = loaded.get("chapters", [])
    chapters = [item for item in chapters_raw if isinstance(item, dict)] if isinstance(chapters_raw, list) else []
    return {
        "schema_version": _safe_int(loaded.get("schema_version")) or 1,
        "updated_at": str(loaded.get("updated_at", "")),
        "chapters": chapters,
    }


def _save_drift_state_ledger(filepath: str, ledger: dict[str, Any]) -> None:
    payload = ledger if isinstance(ledger, dict) else _default_drift_state_ledger()
    payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    chapters_raw = payload.get("chapters", [])
    payload["chapters"] = [item for item in chapters_raw if isinstance(item, dict)] if isinstance(chapters_raw, list) else []
    with open(_drift_state_ledger_path(filepath), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _extract_text_anchor_terms(source_text: str, preferred_terms: list[str], limit: int = 6) -> list[str]:
    picks: list[str] = []
    text = str(source_text or "")
    for term in _normalize_anchor_terms(preferred_terms, limit=20):
        if term in text and term not in picks:
            picks.append(term)
            if len(picks) >= max(1, int(limit)):
                return picks

    if len(picks) >= max(1, int(limit)):
        return picks

    for token in _ANCHOR_TERM_TOKEN_RE.findall(text):
        if token in _ANCHOR_TERM_STOP_WORDS:
            continue
        if token in picks:
            continue
        picks.append(token)
        if len(picks) >= max(1, int(limit)):
            break
    return picks


def _build_drift_ledger_record(
    chapter_num: int,
    chapter_text: str,
    chapter_contract: dict[str, Any] | None,
) -> dict[str, Any]:
    paragraphs = split_chapter_paragraphs(chapter_text)
    opening_text = "\n".join(paragraphs[:2]) if paragraphs else str(chapter_text or "")
    ending_text = "\n".join(paragraphs[-2:]) if paragraphs else str(chapter_text or "")

    anchor_terms = _collect_contract_anchor_terms(chapter_contract)
    preferred_tail_terms = (
        list(anchor_terms.get("key_items", []))
        + list(anchor_terms.get("characters", []))
        + list(anchor_terms.get("locations", []))
    )
    ending_anchor_terms = _extract_text_anchor_terms(ending_text, preferred_tail_terms, limit=8)
    opening_anchor_terms = _extract_text_anchor_terms(
        opening_text,
        list(anchor_terms.get("characters", [])) + list(anchor_terms.get("locations", [])),
        limit=6,
    )

    return {
        "chapter": int(chapter_num),
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "opening_preview": opening_text[:240],
        "ending_preview": ending_text[:240],
        "opening_anchor_terms": opening_anchor_terms,
        "ending_anchor_terms": ending_anchor_terms,
        "contract_anchors": anchor_terms,
    }


def _write_drift_state_ledger_record(
    filepath: str,
    chapter_num: int,
    chapter_text: str,
    chapter_contract: dict[str, Any] | None,
    *,
    max_history: int = 400,
) -> dict[str, Any]:
    ledger = _load_drift_state_ledger(filepath)
    record = _build_drift_ledger_record(chapter_num, chapter_text, chapter_contract)
    chapters_raw = ledger.get("chapters", [])
    chapters = [item for item in chapters_raw if isinstance(item, dict)] if isinstance(chapters_raw, list) else []
    chapters = [item for item in chapters if (_safe_int(item.get("chapter")) or -1) != int(chapter_num)]
    chapters.append(record)
    chapters.sort(key=lambda item: _safe_int(item.get("chapter")) or 0)
    if len(chapters) > max(1, int(max_history)):
        chapters = chapters[-max(1, int(max_history)) :]
    ledger["chapters"] = chapters
    _save_drift_state_ledger(filepath, ledger)
    return record


def _read_drift_state_ledger_record(filepath: str, chapter_num: int) -> dict[str, Any]:
    target = int(chapter_num)
    if target <= 0:
        return {}
    ledger = _load_drift_state_ledger(filepath)
    chapters = ledger.get("chapters", [])
    if not isinstance(chapters, list):
        return {}
    for item in chapters:
        if not isinstance(item, dict):
            continue
        if (_safe_int(item.get("chapter")) or -1) == target:
            return item
    return {}


def _collect_opening_anchor_issues(
    *,
    chapter_num: int,
    chapter_text: str,
    chapter_contract: dict[str, Any] | None,
    previous_ledger_record: dict[str, Any] | None,
    max_issues: int = 3,
) -> list[str]:
    if int(chapter_num) <= 1:
        return []
    text = str(chapter_text or "").strip()
    if not text:
        return ["开篇锚点漂移: 章节正文为空"]

    paragraphs = split_chapter_paragraphs(text)
    opening_text = "\n".join(paragraphs[:2]) if paragraphs else text
    opening_text = opening_text.strip()
    if not opening_text:
        return ["开篇锚点漂移: 开篇段落为空"]

    contract_anchors = _collect_contract_anchor_terms(chapter_contract)
    issues: list[str] = []

    required_chars = contract_anchors.get("characters", [])
    if required_chars and not any(term in opening_text for term in required_chars[:3]):
        issues.append(f"开篇锚点漂移: 未覆盖人物锚点({ '、'.join(required_chars[:3]) })")

    required_locations = contract_anchors.get("locations", [])
    if required_locations and not any(term in opening_text for term in required_locations[:2]):
        issues.append(f"开篇锚点漂移: 未覆盖场景锚点({ '、'.join(required_locations[:2]) })")

    previous = previous_ledger_record if isinstance(previous_ledger_record, dict) else {}
    previous_terms = _normalize_anchor_terms(previous.get("ending_anchor_terms", []), limit=6)
    has_prev_term_hit = bool(previous_terms) and any(term in opening_text for term in previous_terms[:4])
    has_transition_marker = any(marker in opening_text for marker in _OPENING_TRANSITION_MARKERS)
    if previous_terms and not has_prev_term_hit and not has_transition_marker:
        issues.append(
            "开篇锚点漂移: 未承接上一章结尾锚点或过渡语"
        )

    deduped: list[str] = []
    for issue in issues:
        msg = str(issue).strip()
        if msg and msg not in deduped:
            deduped.append(msg)
        if len(deduped) >= max(1, int(max_issues)):
            break
    return deduped


def _reset_runtime_state_for_fresh_batch(filepath: str):
    """从第1章重跑时清理历史运行态，避免硬闸被旧状态污染。"""
    cleared = []
    remove_files = [
        "timeline_state.json",
        ".facts_db.json",
        "world_state.json",
        _DRIFT_STATE_LEDGER_FILENAME,
        "global_summary.txt",
        "character_state.txt",
        "plot_arcs.txt",
    ]
    for name in remove_files:
        p = os.path.join(filepath, name)
        if os.path.exists(p):
            try:
                os.remove(p)
                cleared.append(name)
            except OSError:
                continue

    chapters_dir = os.path.join(filepath, "chapters")
    if os.path.isdir(chapters_dir):
        try:
            for fname in os.listdir(chapters_dir):
                lower = fname.lower()
                if lower.startswith("chapter_") and lower.endswith(".txt"):
                    try:
                        os.remove(os.path.join(chapters_dir, fname))
                        cleared.append(f"chapters/{fname}")
                    except OSError:
                        continue
        except OSError:
            pass

    snapshot_root = _runtime_snapshot_root(filepath)
    if os.path.isdir(snapshot_root):
        try:
            shutil.rmtree(snapshot_root)
            cleared.append(_RUNTIME_STATE_SNAPSHOT_DIRNAME)
        except OSError:
            pass
    return cleared


_RUNTIME_STATE_SNAPSHOT_DIRNAME = ".runtime_state_snapshots"
_RUNTIME_STATE_TRACKED_FILES = [
    "global_summary.txt",
    "character_state.txt",
    "plot_arcs.txt",
    "timeline_state.json",
    "world_state.json",
    _DRIFT_STATE_LEDGER_FILENAME,
    ".facts_db.json",
]


def _runtime_snapshot_root(filepath: str) -> str:
    return os.path.join(filepath, _RUNTIME_STATE_SNAPSHOT_DIRNAME)


def _runtime_snapshot_dir(filepath: str, chapter_num: int) -> str:
    return os.path.join(_runtime_snapshot_root(filepath), f"chapter_{int(chapter_num)}")


def _save_runtime_state_snapshot(filepath: str, chapter_num: int) -> list[str]:
    """
    在章节完成后保存运行态快照，支持中途重跑时回滚到上一章稳定状态。
    """
    snapshot_dir = _runtime_snapshot_dir(filepath, chapter_num)
    if os.path.isdir(snapshot_dir):
        shutil.rmtree(snapshot_dir)
    os.makedirs(snapshot_dir, exist_ok=True)

    saved_files: list[str] = []
    tracked_files = list(_RUNTIME_STATE_TRACKED_FILES)
    tracked_files.append(os.path.join("chapters", f"chapter_{int(chapter_num)}.txt"))

    for rel_path in tracked_files:
        src_path = os.path.join(filepath, rel_path)
        if not os.path.exists(src_path):
            continue
        dst_path = os.path.join(snapshot_dir, rel_path)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        shutil.copy2(src_path, dst_path)
        saved_files.append(rel_path)

    meta = {
        "chapter": int(chapter_num),
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "files": saved_files,
    }
    with open(os.path.join(snapshot_dir, "_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return saved_files


def _restore_runtime_state_for_partial_batch(
    filepath: str,
    start_chapter: int,
    allow_fallback_without_snapshot: bool = True,
) -> tuple[bool, str, list[str]]:
    """
    从 start_chapter-1 的快照恢复运行态，并删除 start_chapter 及之后的章节文件。
    """
    chapter_num = int(start_chapter)
    if chapter_num <= 1:
        return True, "", []

    anchor_chapter = chapter_num - 1
    snapshot_dir = _runtime_snapshot_dir(filepath, anchor_chapter)
    if not os.path.isdir(snapshot_dir):
        if not allow_fallback_without_snapshot:
            return False, f"未找到第{anchor_chapter}章运行态快照", []

        anchor_chapter_path = os.path.join(filepath, "chapters", f"chapter_{anchor_chapter}.txt")
        if not os.path.exists(anchor_chapter_path):
            return (
                False,
                f"未找到第{anchor_chapter}章运行态快照，且缺少第{anchor_chapter}章正文",
                [],
            )

        restored_items: list[str] = []
        for rel_path in _RUNTIME_STATE_TRACKED_FILES:
            target_path = os.path.join(filepath, rel_path)
            if not os.path.exists(target_path):
                continue
            try:
                os.remove(target_path)
                restored_items.append(f"{rel_path} (cleared:fallback)")
            except OSError:
                continue

        chapters_dir = os.path.join(filepath, "chapters")
        removed_chapters: list[str] = []
        if os.path.isdir(chapters_dir):
            try:
                for fname in os.listdir(chapters_dir):
                    match = re.match(r"^chapter_(\d+)\.txt$", str(fname))
                    if not match:
                        continue
                    chapter_id = int(match.group(1))
                    if chapter_id >= chapter_num:
                        try:
                            os.remove(os.path.join(chapters_dir, fname))
                            removed_chapters.append(fname)
                        except OSError:
                            continue
            except OSError:
                pass

        if removed_chapters:
            restored_items.append(f"chapters>= {chapter_num} (cleared {len(removed_chapters)})")

        return (
            True,
            f"未找到第{anchor_chapter}章快照，已启用降级回滚（清空运行态并保留前{anchor_chapter}章正文）",
            restored_items,
        )

    restored_items: list[str] = []
    for rel_path in _RUNTIME_STATE_TRACKED_FILES:
        snap_path = os.path.join(snapshot_dir, rel_path)
        target_path = os.path.join(filepath, rel_path)
        if os.path.exists(snap_path):
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(snap_path, target_path)
            restored_items.append(rel_path)
        else:
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                    restored_items.append(f"{rel_path} (cleared)")
                except OSError:
                    pass

    chapters_dir = os.path.join(filepath, "chapters")
    removed_chapters: list[str] = []
    if os.path.isdir(chapters_dir):
        try:
            for fname in os.listdir(chapters_dir):
                match = re.match(r"^chapter_(\d+)\.txt$", str(fname))
                if not match:
                    continue
                chapter_id = int(match.group(1))
                if chapter_id >= chapter_num:
                    try:
                        os.remove(os.path.join(chapters_dir, fname))
                        removed_chapters.append(fname)
                    except OSError:
                        continue
        except OSError:
            pass

    if removed_chapters:
        restored_items.append(f"chapters>= {chapter_num} (cleared {len(removed_chapters)})")

    return True, f"已恢复至第{anchor_chapter}章运行态", restored_items


def _runtime_architecture_precheck(filepath: str) -> tuple[bool, list[str]]:
    architecture_path = resolve_architecture_file(filepath, prefer_active=False)
    if not os.path.exists(architecture_path):
        return False, ["未找到架构文件 Novel_architecture.txt"]

    architecture_text = read_file(architecture_path)
    if not architecture_text.strip():
        return False, ["架构文件为空"]

    issues = collect_runtime_architecture_issues(architecture_text, required_sections=(0, 88, 136))
    return len(issues) == 0, issues


def _normalize_architecture_context_budget(raw_value: Any, default: int) -> int:
    parsed = _safe_int(raw_value)
    if parsed is None or parsed <= 0:
        parsed = default
    return max(4000, min(120000, int(parsed)))


def _load_runtime_architecture_text(
    filepath: str,
    max_chars: int = 22000,
    ignore_budget: bool = False,
) -> str:
    architecture_path = resolve_architecture_file(filepath, prefer_active=False)
    if not os.path.exists(architecture_path):
        return ""

    budget = _normalize_architecture_context_budget(max_chars, 22000)
    architecture_text = read_file(architecture_path)
    runtime_text = build_runtime_architecture_context(
        architecture_text,
        max_chars=budget,
        section_numbers_hint=(0, 88, 136),
        ignore_budget=bool(ignore_budget),
    )
    return runtime_text or architecture_text


def _load_post_batch_runtime_audit_options(config: dict[str, Any]) -> tuple[bool, int]:
    other_params = config.get("other_params", {}) if isinstance(config, dict) else {}
    if not isinstance(other_params, dict):
        return False, 20

    enabled = _safe_bool(other_params.get("post_batch_runtime_audit_enabled"), default=False)
    try:
        sample_size = int(other_params.get("post_batch_runtime_audit_sample_size", 20))
    except (TypeError, ValueError):
        sample_size = 20

    if sample_size < 0:
        sample_size = 0

    return enabled, sample_size


def _load_blueprint_runtime_options(other_params: object, timeout_fallback: int) -> dict[str, Any]:
    params = other_params if isinstance(other_params, dict) else {}
    fallback_stage_timeout = max(900, int(timeout_fallback))

    blueprint_target_score = _safe_float(params.get("blueprint_target_score"))
    if blueprint_target_score is None:
        blueprint_target_score = 80.0

    blueprint_critic_threshold = _safe_float(params.get("blueprint_critic_threshold"))
    if blueprint_critic_threshold is None:
        blueprint_critic_threshold = 7.5

    blueprint_critic_trigger_margin = _safe_float(params.get("blueprint_critic_trigger_margin"))
    if blueprint_critic_trigger_margin is None:
        blueprint_critic_trigger_margin = 8.0

    blueprint_stage_timeout = _safe_int(params.get("blueprint_stage_timeout"))
    if blueprint_stage_timeout is None or blueprint_stage_timeout <= 0:
        blueprint_stage_timeout = fallback_stage_timeout

    blueprint_heartbeat_interval = _safe_int(params.get("blueprint_heartbeat_interval"))
    if blueprint_heartbeat_interval is None or blueprint_heartbeat_interval <= 0:
        blueprint_heartbeat_interval = 30

    blueprint_full_auto_mode = _safe_bool(params.get("blueprint_full_auto_mode"), default=True)
    blueprint_auto_restart_on_arch_change = _safe_bool(
        params.get("blueprint_auto_restart_on_arch_change"),
        default=True,
    )
    blueprint_resume_auto_repair_existing = _safe_bool(
        params.get("blueprint_resume_auto_repair_existing"),
        default=True,
    )
    blueprint_force_resume_skip_history_validation = _safe_bool(
        params.get("blueprint_force_resume_skip_history_validation"),
        default=False,
    )

    return {
        "blueprint_batch_size": 1,  # 目录生成固定单章串行，避免批次漏节
        "blueprint_target_score": float(blueprint_target_score),
        "optimize_per_batch": _safe_bool(params.get("blueprint_optimize_per_batch"), default=False),
        "enable_blueprint_critic": _safe_bool(params.get("blueprint_enable_critic"), default=False),
        "blueprint_critic_threshold": float(blueprint_critic_threshold),
        "blueprint_critic_trigger_margin": float(blueprint_critic_trigger_margin),
        "blueprint_stage_timeout": int(blueprint_stage_timeout),
        "blueprint_heartbeat_interval": int(blueprint_heartbeat_interval),
        "blueprint_full_auto_mode": blueprint_full_auto_mode,
        "blueprint_auto_restart_on_arch_change": blueprint_auto_restart_on_arch_change,
        "blueprint_resume_auto_repair_existing": blueprint_resume_auto_repair_existing,
        "blueprint_force_resume_skip_history_validation": blueprint_force_resume_skip_history_validation,
    }


def _load_architecture_context_budgets(loaded_config: dict[str, Any]) -> dict[str, Any]:
    other_params = loaded_config.get("other_params", {}) if isinstance(loaded_config, dict) else {}
    if not isinstance(other_params, dict):
        other_params = {}

    def _budget(key: str, default: int) -> int:
        return _normalize_architecture_context_budget(other_params.get(key), default)

    return {
        "chapter_prompt": _budget("architecture_context_budget_chapter_prompt", 18000),
        "consistency": _budget("architecture_context_budget_consistency", 22000),
        "quality_loop": _budget("architecture_context_budget_quality_loop", 16000),
        "ignore_budget": _safe_bool(other_params.get("architecture_context_ignore_budget"), default=True),
    }


def _run_post_batch_runtime_audit(project_dir: str, sample_size: int) -> dict[str, Any]:
    from pathlib import Path
    from scripts.audit_prompt_runtime_architecture import audit_project_logs

    project_path = Path(project_dir)
    if not project_path.exists() or not project_path.is_dir():
        raise ValueError(f"无效目录: {project_dir}")

    return audit_project_logs(project_path, sample_size=int(sample_size))


def _ask_yes_no_on_main_thread(self, title: str, message: str) -> bool:
    if threading.current_thread() is threading.main_thread():
        return bool(messagebox.askyesno(title, message))

    decision = {"ok": False}
    done = threading.Event()

    def _ask() -> None:
        try:
            decision["ok"] = bool(messagebox.askyesno(title, message))
        finally:
            done.set()

    try:
        self.master.after(0, _ask)
    except (RuntimeError, AttributeError):
        return False

    done.wait()
    return bool(decision["ok"])


_DEFAULT_BATCH_SETTINGS = {
    "word_count": 5000,
    "min_word_count": 3500,
    "auto_enrich": True,
    "optimization": True,
}


def _normalize_batch_settings(raw_settings: Any) -> dict[str, Any]:
    settings = dict(_DEFAULT_BATCH_SETTINGS)
    if isinstance(raw_settings, dict):
        settings.update(raw_settings)

    word_count = _safe_int(settings.get("word_count"))
    min_word_count = _safe_int(settings.get("min_word_count"))
    settings["word_count"] = word_count if isinstance(word_count, int) and word_count > 0 else _DEFAULT_BATCH_SETTINGS["word_count"]
    settings["min_word_count"] = (
        min_word_count if isinstance(min_word_count, int) and min_word_count > 0 else _DEFAULT_BATCH_SETTINGS["min_word_count"]
    )
    settings["auto_enrich"] = _safe_bool(settings.get("auto_enrich"), default=bool(_DEFAULT_BATCH_SETTINGS["auto_enrich"]))
    settings["optimization"] = _safe_bool(settings.get("optimization"), default=bool(_DEFAULT_BATCH_SETTINGS["optimization"]))
    return settings


def _batch_settings_path(project_path: str) -> str:
    return os.path.join(project_path, "batch_settings.json")


def _load_batch_settings(project_path: str, log_func: Callable[[str], None]) -> dict[str, Any]:
    settings_path = _batch_settings_path(project_path)
    if not os.path.exists(settings_path):
        return dict(_DEFAULT_BATCH_SETTINGS)

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        return _normalize_batch_settings(loaded)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as settings_error:
        log_func(f"读取批量设置失败，使用默认设置: {settings_error}")
        return dict(_DEFAULT_BATCH_SETTINGS)


def _save_batch_settings(project_path: str, settings: dict[str, Any], log_func: Callable[[str], None]) -> None:
    settings_path = _batch_settings_path(project_path)
    try:
        normalized_settings = _normalize_batch_settings(settings)
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(normalized_settings, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError, ValueError) as save_error:
        log_func(f"保存批量设置失败: {save_error}")


def _detect_next_chapter_number(project_path: str) -> int:
    chapter_dir = os.path.join(project_path, "chapters")
    files = glob.glob(os.path.join(chapter_dir, "chapter_*.txt"))
    if not files:
        return 1
    return max(int(os.path.basename(f).split("_")[1].split(".")[0]) for f in files) + 1


def _parse_batch_chapter_range(start_text: str, end_text: str) -> tuple[int, int]:
    start_raw = str(start_text or "").strip()
    end_raw = str(end_text or "").strip()
    if not start_raw:
        raise ValueError("请填写起始章节。")

    # 兼容单输入范围：如“1-5”“1~5”“1到5”
    m = re.match(r"^\s*(\d+)\s*[-~—–到]\s*(\d+)\s*$", start_raw)
    if m:
        start_val = int(m.group(1))
        end_val = int(m.group(2))
        if end_raw:
            try:
                typed_end = int(end_raw)
            except ValueError as parse_error:
                raise ValueError("结束章节必须是整数。") from parse_error
            if typed_end != end_val:
                raise ValueError("范围输入与结束章节不一致，请只保留一种填写方式。")
        return start_val, end_val

    if not end_raw:
        raise ValueError("请填写结束章节，或在起始章节中输入范围（如 1-5）。")

    try:
        start_val = int(start_raw)
    except ValueError as parse_error:
        raise ValueError("起始章节必须是整数，或使用范围格式（如 1-5）。") from parse_error
    try:
        end_val = int(end_raw)
    except ValueError as parse_error:
        raise ValueError("结束章节必须是整数。") from parse_error
    return start_val, end_val


def _inject_role_library_profiles(
    prompt_text: str,
    role_names: list[str],
    role_lib_path: str,
    log_func: Callable[[str], None],
) -> str:
    final_prompt = str(prompt_text or "")
    role_contents: list[str] = []
    if os.path.exists(role_lib_path):
        for root, _dirs, files in os.walk(role_lib_path):
            for file in files:
                if file.endswith(".txt") and os.path.splitext(file)[0] in role_names:
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            role_contents.append(f.read().strip())
                    except (OSError, UnicodeDecodeError) as e:
                        log_func(f"读取角色文件 {file} 失败: {str(e)}")
    if not role_contents:
        return final_prompt

    role_content_str = "\n".join(role_contents)
    placeholder_variations = [
        "核心人物(可能未指定)：{characters_involved}",
        "核心人物：{characters_involved}",
        "核心人物(可能未指定):{characters_involved}",
        "核心人物:{characters_involved}",
    ]

    for placeholder in placeholder_variations:
        if placeholder in final_prompt:
            return final_prompt.replace(placeholder, f"核心人物：\n{role_content_str}")

    lines = final_prompt.split("\n")
    for idx, line in enumerate(lines):
        if "核心人物" in line and "：" in line:
            lines[idx] = f"核心人物：\n{role_content_str}"
            break
    return "\n".join(lines)


def _emit_quality_loop_score_events(self, chapter_num: int, logs: object) -> None:
    if not isinstance(logs, list):
        return

    for item in logs:
        if not isinstance(item, dict):
            continue
        event = {
            "event_type": "score_round",
            "chapter": chapter_num,
            "iteration": item.get("iteration", 0),
            "raw_score": item.get("raw_score"),
            "critic_score": item.get("critic_score"),
            "final_score": item.get("final_score", item.get("score")),
            "trigger_reasons": item.get("trigger_reasons", []),
            "critic_feedback": item.get("critic_feedback", ""),
            "guard_feedback": item.get("guard_feedback", ""),
        }
        self.safe_log_quality_score_event(event)


def _normalize_quality_loop_result(
    raw_result: object,
    *,
    fallback_content: str,
    fallback_score: float = 0.0,
) -> dict[str, Any]:
    result = raw_result if isinstance(raw_result, dict) else {}

    content = result.get("content", fallback_content)
    if not isinstance(content, str):
        content = fallback_content

    final_score = _safe_float(result.get("final_score"))
    if final_score is None:
        final_score = float(fallback_score)

    iterations = _safe_int(result.get("iterations"))
    if iterations is None or iterations < 0:
        iterations = 0

    logs = result.get("logs", [])
    if not isinstance(logs, list):
        logs = []

    status = str(result.get("status", "unknown") or "unknown")
    hard_gate_blocked = _safe_bool(
        result.get("hard_gate_blocked"),
        default=(status == "hard_gate_blocked"),
    )
    parse_failure_guard_engaged = _safe_bool(
        result.get("parse_failure_guard_engaged"),
        default=False,
    )

    return {
        "content": content,
        "final_score": float(final_score),
        "iterations": int(iterations),
        "status": status,
        "hard_gate_blocked": hard_gate_blocked,
        "parse_failure_guard_engaged": parse_failure_guard_engaged,
        "logs": logs,
    }


def _extract_llm_runtime_settings(
    raw_config: object,
    *,
    default_interface_format: str = "OpenAI",
    default_temperature: float = 0.7,
    default_max_tokens: int = 8192,
    default_timeout: int = 600,
) -> dict[str, Any]:
    cfg = raw_config if isinstance(raw_config, dict) else {}

    temperature = _safe_float(cfg.get("temperature"))
    if temperature is None:
        temperature = float(default_temperature)

    max_tokens = _safe_int(cfg.get("max_tokens"))
    if max_tokens is None or max_tokens <= 0:
        max_tokens = int(default_max_tokens)

    timeout = _safe_int(cfg.get("timeout"))
    if timeout is None or timeout <= 0:
        timeout = int(default_timeout)

    interface_format = str(cfg.get("interface_format", default_interface_format) or default_interface_format)
    model_name = str(cfg.get("model_name", "") or "")
    api_key = str(cfg.get("api_key", "") or "")
    base_url = str(cfg.get("base_url", "") or "")

    return {
        "interface_format": interface_format,
        "api_key": api_key,
        "base_url": base_url,
        "model_name": model_name,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "timeout": int(timeout),
    }


_QUALITY_SCORE_DIMENSIONS = (
    "剧情连贯性",
    "角色一致性",
    "写作质量",
    "架构遵循度",
    "设定遵循度",
    "情感张力",
    "系统机制",
)


class _QualityLoopControllerProtocol(Protocol):
    def execute_quality_loop(
        self,
        initial_content: str,
        chapter_num: int,
        threshold: float = ...,
        progress_callback: Callable[..., Any] | None = ...,
        skip_expand: bool = ...,
        min_word_count: int = ...,
        target_word_count: int = ...,
        max_iterations_override: int | None = ...,
    ) -> dict[str, Any]: ...


def _resolve_quality_score(scores: object, default: float = 0.0) -> float:
    score_map = scores if isinstance(scores, dict) else {}
    direct_score = _safe_float(score_map.get("综合评分"))
    if direct_score is not None:
        return max(0.0, min(10.0, direct_score))

    dims: list[float] = []
    for dim in _QUALITY_SCORE_DIMENSIONS:
        value = _safe_float(score_map.get(dim))
        if value is not None:
            dims.append(max(0.0, min(10.0, value)))
    if dims:
        return round(sum(dims) / len(dims), 2)
    return float(default)


def _run_quality_loop_with_reporting(
    self,
    *,
    controller: _QualityLoopControllerProtocol | None,
    chapter_num: int,
    initial_content: str,
    threshold: float,
    progress_callback,
    stage_label: str,
    fallback_score: float = 0.0,
    skip_expand: bool = False,
    min_word_count: int | None = None,
    target_word_count: int | None = None,
    max_iterations_override: int | None = None,
) -> dict[str, Any]:
    if controller is None:
        self.safe_log(f"⚠️ {stage_label}跳过：质量闭环控制器不可用")
        return _normalize_quality_loop_result(
            {},
            fallback_content=initial_content,
            fallback_score=fallback_score,
        )

    execute_kwargs: dict[str, Any] = {
        "initial_content": initial_content,
        "chapter_num": chapter_num,
        "threshold": threshold,
        "progress_callback": progress_callback,
        "skip_expand": bool(skip_expand),
    }
    if min_word_count is not None:
        execute_kwargs["min_word_count"] = int(min_word_count)
    if target_word_count is not None:
        execute_kwargs["target_word_count"] = int(target_word_count)
    if max_iterations_override is not None:
        execute_kwargs["max_iterations_override"] = int(max_iterations_override)

    raw_result = controller.execute_quality_loop(**execute_kwargs)
    normalized = _normalize_quality_loop_result(
        raw_result,
        fallback_content=initial_content,
        fallback_score=fallback_score,
    )

    _emit_quality_loop_score_events(self, chapter_num, normalized.get("logs", []))
    if normalized.get("parse_failure_guard_engaged"):
        self.safe_log(f"⚠️ {stage_label}触发评分解析失败保护模式（已自动降级为定向修复）")
    return normalized


def _require_llm_config(loaded_config: dict[str, Any], config_name: str) -> dict[str, Any]:
    llm_configs = loaded_config.get("llm_configs", {}) if isinstance(loaded_config, dict) else {}
    if not isinstance(llm_configs, dict):
        raise KeyError("配置文件缺少 llm_configs")

    config = llm_configs.get(str(config_name or "").strip())
    if not isinstance(config, dict) or not config:
        raise KeyError(f"未找到LLM配置: {config_name}")
    return config


def _optional_llm_config(loaded_config: dict[str, Any], config_name: str) -> dict[str, Any]:
    llm_configs = loaded_config.get("llm_configs", {}) if isinstance(loaded_config, dict) else {}
    if not isinstance(llm_configs, dict):
        return {}
    config = llm_configs.get(str(config_name or "").strip(), {})
    return config if isinstance(config, dict) else {}


def _resolve_quality_threshold(raw_value: Any, default_value: float) -> float:
    parsed = _safe_float(raw_value)
    if parsed is None or parsed <= 0:
        parsed = default_value
    return min(parsed, 10.0)


def _build_quality_loop_runtime_config(
    loaded_config: dict[str, Any],
    quality_loop_llm_name: str,
    consistency_review_llm_name: str,
    draft_defaults: dict[str, Any],
    other_params: dict[str, Any],
    min_word_count: int,
    target_word_count: int,
    enable_llm_consistency_check: bool,
    consistency_hard_gate: bool,
    enable_timeline_check: bool,
    timeline_hard_gate: bool,
    default_quality_threshold: float,
) -> tuple[dict[str, Any], float]:
    quality_loop_llm_cfg = _optional_llm_config(loaded_config, quality_loop_llm_name)
    consistency_review_cfg = _optional_llm_config(loaded_config, consistency_review_llm_name)

    consistency_review_config = {
        "api_key": consistency_review_cfg.get("api_key", draft_defaults.get("api_key", "")),
        "base_url": consistency_review_cfg.get("base_url", draft_defaults.get("base_url", "")),
        "model_name": consistency_review_cfg.get("model_name", draft_defaults.get("model_name", "")),
        "temperature": consistency_review_cfg.get("temperature", 0.2),
        "max_tokens": consistency_review_cfg.get("max_tokens", draft_defaults.get("max_tokens", 8192)),
        "timeout": consistency_review_cfg.get("timeout", draft_defaults.get("timeout", 600)),
        "interface_format": consistency_review_cfg.get(
            "interface_format",
            draft_defaults.get("interface_format", "OpenAI"),
        ),
    }

    raw_policy = quality_loop_llm_cfg.get("quality_policy", {})
    if not isinstance(raw_policy, dict):
        raw_policy = {}

    quality_threshold = _resolve_quality_threshold(
        raw_policy.get(
            "default_quality_threshold",
            quality_loop_llm_cfg.get("quality_threshold", default_quality_threshold),
        ),
        default_quality_threshold,
    )
    quality_loop_arch_budget = _normalize_architecture_context_budget(
        other_params.get("architecture_context_budget_quality_loop"),
        16000,
    )
    quality_loop_ignore_budget = _safe_bool(
        other_params.get("architecture_context_ignore_budget"),
        default=True,
    )

    merged_policy = {
        "default_quality_threshold": quality_threshold,
        "max_iterations": raw_policy.get("max_iterations", 10),
        "min_word_count_before_expand": raw_policy.get("min_word_count_before_expand", int(min_word_count)),
        "target_word_count_after_expand": raw_policy.get("target_word_count_after_expand", int(target_word_count)),
        "enable_compression": _safe_bool(raw_policy.get("enable_compression"), default=False),
        "force_critic_logging_each_iteration": _safe_bool(
            raw_policy.get(
                "force_critic_logging_each_iteration",
                other_params.get("force_critic_logging_each_iteration", False),
            ),
            default=False,
        ),
        "word_count_adjust_score_tolerance": raw_policy.get("word_count_adjust_score_tolerance", 0.5),
        "severe_threshold_offset": raw_policy.get("severe_threshold_offset", 2.0),
        "stagnation_threshold": raw_policy.get("stagnation_threshold", 0.05),
        "stagnation_count_limit": raw_policy.get("stagnation_count_limit", 5),
        "parse_failure_streak_limit": max(1, _safe_int(raw_policy.get("parse_failure_streak_limit")) or 3),
        "enable_llm_consistency_check": enable_llm_consistency_check,
        "consistency_hard_gate": consistency_hard_gate,
        "enable_timeline_check": enable_timeline_check,
        "timeline_hard_gate": timeline_hard_gate,
    }

    loop_llm_config = {
        "api_key": quality_loop_llm_cfg.get("api_key", draft_defaults.get("api_key", "")),
        "base_url": quality_loop_llm_cfg.get("base_url", draft_defaults.get("base_url", "")),
        "model_name": quality_loop_llm_cfg.get("model_name", draft_defaults.get("model_name", "")),
        "temperature": 0.7,  # 优化时适当降低温度
        "max_tokens": quality_loop_llm_cfg.get("max_tokens", draft_defaults.get("max_tokens", 8192)),
        "timeout": quality_loop_llm_cfg.get("timeout", draft_defaults.get("timeout", 600)),
        "interface_format": quality_loop_llm_cfg.get(
            "interface_format",
            draft_defaults.get("interface_format", "OpenAI"),
        ),
        "enable_llm_consistency_check": enable_llm_consistency_check,
        "consistency_hard_gate": consistency_hard_gate,
        "enable_timeline_check": enable_timeline_check,
        "timeline_hard_gate": timeline_hard_gate,
        "consistency_review_config": consistency_review_config,
        "quality_threshold": quality_threshold,
        "quality_policy": merged_policy,
        "architecture_context_max_chars": quality_loop_arch_budget,
        "architecture_context_ignore_budget": quality_loop_ignore_budget,
    }
    return loop_llm_config, quality_threshold


def _build_critic_llm_runtime_config(
    loaded_config: dict[str, Any],
    critique_llm_name: str,
    draft_defaults: dict[str, Any],
) -> dict[str, Any]:
    critique_llm_cfg = _optional_llm_config(loaded_config, critique_llm_name)
    return {
        "api_key": critique_llm_cfg.get("api_key", draft_defaults.get("api_key", "")),
        "base_url": critique_llm_cfg.get("base_url", draft_defaults.get("base_url", "")),
        "model_name": critique_llm_cfg.get("model_name", draft_defaults.get("model_name", "")),
        "temperature": 1.0,  # 毒舌需要高创造性
        "max_tokens": critique_llm_cfg.get("max_tokens", draft_defaults.get("max_tokens", 8192)),
        "timeout": critique_llm_cfg.get("timeout", draft_defaults.get("timeout", 600)),
        "interface_format": critique_llm_cfg.get(
            "interface_format",
            draft_defaults.get("interface_format", "OpenAI"),
        ),
    }


def _parse_batch_runtime_request(result: dict[str, Any]) -> tuple[int, int, int, int, bool, bool]:
    try:
        start_chapter = int(result["start"])
        end_chapter = int(result["end"])
        target_word = int(result["word"])
        min_word = int(result["min"])
    except (TypeError, ValueError) as error:
        raise ValueError("章节范围或字数配置无效") from error

    if start_chapter <= 0 or end_chapter <= 0 or target_word <= 0 or min_word <= 0:
        raise ValueError("章节号和字数必须大于0")
    if start_chapter > end_chapter:
        raise ValueError("起始章节不能大于结束章节")

    auto_enrich = _safe_bool(result.get("auto_enrich"), default=True)
    optimization = _safe_bool(result.get("optimization"), default=True)
    return start_chapter, end_chapter, target_word, min_word, auto_enrich, optimization


def _invoke_batch_precheck_runner(
    pre_check_runner: Callable[..., dict[str, Any]],
    filepath: str,
    start_chapter: int,
    end_chapter: int,
    *,
    deep_scan: bool,
) -> dict[str, Any]:
    try:
        return pre_check_runner(
            filepath,
            start_chapter,
            end_chapter,
            print_report=False,
            deep_scan=deep_scan,
        )
    except TypeError as type_error:
        # 兼容旧版 runner：不支持 deep_scan 参数
        if "deep_scan" not in str(type_error):
            raise
        return pre_check_runner(filepath, start_chapter, end_chapter, print_report=False)


def _safe_count(value: Any) -> int:
    parsed = _safe_int(value)
    return parsed if isinstance(parsed, int) and parsed > 0 else 0


def _collect_batch_precheck_deep_warnings(pre_check_report: dict[str, Any]) -> tuple[str, list[str]]:
    deep_checks = pre_check_report.get("deep_checks", {})
    if not isinstance(deep_checks, dict) or not deep_checks:
        return "", []

    placeholder_check = deep_checks.get("placeholder", {}) if isinstance(deep_checks.get("placeholder"), dict) else {}
    structure_check = deep_checks.get("structure", {}) if isinstance(deep_checks.get("structure"), dict) else {}
    duplicate_check = deep_checks.get("duplicate", {}) if isinstance(deep_checks.get("duplicate"), dict) else {}
    consistency_check = deep_checks.get("consistency", {}) if isinstance(deep_checks.get("consistency"), dict) else {}

    placeholder_count = _safe_count(placeholder_check.get("count"))
    structure_chapters = _safe_count(structure_check.get("chapters_affected"))
    duplicate_pairs = _safe_count(duplicate_check.get("pairs_found"))
    consistency_chapters = _safe_count(consistency_check.get("chapters_affected"))

    deep_summary = (
        "🧪 预检深扫: "
        f"占位符{placeholder_count} | "
        f"结构异常章{structure_chapters} | "
        f"重复对{duplicate_pairs} | "
        f"一致性提示章{consistency_chapters}"
    )
    warnings: list[str] = []
    if placeholder_count > 0:
        warnings.append(f"深扫发现占位符问题 {placeholder_count} 处")
    if structure_chapters > 0:
        warnings.append(f"深扫发现结构异常章节 {structure_chapters} 章")
    if duplicate_pairs > 0:
        warnings.append(f"深扫发现重复风险 {duplicate_pairs} 对")
    if consistency_chapters > 0:
        warnings.append(f"深扫提示一致性风险章节 {consistency_chapters} 章（建议人工复核）")

    return deep_summary, warnings


def _extract_batch_precheck_metrics(pre_check_report: dict[str, Any]) -> dict[str, int]:
    summary = pre_check_report.get("summary", {}) if isinstance(pre_check_report.get("summary"), dict) else {}
    deep_checks = pre_check_report.get("deep_checks", {}) if isinstance(pre_check_report.get("deep_checks"), dict) else {}

    placeholder_check = deep_checks.get("placeholder", {}) if isinstance(deep_checks.get("placeholder"), dict) else {}
    structure_check = deep_checks.get("structure", {}) if isinstance(deep_checks.get("structure"), dict) else {}
    duplicate_check = deep_checks.get("duplicate", {}) if isinstance(deep_checks.get("duplicate"), dict) else {}
    consistency_check = deep_checks.get("consistency", {}) if isinstance(deep_checks.get("consistency"), dict) else {}

    return {
        "passed_checks": _safe_count(summary.get("passed_checks")),
        "total_checks": _safe_count(summary.get("total_checks")),
        "warnings_count": _safe_count(summary.get("warnings_count")),
        "placeholder_count": _safe_count(placeholder_check.get("count")),
        "structure_chapters": _safe_count(structure_check.get("chapters_affected")),
        "duplicate_pairs": _safe_count(duplicate_check.get("pairs_found")),
        "consistency_chapters": _safe_count(consistency_check.get("chapters_affected")),
    }


def _resolve_batch_precheck_risk_level(metrics: dict[str, int]) -> tuple[str, str, int]:
    placeholder_count = _safe_count(metrics.get("placeholder_count"))
    structure_chapters = _safe_count(metrics.get("structure_chapters"))
    duplicate_pairs = _safe_count(metrics.get("duplicate_pairs"))
    warnings_count = _safe_count(metrics.get("warnings_count"))
    consistency_chapters = _safe_count(metrics.get("consistency_chapters"))

    if placeholder_count > 0:
        return "high", "🔴 高风险", 95
    if structure_chapters > 0:
        return "high", "🔴 高风险", 90

    risk_score = (
        duplicate_pairs * 12
        + min(consistency_chapters, 6) * 4
        + min(warnings_count, 8) * 5
    )

    if risk_score >= 45:
        return "high", "🔴 高风险", risk_score
    if risk_score >= 18:
        return "medium", "🟡 中风险", risk_score
    return "low", "🟢 低风险", risk_score


def _build_batch_precheck_risk_snapshot(pre_check_report: dict[str, Any]) -> dict[str, Any]:
    metrics = _extract_batch_precheck_metrics(pre_check_report)
    risk_key, risk_label, risk_score = _resolve_batch_precheck_risk_level(metrics)
    warnings = pre_check_report.get("warnings", [])
    if not isinstance(warnings, list):
        warnings = []

    return {
        "event_type": "batch_precheck_risk",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "chapter_range": str(pre_check_report.get("chapter_range", "")),
        "risk_level": risk_key,
        "risk_label": risk_label,
        "risk_score": int(risk_score),
        "metrics": metrics,
        "warnings": [str(item) for item in warnings if str(item).strip()],
    }


def _emit_batch_precheck_risk_event(self, pre_check_report: dict[str, Any]) -> None:
    if not isinstance(pre_check_report, dict):
        return
    snapshot = _build_batch_precheck_risk_snapshot(pre_check_report)
    if hasattr(self, "safe_log_precheck_risk_event"):
        try:
            self.safe_log_precheck_risk_event(snapshot)
            return
        except (RuntimeError, ValueError, TypeError):
            pass
    if hasattr(self, "safe_log"):
        self.safe_log(
            "🧭 预检风险快照: "
            f"{snapshot.get('risk_label', '')} | "
            f"范围 {snapshot.get('chapter_range', '-')}"
        )


def _run_batch_precheck(
    self,
    filepath: str,
    start_chapter: int,
    end_chapter: int,
    pre_check_runner: Callable[..., dict[str, Any]] | None = None,
    *,
    deep_scan: bool = False,
    auto_continue_on_warning: bool = False,
    interactive: bool = True,
) -> bool:
    """执行批量预检查；返回 True 表示继续批量流程。"""
    if pre_check_runner is None:
        try:
            from novel_generator.batch_pre_checker import run_pre_check as pre_check_runner
        except ImportError:
            _stage_log(self, "S3", "⚠️ 预检查模块未找到，跳过预检查")
            return True

    try:
        _stage_log(self, "S3", f"🔍 正在运行批量生成预检查{'（深度扫描）' if deep_scan else ''}...")
        pre_check_report = _invoke_batch_precheck_runner(
            pre_check_runner,
            filepath,
            start_chapter,
            end_chapter,
            deep_scan=deep_scan,
        )
        if not isinstance(pre_check_report, dict):
            _stage_log(self, "S3", "⚠️ 预检查返回格式异常，继续执行")
            return True

        summary = pre_check_report.get("summary", {})
        if not isinstance(summary, dict):
            summary = {}
        passed = int(summary.get("passed_checks", 0) or 0)
        total = int(summary.get("total_checks", 0) or 0)
        warnings = pre_check_report.get("warnings", [])
        if not isinstance(warnings, list):
            warnings = []

        deep_summary, deep_warnings = _collect_batch_precheck_deep_warnings(pre_check_report)
        if deep_summary:
            self.safe_log(deep_summary)
        for warning in deep_warnings:
            if warning not in warnings:
                warnings.append(warning)

        warnings_count = len(warnings)
        if warnings_count > 0:
            summary["warnings_count"] = warnings_count
            pre_check_report["warnings"] = warnings
            pre_check_report["summary"] = summary
        _emit_batch_precheck_risk_event(self, pre_check_report)

        try:
            report_path = _write_batch_precheck_report(filepath, pre_check_report)
            self.safe_log(f"🧾 预检查报告已写入: {report_path}")
        except (OSError, TypeError, ValueError):
            pass

        _stage_log(self, "S3", f"📊 预检查完成: {passed}/{total} 项通过")
        if warnings_count <= 0:
            _stage_log(self, "S3", "✅ 预检查全部通过")
            return True

        self.safe_log(f"⚠️ 发现 {warnings_count} 条警告:")
        for warning in warnings[:5]:
            self.safe_log(f"   - {warning}")

        if auto_continue_on_warning:
            _stage_log(self, "S3", "🤖 全自动策略：预检查告警已自动放行（建议后续修复）")
            return True

        if not interactive:
            _stage_log(self, "S3", "ℹ️ 仅执行预检扫描，未触发继续弹窗。")
            return True

        should_continue = _ask_yes_no_on_main_thread(
            self,
            "预检查警告",
            f"预检查发现 {warnings_count} 条警告.\n\n是否仍然继续批量生成?",
        )
        if not should_continue:
            _stage_log(self, "S3", "❌ 用户取消批量生成")
            return False
        return True
    except (RuntimeError, ValueError, TypeError, OSError, KeyError, ImportError) as e:
        _stage_log(self, "S3", f"⚠️ 预检查失败(继续执行): {e}")
        return True

def generate_novel_architecture_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先选择保存文件路径")
        return
    _stage_log(self, "S1", "入口已触发：小说架构生成")

    def task():
        set_runtime_log_stage("S1")
        try:
            confirm = messagebox.askyesno("确认", "确定要生成小说架构吗？")
            if not confirm:
                self.enable_button_safe(self.btn_generate_architecture)
                return

            self.disable_button_safe(self.btn_generate_architecture)
            try:


                interface_format = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]["interface_format"]
                api_key = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]["api_key"]
                base_url = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]["base_url"]
                model_name = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]["model_name"]
                temperature = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]["temperature"]
                max_tokens = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]["max_tokens"]
                timeout_val = self.loaded_config["llm_configs"][self.architecture_llm_var.get()]["timeout"]



                topic = self.topic_text.get("0.0", "end").strip()
                genre = self.genre_var.get().strip()
                num_chapters = self.safe_get_int(self.num_chapters_var, 10)
                word_number = self.safe_get_int(self.word_number_var, 3000)
                # 获取内容指导
                user_guidance = self.user_guide_text.get("0.0", "end").strip()

                _stage_log(self, "S1", "开始生成小说架构...")
                Novel_architecture_generate(
                    interface_format=interface_format,
                    api_key=api_key,
                    base_url=base_url,
                    llm_model=model_name,
                    topic=topic,
                    genre=genre,
                    number_of_chapters=num_chapters,
                    word_number=word_number,
                    filepath=filepath,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout_val,
                    user_guidance=user_guidance  # 添加内容指导参数
                )
                _stage_log(self, "S1", "✅ 小说架构生成完成。请在 'Novel Architecture' 标签页查看或编辑。")
            except (RuntimeError, ValueError, TypeError, OSError, KeyError, ConnectionError, ImportError):
                self.handle_exception("生成小说架构时出错")
            finally:
                self.enable_button_safe(self.btn_generate_architecture)
        finally:
            clear_runtime_log_stage()
    threading.Thread(target=task, daemon=True).start()

def generate_chapter_blueprint_ui(self):
    def _read_architecture_hash(chapter_dir_path: str) -> str:
        architecture_path = resolve_architecture_file(chapter_dir_path)
        if not os.path.exists(architecture_path):
            return ""
        try:
            content = read_file(architecture_path)
        except OSError:
            return ""
        normalized_content = str(content or "").strip()
        if not normalized_content:
            return ""
        # 与 StrictChapterGenerator 的哈希口径保持一致（strip 后再 hash）
        return hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()

    other_params = self.loaded_config.get("other_params", {})
    full_auto_mode = _safe_bool(
        other_params.get("blueprint_full_auto_mode") if isinstance(other_params, dict) else None,
        default=True,
    )
    auto_restart_on_arch_change = _safe_bool(
        other_params.get("blueprint_auto_restart_on_arch_change") if isinstance(other_params, dict) else None,
        default=True,
    )
    resume_auto_repair_existing = _safe_bool(
        other_params.get("blueprint_resume_auto_repair_existing") if isinstance(other_params, dict) else None,
        default=True,
    )
    force_resume_skip_history_validation = _safe_bool(
        other_params.get("blueprint_force_resume_skip_history_validation") if isinstance(other_params, dict) else None,
        default=False,
    )
    _stage_log(self, "S2", "入口已触发：章节目录生成/续传")

    filepath = self.filepath_var.get().strip()
    if not filepath:
        if full_auto_mode:
            _stage_log(self, "S2", "❌ 全自动模式中止：未配置保存路径")
        else:
            messagebox.showwarning("警告", "请先选择保存文件路径")
        return

    precheck_ok, precheck_issues = _runtime_architecture_precheck(filepath)
    if not precheck_ok:
        issue_text = "\n".join(f"- {item}" for item in precheck_issues)
        _stage_log(self, "S2", "❌ 运行时架构守卫阻断：")
        for item in precheck_issues:
            self.safe_log(f"  - {item}")
        if not full_auto_mode:
            messagebox.showwarning("架构守卫阻断", f"运行时架构预检查未通过：\n{issue_text}")
        return

    number_of_chapters = self.safe_get_int(self.num_chapters_var, 10)
    if number_of_chapters <= 0:
        number_of_chapters = 50
        _stage_log(self, "S2", "⚠️ 章节数设置为0或负数，已回退默认50章")
        self.num_chapters_var.set("50")

    if full_auto_mode:
        _stage_log(
            self,
            "S2",
            "🤖 全自动模式已启用：跳过交互确认，自动续写/"
            f"{'自动修复' if resume_auto_repair_existing else '严格阻断'}"
        )
        if force_resume_skip_history_validation:
            _stage_log(self, "S2", "⚠️ 已启用高风险强制续传：将跳过历史目录校验（仅建议应急使用）")

    resume_mode = True
    progress_probe = _inspect_existing_blueprint_progress(filepath)
    existing_end = int(progress_probe.get("detected_end", 0))
    main_max = int(progress_probe.get("main_max", 0))
    split_contiguous_end = int(progress_probe.get("split_contiguous_end", 0))
    split_max = int(progress_probe.get("split_max", 0))
    split_count = int(progress_probe.get("split_count", 0))
    split_dir_path = os.path.join(filepath, "chapter_blueprints")
    if split_count > 0:
        _stage_log(self, "S2", f"🗂️ 单章目录：{split_dir_path}（{split_count}个文件）")
    elif os.path.isdir(split_dir_path):
        _stage_log(self, "S2", f"🗂️ 单章目录：{split_dir_path}（当前无章节文件）")
    else:
        _stage_log(self, "S2", f"🗂️ 单章目录：{split_dir_path}（目录未创建）")
    if main_max > 0 or split_count > 0:
        _stage_log(
            self,
            "S2",
            "📊 Step2进度探测："
            f"主目录到第{main_max}章 | "
            f"拆分目录连续到第{split_contiguous_end}章（最大第{split_max}章，文件{split_count}个） | "
            f"采用断点第{existing_end}章"
        )
        if split_contiguous_end > main_max:
            _stage_log(self, "S2", "🧭 检测到主目录落后于拆分目录，续传将优先按拆分目录断点继续。")
    current_arch_hash = _read_architecture_hash(filepath)
    saved_state = _load_blueprint_state_file(filepath)
    saved_arch_hash = str(saved_state.get("architecture_hash", "")).strip()
    saved_last_generated = _safe_int(saved_state.get("last_generated_chapter")) or 0
    arch_mismatch_detected = bool(saved_arch_hash and current_arch_hash and saved_arch_hash != current_arch_hash)
    stale_state_detected = bool(existing_end > 0 and saved_last_generated <= 0)
    effective_arch_changed = bool(arch_mismatch_detected)
    if arch_mismatch_detected and stale_state_detected:
        effective_arch_changed = False
        _stage_log(
            self,
            "S2",
            "⚠️ 检测到目录与运行状态不一致（已有目录但状态进度为0），"
            "将按续写模式处理并自动修正状态哈希。"
        )

    if existing_end > 0:
        if full_auto_mode:
            if effective_arch_changed and auto_restart_on_arch_change:
                resume_mode = False
                _stage_log(self, "S2", "🧠 全自动策略：检测到架构变更，自动切换为从头开始生成目录")
            elif effective_arch_changed:
                resume_mode = True
                _stage_log(self, "S2", "⚠️ 全自动策略：检测到架构变更，但配置要求续写，后续可能被严格守卫阻断")
            else:
                resume_mode = True
                _stage_log(self, "S2", f"🔁 全自动策略：检测到已有进度，自动续写（从第{existing_end + 1}章）")
        else:
            if effective_arch_changed:
                continue_after_arch_change = messagebox.askyesno(
                    "架构已变更",
                    "检测到当前架构文件与上次目录生成时不一致。\n\n"
                    "建议从头开始生成目录。\n"
                    "是否仍进入“续写/重开”选择？",
                )
                if not continue_after_arch_change:
                    self.enable_button_safe(self.btn_generate_directory)
                    return

            ask_msg = (
                f"检测到已有目录进度：已生成到第 {existing_end} 章。\n\n"
                "选择“是”：续写（从断点继续）\n"
                "选择“否”：从头开始（清空旧目录）\n"
                "选择“取消”：不启动本次生成"
            )
            continue_choice = messagebox.askyesnocancel("检测到已有进度", ask_msg)
            if continue_choice is None:
                self.enable_button_safe(self.btn_generate_directory)
                return
            resume_mode = bool(continue_choice)

    allow_resume_with_arch_mismatch = bool(arch_mismatch_detected and resume_mode)
    if allow_resume_with_arch_mismatch:
        _stage_log(self, "S2", "🛠️ 已启用“架构变更续写”保护：将自动同步续写状态，避免误判重开。")

    if not full_auto_mode:
        confirm_msg = (
            f"确定要生成章节目录吗？\n\n"
            f"目标总章节数：{number_of_chapters}\n"
            f"启动模式：{'续写' if resume_mode else '从头开始'}\n"
            f"执行方式：单章串行（1章→下一章）"
        )
        if not messagebox.askyesno("确认", confirm_msg):
            self.enable_button_safe(self.btn_generate_directory)
            return
    else:
        _stage_log(
            self,
            "S2",
            f"🤖 全自动执行确认：目标{number_of_chapters}章 | 启动模式：{'续写' if resume_mode else '从头开始'}"
        )
    _set_step2_runtime_status(
        self,
        f"Step2状态：待启动（目标{number_of_chapters}章）",
        0.0,
        text_color="gray",
    )

    def task():
        set_runtime_log_stage("S2")
        try:
            self.disable_button_safe(self.btn_generate_directory)
            monitor_started = False
            run_failed = False
            try:
                _set_step2_runtime_status(self, "Step2状态：运行中（等待修复检测）", 0.0, text_color="#1E90FF")
                _start_step2_repair_progress_monitor(self)
                monitor_started = True

                if allow_resume_with_arch_mismatch:
                    synced, sync_msg = _sync_blueprint_state_for_resume(
                        filepath,
                        current_arch_hash=current_arch_hash,
                        existing_end=existing_end,
                        target_chapters=number_of_chapters,
                        base_state=saved_state,
                    )
                    self.safe_log(("✅ " if synced else "⚠️ ") + sync_msg)

                if not resume_mode:
                    filename_dir = os.path.join(filepath, "Novel_directory.txt")
                    if os.path.exists(filename_dir):
                        clear_file_content(filename_dir)
                    _stage_log(self, "S2", "🧹 已按用户选择清空旧目录，将从第1章开始生成")
                else:
                    if existing_end > 0:
                        _stage_log(self, "S2", f"🔁 检测到已有进度，将从第{existing_end + 1}章继续生成")

                # 目录生成已固定为单章串行，避免多章批次导致漏节/格式错乱。
                blueprint_batch_size = 1

                interface_format = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]["interface_format"]
                api_key = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]["api_key"]
                base_url = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]["base_url"]
                model_name = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]["model_name"]
                temperature = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]["temperature"]
                max_tokens = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]["max_tokens"]
                timeout_val = self.loaded_config["llm_configs"][self.chapter_outline_llm_var.get()]["timeout"]
                blueprint_runtime_options = _load_blueprint_runtime_options(
                    other_params=other_params,
                    timeout_fallback=int(timeout_val),
                )
                blueprint_target_score = blueprint_runtime_options["blueprint_target_score"]
                optimize_per_batch = blueprint_runtime_options["optimize_per_batch"]
                enable_blueprint_critic = blueprint_runtime_options["enable_blueprint_critic"]
                blueprint_critic_threshold = blueprint_runtime_options["blueprint_critic_threshold"]
                blueprint_critic_trigger_margin = blueprint_runtime_options["blueprint_critic_trigger_margin"]
                blueprint_stage_timeout = blueprint_runtime_options["blueprint_stage_timeout"]
                blueprint_heartbeat_interval = blueprint_runtime_options["blueprint_heartbeat_interval"]
                active_full_auto_mode = bool(blueprint_runtime_options.get("blueprint_full_auto_mode", full_auto_mode))
                active_auto_restart_on_arch_change = bool(
                    blueprint_runtime_options.get(
                        "blueprint_auto_restart_on_arch_change",
                        auto_restart_on_arch_change,
                    )
                )
                active_resume_auto_repair_existing = bool(
                    blueprint_runtime_options.get(
                        "blueprint_resume_auto_repair_existing",
                        resume_auto_repair_existing,
                    )
                )
                active_force_resume_skip_history_validation = bool(
                    blueprint_runtime_options.get(
                        "blueprint_force_resume_skip_history_validation",
                        force_resume_skip_history_validation,
                    )
                )


                user_guidance = self.user_guide_text.get("0.0", "end").strip()  # 新增获取用户指导

                _stage_log(self, "S2", "🚀 开始生成章节蓝图（包含自动一致性验证）...")
                self.safe_log("📋 验证功能：")
                self.safe_log("  - ✅ 零容忍省略检查")
                self.safe_log("  - ✅ 自动架构一致性验证")
                self.safe_log("  - ✅ 智能修复机制")
                self.safe_log("  - ✅ 批次间一致性监控")
                self.safe_log("  - ✅ 生成模式: 单章串行（1章→下一章）")
                self.safe_log(f"  - ✅ 蓝图质量目标: {blueprint_target_score:.1f}")
                self.safe_log(f"  - ✅ 批次内优化: {'开启' if optimize_per_batch else '关闭'}")
                self.safe_log(f"  - ✅ 蓝图毒舌评审: {'开启' if enable_blueprint_critic else '关闭'}")
                self.safe_log(f"  - ✅ 全自动模式: {'开启' if active_full_auto_mode else '关闭'}")
                self.safe_log(
                    "  - ✅ 断点续传校验失败自动修复: "
                    f"{'开启' if active_resume_auto_repair_existing else '关闭（直接阻断）'}"
                )
                self.safe_log(
                    "  - ✅ 高风险强制续传(跳过历史校验): "
                    f"{'开启' if active_force_resume_skip_history_validation else '关闭'}"
                )
                if active_full_auto_mode:
                    self.safe_log(
                        "  - ✅ 自动策略: "
                        f"架构变更{'自动重开' if active_auto_restart_on_arch_change else '自动续写'} | "
                        f"目录校验失败{'自动修复后续写' if active_resume_auto_repair_existing else '直接阻断并提示'} | "
                        "低分/格式/衔接问题自动修复"
                    )
                self.safe_log("")

                Chapter_blueprint_generate(
                    interface_format=interface_format,
                    api_key=api_key,
                    base_url=base_url,
                    llm_model=model_name,
                    number_of_chapters=number_of_chapters,
                    filepath=filepath,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout_val,
                    user_guidance=user_guidance,  # 新增参数
                    batch_size=blueprint_batch_size,
                    optimize_per_batch=optimize_per_batch,
                    target_score=blueprint_target_score,
                    stage_timeout_seconds=blueprint_stage_timeout,
                    heartbeat_interval_seconds=blueprint_heartbeat_interval,
                    enable_blueprint_critic=enable_blueprint_critic,
                    blueprint_critic_threshold=blueprint_critic_threshold,
                    blueprint_critic_trigger_margin=blueprint_critic_trigger_margin,
                    enable_resume_auto_repair_existing=active_resume_auto_repair_existing,
                    enable_force_resume_skip_history_validation=active_force_resume_skip_history_validation,
                )

                # 展示最终闸门摘要（成功时也保留可视化确认）
                _log_directory_gate_summary(self, filepath)
                _log_blueprint_runtime_telemetry(self, filepath)

                self.safe_log("")
                _stage_log(self, "S2", "🎉 章节蓝图生成完成！")
                self.safe_log("📊 验证状态：")
                self.safe_log("  - ✅ 结构完整性验证通过")
                self.safe_log("  - ✅ 架构一致性验证通过")
                self.safe_log("  - ✅ 所有检查项目完成")
            
                # 🆕 自动触发蓝图质量检查
                try:
                    self.safe_log("")
                    self.safe_log("🔍 正在进行蓝图质量检查...")
                
                    from novel_generator.batch_quality_check import BatchQualityChecker
                
                    checker = BatchQualityChecker(self.filepath_var.get().strip())
                    report = checker.check_all_chapters()
                
                    if report:
                        avg_score = report.get("average_score", 0)
                        avg_structure_score = _safe_float(report.get("average_structure_score"))
                        avg_semantic_score = _safe_float(report.get("average_semantic_score"))
                        low_score_count = len(report.get("low_score_chapters", []))
                        total_chapters = report.get("total_chapters", 0)
                        quality_dist = report.get("quality_distribution", {})
                        issue_stats = report.get("issue_statistics", {})
                    
                        self.safe_log(f"  - 平均质量分: {avg_score:.1f}/100")
                        if avg_structure_score is not None or avg_semantic_score is not None:
                            parts: list[str] = []
                            if avg_structure_score is not None:
                                parts.append(f"结构合规 {avg_structure_score:.1f}")
                            if avg_semantic_score is not None:
                                parts.append(f"叙事语义 {avg_semantic_score:.1f}")
                            self.safe_log(f"  - 子评分: {' | '.join(parts)}")
                        self.safe_log(f"  - 质量分布: 优秀{quality_dist.get('excellent',0)} | 良好{quality_dist.get('good',0)} | 一般{quality_dist.get('fair',0)} | 较差{quality_dist.get('poor',0)}")
                        self.safe_log(f"  - 低分蓝图数: {low_score_count}/{total_chapters}")
                    
                        # 显示主要问题统计
                        if issue_stats:
                            top_issues = sorted(issue_stats.items(), key=lambda x: x[1], reverse=True)[:3]
                            issue_summary = ", ".join([f"{k}({v})" for k, v in top_issues])
                            self.safe_log(f"  - 主要问题: {issue_summary}")
                    
                        # === 新增：显示架构解析摘要 ===
                        arch_summary = report.get("architecture_summary")
                        if arch_summary:
                            sections = len(arch_summary.get('sections_parsed', []))
                            self.safe_log(f"  - 架构解析: {sections}/12节已覆盖 | "
                                         f"角色{arch_summary.get('characters_count',0)}个 | "
                                         f"剧情弧{arch_summary.get('plot_arcs_count',0)}个")
                    
                        # === 新增：显示章节衔接检查 ===
                        coherence = report.get("coherence_check")
                        if coherence:
                            coh_score = coherence.get('coherence_score', 100)
                            coh_issues = coherence.get('total_issues', 0)
                            self.safe_log(f"  - 章节衔接: {coh_score:.1f}分 | 衔接问题{coh_issues}处")
                        
                            if coh_issues > 0:
                                breakdown = coherence.get('issue_breakdown', {})
                                if breakdown:
                                    coh_summary = ", ".join([f"{k}({v})" for k, v in list(breakdown.items())[:3]])
                                    self.safe_log(f"    └ 衔接问题: {coh_summary}")
                            
                                # 保存衔接报告供后续修复使用
                                self._coherence_report = coherence
                    
                        blueprint_repair_started = False

                        # 只要有低分蓝图，就执行修复流程（全自动模式下直接启动）
                        if low_score_count > 0:
                            low_chapters = report.get('low_score_chapters', [])
                            if full_auto_mode:
                                self.safe_log(f"  - 🤖 检测到{low_score_count}个低分蓝图，已自动启动修复")
                                self._start_blueprint_repair(low_chapters, batch_size=50, auto_continue=True)
                                blueprint_repair_started = True
                            else:
                                self.safe_log(f"  - ⚠️ 检测到{low_score_count}个低分蓝图，即将弹出修复确认...")

                                # 使用默认参数捕获变量，避免闭包问题
                                def ask_repair(chapters=low_chapters, count=low_score_count, total=total_chapters):
                                    repair_msg = (
                                        f"🔍 蓝图质量检查完成\n\n"
                                        f"发现 {count} 个低分蓝图（占比 {count/total*100:.1f}%）\n\n"
                                        f"是否启动自动修复？\n"
                                        f"（每批50章，自动连续修复直到全部完成）"
                                    )
                                    if messagebox.askyesno("蓝图修复选项", repair_msg):
                                        # 传入所有低分章节，每批50章自动连续修复
                                        self._start_blueprint_repair(chapters, batch_size=50, auto_continue=True)
                                    else:
                                        self.safe_log("  - 用户跳过了自动修复")

                                self.master.after(100, ask_repair)  # 稍微延迟以确保UI更新
                        else:
                            # 没有低分蓝图，但检查是否有格式问题 + 分数不够高的章节
                            chapter_details = report.get('chapter_details', [])
                        
                            # 只提取有问题 且 分数低于85的章节（高分章节修复可能反而降低质量）
                            REPAIR_THRESHOLD = 85
                            issue_chapters = []
                            high_score_with_issues = 0
                        
                            for detail in chapter_details:
                                has_issues = detail.get('issues') and len(detail.get('issues', [])) > 0
                                score = detail.get('score', 100)
                            
                                if has_issues:
                                    if score < REPAIR_THRESHOLD:
                                        issue_chapters.append(detail.get('chapter_number'))
                                    else:
                                        high_score_with_issues += 1
                        
                            issues_count = len(issue_chapters)
                        
                            if issues_count > 0:
                                self.safe_log(f"  - ✅ 无低分蓝图，发现 {issues_count} 章分数<{REPAIR_THRESHOLD}且有问题")
                                if high_score_with_issues > 0:
                                    self.safe_log(f"  - ℹ️ 跳过 {high_score_with_issues} 章高分章节（修复可能降低质量）")
                                if full_auto_mode:
                                    self.safe_log("  - 🤖 全自动模式：已自动启动格式问题修复")
                                    self._start_blueprint_repair(issue_chapters, batch_size=50, auto_continue=True)
                                    blueprint_repair_started = True
                                else:
                                    def ask_repair_issues(chapters=issue_chapters, count=issues_count, threshold=REPAIR_THRESHOLD):
                                        repair_msg = (
                                            f"🔍 蓝图质量检查完成\n\n"
                                            f"✅ 无低分蓝图（平均分: {avg_score:.1f}）\n\n"
                                            f"发现 {count} 章分数<{threshold}且存在格式问题\n\n"
                                            f"是否修复这些章节？\n"
                                            f"（高分章节已自动跳过，避免修复反而降分）"
                                        )
                                        if messagebox.askyesno("修复格式问题", repair_msg):
                                            self._start_blueprint_repair(chapters, batch_size=50, auto_continue=True)
                                        else:
                                            self.safe_log("  - 用户跳过了格式问题修复")

                                    self.master.after(100, ask_repair_issues)
                            else:
                                if high_score_with_issues > 0:
                                    self.safe_log(f"  - ✅ 蓝图质量优秀（{high_score_with_issues} 章有小问题但分数高，无需修复）")
                                else:
                                    self.safe_log("  - ✅ 蓝图质量检查通过（无任何问题）")
                    
                        # === 衔接问题修复选项 ===
                        if hasattr(self, '_coherence_report') and self._coherence_report:
                            coh_issues_count = self._coherence_report.get('total_issues', 0)
                            if coh_issues_count > 0:
                                if full_auto_mode:
                                    if blueprint_repair_started:
                                        self.safe_log("  - 🤖 全自动模式：蓝图修复已启动，衔接修复将等待下一轮质量检查触发")
                                    else:
                                        self.safe_log("  - 🤖 全自动模式：已自动启动衔接修复")
                                        self._start_coherence_repair(self._coherence_report)
                                else:
                                    def ask_coherence_repair(coh_report=self._coherence_report, count=coh_issues_count):
                                        repair_msg = (
                                            f"🔗 章节衔接检查完成\n\n"
                                            f"发现 {count} 处衔接问题\n"
                                            f"（地点跳跃、冲突断裂、角色不一致等）\n\n"
                                            f"是否启动衔接修复？"
                                        )
                                        if messagebox.askyesno("衔接问题修复", repair_msg):
                                            self._start_coherence_repair(coh_report)
                                        else:
                                            self.safe_log("  - 用户跳过了衔接问题修复")

                                    # 延迟弹窗，确保格式修复弹窗先处理
                                    self.master.after(500, ask_coherence_repair)
                    else:
                        self.safe_log("  - ⚠️ 质量检查跳过(无报告)")
                except ImportError as ie:
                    self.safe_log(f"  - ⚠️ 质量检查模块未找到(跳过): {ie}")
                except (RuntimeError, ValueError, TypeError, OSError, KeyError, ImportError) as qc_error:
                    self.safe_log(f"  - ⚠️ 质量检查异常: {qc_error}")

                    self.safe_log("")
                    self.safe_log("📝 请在 'Chapter Blueprint' 标签页查看或编辑详细内容。")
                    _set_step2_runtime_status(self, "Step2状态：目录生成完成", 1.0, text_color="#2E8B57")
            except (RuntimeError, ValueError, TypeError, OSError, KeyError, ConnectionError, ImportError):
                run_failed = True
                # 失败时优先输出最终闸门报告，帮助快速定位阻断项
                _log_directory_gate_summary(self, filepath)
                _log_blueprint_runtime_telemetry(self, filepath)
                self.handle_exception("生成章节蓝图时出错")
                _set_step2_runtime_status(self, "Step2状态：执行失败（查看日志）", None, text_color="#CD5C5C")
            finally:
                if monitor_started:
                    _stop_step2_repair_progress_monitor(self)
                if not run_failed and hasattr(self, "step2_repair_status_label"):
                    # 若本轮未命中自动修复，保持“已完成”提示而非空白。
                    pass
                self.enable_button_safe(self.btn_generate_directory)
        finally:
            clear_runtime_log_stage()
    threading.Thread(target=task, daemon=True).start()

def _start_blueprint_repair(self, low_score_chapters: list[int], batch_size: int = 50, auto_continue: bool = True):
    """
    启动蓝图自动修复（后台线程）
    支持自动连续修复：每批完成后自动继续下一批
    """
    def repair_task():
        set_runtime_log_stage("S2")
        try:
            remaining_chapters = low_score_chapters.copy()
            total_repaired = 0
            total_failed = 0
            batch_num = 0
            all_improvements = []
            
            try:
                self.safe_log("")
                self.safe_log("🔧 正在启动蓝图自动修复...")
                self.safe_log(f"  - 总待修复章节: {len(remaining_chapters)}")
                self.safe_log(f"  - 每批修复数量: {batch_size}")
                self.safe_log(f"  - 自动连续修复: {'是' if auto_continue else '否'}")
                
                # 获取 LLM 配置
                llm_key = self.chapter_outline_llm_var.get()
                interface_format = self.loaded_config["llm_configs"][llm_key]["interface_format"]
                api_key = self.loaded_config["llm_configs"][llm_key]["api_key"]
                base_url = self.loaded_config["llm_configs"][llm_key]["base_url"]
                model_name = self.loaded_config["llm_configs"][llm_key]["model_name"]
                filepath = self.filepath_var.get().strip()
                
                from novel_generator.blueprint_repairer import repair_low_score_blueprints
                
                while remaining_chapters:
                    batch_num += 1
                    current_batch = remaining_chapters[:batch_size]
                    remaining_chapters = remaining_chapters[batch_size:]
                    
                    self.safe_log("")
                    self.safe_log(f"📦 开始第 {batch_num} 批修复 ({len(current_batch)} 章)...")
                    
                    def progress_callback(current, total, message):
                        self.safe_log(f"  - [{current}/{total}] {message}")
                    
                    results = repair_low_score_blueprints(
                        interface_format=interface_format,
                        api_key=api_key,
                        base_url=base_url,
                        llm_model=model_name,
                        filepath=filepath,
                        low_score_chapters=current_batch,
                        progress_callback=progress_callback,
                        max_chapters=batch_size
                    )
                    
                    total_repaired += results.get('success', 0)
                    total_failed += results.get('failed', 0)
                    all_improvements.extend(results.get('score_improvements', []))
                    
                    self.safe_log(f"  - 本批完成: 成功 {results.get('success', 0)}, 失败 {results.get('failed', 0)}")
                    
                    if remaining_chapters and auto_continue:
                        self.safe_log(f"  - 剩余 {len(remaining_chapters)} 章，自动继续下一批...")
                        import time
                        time.sleep(2)  # 短暂休息避免API限速
                
                # 输出最终结果
                self.safe_log("")
                self.safe_log("=" * 40)
                self.safe_log("🎉 全部修复任务完成！")
                self.safe_log(f"  - 总批次: {batch_num}")
                self.safe_log(f"  - 成功修复: {total_repaired} 章")
                self.safe_log(f"  - 修复失败: {total_failed} 章")
                
                if all_improvements:
                    avg_improve = sum(all_improvements) / len(all_improvements)
                    self.safe_log(f"  - 平均提升: {avg_improve:+.1f} 分")
                
                self.safe_log("")
                self.safe_log("📊 详细报告已生成: blueprint_repair_report.md")
                self.safe_log("📝 修复后的蓝图已保存，请查看 'Chapter Blueprint' 标签页。")
                
            except (RuntimeError, ValueError, TypeError, OSError, KeyError, ConnectionError, ImportError) as e:
                self.safe_log("⚠️ 蓝图修复异常堆栈：")
                self.safe_log(traceback.format_exc())
                self.safe_log(f"❌ 蓝图修复失败: {e}")
        finally:
            clear_runtime_log_stage()
    
    threading.Thread(target=repair_task, daemon=True).start()


def _start_coherence_repair(self, coherence_report: dict[str, Any]):
    """
    启动衔接问题修复（后台线程）
    """
    def coherence_repair_task():
        set_runtime_log_stage("S2")
        try:
            try:
                self.safe_log("")
                self.safe_log("🔗 正在启动衔接问题修复...")
                
                total_issues = coherence_report.get('total_issues', 0)
                self.safe_log(f"  - 待修复衔接问题: {total_issues} 处")
                
                # 获取 LLM 配置
                llm_key = self.chapter_outline_llm_var.get()
                interface_format = self.loaded_config["llm_configs"][llm_key]["interface_format"]
                api_key = self.loaded_config["llm_configs"][llm_key]["api_key"]
                base_url = self.loaded_config["llm_configs"][llm_key]["base_url"]
                model_name = self.loaded_config["llm_configs"][llm_key]["model_name"]
                filepath = self.filepath_var.get().strip()

                from novel_generator.coherence_repairer import repair_coherence_issues
                
                def progress_callback(current, total, message):
                    self.safe_log(f"  - [{current}/{total}] {message}")
                
                results = repair_coherence_issues(
                    interface_format=interface_format,
                    api_key=api_key,
                    base_url=base_url,
                    llm_model=model_name,
                    filepath=filepath,
                    coherence_report=coherence_report,
                    progress_callback=progress_callback
                )
                
                # 输出结果
                self.safe_log("")
                self.safe_log("=" * 40)
                self.safe_log("🎉 衔接修复完成！")
                self.safe_log(f"  - 成功修复: {results.get('success', 0)} 对章节")
                self.safe_log(f"  - 修复失败: {results.get('failed', 0)} 对章节")
                self.safe_log("")
                self.safe_log("📝 修复后的蓝图已保存，请查看 'Chapter Blueprint' 标签页。")
                
            except (RuntimeError, ValueError, TypeError, OSError, KeyError, ConnectionError, ImportError) as e:
                self.safe_log("⚠️ 衔接修复异常堆栈：")
                self.safe_log(traceback.format_exc())
                self.safe_log(f"❌ 衔接修复失败: {e}")
        finally:
            clear_runtime_log_stage()
    
    threading.Thread(target=coherence_repair_task, daemon=True).start()


def generate_chapter_draft_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        return
    _stage_log(self, "S3", "入口已触发：单章草稿生成")

    precheck_ok, precheck_issues = _runtime_architecture_precheck(filepath)
    if not precheck_ok:
        issue_text = "\n".join(f"- {item}" for item in precheck_issues)
        _stage_log(self, "S3", "❌ 运行时架构守卫阻断：")
        for item in precheck_issues:
            self.safe_log(f"  - {item}")
        messagebox.showwarning("架构守卫阻断", f"运行时架构预检查未通过：\n{issue_text}")
        return

    def task():
        set_runtime_log_stage("S3")
        self.disable_button_safe(self.btn_generate_chapter)
        try:
            architecture_budgets = _load_architecture_context_budgets(self.loaded_config)

            interface_format = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["interface_format"]
            api_key = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["api_key"]
            base_url = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["base_url"]
            model_name = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["model_name"]
            temperature = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["temperature"]
            max_tokens = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["max_tokens"]
            timeout_val = self.loaded_config["llm_configs"][self.prompt_draft_llm_var.get()]["timeout"]


            chap_num = self.safe_get_int(self.chapter_num_var, 1)
            word_number = self.safe_get_int(self.word_number_var, 3000)
            user_guidance = self.user_guide_text.get("0.0", "end").strip()

            char_inv = self.char_inv_text.get("0.0", "end").strip() if hasattr(self, "char_inv_text") else self.characters_involved_var.get().strip()
            if hasattr(self, "characters_involved_var"):
                self.characters_involved_var.set(char_inv)
            key_items = self.key_items_var.get().strip()
            scene_loc = self.scene_location_var.get().strip()
            time_constr = self.time_constraint_var.get().strip()

            embedding_api_key = self.embedding_api_key_var.get().strip()
            embedding_url = self.embedding_url_var.get().strip()
            embedding_interface_format = self.embedding_interface_format_var.get().strip()
            embedding_model_name = self.embedding_model_name_var.get().strip()
            embedding_k = self.safe_get_int(self.embedding_retrieval_k_var, 4)

            _stage_log(self, "S3", f"生成第{chap_num}章草稿：准备生成请求提示词...")

            # 调用新添加的 build_chapter_prompt 函数构造初始提示词
            prompt_text = build_chapter_prompt(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                filepath=filepath,
                novel_number=chap_num,
                word_number=word_number,
                temperature=temperature,
                user_guidance=user_guidance,
                characters_involved=char_inv,
                key_items=key_items,
                scene_location=scene_loc,
                time_constraint=time_constr,
                embedding_api_key=embedding_api_key,
                embedding_url=embedding_url,
                embedding_interface_format=embedding_interface_format,
                embedding_model_name=embedding_model_name,
                embedding_retrieval_k=embedding_k,
                interface_format=interface_format,
                max_tokens=max_tokens,
                timeout=timeout_val,
                runtime_architecture_max_chars=architecture_budgets["chapter_prompt"],
                runtime_architecture_ignore_budget=architecture_budgets["ignore_budget"],
            )

            # 弹出可编辑提示词对话框，等待用户确认或取消
            prompt_holder: list[str | None] = [None]
            event = threading.Event()

            def create_dialog():
                dialog = ctk.CTkToplevel(self.master)
                dialog.title("当前章节请求提示词（可编辑）")
                dialog.geometry("600x400")
                text_box = ctk.CTkTextbox(dialog, wrap="word", font=("Microsoft YaHei", 12))
                text_box.pack(fill="both", expand=True, padx=10, pady=10)

                # 字数统计标签
                wordcount_label = ctk.CTkLabel(dialog, text="字数：0", font=("Microsoft YaHei", 12))
                wordcount_label.pack(side="left", padx=(10,0), pady=5)
                
                # 插入角色内容
                final_prompt = prompt_text
                role_names = [name.strip() for name in self.char_inv_text.get("0.0", "end").strip().split(',') if name.strip()]
                role_lib_path = os.path.join(filepath, "角色库")
                role_contents = []
                
                if os.path.exists(role_lib_path):
                    for root, dirs, files in os.walk(role_lib_path):
                        for file in files:
                            if file.endswith(".txt") and os.path.splitext(file)[0] in role_names:
                                file_path = os.path.join(root, file)
                                try:
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        role_contents.append(f.read().strip())  # 直接使用文件内容，不添加重复名字
                                except (OSError, UnicodeDecodeError) as e:
                                    self.safe_log(f"读取角色文件 {file} 失败: {str(e)}")
                
                if role_contents:
                    role_content_str = "\n".join(role_contents)
                    # 更精确的替换逻辑，处理不同情况下的占位符
                    placeholder_variations = [
                        "核心人物(可能未指定)：{characters_involved}",
                        "核心人物：{characters_involved}",
                        "核心人物(可能未指定):{characters_involved}",
                        "核心人物:{characters_involved}"
                    ]
                    
                    for placeholder in placeholder_variations:
                        if placeholder in final_prompt:
                            final_prompt = final_prompt.replace(
                                placeholder,
                                f"核心人物：\n{role_content_str}"
                            )
                            break
                    else:  # 如果没有找到任何已知占位符变体
                        lines = final_prompt.split('\n')
                        for i, line in enumerate(lines):
                            if "核心人物" in line and "：" in line:
                                lines[i] = f"核心人物：\n{role_content_str}"
                                break
                        final_prompt = '\n'.join(lines)

                text_box.insert("0.0", final_prompt)
                # 更新字数函数
                def update_word_count(event=None):
                    text = text_box.get("0.0", "end-1c")
                    text_length = len(text)
                    wordcount_label.configure(text=f"字数：{text_length}")

                text_box.bind("<KeyRelease>", update_word_count)
                text_box.bind("<ButtonRelease>", update_word_count)
                update_word_count()  # 初始化统计

                button_frame = ctk.CTkFrame(dialog)
                button_frame.pack(pady=10)
                def on_confirm():
                    prompt_holder[0] = text_box.get("1.0", "end").strip()
                    dialog.destroy()
                    event.set()
                def on_cancel():
                    prompt_holder[0] = None
                    dialog.destroy()
                    event.set()
                btn_confirm = ctk.CTkButton(button_frame, text="确认使用", font=("Microsoft YaHei", 12), command=on_confirm)
                btn_confirm.pack(side="left", padx=10)
                btn_cancel = ctk.CTkButton(button_frame, text="取消请求", font=("Microsoft YaHei", 12), command=on_cancel)
                btn_cancel.pack(side="left", padx=10)
                # 若用户直接关闭弹窗，则调用 on_cancel 处理
                dialog.protocol("WM_DELETE_WINDOW", on_cancel)
                dialog.grab_set()
            self.master.after(0, create_dialog)
            event.wait()  # 等待用户操作完成
            edited_prompt = prompt_holder[0]
            if edited_prompt is None:
                _stage_log(self, "S3", "❌ 用户取消了草稿生成请求。")
                return

            _stage_log(self, "S3", "开始生成章节草稿...")
            # 读取语言纯度配置
            other_params = self.loaded_config.get("other_params", {})
            language_purity_enabled = other_params.get("language_purity_enabled", True)
            auto_correct_mixed_language = other_params.get("auto_correct_mixed_language", True)
            preserve_proper_nouns = other_params.get("preserve_proper_nouns", True)
            strict_language_mode = other_params.get("strict_language_mode", False)

            from novel_generator.chapter import generate_chapter_draft
            draft_text = generate_chapter_draft(
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                filepath=filepath,
                novel_number=chap_num,
                word_number=word_number,
                temperature=temperature,
                user_guidance=user_guidance,
                characters_involved=char_inv,
                key_items=key_items,
                scene_location=scene_loc,
                time_constraint=time_constr,
                embedding_api_key=embedding_api_key,
                embedding_url=embedding_url,
                embedding_interface_format=embedding_interface_format,
                embedding_model_name=embedding_model_name,
                embedding_retrieval_k=embedding_k,
                interface_format=interface_format,
                max_tokens=max_tokens,
                timeout=timeout_val,
                custom_prompt_text=edited_prompt,  # 使用用户编辑后的提示词
                runtime_architecture_max_chars=architecture_budgets["chapter_prompt"],
                runtime_architecture_ignore_budget=architecture_budgets["ignore_budget"],
                language_purity_enabled=language_purity_enabled,
                auto_correct_mixed_language=auto_correct_mixed_language,
                preserve_proper_nouns=preserve_proper_nouns,
                strict_language_mode=strict_language_mode
            )
            if draft_text:
                _stage_log(self, "S3", f"✅ 第{chap_num}章草稿生成完成。请在左侧查看或编辑。")
                self.master.after(0, lambda: self.show_chapter_in_textbox(draft_text))
            else:
                _stage_log(self, "S3", "⚠️ 本章草稿生成失败或无内容。")
        except (RuntimeError, ValueError, TypeError, OSError, KeyError, ConnectionError, ImportError):
            self.handle_exception("生成章节草稿时出错")
        finally:
            self.enable_button_safe(self.btn_generate_chapter)
            clear_runtime_log_stage()
    threading.Thread(target=task, daemon=True).start()

def finalize_chapter_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        return

    def task():
        set_runtime_log_stage("S3")
        if not messagebox.askyesno("确认", "确定要定稿当前章节吗？"):
            self.enable_button_safe(self.btn_finalize_chapter)
            return

        self.disable_button_safe(self.btn_finalize_chapter)
        try:

            interface_format = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["interface_format"]
            api_key = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["api_key"]
            base_url = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["base_url"]
            model_name = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["model_name"]
            temperature = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["temperature"]
            max_tokens = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["max_tokens"]
            timeout_val = self.loaded_config["llm_configs"][self.final_chapter_llm_var.get()]["timeout"]


            embedding_api_key = self.embedding_api_key_var.get().strip()
            embedding_url = self.embedding_url_var.get().strip()
            embedding_interface_format = self.embedding_interface_format_var.get().strip()
            embedding_model_name = self.embedding_model_name_var.get().strip()

            chap_num = self.safe_get_int(self.chapter_num_var, 1)
            word_number = self.safe_get_int(self.word_number_var, 3000)

            self.safe_log(f"开始定稿第{chap_num}章...")

            chapters_dir = os.path.join(filepath, "chapters")
            os.makedirs(chapters_dir, exist_ok=True)
            chapter_file = os.path.join(chapters_dir, f"chapter_{chap_num}.txt")

            edited_text = self.chapter_result.get("0.0", "end").strip()

            if len(edited_text) < 0.7 * word_number:
                ask = messagebox.askyesno("字数不足", f"当前章节字数 ({len(edited_text)}) 低于目标字数({word_number})的70%，是否要尝试扩写？")
                if ask:
                    self.safe_log("正在扩写章节内容...")
                    enriched = enrich_chapter_text(
                        chapter_text=edited_text,
                        word_number=word_number,
                        api_key=api_key,
                        base_url=base_url,
                        model_name=model_name,
                        temperature=temperature,
                        interface_format=interface_format,
                        max_tokens=max_tokens,
                        timeout=timeout_val
                    )
                    edited_text = enriched
                    self.master.after(0, lambda: self.chapter_result.delete("0.0", "end"))
                    self.master.after(0, lambda: self.chapter_result.insert("0.0", edited_text))
            clear_file_content(chapter_file)
            save_string_to_txt(edited_text, chapter_file)

            finalize_chapter(
                novel_number=chap_num,
                word_number=word_number,
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                temperature=temperature,
                filepath=filepath,
                embedding_api_key=embedding_api_key,
                embedding_url=embedding_url,
                embedding_interface_format=embedding_interface_format,
                embedding_model_name=embedding_model_name,
                interface_format=interface_format,
                max_tokens=max_tokens,
                timeout=timeout_val
            )
            self.safe_log(f"✅ 第{chap_num}章定稿完成（已更新前文摘要、角色状态、向量库）。")

            final_text = read_file(chapter_file)
            self.master.after(0, lambda: self.show_chapter_in_textbox(final_text))
        except (RuntimeError, ValueError, TypeError, OSError, KeyError, ConnectionError, ImportError):
            self.handle_exception("定稿章节时出错")
        finally:
            self.enable_button_safe(self.btn_finalize_chapter)
            clear_runtime_log_stage()
    threading.Thread(target=task, daemon=True).start()

def do_consistency_check(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        return

    precheck_ok, precheck_issues = _runtime_architecture_precheck(filepath)
    if not precheck_ok:
        issue_text = "\n".join(f"- {item}" for item in precheck_issues)
        _stage_log(self, "S3", "❌ 运行时架构守卫阻断：")
        for item in precheck_issues:
            self.safe_log(f"  - {item}")
        messagebox.showwarning("架构守卫阻断", f"运行时架构预检查未通过：\n{issue_text}")
        return

    def task():
        set_runtime_log_stage("S3")
        self.disable_button_safe(self.btn_check_consistency)
        try:
            architecture_budgets = _load_architecture_context_budgets(self.loaded_config)
            consistency_cfg = _require_llm_config(self.loaded_config, self.consistency_review_llm_var.get())
            interface_format = consistency_cfg.get("interface_format", "OpenAI")
            api_key = consistency_cfg.get("api_key", "")
            base_url = consistency_cfg.get("base_url", "")
            model_name = consistency_cfg.get("model_name", "")
            temperature = consistency_cfg.get("temperature", 0.2)
            max_tokens = consistency_cfg.get("max_tokens", 8192)
            timeout = consistency_cfg.get("timeout", 600)


            chap_num = self.safe_get_int(self.chapter_num_var, 1)
            chap_file = os.path.join(filepath, "chapters", f"chapter_{chap_num}.txt")
            chapter_text = read_file(chap_file)

            if not chapter_text.strip():
                self.safe_log("⚠️ 当前章节文件为空或不存在，无法审校。")
                return

            self.safe_log("开始一致性审校...")
            review_character_state_text, review_summary_text, review_plot_arcs_text = build_ledger_backed_review_inputs(
                filepath=filepath,
                chapter_number=chap_num,
            )
            result = check_consistency(
                novel_setting=_load_runtime_architecture_text(
                    filepath,
                    max_chars=architecture_budgets["consistency"],
                    ignore_budget=architecture_budgets["ignore_budget"],
                ),
                character_state=review_character_state_text,
                global_summary=review_summary_text,
                chapter_text=chapter_text,
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
                temperature=temperature,
                interface_format=interface_format,
                max_tokens=max_tokens,
                timeout=timeout,
                plot_arcs=review_plot_arcs_text,
            )
            self.safe_log("审校结果：")
            self.safe_log(result)
        except (RuntimeError, ValueError, TypeError, OSError, KeyError, ConnectionError, ImportError):
            self.handle_exception("审校时出错")
        finally:
            self.enable_button_safe(self.btn_check_consistency)
            clear_runtime_log_stage()
    threading.Thread(target=task, daemon=True).start()
def generate_batch_ui(self):

    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        return
    _stage_log(self, "S3", "入口已触发：批量章节生成")

    precheck_ok, precheck_issues = _runtime_architecture_precheck(filepath)
    if not precheck_ok:
        issue_text = "\n".join(f"- {item}" for item in precheck_issues)
        _stage_log(self, "S3", "❌ 运行时架构守卫阻断：")
        for item in precheck_issues:
            self.safe_log(f"  - {item}")
        messagebox.showwarning("架构守卫阻断", f"运行时架构预检查未通过：\n{issue_text}")
        return

    # PenBo 优化界面，使用customtkinter进行批量生成章节界面

    def open_batch_dialog():
        dialog = ctk.CTkToplevel(self.master)
        dialog.title("批量生成章节")

        num = _detect_next_chapter_number(filepath)

        # 🆕 加载保存的设置
        saved_settings = _load_batch_settings(filepath, self.safe_log)
            
        dialog.geometry("460x300")
        dialog.resizable(False, False)
        
        # 创建网格布局
        dialog.grid_columnconfigure(0, weight=0)
        dialog.grid_columnconfigure(1, weight=1)
        dialog.grid_columnconfigure(2, weight=0)
        dialog.grid_columnconfigure(3, weight=1)
        
        # 起始章节
        ctk.CTkLabel(dialog, text="起始章节:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        entry_start = ctk.CTkEntry(dialog)
        entry_start.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        entry_start.insert(0, str(num))
        
        # 结束章节
        ctk.CTkLabel(dialog, text="结束章节:").grid(row=0, column=2, padx=10, pady=10, sticky="w")
        entry_end = ctk.CTkEntry(dialog)
        entry_end.grid(row=0, column=3, padx=10, pady=10, sticky="ew")
        
        # 期望字数 - 使用保存的设置
        ctk.CTkLabel(dialog, text="期望字数:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        entry_word = ctk.CTkEntry(dialog)
        entry_word.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        entry_word.insert(0, str(saved_settings.get("word_count", 5000)))
        
        # 最低字数 - 使用保存的设置
        ctk.CTkLabel(dialog, text="最低字数:").grid(row=1, column=2, padx=10, pady=10, sticky="w")
        entry_min = ctk.CTkEntry(dialog)
        entry_min.grid(row=1, column=3, padx=10, pady=10, sticky="ew")
        entry_min.insert(0, str(saved_settings.get("min_word_count", 3500)))

        # 自动扩写选项 - 使用保存的设置
        auto_enrich_bool = ctk.BooleanVar(value=_safe_bool(saved_settings.get("auto_enrich"), default=True))
        auto_enrich_bool_ck = ctk.CTkCheckBox(dialog, text="低于最低字数时自动扩写", variable=auto_enrich_bool)
        auto_enrich_bool_ck.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        # 智能优化系统选项 - 使用保存的设置
        optimization_bool = ctk.BooleanVar(value=_safe_bool(saved_settings.get("optimization"), default=True))
        optimization_bool_ck = ctk.CTkCheckBox(dialog, text="启用智能优化系统", variable=optimization_bool)
        optimization_bool_ck.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        result: dict[str, Any] = {
            "start": None,
            "end": None,
            "word": None,
            "min": None,
            "auto_enrich": None,
            "optimization": None,
            "close": False,
        }

        def _resolve_range_inputs() -> tuple[int, int] | None:
            try:
                start_val, end_val = _parse_batch_chapter_range(entry_start.get(), entry_end.get())
            except ValueError as parse_error:
                messagebox.showwarning("警告", str(parse_error))
                return None

            if start_val <= 0 or end_val <= 0:
                messagebox.showwarning("警告", "章节号必须大于0。")
                return None
            if start_val > end_val:
                messagebox.showwarning("警告", "起始章节不能大于结束章节。")
                return None
            return start_val, end_val

        def _resolve_word_inputs() -> tuple[int, int] | None:
            if not entry_word.get() or not entry_min.get():
                messagebox.showwarning("警告", "请填写期望字数和最低字数。")
                return None
            try:
                word_count = int(entry_word.get())
                min_word_count = int(entry_min.get())
            except ValueError:
                messagebox.showwarning("警告", "期望字数和最低字数必须是整数。")
                return None
            if word_count <= 0 or min_word_count <= 0:
                messagebox.showwarning("警告", "字数必须大于0。")
                return None
            return word_count, min_word_count

        def on_preflight_scan() -> None:
            range_values = _resolve_range_inputs()
            if not range_values:
                return
            start_val, end_val = range_values
            _stage_log(self, "S3", f"🧪 启动预检风险扫描（仅扫描，不生成）：第{start_val}-{end_val}章")

            def _scan_task() -> None:
                set_runtime_log_stage("S3")
                try:
                    _run_batch_precheck(
                        self,
                        filepath=filepath,
                        start_chapter=start_val,
                        end_chapter=end_val,
                        deep_scan=True,
                        auto_continue_on_warning=True,
                        interactive=False,
                    )
                    _stage_log(self, "S3", "✅ 预检风险扫描完成（未启动批量生成）")
                finally:
                    clear_runtime_log_stage()

            threading.Thread(target=_scan_task, daemon=True).start()

        def on_confirm():
            nonlocal result
            if not entry_start.get() or not entry_word.get() or not entry_min.get():
                messagebox.showwarning("警告", "请填写完整信息。")
                return

            range_values = _resolve_range_inputs()
            if not range_values:
                return
            word_values = _resolve_word_inputs()
            if not word_values:
                return

            start_val, end_val = range_values
            word_count, min_word_count = word_values
            
            # 🆕 保存设置供下次使用
            _save_batch_settings(
                filepath,
                {
                    "word_count": word_count,
                    "min_word_count": min_word_count,
                    "auto_enrich": auto_enrich_bool.get(),
                    "optimization": optimization_bool.get(),
                },
                self.safe_log,
            )

            result = {
                "start": str(start_val),
                "end": str(end_val),
                "word": str(word_count),
                "min": str(min_word_count),
                "auto_enrich": auto_enrich_bool.get(),
                "optimization": optimization_bool.get(),
                "close": False
            }
            dialog.destroy()

        def on_cancel():
            nonlocal result
            result["close"] = True
            dialog.destroy()
            
        # 按钮框架
        button_frame = ctk.CTkFrame(dialog)
        button_frame.grid(row=4, column=0, columnspan=4, padx=10, pady=10, sticky="ew")
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        button_frame.grid_columnconfigure(2, weight=1)
        
        ctk.CTkButton(button_frame, text="预检扫描", command=on_preflight_scan).grid(
            row=0, column=0, padx=6, pady=10, sticky="e"
        )
        ctk.CTkButton(button_frame, text="确认生成", command=on_confirm).grid(
            row=0, column=1, padx=6, pady=10, sticky="ew"
        )
        ctk.CTkButton(button_frame, text="取消", command=on_cancel).grid(row=0, column=2, padx=6, pady=10, sticky="w")
        
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        if self.master and self.master.winfo_exists():
            dialog.transient(self.master)
        try:
            # 部分环境下窗口尚未可见时直接 grab_set 会抛错
            dialog.update_idletasks()
            dialog.wait_visibility()
            dialog.grab_set()
        except tk.TclError as e:
            self.safe_log(f"⚠️ 批量窗口未能设置模态抓取，已降级为非模态: {e}")
        dialog.wait_window(dialog)
        return result
    
    def generate_chapter_batch(self ,i ,word, min, auto_enrich, optimization=True):
        draft_cfg = _extract_llm_runtime_settings(
            _require_llm_config(self.loaded_config, self.prompt_draft_llm_var.get())
        )
        draft_interface_format = draft_cfg["interface_format"]
        draft_api_key = draft_cfg["api_key"]
        draft_base_url = draft_cfg["base_url"]
        draft_model_name = draft_cfg["model_name"]
        draft_temperature = draft_cfg["temperature"]
        draft_max_tokens = draft_cfg["max_tokens"]
        draft_timeout = draft_cfg["timeout"]

        finalize_cfg = _extract_llm_runtime_settings(
            _require_llm_config(self.loaded_config, self.final_chapter_llm_var.get())
        )
        finalize_interface_format = finalize_cfg["interface_format"]
        finalize_api_key = finalize_cfg["api_key"]
        finalize_base_url = finalize_cfg["base_url"]
        finalize_model_name = finalize_cfg["model_name"]
        finalize_temperature = finalize_cfg["temperature"]
        finalize_max_tokens = finalize_cfg["max_tokens"]
        finalize_timeout = finalize_cfg["timeout"]

        user_guidance = self.user_guide_text.get("0.0", "end").strip()  

        char_inv = self.char_inv_text.get("0.0", "end").strip() if hasattr(self, "char_inv_text") else self.characters_involved_var.get().strip()
        if hasattr(self, "characters_involved_var"):
            self.characters_involved_var.set(char_inv)
        key_items = self.key_items_var.get().strip()
        scene_loc = self.scene_location_var.get().strip()
        time_constr = self.time_constraint_var.get().strip()

        embedding_api_key = self.embedding_api_key_var.get().strip()
        embedding_url = self.embedding_url_var.get().strip()
        embedding_interface_format = self.embedding_interface_format_var.get().strip()
        embedding_model_name = self.embedding_model_name_var.get().strip()
        embedding_k = self.safe_get_int(self.embedding_retrieval_k_var, 4)
        architecture_budgets = _load_architecture_context_budgets(self.loaded_config)

        prompt_text = build_chapter_prompt(
            api_key=draft_api_key,
            base_url=draft_base_url,
            model_name=draft_model_name,
            filepath=self.filepath_var.get().strip(),
            novel_number=i,
            word_number=word,
            min_word_number=int(min),
            temperature=draft_temperature,
            user_guidance=user_guidance,
            characters_involved=char_inv,
            key_items=key_items,
            scene_location=scene_loc,
            time_constraint=time_constr,
            embedding_api_key=embedding_api_key,
            embedding_url=embedding_url,
            embedding_interface_format=embedding_interface_format,
            embedding_model_name=embedding_model_name,
            embedding_retrieval_k=embedding_k,
            interface_format=draft_interface_format,
            max_tokens=draft_max_tokens,
            timeout=draft_timeout,
            runtime_architecture_max_chars=architecture_budgets["chapter_prompt"],
            runtime_architecture_ignore_budget=architecture_budgets["ignore_budget"],
        )
        role_names = [name.strip() for name in self.char_inv_text.get("0.0", "end").split("\n")]
        role_lib_path = os.path.join(self.filepath_var.get().strip(), "角色库")
        final_prompt = _inject_role_library_profiles(
            prompt_text=prompt_text,
            role_names=role_names,
            role_lib_path=role_lib_path,
            log_func=self.safe_log,
        )
        # 读取语言纯度配置
        other_params = self.loaded_config.get("other_params", {})
        language_purity_enabled = _safe_bool(other_params.get("language_purity_enabled"), default=True)
        auto_correct_mixed_language = _safe_bool(other_params.get("auto_correct_mixed_language"), default=True)
        preserve_proper_nouns = _safe_bool(other_params.get("preserve_proper_nouns"), default=True)
        strict_language_mode = _safe_bool(other_params.get("strict_language_mode"), default=False)
        enable_llm_consistency_check = _safe_bool(
            other_params.get("enable_llm_consistency_check"),
            default=True,
        )
        consistency_hard_gate = _safe_bool(other_params.get("consistency_hard_gate"), default=True)
        enable_timeline_check = _safe_bool(other_params.get("enable_timeline_check"), default=True)
        timeline_hard_gate = _safe_bool(other_params.get("timeline_hard_gate"), default=True)
        stop_batch_on_hard_gate = _safe_bool(other_params.get("stop_batch_on_hard_gate"), default=True)
        enable_chapter_contract_guard = _safe_bool(
            other_params.get("enable_chapter_contract_guard"),
            default=True,
        )
        chapter_contract_hard_gate = _safe_bool(
            other_params.get("chapter_contract_hard_gate"),
            default=True,
        )
        enable_state_ledger_writeback = _safe_bool(
            other_params.get("enable_state_ledger_writeback"),
            default=True,
        )
        state_ledger_hard_gate = _safe_bool(
            other_params.get("state_ledger_hard_gate"),
            default=True,
        )
        enable_next_opening_anchor_guard = _safe_bool(
            other_params.get("enable_next_opening_anchor_guard"),
            default=True,
        )
        next_opening_anchor_hard_gate = _safe_bool(
            other_params.get("next_opening_anchor_hard_gate"),
            default=True,
        )
        enable_output_integrity_guard = _safe_bool(
            other_params.get("enable_output_integrity_guard"),
            default=True,
        )
        output_integrity_hard_gate = _safe_bool(
            other_params.get("output_integrity_hard_gate"),
            default=True,
        )
        filepath = self.filepath_var.get().strip()
        consistency_review_llm_name = self.consistency_review_llm_var.get()
        try:
            consistency_cfg = _require_llm_config(self.loaded_config, consistency_review_llm_name)
        except KeyError:
            consistency_cfg = {}
        consistency_architecture_text = _load_runtime_architecture_text(
            filepath,
            max_chars=architecture_budgets["consistency"],
            ignore_budget=architecture_budgets["ignore_budget"],
        )
        consistency_character_state_text, consistency_summary_text, consistency_plot_arcs_text = build_ledger_backed_review_inputs(
            filepath=filepath,
            chapter_number=i,
        )
        consistency_review_cache: dict[str, dict[str, Any]] = {}

        chapter_contract: dict[str, Any] = {}
        if enable_chapter_contract_guard:
            try:
                from chapter_directory_parser import load_chapter_info

                chapter_info_for_contract = load_chapter_info(filepath, i)
                chapter_contract = build_chapter_contract(
                    chapter_info_for_contract if isinstance(chapter_info_for_contract, dict) else {},
                    characters_involved=char_inv,
                    key_items=key_items,
                    scene_location=scene_loc,
                    time_constraint=time_constr,
                    user_guidance=user_guidance,
                )
            except (RuntimeError, ValueError, TypeError, OSError, ImportError) as contract_error:
                self.safe_log(f"⚠️ 第{i}章章节契约初始化失败: {contract_error}")
                chapter_contract = {}

        previous_drift_record: dict[str, Any] = {}
        if i > 1 and enable_next_opening_anchor_guard:
            previous_drift_record = _read_drift_state_ledger_record(filepath, i - 1)

        chapter_title_for_output = ""
        try:
            from chapter_directory_parser import load_chapter_info
            chapter_info_for_title = load_chapter_info(filepath, i)
            if isinstance(chapter_info_for_title, dict):
                chapter_title_for_output = str(chapter_info_for_title.get("chapter_title", "")).strip()
        except (RuntimeError, ValueError, TypeError, OSError, ImportError):
            chapter_title_for_output = ""

        def _set_chapter_stage(stage_name: str, model_name: str = "", interface_fmt: str = "") -> None:
            set_llm_log_context(
                stage=stage_name,
                model_name=model_name or None,
                interface_format=interface_fmt or None,
            )

        def _run_cached_llm_consistency_review(
            chapter_text_to_check: str,
            *,
            stage_name: str,
            item_limit: int,
        ) -> tuple[str, bool, list[str]]:
            text = (chapter_text_to_check or "").strip()
            if not text:
                return "", False, []

            text_hash = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()
            cache_entry = consistency_review_cache.get(text_hash)
            if isinstance(cache_entry, dict):
                cached_review = str(cache_entry.get("review_text", ""))
                cached_conflict = bool(cache_entry.get("has_conflict", False))
                cached_items = cache_entry.get("items", [])
                if not isinstance(cached_items, list):
                    cached_items = []
                return cached_review, cached_conflict, [str(x) for x in cached_items if str(x).strip()][:item_limit]

            _set_chapter_stage(
                stage_name,
                model_name=consistency_cfg.get("model_name", draft_model_name),
                interface_fmt=consistency_cfg.get("interface_format", draft_interface_format),
            )
            review_text = check_consistency(
                novel_setting=consistency_architecture_text,
                character_state=consistency_character_state_text,
                global_summary=consistency_summary_text,
                chapter_text=text,
                api_key=consistency_cfg.get("api_key", draft_api_key),
                base_url=consistency_cfg.get("base_url", draft_base_url),
                model_name=consistency_cfg.get("model_name", draft_model_name),
                temperature=consistency_cfg.get("temperature", 0.2),
                interface_format=consistency_cfg.get("interface_format", draft_interface_format),
                max_tokens=consistency_cfg.get("max_tokens", draft_max_tokens),
                timeout=consistency_cfg.get("timeout", draft_timeout),
                plot_arcs=consistency_plot_arcs_text,
            )
            has_conflict = has_obvious_conflict(review_text)
            items = extract_conflict_items(review_text, limit=max(item_limit, 1))
            consistency_review_cache[text_hash] = {
                "review_text": review_text,
                "has_conflict": has_conflict,
                "items": items,
            }
            return review_text, has_conflict, items[:item_limit]

        def _auto_fix_term_consistency(chapter_text: str, issues: list[str]) -> str:
            """针对术语冲突做一次确定性术语统一与高风险词降级。"""
            if not chapter_text:
                return chapter_text
            issue_text = "；".join([str(x) for x in (issues or [])])
            trigger_markers = (
                "命名不一致",
                "系统命名",
                "金手指",
                "术语冲突",
                "世界观语言纯度",
                "双轨叙事",
                "LLM深度一致性冲突",
            )
            if not any(k in issue_text for k in trigger_markers):
                return chapter_text

            def _is_valid_system_term(term: str) -> bool:
                if not term or "系统" not in term:
                    return False
                t = term.strip()
                if len(t) < 2 or len(t) > 10:
                    return False
                bad = ("点击", "直接", "构建", "循环", "经脉", "灵气", "一个", "小型", "大型")
                return not any(x in t for x in bad)

            fixed = chapter_text
            replacement_stats: list[str] = []

            # 抽取章节中所有“X系统”候选名，统一为单一术语
            found = re.findall(
                r"(?<![A-Za-z0-9\u4e00-\u9fa5])([A-Za-z0-9\u4e00-\u9fa5·\-]{2,10}系统)(?![A-Za-z0-9\u4e00-\u9fa5])",
                fixed,
            )
            ordered_terms = []
            for t in found:
                if t not in ordered_terms and _is_valid_system_term(t):
                    ordered_terms.append(t)
            if len(ordered_terms) > 1:
                canonical = None
                for term in ordered_terms:
                    if term and term in consistency_architecture_text:
                        canonical = term
                        break
                if not canonical:
                    canonical = ordered_terms[0]

                for term in ordered_terms:
                    if term == canonical:
                        continue
                    fixed = re.sub(re.escape(term), canonical, fixed)
                replacement_stats.append(f"系统命名统一->{canonical}")

            # 术语冲突硬替换：统一到本项目世界观词汇
            strict_term_replacements = [
                (r"Listening Wind Cicada", "听风蝉"),
                (r"精神力", "心神"),
                (r"灵气", "灵机"),
                (r"外挂", "秘契"),
                (r"(?<!天书)系统界面", "天书残页界面"),
                (r"(?<!天书)系统", "天书残页"),
            ]
            strict_replace_count = 0
            for pattern, repl in strict_term_replacements:
                fixed, count = re.subn(pattern, repl, fixed)
                strict_replace_count += int(count)
            if strict_replace_count > 0:
                replacement_stats.append(f"术语替换{strict_replace_count}处")

            # 高层机密降级：开篇阶段避免直接透出终局势力名
            if any(k in issue_text for k in ("王朝线", "过早", "卷1-2", "命轨司", "道庭")):
                reveal_downgrade = [
                    (r"道庭", "上层势力"),
                    (r"命轨司", "秘司"),
                ]
                reveal_count = 0
                for pattern, repl in reveal_downgrade:
                    fixed, count = re.subn(pattern, repl, fixed)
                    reveal_count += int(count)
                if reveal_count > 0:
                    replacement_stats.append(f"机密降级{reveal_count}处")

            if fixed != chapter_text and replacement_stats:
                self.safe_log(f"🔧 第{i}章术语一致性自动修复: {'；'.join(replacement_stats)}")
            return fixed

        def _repair_llm_consistency_conflicts(chapter_text: str) -> str:
            """基于LLM一致性审校报告做一次强制对齐重写（不降标准）。"""
            try:
                def _extract_focus_lines(src: str):
                    keys = ("主角", "血脉", "天书", "器灵", "境界", "炼气", "变数", "三轨", "九术", "命轨")
                    lines = [ln.strip() for ln in (src or "").splitlines() if ln.strip()]
                    picked = [ln for ln in lines if any(k in ln for k in keys)]
                    return "\n".join(picked[:40]) if picked else (src or "")[:1500]

                focus_constraints = _extract_focus_lines(consistency_architecture_text)
                repair_character_state_text, repair_summary_text, _ = build_ledger_backed_review_inputs(
                    filepath=filepath,
                    chapter_number=i,
                )
                current_text = chapter_text
                for round_idx in range(3):
                    _, has_conflict, items = _run_cached_llm_consistency_review(
                        current_text,
                        stage_name="hard_gate_consistency_review",
                        item_limit=8,
                    )
                    if not has_conflict:
                        return current_text

                    if not items:
                        return current_text

                    repair_prompt = (
                        "你是资深仙侠编辑。请做【一致性强制对齐修复】。\n\n"
                        "【强约束】\n"
                        "1) 只修复冲突，不改本章核心事件结论。\n"
                        "2) 主角修为/境界必须与设定和已发生剧情一致，不得越阶漂移。\n"
                        "3) 仅允许使用本书已存在角色，不得引入无关姓名或跨书人设。\n"
                        "4) 金手指/器灵/术语命名必须与本书设定一致（三轨九术、天书残页等）。\n"
                        "5) 外轨旁白禁止科技UI词（检测/校正/程序/面板/Bug等）。\n\n"
                        "6) 若当前卷次偏前期，禁止直接暴露终局势力名（如“道庭/命轨司”），需降级为地方势力代称。\n\n"
                        f"【本轮冲突清单】\n- " + "\n- ".join(items) + "\n\n"
                        "【重点设定约束（摘录）】\n" + focus_constraints + "\n\n"
                        "【角色状态】\n" + repair_character_state_text[:2200] + "\n\n"
                        "【前文摘要】\n" + repair_summary_text[:2200] + "\n\n"
                        "【待修复章节】\n" + current_text[:12000] + "\n\n"
                        "请直接输出修复后的完整章节正文，不要解释。"
                    )
                    _set_chapter_stage(
                        "hard_gate_consistency_rewrite",
                        model_name=finalize_model_name,
                        interface_fmt=finalize_interface_format,
                    )
                    fixed = invoke_text_generation(
                        repair_prompt,
                        interface_format=finalize_interface_format,
                        base_url=finalize_base_url,
                        model_name=finalize_model_name,
                        api_key=finalize_api_key,
                        temperature=0.3,
                        max_tokens=finalize_max_tokens,
                        timeout=finalize_timeout,
                    )
                    if isinstance(fixed, str):
                        fixed = fixed.strip()
                    if fixed and len(fixed) >= int(len(current_text) * 0.7):
                        current_text = fixed
                        self.safe_log(f"🔧 第{i}章一致性冲突定向修复完成(轮次{round_idx + 1})")
                    else:
                        break
                return current_text
            except (RuntimeError, ValueError, TypeError, OSError, ImportError) as e:
                self.safe_log(f"⚠️ 第{i}章一致性定向修复失败: {e}")
            return chapter_text

        def _collect_hard_gate_issues(chapter_text: str):
            issues = []

            # 规则一致性冲突
            try:
                if consistency_hard_gate:
                    from novel_generator.consistency_checker import get_consistency_checker
                    checker = get_consistency_checker(filepath)
                    conflicts = checker.check_consistency(chapter_text, i)
                    high_conflicts = [c for c in conflicts if c.get("severity") == "high"]
                    if high_conflicts:
                        issues.append(f"规则一致性冲突: {high_conflicts[0].get('message', '')}")
            except (RuntimeError, ValueError, TypeError, OSError, ImportError) as e:
                self.safe_log(f"⚠️ 规则一致性守卫检查异常: {e}")

            # 时间线冲突
            try:
                if enable_timeline_check and timeline_hard_gate:
                    from novel_generator.timeline_manager import TimelineManager
                    timeline_manager = TimelineManager(filepath)
                    timeline_conflicts = timeline_manager.check_timeline_consistency(chapter_text, i)
                    high_timeline = [c for c in timeline_conflicts if c.get("severity") == "high"]
                    if high_timeline:
                        issues.append(f"时间线冲突: {high_timeline[0].get('message', '')}")
            except (RuntimeError, ValueError, TypeError, OSError, ImportError) as e:
                self.safe_log(f"⚠️ 时间线守卫检查异常: {e}")

            # LLM深度一致性冲突
            try:
                if enable_llm_consistency_check and consistency_hard_gate:
                    _, has_conflict, items = _run_cached_llm_consistency_review(
                        chapter_text,
                        stage_name="hard_gate_consistency_gate",
                        item_limit=2,
                    )
                    if has_conflict:
                        if items:
                            issues.append(f"LLM深度一致性冲突: {'；'.join(items)}")
                        else:
                            self.safe_log("ℹ️ LLM一致性审校返回建议性风险，未达到硬阻断标准")
            except (RuntimeError, ValueError, TypeError, OSError, ImportError) as e:
                self.safe_log(f"⚠️ LLM一致性守卫检查异常: {e}")

            # 章节契约漂移（基于蓝图锚点的结构化守卫）
            try:
                if enable_chapter_contract_guard and chapter_contract:
                    contract_issues = detect_chapter_contract_drift(
                        chapter_text,
                        chapter_contract,
                        max_issues=3,
                    )
                    if contract_issues:
                        if chapter_contract_hard_gate:
                            issues.extend(contract_issues)
                        else:
                            self.safe_log("⚠️ 章节契约漂移预警（未开启硬阻断）: " + "；".join(contract_issues[:2]))
            except (RuntimeError, ValueError, TypeError, OSError, ImportError) as e:
                self.safe_log(f"⚠️ 章节契约守卫检查异常: {e}")

            # 下一章开篇锚点衔接检查（强制防首段漂移）
            try:
                if enable_next_opening_anchor_guard:
                    opening_anchor_issues = _collect_opening_anchor_issues(
                        chapter_num=i,
                        chapter_text=chapter_text,
                        chapter_contract=chapter_contract,
                        previous_ledger_record=previous_drift_record,
                        max_issues=3,
                    )
                    if opening_anchor_issues:
                        if next_opening_anchor_hard_gate:
                            issues.extend(opening_anchor_issues)
                        else:
                            self.safe_log(
                                "⚠️ 开篇锚点漂移预警（未开启硬阻断）: "
                                + "；".join(opening_anchor_issues[:2])
                            )
            except (RuntimeError, ValueError, TypeError, OSError, ImportError) as e:
                self.safe_log(f"⚠️ 开篇锚点守卫检查异常: {e}")

            # 输出文本完整性检查（防 JSON/编辑批注/标题丢失）
            if enable_output_integrity_guard:
                sanitized_preview = _clean_generated_chapter_text(chapter_text)
                sanitized_preview = _ensure_chapter_title_line(
                    sanitized_preview,
                    i,
                    chapter_title_for_output,
                )
                integrity_issues = _collect_chapter_text_integrity_issues(
                    sanitized_preview,
                    i,
                )
                if integrity_issues:
                    if output_integrity_hard_gate:
                        issues.extend([f"输出结构冲突: {item}" for item in integrity_issues[:3]])
                    else:
                        self.safe_log(
                            "⚠️ 输出结构预警（未开启硬阻断）: " + "；".join(integrity_issues[:2])
                        )

            return issues

        def _repair_chapter_contract_drift(chapter_text: str, contract_issues: list[str]) -> str:
            if not chapter_text or not chapter_contract:
                return chapter_text
            try:
                contract_lines: list[str] = []
                required = (
                    chapter_contract.get("required_terms", {})
                    if isinstance(chapter_contract.get("required_terms"), dict)
                    else {}
                )
                for key, label in (("characters", "人物锚点"), ("key_items", "关键要素"), ("locations", "场景锚点")):
                    terms = required.get(key, [])
                    if isinstance(terms, list) and terms:
                        contract_lines.append(f"- {label}: {'、'.join(str(x) for x in terms[:4])}")
                forbidden_terms = chapter_contract.get("forbidden_terms", [])
                if isinstance(forbidden_terms, list) and forbidden_terms:
                    contract_lines.append(f"- 禁止要素: {'、'.join(str(x) for x in forbidden_terms[:6])}")

                if not contract_lines:
                    return chapter_text

                repair_prompt = (
                    "你是长篇连载小说主编。请执行【章节契约对齐修复】。\n\n"
                    "【修复原则】\n"
                    "1) 只修复漂移问题，不改变本章核心事件结论。\n"
                    "2) 优先补齐契约缺失的人物/关键物件/场景锚点。\n"
                    "3) 禁止出现契约明确禁止的要素或词汇。\n"
                    "4) 不要删掉有效情节，保留原有文风与张力。\n\n"
                    f"【命中问题】\n- " + "\n- ".join(contract_issues[:4]) + "\n\n"
                    "【章节契约】\n" + "\n".join(contract_lines) + "\n\n"
                    "【待修复正文】\n" + chapter_text[:12000] + "\n\n"
                    "请直接输出修复后的完整章节正文，不要解释。"
                )
                _set_chapter_stage(
                    "hard_gate_contract_rewrite",
                    model_name=finalize_model_name,
                    interface_fmt=finalize_interface_format,
                )
                fixed = invoke_text_generation(
                    repair_prompt,
                    interface_format=finalize_interface_format,
                    base_url=finalize_base_url,
                    model_name=finalize_model_name,
                    api_key=finalize_api_key,
                    temperature=0.25,
                    max_tokens=finalize_max_tokens,
                    timeout=finalize_timeout,
                )
                if isinstance(fixed, str):
                    fixed = fixed.strip()
                if fixed and len(fixed) >= int(len(chapter_text) * 0.7):
                    self.safe_log(f"🔧 第{i}章章节契约定向修复完成")
                    return fixed
            except (RuntimeError, ValueError, TypeError, OSError, ImportError) as contract_fix_error:
                self.safe_log(f"⚠️ 第{i}章章节契约修复失败: {contract_fix_error}")
            return chapter_text

        def _repair_chapter_contract_paragraphs(chapter_text: str) -> tuple[str, bool]:
            if not chapter_text or not chapter_contract:
                return chapter_text, False

            paragraph_issues = detect_paragraph_contract_drift(
                chapter_text,
                chapter_contract,
                max_paragraph_issues=3,
                opening_window=2,
            )
            if not paragraph_issues:
                return chapter_text, False

            paragraphs = split_chapter_paragraphs(chapter_text)
            if not paragraphs:
                return chapter_text, False

            required = (
                chapter_contract.get("required_terms", {})
                if isinstance(chapter_contract.get("required_terms"), dict)
                else {}
            )
            contract_lines: list[str] = []
            for key, label in (("characters", "人物锚点"), ("key_items", "关键要素"), ("locations", "场景锚点")):
                terms = required.get(key, [])
                if isinstance(terms, list) and terms:
                    contract_lines.append(f"- {label}: {'、'.join(str(x) for x in terms[:4])}")
            forbidden_terms = chapter_contract.get("forbidden_terms", [])
            if isinstance(forbidden_terms, list) and forbidden_terms:
                contract_lines.append(f"- 禁止要素: {'、'.join(str(x) for x in forbidden_terms[:6])}")

            if not contract_lines:
                return chapter_text, False

            max_rewrite = builtins.min(2, len(paragraph_issues))
            rewritten = 0
            for issue in paragraph_issues[:max_rewrite]:
                idx = _safe_int(issue.get("paragraph_index"))
                if idx is None or idx < 0 or idx >= len(paragraphs):
                    continue
                para_issues = issue.get("issues", [])
                issue_lines = [str(x).strip() for x in para_issues if str(x).strip()] if isinstance(para_issues, list) else []
                if not issue_lines:
                    continue
                source_paragraph = paragraphs[idx]
                repair_prompt = (
                    "你是长篇连载小说主编。请仅重写指定段落，修复契约漂移。\n\n"
                    "【硬规则】\n"
                    "1) 只能输出重写后的这一个段落，不要输出整章。\n"
                    "2) 不能改变本段承载的核心事件。\n"
                    "3) 必须满足章节契约锚点，且禁止要素不得出现。\n\n"
                    f"【该段问题】\n- " + "\n- ".join(issue_lines[:3]) + "\n\n"
                    "【章节契约摘录】\n" + "\n".join(contract_lines) + "\n\n"
                    "【待重写段落】\n" + source_paragraph[:3200] + "\n\n"
                    "请直接输出重写后的单段正文。"
                )
                _set_chapter_stage(
                    "hard_gate_contract_paragraph_rewrite",
                    model_name=finalize_model_name,
                    interface_fmt=finalize_interface_format,
                )
                rewritten_para = invoke_text_generation(
                    repair_prompt,
                    interface_format=finalize_interface_format,
                    base_url=finalize_base_url,
                    model_name=finalize_model_name,
                    api_key=finalize_api_key,
                    temperature=0.2,
                    max_tokens=builtins.min(finalize_max_tokens, 3000),
                    timeout=finalize_timeout,
                )
                if not isinstance(rewritten_para, str):
                    continue
                rewritten_para = rewritten_para.strip()
                if not rewritten_para:
                    continue
                if len(rewritten_para) < int(len(source_paragraph) * 0.45):
                    continue
                paragraphs[idx] = rewritten_para
                rewritten += 1

            if rewritten <= 0:
                return chapter_text, False

            merged_text = merge_chapter_paragraphs(paragraphs)
            if not merged_text:
                return chapter_text, False

            remaining_para_issues = detect_paragraph_contract_drift(
                merged_text,
                chapter_contract,
                max_paragraph_issues=3,
                opening_window=2,
            )
            self.safe_log(
                f"🔧 第{i}章段落级契约修复: 重写{rewritten}段, "
                f"剩余段落漂移{len(remaining_para_issues)}项"
            )
            return merged_text, True

        def _repair_opening_anchor_drift(chapter_text: str, opening_issues: list[str]) -> str:
            if not chapter_text or not opening_issues:
                return chapter_text
            paragraphs = split_chapter_paragraphs(chapter_text)
            if not paragraphs:
                return chapter_text

            opening_source = "\n\n".join(paragraphs[:2])
            required = _collect_contract_anchor_terms(chapter_contract)
            required_lines: list[str] = []
            if required.get("characters"):
                required_lines.append(f"- 人物锚点: {'、'.join(required['characters'][:3])}")
            if required.get("locations"):
                required_lines.append(f"- 场景锚点: {'、'.join(required['locations'][:2])}")
            if required.get("key_items"):
                required_lines.append(f"- 关键要素: {'、'.join(required['key_items'][:2])}")
            previous_preview = str(previous_drift_record.get("ending_preview", "")).strip()
            previous_terms = _normalize_anchor_terms(previous_drift_record.get("ending_anchor_terms", []), limit=4)
            if previous_terms:
                required_lines.append(f"- 上章结尾锚点: {'、'.join(previous_terms)}")
            if previous_preview:
                required_lines.append(f"- 上章结尾片段: {previous_preview[:120]}")
            if not required_lines:
                return chapter_text

            try:
                repair_prompt = (
                    "你是长篇连载小说主编。请仅重写本章开头1-2段，让其与上一章衔接并满足锚点。\n\n"
                    "【硬规则】\n"
                    "1) 只输出重写后的开头段落，不要输出整章。\n"
                    "2) 开头必须自然承接上一章，不能突然跳场。\n"
                    "3) 至少命中1个人物锚点与1个场景锚点。\n"
                    "4) 保持文风一致，不改变本章主冲突方向。\n\n"
                    f"【命中问题】\n- " + "\n- ".join(opening_issues[:3]) + "\n\n"
                    "【锚点要求】\n" + "\n".join(required_lines) + "\n\n"
                    "【当前开头】\n" + opening_source[:3200] + "\n\n"
                    "请直接输出重写后的开头段落。"
                )
                _set_chapter_stage(
                    "hard_gate_opening_anchor_rewrite",
                    model_name=finalize_model_name,
                    interface_fmt=finalize_interface_format,
                )
                rewritten_opening = invoke_text_generation(
                    repair_prompt,
                    interface_format=finalize_interface_format,
                    base_url=finalize_base_url,
                    model_name=finalize_model_name,
                    api_key=finalize_api_key,
                    temperature=0.2,
                    max_tokens=builtins.min(finalize_max_tokens, 2600),
                    timeout=finalize_timeout,
                )
                if not isinstance(rewritten_opening, str):
                    return chapter_text
                rewritten_opening = rewritten_opening.strip()
                if not rewritten_opening:
                    return chapter_text
                opening_paragraphs = split_chapter_paragraphs(rewritten_opening)
                if not opening_paragraphs:
                    return chapter_text
                replace_count = 2 if len(paragraphs) >= 2 else 1
                merged = merge_chapter_paragraphs(opening_paragraphs[:2] + paragraphs[replace_count:])
                if not merged or len(merged) < int(len(chapter_text) * 0.65):
                    return chapter_text
                self.safe_log(f"🔧 第{i}章开篇锚点定向修复完成")
                return merged
            except (RuntimeError, ValueError, TypeError, OSError, ImportError) as opening_fix_error:
                self.safe_log(f"⚠️ 第{i}章开篇锚点修复失败: {opening_fix_error}")
                return chapter_text

        def update_progress(step_name, progress, event_payload=None):
            # 将进度信息输出到日志
            self.safe_log(f"  Using Quality Loop: {step_name} ({int(progress*100)}%)")
            # 这里也可以扩展更新进度条，如果UI有专门的进度条组件
            if isinstance(event_payload, dict) and event_payload.get("event_type") == "score_round":
                self.safe_log_quality_score_event(event_payload)

        def _attempt_hard_gate_repair(chapter_text: str, stage_label: str) -> tuple[str, list[str]]:
            issues = _collect_hard_gate_issues(chapter_text)
            if not issues:
                return chapter_text, []

            self.safe_log(f"⚠️ {stage_label}命中硬阻断({len(issues)}项)，尝试问题定向修复...")
            self.safe_log("  - 命中项: " + "；".join(issues[:3]))

            fixed_text, unresolved, used_llm_fix = _apply_hard_gate_repairs(
                chapter_text=chapter_text,
                issues=issues,
                auto_fix_fn=_auto_fix_term_consistency,
                llm_fix_fn=_repair_llm_consistency_conflicts,
                collect_issues_fn=_collect_hard_gate_issues,
            )
            if used_llm_fix:
                self.safe_log("  - 已执行LLM一致性定向修复")

            contract_unresolved = [
                str(item).strip() for item in unresolved if "章节契约漂移" in str(item)
            ]
            if contract_unresolved:
                repaired_contract_text = _repair_chapter_contract_drift(fixed_text, contract_unresolved)
                if repaired_contract_text != fixed_text:
                    fixed_text = repaired_contract_text
                    unresolved = _collect_hard_gate_issues(fixed_text)
                if unresolved:
                    paragraph_repaired_text, paragraph_used = _repair_chapter_contract_paragraphs(fixed_text)
                    if paragraph_used and paragraph_repaired_text != fixed_text:
                        fixed_text = paragraph_repaired_text
                        unresolved = _collect_hard_gate_issues(fixed_text)

            opening_unresolved = [
                str(item).strip() for item in unresolved if "开篇锚点漂移" in str(item)
            ]
            if opening_unresolved:
                opening_repaired_text = _repair_opening_anchor_drift(fixed_text, opening_unresolved)
                if opening_repaired_text != fixed_text:
                    fixed_text = opening_repaired_text
                    unresolved = _collect_hard_gate_issues(fixed_text)

            if unresolved and optimization and controller is not None and isinstance(loop_llm_config, dict):
                re_loop_max_iter = 3 if any("LLM深度一致性冲突" in str(x) for x in unresolved) else 2
                self.safe_log(f"  - 初次修复后仍命中，进入重闭环(限{re_loop_max_iter}轮)...")
                re_loop_threshold = float(loop_llm_config.get("quality_threshold", 9.0))
                re_loop_result = _run_quality_loop_with_reporting(
                    self,
                    controller=controller,
                    chapter_num=i,
                    initial_content=fixed_text,
                    threshold=re_loop_threshold,
                    progress_callback=update_progress,
                    stage_label=f"第{i}章重闭环",
                    fallback_score=0.0,
                    skip_expand=True,
                    min_word_count=int(min),
                    target_word_count=int(word),
                    max_iterations_override=re_loop_max_iter,
                )
                fixed_text = re_loop_result["content"]
                self.safe_log(
                    f"  - 重闭环完成: 分数={re_loop_result['final_score']:.2f}, "
                    f"迭代={re_loop_result['iterations']}"
                )

                fixed_text, unresolved, used_llm_fix = _apply_hard_gate_repairs(
                    chapter_text=fixed_text,
                    issues=unresolved,
                    auto_fix_fn=_auto_fix_term_consistency,
                    llm_fix_fn=_repair_llm_consistency_conflicts,
                    collect_issues_fn=_collect_hard_gate_issues,
                )
                if used_llm_fix:
                    self.safe_log("  - 重闭环后再次执行LLM定向修复")

            if unresolved:
                deterministic_fixed = _auto_fix_term_consistency(fixed_text, unresolved)
                if deterministic_fixed != fixed_text:
                    fixed_text = deterministic_fixed
                    unresolved = _collect_hard_gate_issues(fixed_text)
                    if unresolved:
                        self.safe_log("  - 术语硬修复后仍命中: " + "；".join(unresolved[:3]))
                    else:
                        self.safe_log("✅ 术语硬修复后已通过硬闸")

            if unresolved:
                self.safe_log("  - 修复后仍命中: " + "；".join(unresolved[:3]))
            else:
                self.safe_log("✅ 硬阻断问题修复完成，继续后续流程")

            return fixed_text, unresolved

        def _sanitize_chapter_before_save(chapter_text: str, stage_label: str) -> tuple[str, list[str]]:
            sanitized = _clean_generated_chapter_text(chapter_text)
            sanitized = _ensure_chapter_title_line(
                sanitized,
                i,
                chapter_title_for_output,
            )
            integrity_issues = _collect_chapter_text_integrity_issues(sanitized, i)
            if integrity_issues:
                self.safe_log(
                    f"⚠️ {stage_label}输出结构守卫命中: " + "；".join(integrity_issues[:3])
                )
            else:
                self.safe_log(f"✅ {stage_label}输出结构守卫通过")
            return sanitized, integrity_issues

        # 🆕 质量闭环优化 (Quality Loop)
        controller = None
        loop_llm_config: dict[str, Any] | None = None

        # 🆕 每章预生成验证器增强（注入分卷定位、伏笔、女主等提示）
        pre_validation_enhancement = ""
        try:
            from novel_generator.pre_generation_validator import get_chapter_enhancement
            filepath = self.filepath_var.get().strip()
            pre_validation_enhancement = get_chapter_enhancement(filepath, i)
            if pre_validation_enhancement:
                self.safe_log(f"💡 第{i}章应用增强提示: 分卷/伏笔/女主等")
        except ImportError:
            pass
        except (RuntimeError, ValueError, TypeError, OSError, KeyError, ImportError) as e:
            self.safe_log(f"⚠️ 预生成验证失败: {e}")
        
        # 将增强提示合并到final_prompt
        if pre_validation_enhancement:
            final_prompt = final_prompt + "\n\n" + pre_validation_enhancement

        _set_chapter_stage(
            "draft_generation",
            model_name=draft_model_name,
            interface_fmt=draft_interface_format,
        )
        draft_text = generate_chapter_draft(
            api_key=draft_api_key,
            base_url=draft_base_url,
            model_name=draft_model_name,
            filepath=self.filepath_var.get().strip(),
            novel_number=i,
            word_number=word,
            min_word_number=int(min),
            temperature=draft_temperature,
            user_guidance=user_guidance,
            characters_involved=char_inv,
            key_items=key_items,
            scene_location=scene_loc,
            time_constraint=time_constr,
            embedding_api_key=embedding_api_key,
            embedding_url=embedding_url,
            embedding_interface_format=embedding_interface_format,
            embedding_model_name=embedding_model_name,
            embedding_retrieval_k=embedding_k,
            interface_format=draft_interface_format,
            max_tokens=draft_max_tokens,
            timeout=draft_timeout,
            custom_prompt_text=final_prompt,
            runtime_architecture_max_chars=architecture_budgets["chapter_prompt"],
            runtime_architecture_ignore_budget=architecture_budgets["ignore_budget"],
            language_purity_enabled=language_purity_enabled,
            auto_correct_mixed_language=auto_correct_mixed_language,
            preserve_proper_nouns=preserve_proper_nouns,
            strict_language_mode=strict_language_mode,
            # 避免与后续质量闭环重复优化，减少策略打架。
            auto_optimize=not optimization
        )

        # 🆕 质量闭环优化 (Quality Loop)
        if optimization:
            try:
                from novel_generator.quality_loop_controller import (
                    QualityLoopController,
                    DEFAULT_QUALITY_THRESHOLD,
                )

                # 🆕 使用用户选择的质量闭环LLM配置（动态选择，不硬编码）
                quality_loop_llm_name = self.quality_loop_llm_var.get()
                consistency_review_llm_name = self.consistency_review_llm_var.get()
                loop_llm_config, quality_threshold = _build_quality_loop_runtime_config(
                    loaded_config=self.loaded_config,
                    quality_loop_llm_name=quality_loop_llm_name,
                    consistency_review_llm_name=consistency_review_llm_name,
                    draft_defaults={
                        "api_key": draft_api_key,
                        "base_url": draft_base_url,
                        "model_name": draft_model_name,
                        "max_tokens": draft_max_tokens,
                        "timeout": draft_timeout,
                        "interface_format": draft_interface_format,
                    },
                    other_params=other_params,
                    min_word_count=int(min),
                    target_word_count=int(word),
                    enable_llm_consistency_check=enable_llm_consistency_check,
                    consistency_hard_gate=consistency_hard_gate,
                    enable_timeline_check=enable_timeline_check,
                    timeline_hard_gate=timeline_hard_gate,
                    default_quality_threshold=float(DEFAULT_QUALITY_THRESHOLD),
                )
                
                # 🆕 获取毒舌专用LLM配置
                try:
                    critique_llm_name = self.critique_llm_var.get()
                    critic_llm_config = _build_critic_llm_runtime_config(
                        loaded_config=self.loaded_config,
                        critique_llm_name=critique_llm_name,
                        draft_defaults={
                            "api_key": draft_api_key,
                            "base_url": draft_base_url,
                            "model_name": draft_model_name,
                            "max_tokens": draft_max_tokens,
                            "timeout": draft_timeout,
                            "interface_format": draft_interface_format,
                        },
                    )
                    self.safe_log(f"😈 毒舌鉴赏使用模型: {critique_llm_name}")
                except (RuntimeError, ValueError, TypeError, OSError, KeyError) as e:
                    self.safe_log(f"⚠️ 获取毒舌配置失败，使用默认配置: {e}")
                    critic_llm_config = None

                self.safe_log(f"🔧 质量闭环使用模型: {quality_loop_llm_name}")

                controller = QualityLoopController(
                    novel_path=self.filepath_var.get().strip(),
                    llm_config=loop_llm_config,
                    critic_llm_config=critic_llm_config
                )

                self.safe_log(f"🔄 第{i}章进入质量闭环优化...")
                loop_result = _run_quality_loop_with_reporting(
                    self,
                    controller=controller,
                    chapter_num=i,
                    initial_content=draft_text,
                    threshold=quality_threshold,
                    progress_callback=update_progress,
                    stage_label=f"第{i}章闭环",
                    fallback_score=0.0,
                    min_word_count=int(min),
                    target_word_count=int(word),
                )

                loop_final_score = loop_result["final_score"]
                loop_iterations = loop_result["iterations"]

                if loop_result["content"] != draft_text:
                    draft_text = loop_result["content"]
                    self.safe_log(
                        f"✅ 第{i}章闭环优化完成 (闭环分: {loop_final_score:.1f}, 迭代: {loop_iterations}次)"
                    )
                else:
                    if loop_final_score >= quality_threshold:
                        self.safe_log(f"✅ 第{i}章闭环已达标 (闭环分: {loop_final_score:.1f})")
                    else:
                        self.safe_log(
                            f"⚠️ 第{i}章闭环结束 (闭环分: {loop_final_score:.1f} < 目标分)"
                        )

                if loop_result.get("status") == "hard_gate_blocked":
                    draft_text, unresolved_loop_issues = _attempt_hard_gate_repair(
                        draft_text,
                        stage_label=f"第{i}章闭环后",
                    )
                    if _should_raise_hard_gate_after_repair(stop_batch_on_hard_gate, unresolved_loop_issues):
                        raise RuntimeError(
                            f"HARD_GATE_BLOCK: 第{i}章触发硬阻断且闭环未修复，已终止当前章节。"
                        )
                    if unresolved_loop_issues:
                        self.safe_log(
                            f"⚠️ 第{i}章仍有{len(unresolved_loop_issues)}项硬阻断未修复，按配置继续后续流程"
                        )

            except (RuntimeError, ValueError, TypeError, OSError, KeyError, ConnectionError, ImportError) as e:
                if "HARD_GATE_BLOCK" in str(e):
                    self.safe_log(f"⛔ 第{i}章质量闭环命中硬阻断: {e}")
                else:
                    self.safe_log(f"❌ 第{i}章质量闭环优化异常，终止当前章节: {e}")
                # 严格模式：质量闭环异常不再跳过，直接失败当前章节
                raise

        if not optimization:
            base_guard_issues = _collect_hard_gate_issues(draft_text)
            if base_guard_issues:
                raise RuntimeError(
                    "HARD_GATE_BLOCK: 关闭优化时命中基础守卫 -> " + "；".join(base_guard_issues[:3])
                )

        chapters_dir = os.path.join(self.filepath_var.get().strip(), "chapters")
        os.makedirs(chapters_dir, exist_ok=True)
        chapter_path = os.path.join(chapters_dir, f"chapter_{i}.txt")
        if len(draft_text) < 0.7 * min and auto_enrich:
            self.safe_log(f"第{i}章草稿字数 ({len(draft_text)}) 低于目标字数({min})的70%，正在扩写...")
            _set_chapter_stage(
                "auto_enrich",
                model_name=draft_model_name,
                interface_fmt=draft_interface_format,
            )
            enriched = enrich_chapter_text(
                chapter_text=draft_text,
                word_number=word,
                api_key=draft_api_key,
                base_url=draft_base_url,
                model_name=draft_model_name,
                temperature=draft_temperature,
                interface_format=draft_interface_format,
                max_tokens=draft_max_tokens,
                timeout=draft_timeout
            )
            draft_text = enriched
        
        # 🔧 修复章节标题重复问题（如"第X章 第X章"）
        try:
            draft_text = _ensure_chapter_title_line(
                draft_text,
                i,
                chapter_title_for_output,
            )
            self.safe_log(f'🔧 第{i}章标题已清洗')
        except (RuntimeError, ValueError, TypeError, OSError, KeyError, ImportError) as e:
            self.safe_log(f'⚠️ 第{i}章标题清洗失败: {e}')
        
        # 🆕 真正的精校步骤（润色、格式规范、错别字修正）
        try:
            from novel_generator.finalization import polish_chapter_content
            
            self.safe_log(f'✨ 第{i}章进行精校润色...')
            _set_chapter_stage(
                "polish_chapter",
                model_name=finalize_model_name,
                interface_fmt=finalize_interface_format,
            )
            polished_text = polish_chapter_content(
                chapter_text=draft_text,
                api_key=finalize_api_key,
                base_url=finalize_base_url,
                model_name=finalize_model_name,
                temperature=0.5,  # 精校时使用较低温度
                interface_format=finalize_interface_format,
                max_tokens=finalize_max_tokens,
                timeout=finalize_timeout
            )
            
            if polished_text and len(polished_text) >= len(draft_text) * 0.7:
                draft_text = polished_text
                self.safe_log(f'✅ 第{i}章精校完成 (字数: {len(polished_text)})')
            else:
                self.safe_log(f'⚠️ 第{i}章精校结果异常，保留原文')
                
        except (RuntimeError, ValueError, TypeError, OSError, ConnectionError) as e:
            self.safe_log(f'⚠️ 第{i}章精校失败(跳过): {e}')

        # 精校后硬闸复核：防止润色引入时序/一致性回退
        draft_text, post_polish_issues = _attempt_hard_gate_repair(
            draft_text,
            stage_label=f"第{i}章精校后",
        )
        if _should_raise_hard_gate_after_repair(stop_batch_on_hard_gate, post_polish_issues):
            raise RuntimeError(
                "HARD_GATE_BLOCK: 精校后仍命中硬阻断 -> " + "；".join(post_polish_issues[:3])
            )
        if post_polish_issues:
            self.safe_log(
                f"⚠️ 第{i}章精校后仍有{len(post_polish_issues)}项硬阻断未修复，按配置继续后续流程"
            )
        
        def _sync_runtime_context_after_chapter_write(stage_name: str) -> None:
            try:
                _set_chapter_stage(
                    stage_name,
                    model_name=finalize_model_name,
                    interface_fmt=finalize_interface_format,
                )
                finalize_chapter(
                    novel_number=i,
                    word_number=word,
                    api_key=finalize_api_key,
                    base_url=finalize_base_url,
                    model_name=finalize_model_name,
                    temperature=finalize_temperature,
                    filepath=self.filepath_var.get().strip(),
                    embedding_api_key=embedding_api_key,
                    embedding_url=embedding_url,
                    embedding_interface_format=embedding_interface_format,
                    embedding_model_name=embedding_model_name,
                    interface_format=finalize_interface_format,
                    max_tokens=finalize_max_tokens,
                    timeout=finalize_timeout
                )
            except (RuntimeError, ValueError, TypeError, OSError, ImportError) as e:
                msg = str(e)
                if "chroma_server_nofile" in msg or "unable to infer type for attribute" in msg:
                    self.safe_log(f"⚠️ 向量库组件兼容异常，已跳过向量库更新: {msg}")
                else:
                    raise

        draft_text, save_integrity_issues = _sanitize_chapter_before_save(
            draft_text,
            stage_label=f"第{i}章保存前",
        )
        if save_integrity_issues and output_integrity_hard_gate:
            raise RuntimeError(
                "HARD_GATE_BLOCK: 保存前输出结构守卫未通过 -> "
                + "；".join(save_integrity_issues[:3])
            )
        clear_file_content(chapter_path)
        save_string_to_txt(draft_text, chapter_path)
        _sync_runtime_context_after_chapter_write("finalize_context_update")
        context_resync_required = False
        
        # 🆕 保存前确认评分（精校后可能引入问题）
        if optimization:
            try:
                from chapter_quality_analyzer import ChapterQualityAnalyzer
                from novel_generator.quality_loop_controller import (
                    POST_FINALIZE_TOLERANCE,
                    DEFAULT_QUALITY_THRESHOLD,
                )
                confirm_loop_llm_config: dict[str, Any]
                if isinstance(loop_llm_config, dict):
                    confirm_loop_llm_config = loop_llm_config
                else:
                    confirm_loop_llm_config = {}
                
                # 读取精校后的内容
                with open(chapter_path, 'r', encoding='utf-8') as f:
                    finalized_content = f.read()
                
                # 评分确认：复用闭环同一 analyzer（同一 rubric）
                if controller and hasattr(controller, "analyzer"):
                    confirm_analyzer = controller.analyzer
                else:
                    confirm_analyzer = ChapterQualityAnalyzer(
                        self.filepath_var.get().strip(),
                        llm_config=confirm_loop_llm_config
                    )
                confirm_scores = confirm_analyzer.analyze_content(finalized_content)
                confirm_score = _resolve_quality_score(confirm_scores, default=0.0)
                
                # 获取动态阈值（从QualityLoopController获取）
                quality_threshold = float(confirm_loop_llm_config.get('quality_threshold', DEFAULT_QUALITY_THRESHOLD))
                min_acceptable_score = quality_threshold - POST_FINALIZE_TOLERANCE
                
                if confirm_score < min_acceptable_score:
                    # 精校后评分过低，需要重新闭环（最多重试1次，避免无限循环）
                    self.safe_log(f"⚠️ 第{i}章精校后评分({confirm_score:.1f})低于最低要求({min_acceptable_score:.1f})，重新进入闭环...")
                    
                    # 定义重试进度回调
                    def re_loop_progress(step_name, progress, event_payload=None):
                        self.safe_log(f"  [重新闭环] {step_name}")
                        if isinstance(event_payload, dict) and event_payload.get("event_type") == "score_round":
                            self.safe_log_quality_score_event(event_payload)
                    
                    controller_for_reloop = controller
                    re_loop_result = _run_quality_loop_with_reporting(
                        self,
                        controller=controller_for_reloop,
                        chapter_num=i,
                        initial_content=finalized_content,
                        threshold=quality_threshold,
                        progress_callback=re_loop_progress,
                        stage_label=f"第{i}章重新闭环",
                        fallback_score=confirm_score,
                        skip_expand=True,  # 🆕 禁用扩写，防止字数膨胀
                    )
                    
                    # 保存重新优化后的内容
                    re_loop_content = re_loop_result["content"]
                    final_score = re_loop_result["final_score"]

                    if str(re_loop_content or "").strip() != str(finalized_content or "").strip():
                        re_loop_content, reloop_integrity_issues = _sanitize_chapter_before_save(
                            re_loop_content,
                            stage_label=f"第{i}章重新闭环后",
                        )
                        if reloop_integrity_issues and output_integrity_hard_gate:
                            raise RuntimeError(
                                "HARD_GATE_BLOCK: 重新闭环后输出结构守卫未通过 -> "
                                + "；".join(reloop_integrity_issues[:3])
                            )
                        clear_file_content(chapter_path)
                        save_string_to_txt(re_loop_content, chapter_path)
                        context_resync_required = True
                    else:
                        self.safe_log(f"ℹ️ 第{i}章重新闭环未改写正文，跳过上下文重同步")
                    
                    if final_score >= min_acceptable_score:
                        self.safe_log(f"✅ 第{i}章重新闭环成功 (闭环分: {final_score:.1f})")
                    else:
                        # 即使分数仍不达标，也接受结果，避免无限循环
                        self.safe_log(
                            f"⚠️ 第{i}章重新闭环后仍未达标 (闭环分: {final_score:.1f})，已接受当前结果"
                        )
                else:
                    self.safe_log(
                        f"✅ 第{i}章最终放行通过 (放行分: {confirm_score:.1f} >= {min_acceptable_score:.1f})"
                    )
                    
            except (RuntimeError, ValueError, TypeError, OSError, ConnectionError) as e:
                self.safe_log(f"⚠️ 第{i}章保存前评分确认出错(跳过): {e}")

        if context_resync_required:
            self.safe_log(f"♻️ 第{i}章正文在保存前闭环后发生改写，正在重新同步运行态...")
            latest_chapter_text = read_file(chapter_path)
            latest_chapter_text, post_reloop_issues = _attempt_hard_gate_repair(
                latest_chapter_text,
                stage_label=f"第{i}章保存前闭环后",
            )
            if _should_raise_hard_gate_after_repair(stop_batch_on_hard_gate, post_reloop_issues):
                raise RuntimeError(
                    "HARD_GATE_BLOCK: 保存前闭环后仍命中硬阻断 -> " + "；".join(post_reloop_issues[:3])
                )
            latest_chapter_text, resync_integrity_issues = _sanitize_chapter_before_save(
                latest_chapter_text,
                stage_label=f"第{i}章运行态重同步前",
            )
            if resync_integrity_issues and output_integrity_hard_gate:
                raise RuntimeError(
                    "HARD_GATE_BLOCK: 运行态重同步前输出结构守卫未通过 -> "
                    + "；".join(resync_integrity_issues[:3])
                )
            if latest_chapter_text != read_file(chapter_path):
                clear_file_content(chapter_path)
                save_string_to_txt(latest_chapter_text, chapter_path)
            if post_reloop_issues:
                self.safe_log(
                    f"⚠️ 第{i}章保存前闭环后仍有{len(post_reloop_issues)}项硬阻断未修复，按配置继续"
                )
            _sync_runtime_context_after_chapter_write("finalize_context_resync")

        if enable_state_ledger_writeback:
            try:
                final_text_for_ledger = read_file(chapter_path)
                if not final_text_for_ledger.strip():
                    raise RuntimeError("章节文件为空，无法写入防漂移账本")
                ledger_record = _write_drift_state_ledger_record(
                    filepath=self.filepath_var.get().strip(),
                    chapter_num=i,
                    chapter_text=final_text_for_ledger,
                    chapter_contract=chapter_contract,
                    max_history=600,
                )
                anchor_count = len(_normalize_anchor_terms(ledger_record.get("ending_anchor_terms", []), limit=20))
                self.safe_log(f"🧾 第{i}章防漂移状态账本已写回（结尾锚点{anchor_count}项）")
            except (RuntimeError, ValueError, TypeError, OSError) as ledger_error:
                message = f"第{i}章防漂移状态账本写回失败: {ledger_error}"
                self.safe_log(f"⚠️ {message}")
                if state_ledger_hard_gate:
                    raise RuntimeError(f"HARD_GATE_BLOCK: {message}") from ledger_error

        try:
            saved_snapshot_files = _save_runtime_state_snapshot(self.filepath_var.get().strip(), i)
            if saved_snapshot_files:
                self.safe_log(f"💾 第{i}章运行态快照已保存 ({len(saved_snapshot_files)}项)")
            else:
                self.safe_log(f"⚠️ 第{i}章未写入运行态快照（无可保存文件）")
        except (RuntimeError, ValueError, TypeError, OSError) as e:
            self.safe_log(f"⚠️ 第{i}章运行态快照保存失败: {e}")

        return {"ok": True}

    result = open_batch_dialog()
    if result["close"]:
        return

    def batch_task():
        set_runtime_log_stage("S3")
        try:
            start_chapter, end_chapter, target_word, min_word, auto_enrich, optimization = _parse_batch_runtime_request(
                result
            )
        except ValueError as e:
            _stage_log(self, "S3", f"❌ 批量参数解析失败: {e}")
            self.master.after(0, lambda: messagebox.showwarning("参数错误", str(e)))
            return
        filepath = self.filepath_var.get().strip()

        precheck_ok, precheck_issues = _runtime_architecture_precheck(filepath)
        if not precheck_ok:
            _stage_log(self, "S3", "❌ 运行时架构守卫阻断，批量生成已停止：")
            for item in precheck_issues:
                self.safe_log(f"  - {item}")
            issue_text = "\n".join(f"- {item}" for item in precheck_issues)
            self.master.after(0, lambda: messagebox.showwarning("架构守卫阻断", f"运行时架构预检查未通过：\n{issue_text}"))
            return

        other_params = self.loaded_config.get("other_params", {})
        if not isinstance(other_params, dict):
            other_params = {}
        full_auto_mode = _safe_bool(other_params.get("blueprint_full_auto_mode"), default=True)
        precheck_deep_scan = _safe_bool(
            other_params.get("batch_precheck_deep_scan"),
            default=full_auto_mode,
        )
        precheck_auto_continue = _safe_bool(
            other_params.get("batch_precheck_auto_continue_on_warning"),
            default=full_auto_mode,
        )
        self.safe_log(
            "ℹ️ 批量预检策略: "
            f"深度扫描{'开启' if precheck_deep_scan else '关闭'} | "
            f"告警{'自动放行' if precheck_auto_continue else '人工确认'}"
        )

        if not _run_batch_precheck(
            self,
            filepath,
            start_chapter,
            end_chapter,
            deep_scan=precheck_deep_scan,
            auto_continue_on_warning=precheck_auto_continue,
            interactive=not precheck_auto_continue,
        ):
            return
        

            

        
        total = end_chapter - start_chapter + 1
        success_count = 0
        hard_gate_failures = []
        runtime_failures = []
        stopped_by_hard_gate = False
        stop_on_hard_gate = _safe_bool(
            self.loaded_config.get("other_params", {}).get("stop_batch_on_hard_gate"),
            default=True,
        )
        allow_partial_resume_fallback = _safe_bool(
            self.loaded_config.get("other_params", {}).get("batch_partial_resume_allow_fallback"),
            default=True,
        )
        
        self.safe_log(f"🚀 开始批量生成章节: {start_chapter} - {end_chapter}")
        if start_chapter == 1:
            cleared_items = _reset_runtime_state_for_fresh_batch(filepath)
            if cleared_items:
                self.safe_log(f"🧹 从第1章重跑，已清理历史运行态 {len(cleared_items)} 项")
            else:
                self.safe_log("🧹 从第1章重跑，未发现可清理的历史运行态")
        else:
            restored_ok, restore_msg, restored_items = _restore_runtime_state_for_partial_batch(
                filepath,
                start_chapter,
                allow_fallback_without_snapshot=allow_partial_resume_fallback,
            )
            if not restored_ok:
                self.safe_log(f"⛔ 中途重跑阻断: {restore_msg}")
                self.safe_log("💡 请先补齐上一章快照，或改为从第1章重跑。")
                self.master.after(
                    0,
                    lambda: messagebox.showwarning(
                        "中途重跑阻断",
                        f"{restore_msg}\n\n为防止运行态污染，本次批量已停止。",
                    ),
                )
                return

            self.safe_log(f"🧯 中途重跑前已回滚运行态: {restore_msg}")
            if restored_items:
                self.safe_log("  - 回滚项: " + "；".join(restored_items[:4]))

        if start_chapter > 1 and allow_partial_resume_fallback:
            self.safe_log("ℹ️ 中途重跑策略：缺快照时允许降级回滚")
        elif start_chapter > 1:
            self.safe_log("ℹ️ 中途重跑策略：缺快照时严格阻断")

        if stop_on_hard_gate:
            self.safe_log("ℹ️ 硬阻断策略：命中后终止当前批次")
        else:
            self.safe_log("ℹ️ 硬阻断策略：命中后记录报告并继续后续章节")
        for i in range(start_chapter, end_chapter + 1):
            set_llm_log_context(
                project_path=filepath,
                chapter_num=i,
                stage="chapter_pipeline",
            )
            try:
                self.safe_log(f"📝 正在生成第 {i} 章 ({i - start_chapter + 1}/{total})...")
                # 调用内部函数生成章节
                generate_chapter_batch(self, i, target_word, min_word, auto_enrich, optimization)
                success_count += 1
                self.safe_log(f"✅ 第 {i} 章生成完成")
                

                    
            except (RuntimeError, ValueError, TypeError, OSError, KeyError, ConnectionError, ImportError) as e:
                error_text = str(e)
                error_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                traceback_text = traceback.format_exc()
                self.safe_log(f"❌ 第 {i} 章生成失败: {error_text}")
                self.safe_log(traceback_text)
                lower_error = error_text.lower()
                is_timeout_error = (
                    isinstance(e, TimeoutError)
                    or "timed out" in lower_error
                    or "timeout" in lower_error
                    or e.__class__.__name__ in {"APITimeoutError", "ConnectTimeout", "ReadTimeout"}
                )
                if "HARD_GATE_BLOCK" in error_text:
                    failure_item = {
                        "chapter": i,
                        "error": error_text,
                        "timestamp": error_timestamp,
                    }
                    try:
                        report_path = _write_chapter_hard_gate_report(
                            filepath=filepath,
                            chapter_num=i,
                            error_text=error_text,
                            timestamp=error_timestamp,
                            traceback_text=traceback_text,
                            stop_on_hard_gate=stop_on_hard_gate,
                        )
                        failure_item["detail_report"] = report_path
                        self.safe_log(f"🧾 第{i}章硬阻断详细报告已写入: {report_path}")
                    except (OSError, TypeError, ValueError) as report_err:
                        self.safe_log(f"⚠️ 第{i}章硬阻断详细报告写入失败: {report_err}")
                    hard_gate_failures.append(failure_item)
                    if stop_on_hard_gate:
                        stopped_by_hard_gate = True
                        self.safe_log("⛔ 检测到硬阻断失败，按策略终止当前批次。")
                        break

                    self.safe_log("⏭️ 检测到硬阻断失败，已记录报告并继续后续批量生成。")
                    continue
                if is_timeout_error:
                    self.safe_log("🌐 检测到网络/握手超时，已记录失败并继续下一章。")
                runtime_failures.append(
                    {
                        "chapter": i,
                        "error": error_text,
                        "timestamp": error_timestamp,
                    }
                )
                self.safe_log("⏭️ 非硬阻断失败已记录，继续后续章节。")
            finally:
                clear_llm_log_context()
                

        

        if hard_gate_failures or runtime_failures:
            report = {
                "type": "batch_guard_report",
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "project_path": filepath,
                "range": {"start": start_chapter, "end": end_chapter},
                "optimization_enabled": bool(optimization),
                "stop_batch_on_hard_gate": bool(stop_on_hard_gate),
                "stopped_by_hard_gate": bool(stopped_by_hard_gate),
                "hard_gate_failures": hard_gate_failures,
                "runtime_failures": runtime_failures,
                "failures": hard_gate_failures + runtime_failures,
                "summary": {
                    "total_requested": total,
                    "success_count": success_count,
                    "hard_gate_failure_count": len(hard_gate_failures),
                    "runtime_failure_count": len(runtime_failures),
                    "failure_count": len(hard_gate_failures) + len(runtime_failures),
                },
            }
            try:
                report_path = _write_batch_guard_report(filepath, report)
                self.safe_log(f"🧾 已写入批量失败报告: {report_path}")
            except (OSError, TypeError, ValueError) as e:
                self.safe_log(f"⚠️ 写入硬阻断报告失败: {e}")
        

        self.safe_log(
            f"🎉 批量生成完成! 成功: {success_count}/{total} | 失败: {total - success_count}"
        )

        audit_enabled, audit_sample_size = _load_post_batch_runtime_audit_options(self.loaded_config)
        if audit_enabled:
            def _post_batch_audit_task() -> None:
                set_runtime_log_stage("S3")
                try:
                    sample_label = "全量" if audit_sample_size <= 0 else f"最近{audit_sample_size}份"
                    self.safe_log(f"🔍 启动批量后运行时Prompt审计（{sample_label}日志）...")
                    try:
                        report = _run_post_batch_runtime_audit(filepath, sample_size=audit_sample_size)
                        files_scanned = int(report.get("files_scanned", 0))
                        prompt_blocks = int(report.get("prompt_blocks_scanned", 0))
                        violations = report.get("violations", [])
                        violation_count = len(violations) if isinstance(violations, list) else 0
                        self.safe_log(
                            f"🧪 运行时Prompt审计完成：日志{files_scanned}个 | Prompt块{prompt_blocks}个 | 泄漏命中{violation_count}个"
                        )
                        if violation_count:
                            for item in violations[:3]:
                                sections = ",".join(str(num) for num in item.get("archive_sections", []))
                                file_name = os.path.basename(str(item.get("file", "")))
                                block_index = item.get("block_index", "?")
                                self.safe_log(
                                    f"  - 泄漏样本: {file_name} [block #{block_index}] -> {sections}"
                                )
                    except (RuntimeError, ValueError, TypeError, OSError) as e:
                        self.safe_log(f"⚠️ 批量后运行时Prompt审计失败: {e}")
                finally:
                    clear_runtime_log_stage()

            threading.Thread(target=_post_batch_audit_task, daemon=True).start()

        self.master.after(0, lambda: messagebox.showinfo("完成", f"批量生成完成\n成功: {success_count}/{total}"))

    threading.Thread(target=batch_task, daemon=True).start()


def import_knowledge_handler(self):
    selected_file = filedialog.askopenfilename(
        title="选择要导入的知识库文件",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
    )
    if selected_file:
        def task():
            self.disable_button_safe(self.btn_import_knowledge)
            try:
                emb_api_key = self.embedding_api_key_var.get().strip()
                emb_url = self.embedding_url_var.get().strip()
                emb_format = self.embedding_interface_format_var.get().strip()
                emb_model = self.embedding_model_name_var.get().strip()

                # 尝试不同编码读取文件
                content = None
                encodings = ['utf-8', 'gbk', 'gb2312', 'ansi']
                for encoding in encodings:
                    try:
                        with open(selected_file, 'r', encoding=encoding) as f:
                            content = f.read()
                            break
                    except UnicodeDecodeError:
                        continue
                    except OSError as e:
                        self.safe_log(f"读取文件时发生错误: {str(e)}")
                        raise

                if content is None:
                    raise RuntimeError("无法以任何已知编码格式读取文件")

                # 创建临时UTF-8文件
                import tempfile
                import os
                with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as temp:
                    temp.write(content)
                    temp_path = temp.name

                try:
                    self.safe_log(f"开始导入知识库文件: {selected_file}")
                    import_knowledge_file(
                        embedding_api_key=emb_api_key,
                        embedding_url=emb_url,
                        embedding_interface_format=emb_format,
                        embedding_model_name=emb_model,
                        file_path=temp_path,
                        filepath=self.filepath_var.get().strip()
                    )
                    self.safe_log("✅ 知识库文件导入完成。")
                finally:
                    # 清理临时文件
                    try:
                        os.unlink(temp_path)
                    except OSError as cleanup_error:
                        self.safe_log(f"清理临时文件失败: {cleanup_error}")

            except (RuntimeError, ValueError, TypeError, OSError, UnicodeDecodeError):
                self.handle_exception("导入知识库时出错")
            finally:
                self.enable_button_safe(self.btn_import_knowledge)

        try:
            thread = threading.Thread(target=task, daemon=True)
            thread.start()
        except (RuntimeError, OSError, ValueError, TypeError) as e:
            self.enable_button_safe(self.btn_import_knowledge)
            messagebox.showerror("错误", f"线程启动失败: {str(e)}")

def clear_vectorstore_handler(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        return

    first_confirm = messagebox.askyesno("警告", "确定要清空本地向量库吗？此操作不可恢复！")
    if first_confirm:
        second_confirm = messagebox.askyesno("二次确认", "你确定真的要删除所有向量数据吗？此操作不可恢复！")
        if second_confirm:
            if clear_vector_store(filepath):
                self.log("已清空向量库。")
            else:
                self.log(f"未能清空向量库，请关闭程序后手动删除 {filepath} 下的 vectorstore 文件夹。")

def show_plot_arcs_ui(self):
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先在主Tab中设置保存文件路径")
        return

    plot_arcs_file = os.path.join(filepath, "plot_arcs.txt")
    if not os.path.exists(plot_arcs_file):
        messagebox.showinfo("剧情要点", "当前还未生成任何剧情要点或冲突记录。")
        return

    arcs_text = read_file(plot_arcs_file).strip()
    if not arcs_text:
        arcs_text = "当前没有记录的剧情要点或冲突。"

    top = ctk.CTkToplevel(self.master)
    top.title("剧情要点/未解决冲突")
    top.geometry("600x400")
    text_area = ctk.CTkTextbox(top, wrap="word", font=("Microsoft YaHei", 12))
    text_area.pack(fill="both", expand=True, padx=10, pady=10)
    text_area.insert("0.0", arcs_text)
    text_area.configure(state="disabled")

def auto_consistency_check_ui(self):
    """自动一致性验证UI"""
    filepath = self.filepath_var.get().strip()
    if not filepath:
        messagebox.showwarning("警告", "请先配置保存文件路径。")
        return

    def task():
        self.disable_button_safe(getattr(self, 'btn_auto_consistency_check', None))

        try:
            self.safe_log("🔍 开始自动一致性验证...")
            self.safe_log("📋 验证范围：")
            self.safe_log("  - 叙事流畅性检查")
            self.safe_log("  - 角色弧光一致性")
            self.safe_log("  - 情节推进合理性")
            self.safe_log("  - 世界构建一致性")
            self.safe_log("  - 主题一致性")
            self.safe_log("")

            # 检查必要文件
            architecture_file = os.path.join(filepath, "Novel_architecture.txt")
            directory_file = os.path.join(filepath, "Novel_directory.txt")

            if not os.path.exists(architecture_file):
                self.safe_log("❌ 未找到架构文件：Novel_architecture.txt")
                return

            if not os.path.exists(directory_file):
                self.safe_log("❌ 未找到目录文件：Novel_directory.txt")
                return

            # 导入并使用一致性检查器
            from architecture_consistency_checker import check_architecture_consistency

            self.safe_log("📊 正在执行一致性检查...")
            result = check_architecture_consistency(architecture_file, directory_file)

            # 显示结果
            self.safe_log(f"📊 总体一致性得分：{result['overall_score']:.2f}/1.00")

            if result["overall_score"] >= 0.9:
                self.safe_log("🎉 架构一致性优秀！")
            elif result["overall_score"] >= 0.7:
                self.safe_log("✅ 架构一致性良好")
            elif result["overall_score"] >= 0.5:
                self.safe_log("⚠️ 架构一致性一般")
            else:
                self.safe_log("❌ 架构一致性需要改进")

            if result["issues"]:
                self.safe_log("")
                self.safe_log("❌ 发现问题：")
                for issue in result["issues"]:
                    self.safe_log(f"  - {issue}")

            if result["recommendations"]:
                self.safe_log("")
                self.safe_log("💡 建议：")
                for rec in result["recommendations"]:
                    self.safe_log(f"  - {rec}")

            self.safe_log("")
            self.safe_log("📋 详细检查结果：")
            for check_name, check_result in result["checks"].items():
                status = "✅" if check_result["consistent"] else "❌"
                score_emoji = "🌟" if check_result["score"] >= 0.9 else "⭐" if check_result["score"] >= 0.7 else "🔶" if check_result["score"] >= 0.5 else "❌"
                self.safe_log(f"  {status} {score_emoji} {check_name}: {check_result['score']:.2f}")

                if check_result["issues"]:
                    for issue in check_result["issues"]:
                        self.safe_log(f"    - {issue}")

            self.safe_log("")
            self.safe_log("🎯 自动一致性验证完成！")

        except (RuntimeError, ValueError, TypeError, OSError, ImportError, KeyError) as e:
            self.safe_log(f"❌ 验证过程异常：{e}")
            self.handle_exception("自动一致性验证时出错")
        finally:
            self.enable_button_safe(getattr(self, 'btn_auto_consistency_check', None))

    threading.Thread(target=task, daemon=True).start()
