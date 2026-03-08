# strict_blueprint_generator.py
# -*- coding: utf-8 -*-
"""
严格版章节蓝图生成器
- 零容忍省略
- 零容忍失败
- 强制一致性检查
- 分批次生成（每批50章）
"""
import os
import re
import json
import csv
import time
import difflib
import hashlib
import logging
import threading
import subprocess
import sys
from typing import Any, cast
from datetime import datetime
from novel_generator.common import invoke_with_cleaning
from llm_adapters import create_llm_adapter
from prompt_definitions import (
    BLUEPRINT_EXAMPLE_V3,
    STEP2_GUIDED_STRICT_BLUEPRINT_PROMPT,
    chunked_chapter_blueprint_prompt,
)
from utils import read_file, clear_file_content, save_string_to_txt, resolve_architecture_file
from novel_generator.architecture_extractor import DynamicArchitectureExtractor
from novel_generator.architecture_runtime_slice import (
    build_runtime_architecture_view,
    contains_archive_sections,
)

PoisonousReaderAgent = None
blueprint_critic_available = False
try:
    from novel_generator.critique_agent import PoisonousReaderAgent
    blueprint_critic_available = True
except ImportError:
    PoisonousReaderAgent = None
    blueprint_critic_available = False
except (RuntimeError, ValueError, TypeError) as e:
    logging.warning(f"蓝图评审代理加载失败: {e}")
    PoisonousReaderAgent = None
    blueprint_critic_available = False


class ArchitectureMappingGapError(RuntimeError):
    def __init__(self, message: str, diagnostics: dict[str, Any] | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}

class StrictChapterGenerator:
    def __init__(self, interface_format, api_key, base_url, llm_model,
                 temperature=0.8, max_tokens=60000, timeout=1800,
                 stage_timeout_seconds: int | None = None, heartbeat_interval_seconds=30,
                 enable_blueprint_critic=False, blueprint_critic_threshold=7.5,
                 blueprint_critic_trigger_margin=8.0,
                 enable_resume_auto_repair_existing: bool = True,
                 enable_force_resume_skip_history_validation: bool = False):
        self.interface_format = interface_format
        self.api_key = api_key
        self.base_url = base_url
        self.llm_model = llm_model
        self.temperature = temperature
        self.max_tokens = max_tokens  # 使用完整的60000
        self.timeout = timeout
        self.stage_timeout_seconds = int(stage_timeout_seconds or max(900, timeout))
        self.heartbeat_interval_seconds = int(max(5, heartbeat_interval_seconds))
        self.enable_blueprint_critic = bool(enable_blueprint_critic and blueprint_critic_available)
        self.blueprint_critic_threshold = float(blueprint_critic_threshold)
        self.blueprint_critic_trigger_margin = float(max(0.0, blueprint_critic_trigger_margin))
        self.enable_resume_auto_repair_existing = bool(enable_resume_auto_repair_existing)
        self.enable_force_resume_skip_history_validation = bool(enable_force_resume_skip_history_validation)
        # 任务卡缓存：{ "path": str, "mtime": float, "records": dict[int, dict[str, str]] }
        self._task_card_cache: dict[str, Any] = {}
        self._architecture_extractor_cache: dict[str, Any] = {}

        # 🚨 LLM 对话日志记录器
        self.llm_log_dir = None  # 将在生成时设置
        self.current_log_file = None
        self.llm_conversation_log = []  # 存储当前批次的对话日志
        self._latest_batch_telemetry: dict[str, Any] = {}

        self.llm_adapter = create_llm_adapter(
            interface_format=interface_format,
            base_url=base_url,
            model_name=llm_model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout
        )

        self.blueprint_critic_agent = None
        if self.enable_blueprint_critic and PoisonousReaderAgent is not None:
            try:
                critic_cfg = {
                    "interface_format": interface_format,
                    "api_key": api_key,
                    "base_url": base_url,
                    "model_name": llm_model,
                    "timeout": timeout,
                }
                self.blueprint_critic_agent = PoisonousReaderAgent(critic_cfg, is_independent=False)
                logging.info(
                    f"😈 蓝图毒舌评审已开启 (threshold={self.blueprint_critic_threshold}, margin={self.blueprint_critic_trigger_margin})"
                )
            except (RuntimeError, ValueError, TypeError, OSError) as critic_e:
                logging.warning(f"蓝图毒舌评审初始化失败，自动关闭: {critic_e}")
                self.blueprint_critic_agent = None
                self.enable_blueprint_critic = False

    def _state_file_path(self, filepath: str) -> str:
        return os.path.join(filepath, ".blueprint_state.json")

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    def _sync_split_directory_files(
        self,
        filepath: str,
        directory_text: str,
        *,
        remove_stale: bool = False,
    ) -> None:
        """同步章节目录拆分文件（chapter_blueprints/chapter_X.txt）。"""
        text = str(directory_text or "").strip()
        if not text:
            return
        try:
            from chapter_directory_parser import split_blueprint_to_chapter_files

            result = split_blueprint_to_chapter_files(
                filepath,
                text,
                remove_stale=bool(remove_stale),
            )
            logging.info(
                "🗂️ 目录拆分同步：写入%d章%s",
                int(result.get("chapter_count", 0) or 0),
                f"，清理{len(result.get('removed_files', []))}个旧文件" if remove_stale else "",
            )
        except Exception as sync_error:
            logging.warning(f"⚠️ 目录拆分同步失败（不影响主流程）: {sync_error}")

    def _sync_single_split_directory_file(
        self,
        filepath: str,
        chapter_num: int,
        chapter_text: str,
    ) -> None:
        """
        增量同步单个章节拆分文件（chapter_blueprints/chapter_X.txt）。
        用于断点修复过程中，避免“进度已显示但单章文件尚未落盘”的体验问题。
        """
        text = str(chapter_text or "").strip()
        if int(chapter_num) <= 0 or not text:
            return
        try:
            from chapter_directory_parser import get_chapter_blueprint_file

            chapter_path = get_chapter_blueprint_file(filepath, int(chapter_num))
            os.makedirs(os.path.dirname(chapter_path), exist_ok=True)
            with open(chapter_path, "w", encoding="utf-8") as f:
                f.write(text + "\n")
            logging.info("🗂️ 断点修复单章同步：第%d章", int(chapter_num))
        except Exception as sync_error:
            logging.warning(f"⚠️ 断点修复单章同步失败（第{chapter_num}章）: {sync_error}")

    def _extract_directory_chapter_numbers(self, directory_text: str) -> list[int]:
        text = str(directory_text or "").strip()
        if not text:
            return []
        chapter_pattern = r"(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*[^\n]*)?\s*(?:\*\*)?\s*$"
        numbers = [int(num) for num in re.findall(chapter_pattern, text)]
        if numbers:
            return numbers
        fallback_pattern = r"(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章\s*(?:\*\*)?\s*$"
        return [int(num) for num in re.findall(fallback_pattern, text)]

    def _get_split_directory_progress(self, filepath: str) -> dict[str, int]:
        split_dir = os.path.join(str(filepath or "").strip(), "chapter_blueprints")
        if not os.path.isdir(split_dir):
            return {
                "chapter_count": 0,
                "max_chapter": 0,
                "contiguous_end": 0,
            }

        chapter_numbers: list[int] = []
        try:
            for fname in os.listdir(split_dir):
                match = re.match(r"^chapter_(\d+)\.txt$", str(fname))
                if match:
                    chapter_numbers.append(int(match.group(1)))
        except OSError:
            return {
                "chapter_count": 0,
                "max_chapter": 0,
                "contiguous_end": 0,
            }

        if not chapter_numbers:
            return {
                "chapter_count": 0,
                "max_chapter": 0,
                "contiguous_end": 0,
            }

        unique_sorted = sorted(set(chapter_numbers))
        contiguous_end = 0
        expected = 1
        for chapter_num in unique_sorted:
            if chapter_num != expected:
                break
            contiguous_end = chapter_num
            expected += 1

        return {
            "chapter_count": len(unique_sorted),
            "max_chapter": int(unique_sorted[-1]),
            "contiguous_end": int(contiguous_end),
        }

    def _rebuild_directory_from_split_files(self, filepath: str, end_chapter: int) -> tuple[str, int]:
        end = int(end_chapter)
        if end <= 0:
            return "", 0

        merged_parts: list[str] = []
        for chapter_num in range(1, end + 1):
            chapter_path = os.path.join(
                str(filepath or "").strip(),
                "chapter_blueprints",
                f"chapter_{chapter_num}.txt",
            )
            if not os.path.exists(chapter_path):
                break
            chapter_text = read_file(chapter_path).strip()
            if not chapter_text:
                break
            merged_parts.append(chapter_text)

        recovered_count = len(merged_parts)
        if recovered_count <= 0:
            return "", 0
        return "\n\n".join(merged_parts).strip(), recovered_count

    def _get_architecture_extractor(self, architecture_text: str) -> DynamicArchitectureExtractor:
        arch_hash = self._hash_text(architecture_text)
        cached = self._architecture_extractor_cache.get(arch_hash)
        if isinstance(cached, DynamicArchitectureExtractor):
            return cached

        extractor = DynamicArchitectureExtractor(architecture_text)
        self._architecture_extractor_cache[arch_hash] = extractor

        while len(self._architecture_extractor_cache) > 2:
            oldest_key = next(iter(self._architecture_extractor_cache), None)
            if oldest_key is None:
                break
            self._architecture_extractor_cache.pop(oldest_key, None)

        return extractor

    def _analyze_architecture_chapter_coverage(
        self,
        architecture_text: str,
        start_chapter: int,
        end_chapter: int,
    ) -> dict[str, Any]:
        extractor = self._get_architecture_extractor(architecture_text)
        raw_defs = extractor.structure.get("chapters", {})
        chapter_defs: dict[int, str] = raw_defs if isinstance(raw_defs, dict) else {}

        if end_chapter < start_chapter:
            start_chapter, end_chapter = end_chapter, start_chapter

        missing: list[int] = []
        mapped: list[int] = []
        for chapter in range(start_chapter, end_chapter + 1):
            snippet = str(chapter_defs.get(chapter, "") or "").strip()
            if snippet:
                mapped.append(chapter)
            else:
                missing.append(chapter)

        keys = [k for k in chapter_defs.keys() if isinstance(k, int)]
        keys_sorted = sorted(keys)
        sample_keys: list[int] = []
        if keys_sorted:
            head = keys_sorted[:8]
            tail = keys_sorted[-8:] if len(keys_sorted) > 8 else []
            sample_keys = head + [k for k in tail if k not in head]

        return {
            "start_chapter": int(start_chapter),
            "end_chapter": int(end_chapter),
            "requested_count": int(max(0, end_chapter - start_chapter + 1)),
            "available_chapter_defs": int(len(chapter_defs)),
            "mapped_chapters": mapped,
            "mapped_count": int(len(mapped)),
            "missing_chapters": missing,
            "missing_count": int(len(missing)),
            "is_fully_covered": len(missing) == 0,
            "chapter_def_keys_min": int(keys_sorted[0]) if keys_sorted else None,
            "chapter_def_keys_max": int(keys_sorted[-1]) if keys_sorted else None,
            "chapter_def_keys_sample": sample_keys,
        }

    def _build_architecture_coverage_patch_from_full(
        self,
        full_architecture_text: str,
        missing_chapters: list[int],
    ) -> str:
        missing = [int(ch) for ch in missing_chapters if isinstance(ch, int)]
        if not missing:
            return ""

        extractor = self._get_architecture_extractor(full_architecture_text)
        raw_defs = extractor.structure.get("chapters", {})
        chapter_defs: dict[int, str] = raw_defs if isinstance(raw_defs, dict) else {}

        lines: list[str] = []
        for chapter in missing:
            snippet = str(chapter_defs.get(chapter, "") or "").strip()
            if not snippet:
                continue
            snippet = re.sub(r"\s+", " ", snippet).strip()
            if len(snippet) > 1500:
                snippet = snippet[:1500].rstrip()
            lines.append(f"第{chapter}章：{snippet}")

        return "\n".join(lines).strip()

    def _resolve_architecture_text_for_batch(
        self,
        runtime_architecture_text: str,
        full_architecture_text: str,
        start_chapter: int,
        end_chapter: int,
    ) -> dict[str, Any]:
        runtime_cov = self._analyze_architecture_chapter_coverage(
            runtime_architecture_text,
            start_chapter,
            end_chapter,
        )
        if runtime_cov.get("is_fully_covered") is True:
            return {
                "architecture_text": runtime_architecture_text,
                "coverage_source": "runtime",
                "preflight": runtime_cov,
                "resolved": runtime_cov,
            }

        full_text = str(full_architecture_text or "").strip()
        if not full_text:
            raise ArchitectureMappingGapError(
                f"架构映射缺失：第{start_chapter}章到第{end_chapter}章在运行时架构视图中无有效章节定义，且未提供完整架构文本",
                diagnostics={
                    "runtime": runtime_cov,
                },
            )

        patch = self._build_architecture_coverage_patch_from_full(
            full_architecture_text=full_text,
            missing_chapters=list(runtime_cov.get("missing_chapters") or []),
        )
        patched_text = runtime_architecture_text
        if patch:
            patched_text = (
                runtime_architecture_text.rstrip()
                + "\n\n## 999. 章节锁定补丁（自动）\n"
                + patch
                + "\n"
            )

        patched_cov = self._analyze_architecture_chapter_coverage(
            patched_text,
            start_chapter,
            end_chapter,
        )
        if patched_cov.get("is_fully_covered") is True:
            return {
                "architecture_text": patched_text,
                "coverage_source": "patched_from_full",
                "preflight": runtime_cov,
                "resolved": patched_cov,
            }

        full_cov = self._analyze_architecture_chapter_coverage(
            full_text,
            start_chapter,
            end_chapter,
        )
        if full_cov.get("is_fully_covered") is True:
            return {
                "architecture_text": full_text,
                "coverage_source": "full",
                "preflight": runtime_cov,
                "resolved": full_cov,
            }

        raise ArchitectureMappingGapError(
            f"架构映射缺失：第{start_chapter}章到第{end_chapter}章在运行时架构视图与完整架构中均未形成有效章节映射",
            diagnostics={
                "runtime": runtime_cov,
                "patched": patched_cov,
                "full": full_cov,
            },
        )

    def _load_state(self, filepath: str) -> dict[str, Any]:
        state_path = self._state_file_path(filepath)
        if not os.path.exists(state_path):
            return {}
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                return loaded
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logging.warning(f"⚠️ 读取蓝图状态文件失败（将重建）: {e}")
        return {}

    def _save_state(self, filepath: str, state: dict[str, Any]) -> None:
        state_path = self._state_file_path(filepath)
        try:
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except (OSError, json.JSONDecodeError) as e:
            logging.warning(f"⚠️ 写入蓝图状态文件失败: {e}")

    def _append_run_batch_telemetry(
        self,
        run_state: dict[str, Any],
        batch_telemetry: dict[str, Any],
        max_history: int = 30,
    ) -> None:
        if not isinstance(run_state, dict):
            return
        if not isinstance(batch_telemetry, dict) or not batch_telemetry:
            return

        attempts = batch_telemetry.get("attempts", [])
        attempt_count = batch_telemetry.get("attempt_count")
        if not isinstance(attempt_count, int):
            attempt_count = len(attempts) if isinstance(attempts, list) else 0

        retry_reasons = batch_telemetry.get("retry_reasons", [])
        if not isinstance(retry_reasons, list):
            retry_reasons = []

        success_attempt = batch_telemetry.get("success_attempt")
        summary = {
            "chapter_range": str(batch_telemetry.get("chapter_range", "")),
            "status": str(batch_telemetry.get("status", "")),
            "attempt_count": int(max(0, attempt_count)),
            "total_seconds": float(batch_telemetry.get("total_seconds") or 0.0),
            "retry_reasons": [str(item) for item in retry_reasons[:8]],
            "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if isinstance(success_attempt, int) and success_attempt > 0:
            summary["success_attempt"] = success_attempt

        if isinstance(attempts, list) and attempts:
            last_attempt = attempts[-1] if isinstance(attempts[-1], dict) else {}
            if isinstance(last_attempt, dict):
                coverage_source = str(last_attempt.get("coverage_source", "")).strip()
                if coverage_source:
                    summary["coverage_source"] = coverage_source
                missing_chapters = last_attempt.get("missing_chapters_preflight")
                if isinstance(missing_chapters, list):
                    summary["missing_chapters_preflight_count"] = len(missing_chapters)

        history = run_state.get("batch_telemetry_history")
        if not isinstance(history, list):
            history = []

        history.append(summary)
        run_state["batch_telemetry_history"] = history[-max_history:]
        run_state["last_batch_telemetry"] = summary

    def _find_task_card_file(self, filepath: str) -> str:
        """
        在项目目录中自动发现逐章任务卡CSV文件。
        优先使用常见标准命名，其次回退到模糊匹配。
        """
        preferred_names = [
            "逆命天书_逐章任务卡_v2.4.csv",
            "逆命天书_逐章任务卡_v2.5.csv",
            "逆命天书_逐章任务卡.csv",
            "逐章任务卡.csv",
        ]
        for name in preferred_names:
            candidate = os.path.join(filepath, name)
            if os.path.isfile(candidate):
                return candidate

        candidates: list[tuple[float, str]] = []
        try:
            for name in os.listdir(filepath):
                if "逐章任务卡" in name and name.lower().endswith(".csv"):
                    full = os.path.join(filepath, name)
                    if os.path.isfile(full):
                        candidates.append((os.path.getmtime(full), full))
        except OSError:
            return ""

        if not candidates:
            return ""
        candidates.sort(reverse=True)
        return candidates[0][1]

    def _load_task_card_records(self, filepath: str) -> dict[int, dict[str, str]]:
        """
        加载逐章任务卡CSV，返回 chapter -> row 映射。
        仅作为可选增强数据源，读取失败时返回空映射，不阻断主流程。
        """
        csv_path = self._find_task_card_file(filepath)
        if not csv_path:
            return {}

        try:
            mtime = os.path.getmtime(csv_path)
        except OSError:
            return {}

        if (
            self._task_card_cache.get("path") == csv_path
            and self._task_card_cache.get("mtime") == mtime
            and isinstance(self._task_card_cache.get("records"), dict)
        ):
            return self._task_card_cache["records"]

        records: dict[int, dict[str, str]] = {}
        try:
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    chapter_raw = str((row or {}).get("chapter", "")).strip()
                    if not chapter_raw.isdigit():
                        continue
                    chapter_num = int(chapter_raw)
                    clean_row = {str(k).strip(): str(v or "").strip() for k, v in row.items()}
                    records[chapter_num] = clean_row
        except (OSError, csv.Error, UnicodeDecodeError) as e:
            logging.warning(f"⚠️ 读取逐章任务卡失败（已忽略，不影响主流程）: {e}")
            return {}

        self._task_card_cache = {"path": csv_path, "mtime": mtime, "records": records}
        logging.info(f"📌 已加载任务卡: {os.path.basename(csv_path)} ({len(records)} 章)")
        return records

    def _build_task_card_guidance(self, filepath: str, start_chapter: int, end_chapter: int) -> str:
        """
        生成章节任务卡增强提示词，注入到当前批次的用户指导语中。
        """
        records = self._load_task_card_records(filepath)
        if not records:
            return ""

        lines = []
        for chapter in range(start_chapter, end_chapter + 1):
            row = records.get(chapter)
            if not row:
                continue

            details = []
            core_goal = row.get("core_goal", "")
            if core_goal:
                details.append(f"核心目标：{core_goal}")

            realm_stage = row.get("realm_stage", "")
            realm_substage = row.get("realm_substage", "")
            if realm_stage:
                realm_text = realm_stage if not realm_substage else f"{realm_stage}/{realm_substage}"
                details.append(f"九境：{realm_text}")

            combo = row.get("combo_2p1s", "")
            if combo:
                details.append(f"术法组合：{combo}")

            conflict_hint = row.get("conflict_hint", "")
            if conflict_hint:
                details.append(f"冲突优先：{conflict_hint}")

            trope_ban = row.get("trope_ban", "")
            if trope_ban:
                details.append(f"禁用桥段：{trope_ban}")

            if details:
                lines.append(f"- 第{chapter}章：" + "；".join(details))

        if not lines:
            return ""

        return (
            "\n### 章节任务卡（硬约束，优先级高于通用模板）\n"
            + "\n".join(lines)
            + "\n⚠️ 请严格遵守以上章节任务卡，不得偏离核心目标。\n"
        )

    def _invoke_with_heartbeat(self, prompt: str, stage_name: str, timeout_seconds: int | None = None) -> str:
        """
        调用 LLM 时输出心跳日志并支持阶段级超时。
        注意：超时后后台线程可能仍在运行，但主流程会进入重试分支。
        """
        effective_timeout = int(self.stage_timeout_seconds if timeout_seconds is None else timeout_seconds)
        result_box: list[str] = [""]
        error_box: list[Exception | None] = [None]

        def worker():
            try:
                raw = invoke_with_cleaning(self.llm_adapter, prompt)
                if raw is None:
                    result_box[0] = ""
                elif isinstance(raw, str):
                    result_box[0] = raw
                else:
                    result_box[0] = str(raw)
            except Exception as e:
                error_box[0] = e

        start_ts = time.time()
        t = threading.Thread(target=worker, daemon=True)
        t.start()

        next_heartbeat = self.heartbeat_interval_seconds
        while t.is_alive():
            elapsed = int(time.time() - start_ts)
            if elapsed >= effective_timeout:
                raise TimeoutError(
                    f"{stage_name} 超时（{elapsed}s >= {effective_timeout}s）"
                )
            if elapsed >= next_heartbeat:
                logging.info(f"⏳ {stage_name} 进行中... 已耗时 {elapsed}s")
                next_heartbeat += self.heartbeat_interval_seconds
            time.sleep(1)

        err = error_box[0]
        if err is not None:
            raise cast(Exception, err)

        elapsed = int(time.time() - start_ts)
        logging.info(f"✅ {stage_name} 完成，耗时 {elapsed}s")
        return result_box[0]

    def _run_with_heartbeat(self, fn, stage_name: str, timeout_seconds: int | None = None):
        """对任意可调用对象执行心跳监控和阶段超时。"""
        effective_timeout = int(self.stage_timeout_seconds if timeout_seconds is None else timeout_seconds)
        result_box: list[Any] = [None]
        error_box: list[Exception | None] = [None]

        def worker():
            try:
                result_box[0] = fn()
            except Exception as e:
                error_box[0] = e

        start_ts = time.time()
        t = threading.Thread(target=worker, daemon=True)
        t.start()

        next_heartbeat = self.heartbeat_interval_seconds
        while t.is_alive():
            elapsed = int(time.time() - start_ts)
            if elapsed >= effective_timeout:
                raise TimeoutError(
                    f"{stage_name} 超时（{elapsed}s >= {effective_timeout}s）"
                )
            if elapsed >= next_heartbeat:
                logging.info(f"⏳ {stage_name} 进行中... 已耗时 {elapsed}s")
                next_heartbeat += self.heartbeat_interval_seconds
            time.sleep(1)

        err = error_box[0]
        if err is not None:
            raise cast(Exception, err)
        elapsed = int(time.time() - start_ts)
        logging.info(f"✅ {stage_name} 完成，耗时 {elapsed}s")
        return result_box[0]

    def _init_llm_log(self, filepath: str, start_chapter: int, end_chapter: int):
        """初始化 LLM 对话日志文件"""
        from datetime import datetime

        try:
            # 创建日志目录
            self.llm_log_dir = os.path.join(filepath, "llm_conversation_logs")
            os.makedirs(self.llm_log_dir, exist_ok=True)

            # 创建日志文件名（按章节范围）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"llm_log_chapters_{start_chapter}-{end_chapter}_{timestamp}.md"
            self.current_log_file = os.path.join(self.llm_log_dir, log_filename)

            # 初始化日志内容
            self.llm_conversation_log = []

            # 写入日志头部
            header = f"""# LLM 对话日志 - 第{start_chapter}章到第{end_chapter}章

**生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**章节范围**: 第{start_chapter}章 - 第{end_chapter}章
**LLM模型**: {self.llm_model}
**温度参数**: {self.temperature}

---

"""
            with open(self.current_log_file, 'w', encoding='utf-8') as f:
                f.write(header)

            logging.info(f"🚨 LLM对话日志已初始化: {self.current_log_file}")
        except (OSError, UnicodeEncodeError) as e:
            logging.error(f"❌ 初始化LLM对话日志失败: {e}")
            self.current_log_file = None
            self.llm_log_dir = None

    def _log_llm_call(
        self,
        call_type: str,
        prompt: str,
        response: str,
        validation_result: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """记录单次LLM调用"""
        from datetime import datetime

        # 🚨 检查日志文件是否已初始化
        if not self.current_log_file:
            return

        timestamp = datetime.now().strftime("%H:%M:%S")

        log_entry = f"""## {call_type} - {timestamp}

### 📝 Prompt (提示词)
```
{prompt[:3000]}{"..." if len(prompt) > 3000 else ""}
```

### 🤖 Response (LLM响应)
```
{response[:5000]}{"..." if len(response) > 5000 else ""}
```

### 📊 元数据
"""

        # 添加元数据
        if metadata:
            for key, value in metadata.items():
                log_entry += f"- **{key}**: {value}\n"

        # 添加验证结果
        if validation_result:
            log_entry += f"\n### ✅ 验证结果\n"
            log_entry += f"- **是否通过**: {'✅ 是' if validation_result.get('is_valid') else '❌ 否'}\n"

            if validation_result.get('generated_chapters'):
                log_entry += f"- **生成的章节**: {validation_result['generated_chapters']}\n"

            if validation_result.get('errors'):
                log_entry += f"- **错误信息**:\n"
                for error in validation_result['errors']:
                    log_entry += f"  - {error}\n"

        log_entry += "\n---\n\n"

        # 追加到内存日志
        self.llm_conversation_log.append(log_entry)

        # 立即写入文件
        try:
            with open(self.current_log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            logging.info(f"📝 已记录LLM调用: {call_type}")
        except (OSError, UnicodeEncodeError) as e:
            logging.error(f"❌ 写入LLM调用日志失败: {e}")

    def _log_separator(self, title: str):
        """记录分隔符"""
        from datetime import datetime

        # 🚨 检查日志文件是否已初始化
        if not self.current_log_file:
            return

        separator = f"""
# {title} - {datetime.now().strftime("%H:%M:%S")}

---

"""
        try:
            with open(self.current_log_file, 'a', encoding='utf-8') as f:
                f.write(separator)
        except (OSError, UnicodeEncodeError) as e:
            logging.error(f"❌ 写入分隔符失败: {e}")

    def _save_llm_log(self):
        """保存当前批次日志到文件"""
        if not self.current_log_file:
            return

        # 追加所有日志到文件
        with open(self.current_log_file, 'a', encoding='utf-8') as f:
            f.write("\n".join(self.llm_conversation_log))

    def _finalize_llm_log(self, success: bool, error_message: str = ""):
        """完成日志文件，添加最终状态"""
        from datetime import datetime

        # 🚨 检查日志文件是否存在，避免因初始化失败导致文件不存在
        if not self.current_log_file or not os.path.exists(self.current_log_file):
            logging.warning(f"⚠️ 日志文件不存在，跳过完成日志写入: {self.current_log_file}")
            return

        status = "✅ 成功" if success else "❌ 失败"
        footer = f"""
# 🏁 生成完成 - {datetime.now().strftime("%H:%M:%S")}

**最终状态**: {status}
"""

        if error_message:
            footer += f"**错误信息**: {error_message}\n"

        footer += f"""
**日志条目数**: {len(self.llm_conversation_log)}
**结束时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

*本日志由 AI 小说生成工具自动生成*
"""

        try:
            with open(self.current_log_file, 'a', encoding='utf-8') as f:
                f.write(footer)
            logging.info(f"🚨 LLM对话日志已完成: {self.current_log_file} (状态: {status})")
        except (OSError, UnicodeEncodeError) as e:
            logging.error(f"❌ 写入日志文件失败: {e}")

    def _iter_chapter_payloads(self, content: str) -> list[dict[str, Any]]:
        """解析目录中的章节块，返回章节号/标题/正文块。"""
        if not content or not content.strip():
            return []
        header_pattern = re.compile(
            r"(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*([^\n*]+))?\s*(?:\*\*)?\s*$"
        )
        headers = list(header_pattern.finditer(content))
        payloads: list[dict[str, Any]] = []
        for idx, match in enumerate(headers):
            chapter_num = int(match.group(1))
            chapter_title = str(match.group(2) or "").strip()
            start = match.start()
            end = headers[idx + 1].start() if idx + 1 < len(headers) else len(content)
            block = content[start:end].strip()
            payloads.append(
                {
                    "chapter": chapter_num,
                    "title": chapter_title,
                    "block": block,
                    "start": start,
                    "end": end,
                }
            )
        return payloads

    def _detect_location_placeholder_tokens(self, location_text: str) -> list[str]:
        """
        检测“定位”字段中的占位词（第X卷/子幕X/卷名待定等）。
        返回命中标签列表（为空表示未命中）。
        """
        text = str(location_text or "").strip()
        if not text:
            return []

        checks: list[tuple[str, str]] = [
            ("第X卷", r"第\s*[XxＸｘ]\s*卷"),
            ("子幕X", r"子幕\s*[XxＸｘ]"),
            ("卷名待定", r"卷名\s*待定"),
            ("待定", r"(?:\[|\(|（)?\s*待定\s*(?:\]|\)|）)?"),
            ("TBD/TODO", r"\b(?:TBD|TODO)\b"),
        ]
        hits: list[str] = []
        for label, pattern in checks:
            if re.search(pattern, text, flags=re.IGNORECASE):
                hits.append(label)
        return hits

    def _collect_recent_title_conflicts(
        self,
        generated_content: str,
        existing_content: str,
        lookback: int = 120,
    ) -> list[str]:
        """
        检查本次新生成标题是否与最近N章重复。
        返回可直接写入 validation["errors"] 的错误信息列表。
        """
        generated_payloads = self._iter_chapter_payloads(generated_content)
        if not generated_payloads:
            return []

        existing_payloads = self._iter_chapter_payloads(existing_content)
        if not existing_payloads:
            return []

        recent_payloads = sorted(existing_payloads, key=lambda item: int(item.get("chapter", 0)))
        recent_payloads = recent_payloads[-max(1, int(lookback)):]
        recent_title_map: dict[str, list[int]] = {}
        for item in recent_payloads:
            title = str(item.get("title", "")).strip()
            chapter_num = int(item.get("chapter", 0))
            if not title or chapter_num <= 0:
                continue
            recent_title_map.setdefault(title, []).append(chapter_num)

        errors: list[str] = []
        for item in generated_payloads:
            chapter_num = int(item.get("chapter", 0))
            title = str(item.get("title", "")).strip()
            if chapter_num <= 0 or not title:
                continue
            repeated_in = recent_title_map.get(title, [])
            if not repeated_in:
                continue
            sample = "、".join(str(num) for num in repeated_in[-3:])
            errors.append(
                f"🚨 第{chapter_num}章标题重复：'{title}' 与近{lookback}章重复（已出现在第{sample}章）"
            )
        return errors

    def _strict_validation(self, content: str, expected_start: int, expected_end: int) -> dict:
        """
        严格验证：章节完整、结构完整、格式一致。
        """
        result = {
            "is_valid": True,
            "errors": [],
            "missing_chapters": [],
            "generated_chapters": []
        }

        if not content or not content.strip():
            result["is_valid"] = False
            result["errors"].append("🚨 生成内容为空")
            return result

        # 格式混乱检测：严格禁止“第 1 章”这类带空格标题
        loose_pattern = r"(?m)^[#*\s]*第\s+\d+\s+章"
        loose_matches = re.findall(loose_pattern, content)
        if loose_matches:
            result["is_valid"] = False
            result["errors"].append(
                f"🚨 检测到格式混乱：发现{len(loose_matches)}个章节使用了 `第 X 章` 格式，应为 `第X章`"
            )

        chapter_payloads = self._iter_chapter_payloads(content)
        if not chapter_payloads:
            result["is_valid"] = False
            result["errors"].append("🚨 未检测到章节标题（应为 `第X章 - 标题`）")
            return result

        chapter_blocks = [
            (int(item.get("chapter", 0)), str(item.get("block", "")).strip())
            for item in chapter_payloads
        ]

        generated_numbers = [num for num, _ in chapter_blocks]
        result["generated_chapters"] = sorted(set(generated_numbers))

        # 重复章节号硬失败
        duplicate_numbers = sorted({n for n in generated_numbers if generated_numbers.count(n) > 1})
        if duplicate_numbers:
            result["is_valid"] = False
            result["errors"].append(f"🚨 检测到重复章节号：{duplicate_numbers}")

        expected_numbers = set(range(expected_start, expected_end + 1))
        actual_numbers = set(generated_numbers)
        missing_chapters = sorted(expected_numbers - actual_numbers)
        if missing_chapters:
            result["is_valid"] = False
            result["missing_chapters"] = missing_chapters
            result["errors"].append(f"🚨 缺失章节：{missing_chapters}")

        out_of_range = sorted(actual_numbers - expected_numbers)
        if out_of_range:
            result["is_valid"] = False
            result["errors"].append(f"🚨 出现范围外章节：{out_of_range}")

        # 重复标题硬失败（同批内）
        title_map: dict[str, list[int]] = {}
        for item in chapter_payloads:
            chapter_num = int(item.get("chapter", 0))
            chapter_title = str(item.get("title", "")).strip()
            if chapter_num <= 0 or not chapter_title:
                continue
            title_map.setdefault(chapter_title, []).append(chapter_num)
        duplicate_titles = {
            title: chapters
            for title, chapters in title_map.items()
            if len(chapters) > 1
        }
        for title, chapters in sorted(duplicate_titles.items(), key=lambda item: len(item[1]), reverse=True)[:6]:
            chapter_text = "、".join(f"第{num}章" for num in sorted(chapters)[:8])
            result["is_valid"] = False
            result["errors"].append(f"🚨 章节标题重复：'{title}' 出现在 {chapter_text}")

        # 7节硬约束：每章必须出现且仅出现一次
        required_sections = [
            (1, "基础元信息"),
            (2, "张力与冲突"),
            (3, "匠心思维应用"),
            (4, "伏笔与信息差"),
            (5, "暧昧与修罗场"),
            (6, "剧情精要"),
            (7, "衔接设计"),
        ]

        for chapter_num, block in chapter_blocks:
            # 最低内容行数检查
            lines = [ln for ln in block.splitlines() if ln.strip()]
            if len(lines) < 12:
                result["is_valid"] = False
                result["errors"].append(f"🚨 第{chapter_num}章内容过少（仅{len(lines)}行）")

            for sec_num, sec_name in required_sections:
                sec_pattern = re.compile(
                    rf'(?m)^\s*(?:##\s*)?{sec_num}\.\s*{re.escape(sec_name)}\s*$'
                )
                matches = sec_pattern.findall(block)
                if len(matches) == 0:
                    result["is_valid"] = False
                    result["errors"].append(f"🚨 第{chapter_num}章缺失节：{sec_num}. {sec_name}")
                elif len(matches) > 1:
                    result["is_valid"] = False
                    result["errors"].append(f"🚨 第{chapter_num}章重复节：{sec_num}. {sec_name}")

            # 定位字段占位符硬失败（第X卷/子幕X/待定）
            location_value = self._extract_labeled_value(block, "定位")
            placeholder_hits = self._detect_location_placeholder_tokens(location_value)
            if placeholder_hits:
                result["is_valid"] = False
                result["errors"].append(
                    f"🚨 第{chapter_num}章定位含占位符：{','.join(placeholder_hits)}"
                )

        if result["is_valid"]:
            logging.info(
                f"✅ 验证通过：章节{expected_start}-{expected_end}结构完整，共{len(chapter_blocks)}章"
            )
        else:
            logging.warning(f"⚠️ 验证失败：{len(result['errors'])}个问题")

        return result

    def _promote_section1_metadata_block(self, chapter_block: str) -> tuple[str, bool]:
        if not chapter_block:
            return chapter_block, False

        section1_header_pattern = re.compile(r"(?m)^\s*(?:##\s*)?1\.\s*基础元信息\s*$")
        if section1_header_pattern.search(chapter_block):
            return chapter_block, False

        lines = chapter_block.splitlines()
        if len(lines) < 4:
            return chapter_block, False

        section_header_pattern = re.compile(r"^\s*(?:##\s*)?[1-7]\.\s*[^\n]+$")
        first_section_idx = len(lines)
        for idx, line in enumerate(lines):
            if section_header_pattern.match(line.strip()):
                first_section_idx = idx
                break

        if first_section_idx <= 1:
            return chapter_block, False

        metadata_line_pattern = re.compile(
            r"^\s*(?:[-*]\s*)?(?:\*\*)?\s*(章节序号|章节标题|定位|核心功能|字数目标|目标字数|出场角色)\s*(?:\*\*)?\s*[：:]\s*.+$"
        )
        metadata_indexes = []
        metadata_keys = set()
        for idx in range(1, first_section_idx):
            match = metadata_line_pattern.match(lines[idx])
            if not match:
                continue
            metadata_indexes.append(idx)
            metadata_keys.add(match.group(1))

        if len(metadata_keys) < 3:
            return chapter_block, False

        if not ({"章节标题", "定位", "核心功能"} & metadata_keys):
            return chapter_block, False

        insert_idx = metadata_indexes[0]
        rebuilt_lines = lines[:insert_idx]
        if rebuilt_lines and rebuilt_lines[-1].strip():
            rebuilt_lines.append("")
        rebuilt_lines.append("## 1. 基础元信息")
        rebuilt_lines.extend(lines[insert_idx:])
        return "\n".join(rebuilt_lines).strip(), True

    def _normalize_missing_sections(self, content: str, expected_start: int, expected_end: int) -> tuple[str, int]:
        """
        在验证前做结构兜底：若某章缺失 1-7 节中的任一节，自动补齐最小模板。
        仅补缺失节，不删除/重排原内容。
        """
        if not content or not content.strip():
            return content, 0

        header_pattern = re.compile(
            r'(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*([^\n*]+))?\s*(?:\*\*)?\s*$'
        )
        headers = list(header_pattern.finditer(content))
        if not headers:
            return content, 0

        section_templates = {
            1: "## 1. 基础元信息\n* **章节序号**：第X章\n* **章节标题**：[待完善]\n* **定位**：[待完善]\n* **核心功能**：[待完善]\n* **字数目标**：3000-5000字\n* **出场角色**：[待完善]",
            2: "## 2. 张力与冲突\n* **冲突类型**：[待完善]\n* **核心冲突点**：[待完善]\n* **紧张感曲线**：[铺垫→爬升→爆发→回落]",
            3: "## 3. 匠心思维应用\n* **应用场景**：[待完善]\n* **思维模式**：[待完善]\n* **视觉化描述**：[待完善]\n* **经典台词**：[待完善]",
            4: "## 4. 伏笔与信息差\n* **本章植入伏笔**：[待完善]\n* **本章回收伏笔**：[待完善]\n* **信息差控制**：[待完善]",
            5: "## 5. 暧昧与修罗场\n* **涉及的女性角色互动**：本章不涉及女性角色互动\n* **说明**：按格式保留该节",
            6: "## 6. 剧情精要\n* **开场**：[待完善]\n* **发展**：[待完善]\n* **高潮**：[待完善]\n* **收尾**：[待完善]",
            7: "## 7. 衔接设计\n* **承上**：[待完善]\n* **转场**：[待完善]\n* **启下**：[待完善]",
        }

        fixed_blocks = []
        fixes = 0
        section_header_pattern = re.compile(r'(?m)^\s*(?:##\s*)?([1-7])\.\s*[^\n]+$')

        for idx, match in enumerate(headers):
            chapter_num = int(match.group(1))
            start = match.start()
            end = headers[idx + 1].start() if idx + 1 < len(headers) else len(content)
            block = content[start:end].strip()

            if not (expected_start <= chapter_num <= expected_end):
                fixed_blocks.append(block)
                continue

            block, promoted_section1 = self._promote_section1_metadata_block(block)
            if promoted_section1:
                fixes += 1

            block, deduped_sections = self._dedupe_required_sections_in_block(block)
            if deduped_sections > 0:
                fixes += deduped_sections

            present_sections = {int(m.group(1)) for m in section_header_pattern.finditer(block)}
            missing_sections = [n for n in range(1, 8) if n not in present_sections]
            if missing_sections:
                fixes += len(missing_sections)
                block = block + "\n\n" + "\n\n".join(section_templates[n] for n in missing_sections)
            fixed_blocks.append(block)

        return "\n\n".join(fixed_blocks), fixes

    def _iter_chapter_blocks(self, content: str) -> list[tuple[int, int, int]]:
        if not content:
            return []

        header_pattern = re.compile(
            r"(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*[^\n*]+)?\s*(?:\*\*)?\s*$"
        )
        headers = list(header_pattern.finditer(content))
        if not headers:
            return []

        blocks: list[tuple[int, int, int]] = []
        for idx, match in enumerate(headers):
            chapter_num = int(match.group(1))
            start = match.start()
            end = headers[idx + 1].start() if idx + 1 < len(headers) else len(content)
            blocks.append((chapter_num, start, end))
        return blocks

    def _dedupe_required_sections_in_block(self, chapter_block: str) -> tuple[str, int]:
        if not chapter_block:
            return chapter_block, 0

        required_lookup = {
            1: "基础元信息",
            2: "张力与冲突",
            3: "匠心思维应用",
            4: "伏笔与信息差",
            5: "暧昧与修罗场",
            6: "剧情精要",
            7: "衔接设计",
        }
        section_pattern = re.compile(r"(?m)^\s*(?:##\s*)?([1-7])\.\s*([^\n]+?)\s*$")
        matches = list(section_pattern.finditer(chapter_block))
        if not matches:
            return chapter_block, 0

        rebuilt_parts: list[str] = []
        cursor = 0
        removed_duplicates = 0
        seen_required: set[tuple[int, str]] = set()

        for idx, match in enumerate(matches):
            seg_start = match.start()
            seg_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(chapter_block)

            if cursor < seg_start:
                rebuilt_parts.append(chapter_block[cursor:seg_start])

            section_num = int(match.group(1))
            section_name = match.group(2).strip()
            segment = chapter_block[seg_start:seg_end]

            canonical_name = required_lookup.get(section_num)
            if canonical_name and section_name == canonical_name:
                key = (section_num, canonical_name)
                if key in seen_required:
                    removed_duplicates += 1
                else:
                    seen_required.add(key)
                    rebuilt_parts.append(segment)
            else:
                rebuilt_parts.append(segment)

            cursor = seg_end

        if cursor < len(chapter_block):
            rebuilt_parts.append(chapter_block[cursor:])

        if removed_duplicates <= 0:
            return chapter_block, 0

        deduped = "".join(rebuilt_parts)
        deduped = re.sub(r"\n{4,}", "\n\n\n", deduped).strip()
        return deduped, removed_duplicates

    def _extract_chapter_titles_only(self, existing_content: str, max_chapters: int = 10) -> str:
        """
        从已有内容中仅提取章节标题，避免展示旧格式导致LLM模仿错误格式

        Args:
            existing_content: 已有的章节目录内容
            max_chapters: 最多提取多少章的标题

        Returns:
            格式化的章节标题列表字符串
        """
        if not existing_content:
            return ""

        import re

        # 匹配多种章节标题格式
        patterns = [
            r'^(第\d+章[：\s\-——]+.+?)(?:\n|$)',  # 第1章：标题 或 第1章 - 标题
            r'^第(\d+)章[：\s\-——]*(.+?)(?:\n|$)',  # 第1章标题
            r'^【(.+?)】.*?章节.*?[:：](.+?)(?:\n|$)',  # 【基础元信息】章节标题：xxx
        ]

        titles = []
        seen_chapters = set()

        for line in existing_content.split('\n'):
            line = line.strip()
            if not line:
                continue

            # 尝试匹配章节标题
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    # 提取章节号和标题
                    if '第' in line and '章' in line:
                        # 直接使用匹配到的完整标题行
                        title = line
                        # 提取章节号用于去重
                        chapter_match = re.search(r'第(\d+)章', title)
                        if chapter_match:
                            chapter_num = chapter_match.group(1)
                            if chapter_num not in seen_chapters:
                                seen_chapters.add(chapter_num)
                                titles.append(title)
                    break

            if len(titles) >= max_chapters:
                break

        if titles:
            # 返回简洁的标题列表
            result = "以下是已生成章节的标题列表（仅用于了解剧情连贯性）：\n"
            result += "\n".join(titles)
            return result
        else:
            # 如果无法提取标题，返回空字符串
            return ""


    def _auto_fix_missing_sections(self, content: str, validation_result: dict) -> tuple[str, bool]:
        """
        自动修复缺失的节，支持修复多个连续缺失的节

        增强版：可以修复如"第2章缺失: 暧昧与修罗场, 剧情精要, 衔接设计"这种情况
        """
        import re

        errors = validation_result.get("errors", [])
        section_errors = [e for e in errors if "节完整性检测" in e or "缺失:" in e]

        if not section_errors:
            return content, False

        logging.info("🔧 尝试自动修复缺失的节（增强版）...")

        # 定义所有可能的节模板
        section_templates = {
            5: ("暧昧与修罗场", """## 5. 暧昧与修罗场
*   **涉及的女性角色互动**：本章不涉及女性角色互动
*   **说明**：本章未涉及女性角色互动，保留此节以满足格式要求"""),
            6: ("剧情精要", """## 6. 剧情精要
*   **开场**：[开场场景]
*   **发展**：[剧情发展节点]
*   **高潮**：[高潮事件]
*   **收尾**：[结尾状态/悬念]"""),
            7: ("衔接设计", """## 7. 衔接设计
*   **承上**：[承接前文]
*   **转场**：[转场方式]
*   **启下**：[为后续埋下伏笔]""")
        }

        lines = content.split('\n')
        fixed_lines = []
        i = 0
        fixes_made = 0

        # 解析需要修复的章节和缺失的节
        chapters_to_fix = {}  # {章节号: 缺失的节列表}
        for error in section_errors:
            match = re.search(r'第(\d+)章缺失:\s*(.+)', error)
            if match:
                chapter_num = int(match.group(1))
                missing_sections = match.group(2).strip()
                # 解析缺失的节
                missing_list = [s.strip() for s in missing_sections.split(',')]
                chapters_to_fix[chapter_num] = missing_list

        if not chapters_to_fix:
            return content, False

        logging.info(f"📋 需要修复的章节: {list(chapters_to_fix.keys())}")
        for ch, secs in chapters_to_fix.items():
            logging.info(f"  第{ch}章缺失节: {secs}")

        current_chapter = None
        last_section = 0
        in_chapter = False

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # 检测章节标题
            chapter_match = re.match(r'^#{1,3}\s*\*{0,2}\s*第(\d+)章', stripped) or \
                           re.match(r'^\*{0,2}第(\d+)章', stripped)

            if chapter_match:
                current_chapter = int(chapter_match.group(1))
                last_section = 0
                in_chapter = True
                fixed_lines.append(line)
                i += 1
                continue

            # 检测节标题
            section_match = re.match(r'^##\s*(\d+)\.\s*(.+)', stripped)
            if section_match and in_chapter and current_chapter in chapters_to_fix:
                section_num = int(section_match.group(1))
                section_name = section_match.group(2).strip()

                # 检查是否需要插入缺失的节
                if section_num > 1:
                    missing_sections = chapters_to_fix[current_chapter]
                    for missing_num in range(last_section + 1, section_num):
                        if missing_num in section_templates:
                            missing_name, missing_template = section_templates[missing_num]
                            if any(missing_name in s for s in missing_sections):
                                logging.info(f"  🔧 在第{current_chapter}章第{last_section}节后插入第{missing_num}节（{missing_name}）")
                                fixed_lines.append("")
                                for template_line in missing_template.split('\n'):
                                    fixed_lines.append(template_line)
                                fixed_lines.append("")
                                fixes_made += 1

                last_section = section_num

            fixed_lines.append(line)
            i += 1

        if fixes_made > 0:
            fixed_content = '\n'.join(fixed_lines)
            logging.info(f"✅ 自动修复完成，共修复了 {fixes_made} 个节")
            return fixed_content, True
        else:
            logging.warning("⚠️ 无法自动修复")
            return content, False

    def _resolve_directory_validator_paths(self, filepath: str) -> tuple[str, str]:
        """Resolve validator and rules paths for final directory quality gate."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            (
                os.path.join(filepath, "autogen", "validate_directory_blueprint.py"),
                os.path.join(filepath, "autogen", "directory_quality_rules.json"),
            ),
            (
                os.path.join(repo_root, "autogen", "validate_directory_blueprint.py"),
                os.path.join(repo_root, "autogen", "directory_quality_rules.json"),
            ),
        ]

        for validator_path, rules_path in candidates:
            if os.path.exists(validator_path) and os.path.exists(rules_path):
                return validator_path, rules_path
        return "", ""

    def _run_builtin_directory_quality_gate(self, directory_file: str) -> tuple[bool, dict]:
        """Fallback quality gate used when external validator assets are unavailable."""
        content = read_file(directory_file).strip()
        if not content:
            report = {
                "passed": False,
                "summary": {
                    "total_chapters": 0,
                    "placeholder_count": 0,
                    "missing_section_chapter_count": 0,
                    "missing_section4_chapters": 0,
                    "missing_section5_chapters": 0,
                    "template_leak_count": 0,
                },
                "hard_fail_reasons": ["目录文件为空"],
                "rewrite_hints": ["重新生成目录内容后再发布"],
            }
            return False, report

        chapter_pattern = r"(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*[^\n]*)?\s*(?:\*\*)?\s*$"
        chapter_numbers = sorted({int(num) for num in re.findall(chapter_pattern, content)})
        if not chapter_numbers:
            report = {
                "passed": False,
                "summary": {
                    "total_chapters": 0,
                    "placeholder_count": 0,
                    "missing_section_chapter_count": 0,
                    "missing_section4_chapters": 0,
                    "missing_section5_chapters": 0,
                    "template_leak_count": 0,
                },
                "hard_fail_reasons": ["未检测到有效章节标题"],
                "rewrite_hints": ["确保目录使用“第X章 - 标题”格式"],
            }
            return False, report

        validation = self._strict_validation(content, 1, chapter_numbers[-1])
        hard_fail_reasons = list(validation.get("errors", []))

        placeholder_patterns = [
            r"\bTODO\b",
            r"\bTBD\b",
            r"待补",
            r"待完善",
            r"此处省略",
            r"(?m)^\s*(?:\.\.\.|…{2,}|（略）)\s*$",
            r"【占位】",
        ]
        placeholder_count = 0
        for pattern in placeholder_patterns:
            placeholder_count += len(re.findall(pattern, content, flags=re.IGNORECASE))
        if placeholder_count > 0:
            hard_fail_reasons.append(f"检测到占位/省略痕迹 {placeholder_count} 处")

        chapter_payloads = self._iter_chapter_payloads(content)
        location_placeholder_chapters: list[int] = []
        title_map: dict[str, list[int]] = {}
        for payload in chapter_payloads:
            chapter_num = int(payload.get("chapter", 0))
            chapter_title = str(payload.get("title", "")).strip()
            chapter_block = str(payload.get("block", ""))
            if chapter_num <= 0:
                continue

            location_value = self._extract_labeled_value(chapter_block, "定位")
            location_placeholder_hits = self._detect_location_placeholder_tokens(location_value)
            if location_placeholder_hits:
                location_placeholder_chapters.append(chapter_num)

            if chapter_title:
                title_map.setdefault(chapter_title, []).append(chapter_num)

        if location_placeholder_chapters:
            chapter_hint = "、".join(f"第{num}章" for num in location_placeholder_chapters[:8])
            hard_fail_reasons.append(f"定位字段含占位符：{chapter_hint}")

        duplicate_title_groups = {
            title: sorted(chapters)
            for title, chapters in title_map.items()
            if len(chapters) > 1
        }
        if duplicate_title_groups:
            top_title, chapters = next(
                iter(
                    sorted(
                        duplicate_title_groups.items(),
                        key=lambda item: len(item[1]),
                        reverse=True,
                    )
                )
            )
            chapter_hint = "、".join(f"第{num}章" for num in chapters[:8])
            hard_fail_reasons.append(f"章节标题重复：'{top_title}' 出现在 {chapter_hint}")

        missing_section_chapters = set()
        missing_section4 = set()
        missing_section5 = set()
        for err in validation.get("errors", []):
            match = re.search(r"第(\d+)章缺失节：(\d+)\.", str(err))
            if not match:
                continue
            chapter_num = int(match.group(1))
            section_num = int(match.group(2))
            missing_section_chapters.add(chapter_num)
            if section_num == 4:
                missing_section4.add(chapter_num)
            elif section_num == 5:
                missing_section5.add(chapter_num)

        passed = len(hard_fail_reasons) == 0
        rewrite_hints = []
        if not passed:
            rewrite_hints = [
                "按章节模板补齐缺失节并重新校验",
                "移除占位符/省略语句后重新生成",
                "定位字段必须使用真实卷/子幕，不得出现第X卷或待定",
                "重复标题请改为有辨识度的新标题",
            ]
        report = {
            "passed": passed,
            "summary": {
                "total_chapters": len(chapter_numbers),
                "placeholder_count": placeholder_count,
                "missing_section_chapter_count": len(missing_section_chapters),
                "missing_section4_chapters": len(missing_section4),
                "missing_section5_chapters": len(missing_section5),
                "template_leak_count": 0,
                "location_placeholder_chapter_count": len(location_placeholder_chapters),
                "duplicate_title_group_count": len(duplicate_title_groups),
            },
            "hard_fail_reasons": hard_fail_reasons,
            "rewrite_hints": rewrite_hints,
        }
        return passed, report

    def _run_transition_recovery_gate(self, filepath: str, directory_content: str) -> tuple[bool, dict]:
        """
        跨章过渡守卫：重点拦截“上章受伤 -> 下章直接战斗（无恢复）”。
        返回 (passed, report)。
        """
        payloads = self._iter_chapter_payloads(directory_content)
        if len(payloads) < 2:
            return True, {"passed": True, "issues": [], "hard_fail_reasons": [], "rewrite_hints": []}

        try:
            from novel_generator.coherence_checker import CoherenceChecker
        except ImportError:
            return True, {
                "passed": True,
                "issues": [],
                "hard_fail_reasons": [],
                "rewrite_hints": [],
            }

        checker = CoherenceChecker(filepath)
        chapters = [
            {
                "chapter_number": int(item.get("chapter", 0)),
                "content": str(item.get("block", "")),
            }
            for item in payloads
            if int(item.get("chapter", 0)) > 0 and str(item.get("block", "")).strip()
        ]
        if len(chapters) < 2:
            return True, {"passed": True, "issues": [], "hard_fail_reasons": [], "rewrite_hints": []}

        try:
            coherence_result = checker.check_all_chapters(chapters)
        except Exception as e:
            return False, {
                "passed": False,
                "issues": [],
                "hard_fail_reasons": [f"衔接守卫执行失败: {e}"],
                "rewrite_hints": ["检查章节衔接检测模块并重试"],
            }

        raw_issues = coherence_result.get("issues", []) if isinstance(coherence_result, dict) else []
        transition_issues: list[dict[str, Any]] = []
        for item in raw_issues:
            if isinstance(item, dict):
                issue_type = str(item.get("issue_type", "")).strip()
                description = str(item.get("description", "")).strip()
                chapter_pair = item.get("chapter_pair", (0, 0))
            else:
                issue_type = str(getattr(item, "issue_type", "")).strip()
                description = str(getattr(item, "description", "")).strip()
                chapter_pair = getattr(item, "chapter_pair", (0, 0))

            if issue_type != "character_inconsistency":
                continue
            if "上章受伤" not in description or "本章直接战斗" not in description:
                continue
            if isinstance(chapter_pair, list):
                chapter_pair = tuple(chapter_pair)
            transition_issues.append(
                {
                    "issue_type": issue_type,
                    "description": description,
                    "chapter_pair": chapter_pair,
                }
            )

        hard_fail_reasons: list[str] = []
        for issue in transition_issues[:8]:
            chapter_pair = issue.get("chapter_pair", (0, 0))
            if not isinstance(chapter_pair, tuple) or len(chapter_pair) != 2:
                chapter_pair = (0, 0)
            prev_ch, curr_ch = chapter_pair
            hard_fail_reasons.append(
                f"第{prev_ch}章→第{curr_ch}章衔接风险：上章受伤后直接战斗，缺少恢复过渡"
            )

        passed = len(hard_fail_reasons) == 0
        rewrite_hints: list[str] = []
        if not passed:
            rewrite_hints = [
                "在下一章开场补充伤势恢复/带伤作战说明",
                "承上段需明确治疗、调息或代价承受过程",
            ]

        return passed, {
            "passed": passed,
            "issues": transition_issues,
            "hard_fail_reasons": hard_fail_reasons,
            "rewrite_hints": rewrite_hints,
        }

    def _run_directory_quality_gate(self, filepath: str, directory_file: str) -> tuple[bool, dict]:
        """
        Run final directory quality validation as the release gate.
        Returns:
            (passed, report)
        """
        validator_path, rules_path = self._resolve_directory_validator_paths(filepath)
        if not validator_path or not rules_path:
            logging.warning("⚠️ 外部目录质量校验器缺失，启用内置校验兜底")
            base_passed, report = self._run_builtin_directory_quality_gate(directory_file)
        else:
            report_out = os.path.join(filepath, "autogen", "examples", "directory.report.json")
            try:
                os.makedirs(os.path.dirname(report_out), exist_ok=True)
            except OSError:
                report_out = os.path.join(filepath, "directory.report.json")

            cmd = [
                sys.executable,
                validator_path,
                "--directory",
                directory_file,
                "--rules",
                rules_path,
                "--out",
                report_out,
                "--failed-only",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                stderr = (proc.stderr or "").strip()
                stdout = (proc.stdout or "").strip()
                raise RuntimeError(f"目录质量校验执行失败: {stderr or stdout or 'unknown error'}")

            report = {}
            try:
                with open(report_out, "r", encoding="utf-8") as f:
                    report = json.load(f)
            except (OSError, json.JSONDecodeError):
                try:
                    report = json.loads(proc.stdout)
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"目录质量报告解析失败: {e}") from e

            base_passed = bool(report.get("passed", False))

        # 无论是否命中外部校验器，都叠加内置补充守卫（定位占位/标题重复等）
        builtin_passed, builtin_report = self._run_builtin_directory_quality_gate(directory_file)
        report_summary = report.setdefault("summary", {})
        builtin_summary = builtin_report.get("summary", {}) if isinstance(builtin_report, dict) else {}
        for key, value in builtin_summary.items():
            if key not in report_summary:
                report_summary[key] = value

        hard_fail_reasons = report.setdefault("hard_fail_reasons", [])
        for reason in builtin_report.get("hard_fail_reasons", []) if isinstance(builtin_report, dict) else []:
            if reason not in hard_fail_reasons:
                hard_fail_reasons.append(reason)

        rewrite_hints = report.setdefault("rewrite_hints", [])
        for hint in builtin_report.get("rewrite_hints", []) if isinstance(builtin_report, dict) else []:
            if hint not in rewrite_hints:
                rewrite_hints.append(hint)

        directory_content = read_file(directory_file).strip()
        transition_passed, transition_report = self._run_transition_recovery_gate(
            filepath=filepath,
            directory_content=directory_content,
        )
        report_summary["transition_violation_count"] = len(
            transition_report.get("hard_fail_reasons", []) or []
        )
        for reason in transition_report.get("hard_fail_reasons", []) or []:
            if reason not in hard_fail_reasons:
                hard_fail_reasons.append(reason)
        for hint in transition_report.get("rewrite_hints", []) or []:
            if hint not in rewrite_hints:
                rewrite_hints.append(hint)

        entity_passed, entity_report = self._run_entity_consistency_gate(
            filepath=filepath,
            directory_content=directory_content,
        )

        report_summary["entity_violation_count"] = len(entity_report.get("hard_fail_reasons", []) or [])
        report_summary["entity_protagonist"] = entity_report.get("protagonist", "")
        report_summary["entity_female_leads"] = len(entity_report.get("female_leads", []) or [])

        for reason in entity_report.get("hard_fail_reasons", []) or []:
            if reason not in hard_fail_reasons:
                hard_fail_reasons.append(reason)

        for hint in entity_report.get("rewrite_hints", []) or []:
            if hint not in rewrite_hints:
                rewrite_hints.append(hint)

        passed = bool(base_passed and builtin_passed and entity_passed and transition_passed)
        report["passed"] = passed
        return passed, report

    def _run_entity_consistency_gate(self, filepath: str, directory_content: str) -> tuple[bool, dict]:
        arch_file = resolve_architecture_file(filepath)
        if not os.path.exists(arch_file):
            return False, {
                "passed": False,
                "protagonist": "",
                "female_leads": [],
                "hard_fail_reasons": ["缺少架构文件（Novel_architecture.txt），无法执行实体一致性闸门"],
                "rewrite_hints": ["先补齐架构文件后再执行目录发布校验"],
            }

        architecture_text = build_runtime_architecture_view(read_file(arch_file).strip())
        if not architecture_text:
            return False, {
                "passed": False,
                "protagonist": "",
                "female_leads": [],
                "hard_fail_reasons": ["架构文件为空，无法执行实体一致性闸门"],
                "rewrite_hints": ["重新生成或恢复架构内容后再校验"],
            }
        if contains_archive_sections(architecture_text):
            return False, {
                "passed": False,
                "protagonist": "",
                "female_leads": [],
                "hard_fail_reasons": ["运行时架构视图含归档节（13-87），已阻断实体一致性闸门"],
                "rewrite_hints": ["检查架构切片逻辑，仅允许0-12和88-136进入运行时"],
            }

        protagonist, female_leads = self._extract_architecture_entities(architecture_text)
        hard_fail_reasons: list[str] = []

        if not protagonist:
            hard_fail_reasons.append("架构中未识别到主角实名，无法完成实体一致性校验")
        elif protagonist not in directory_content:
            hard_fail_reasons.append(f"目录未出现架构主角实名：{protagonist}")

        all_lines = [line.strip() for line in directory_content.splitlines()]
        for idx, line in enumerate(all_lines):
            if "涉及的女性角色互动" not in line:
                continue

            evidence_lines = [line]
            for look_ahead in range(idx + 1, min(len(all_lines), idx + 5)):
                next_line = all_lines[look_ahead]
                if not next_line:
                    continue
                if re.match(r"^(?:第\s*\d+\s*章|##\s*[1-7]\.\s*)", next_line):
                    break
                evidence_lines.append(next_line)

            evidence_text = " ".join(evidence_lines)
            if "不涉及" in evidence_text:
                continue

            if female_leads and not any(name in evidence_text for name in female_leads):
                hard_fail_reasons.append("检测到女性互动描述，但未命中架构女主实名")
                break

        if "三轨九术" in architecture_text:
            legacy_terms = ["五脉", "道脉", "巫脉", "魔脉", "释脉", "儒脉"]
            legacy_hits = [term for term in legacy_terms if term in directory_content]
            if len(legacy_hits) >= 2:
                hard_fail_reasons.append(
                    "目录出现旧体系术语污染（命中：" + "、".join(legacy_hits[:4]) + "）"
                )

        key_terms = [term for term in ("天书", "命轨", "改命") if term in architecture_text]
        if key_terms and not any(term in directory_content for term in key_terms):
            hard_fail_reasons.append("目录未体现架构关键术语（天书/命轨/改命）")

        passed = len(hard_fail_reasons) == 0
        rewrite_hints: list[str] = []
        if not passed:
            rewrite_hints = [
                "确保章节内容沿用架构实名，不得改名或替换旧模板人名",
                "第5节涉及女性互动时，必须使用架构女主实名",
                "沿用架构关键术语并清除旧体系词汇污染",
            ]

        return passed, {
            "passed": passed,
            "protagonist": protagonist,
            "female_leads": female_leads,
            "hard_fail_reasons": hard_fail_reasons,
            "rewrite_hints": rewrite_hints,
        }


    def _create_strict_prompt_with_guide(
        self,
        architecture_text: str,
        context_guide: str | None,
        chapter_list: str | None,
        start_chapter: int,
        end_chapter: int,
        user_guidance: str | None = "",
        project_path: str = "",
    ) -> str:
        """
        创建严格提示词 (两阶段版) - 使用 Context Guide 替代完整架构
        """
        chapter_count = end_chapter - start_chapter + 1
        safe_context_guide = (context_guide or "").strip() or "（无）"
        safe_chapter_list = (chapter_list or "").strip() or "（无）"
        safe_user_guidance = (user_guidance or "").strip()
        novel_title = self._extract_novel_title_from_architecture(architecture_text, project_path)

        return STEP2_GUIDED_STRICT_BLUEPRINT_PROMPT.format(
            novel_title=novel_title,
            start_chapter=start_chapter,
            end_chapter=end_chapter,
            chapter_count=chapter_count,
            context_guide=safe_context_guide,
            chapter_list=safe_chapter_list,
            user_guidance=safe_user_guidance,
            blueprint_example=BLUEPRINT_EXAMPLE_V3.strip(),
        )

    def _extract_novel_title_from_architecture(self, architecture_text: str, project_path: str = "") -> str:
        text = str(architecture_text or "")
        explicit_patterns = [
            r"(?m)^\s*(?:小说名|书名|作品名|项目名|小说标题|作品标题|标题)\s*[：:]\s*《?([^《》\n]{1,40})》?\s*$",
            r"(?m)^\s*#+\s*(?:小说|作品)\s*[：:]\s*《?([^《》\n]{1,40})》?\s*$",
            r"(?m)^\s*#+\s*《([^》\n]{1,40})》\s*(?:小说|项目|架构|设定)?\s*$",
            r"(?m)^\s*《([^》\n]{1,40})》\s*$",
        ]
        for pattern in explicit_patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            normalized = self._normalize_novel_title_candidate(match.group(1))
            if normalized:
                return normalized

        project_title = self._extract_novel_title_from_project_path(project_path)
        if project_title:
            return project_title
        return "本书"

    def _normalize_novel_title_candidate(self, raw_title: str) -> str:
        candidate = str(raw_title or "").strip()
        candidate = candidate.strip("《》「」『』\"'“”‘’")
        candidate = re.sub(r"\s+", "", candidate)
        if not candidate or len(candidate) < 2 or len(candidate) > 24:
            return ""
        if re.fullmatch(r"\d+", candidate):
            return ""

        banned_fragments = (
            "参考",
            "借鉴",
            "模板",
            "卷",
            "章",
            "情节点",
            "白名单",
            "架构",
            "总表",
            "执行",
        )
        if any(fragment in candidate for fragment in banned_fragments):
            return ""
        return candidate

    def _extract_novel_title_from_project_path(self, project_path: str) -> str:
        normalized_path = str(project_path or "").strip()
        if not normalized_path:
            return ""
        base_name = os.path.basename(os.path.normpath(normalized_path))
        if not base_name:
            return ""

        candidate = re.sub(r"[_\-\s]+", "", base_name)
        if not re.search(r"[\u4e00-\u9fff]", candidate):
            return ""
        return self._normalize_novel_title_candidate(candidate)

    def _context_guide_is_usable(self, context_guide: str | None) -> bool:
        if not context_guide:
            return False
        text = context_guide.strip()
        if len(text) < 80:
            return False
        blocked_markers = [
            "输入资料",
            "为空白",
            "无法为您生成",
            "无法提取",
            "补充上述空白资料",
            "基于假设数据",
            "模拟数据",
            "示范性蓝图指南",
            "语境萃取失败",
        ]
        return not any(marker in text for marker in blocked_markers)

    def _build_context_guide_fallback(self, architecture_text: str, start_chapter: int, end_chapter: int) -> str:
        protagonist, female_leads = self._extract_architecture_entities(architecture_text)
        lines = architecture_text.splitlines()
        chapter_range_pattern = re.compile(r"(\d+)\s*[-~—–至到]\s*(\d+)\s*章")
        chapter_event_lines: list[str] = []

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            match = chapter_range_pattern.search(line)
            if not match:
                continue
            range_start = int(match.group(1))
            range_end = int(match.group(2))
            if range_end < range_start:
                range_start, range_end = range_end, range_start
            if range_end < start_chapter or range_start > end_chapter:
                continue
            chapter_event_lines.append(line)
            if len(chapter_event_lines) >= 18:
                break

        guide_parts: list[str] = [
            f"目标章节：第{start_chapter}章-第{end_chapter}章",
            f"主角实名：{protagonist or '未识别'}",
        ]
        if female_leads:
            guide_parts.append("关键女性角色：" + "、".join(female_leads[:6]))
        if chapter_event_lines:
            guide_parts.append("章节锁定摘要：")
            guide_parts.extend([f"- {line}" for line in chapter_event_lines])

        if len(guide_parts) <= 2:
            fallback_excerpt = architecture_text[:6000].strip()
            if fallback_excerpt:
                guide_parts.append("架构节选：")
                guide_parts.append(fallback_excerpt)

        return "\n".join(guide_parts).strip()

    def _extract_architecture_entities(self, architecture_text: str) -> tuple[str, list[str]]:
        protagonist = ""
        protagonist_patterns = [
            r"主角实名[：:]\s*([^\s（(，。,；;]+)",
            r"主角[：:]\s*([^\s（(，。,；;]+)",
            r"###\s*角色一[：:]\s*([^\s（(，。,；;]+)",
        ]
        for pattern in protagonist_patterns:
            match = re.search(pattern, architecture_text)
            if match:
                protagonist = match.group(1).strip()
                break

        female_names = re.findall(
            r"(?m)^\s*\d+\.\s*([^\s（(，。,；;]{2,6})（[^）\n]{0,8}线）",
            architecture_text,
        )
        if not female_names:
            female_names = re.findall(
                r"(?m)^\s*女主[一二三四五六七八九十\d]*[：:]\s*([^\s（(，。,；;]+)",
                architecture_text,
            )
        female_leads: list[str] = []
        noise_fragments = ("协作", "系统", "源海", "阵营", "税制", "规则", "路线")
        for name in female_names:
            normalized = name.strip()
            if any(fragment in normalized for fragment in noise_fragments):
                continue
            if normalized and normalized not in female_leads:
                female_leads.append(normalized)

        return protagonist, female_leads

    def _normalize_consistency_text(self, text: str) -> str:
        normalized = str(text or "").strip()
        replacements = {
            "陨落": "身死",
            "殒落": "身死",
            "殒命": "身死",
            "死亡": "身死",
            "显化": "显字",
            "显现": "显字",
            "首次": "第一次",
            "首度": "第一次",
        }
        for source, target in replacements.items():
            normalized = normalized.replace(source, target)
        return normalized

    def _slice_architecture_event_focus(self, architecture_snippet: str) -> str:
        text = str(architecture_snippet or "").strip()
        if not text:
            return ""
        text = re.sub(r"^\s*\d+\.\s*", "", text)
        text = re.sub(r"^\s*(?:第\s*)?\d+\s*[-~—–至到]\s*\d+\s*章[：:]\s*", "", text)
        text = re.split(r"(?:功能|回报/?代价|代价|后续作用|作用)\s*[：:]", text, maxsplit=1)[0]
        return text.strip(" \t，。；;")

    def _extract_consistency_keywords(self, architecture_snippet: str, stopwords: set[str]) -> list[str]:
        focus_text = self._slice_architecture_event_focus(architecture_snippet)
        if not focus_text:
            focus_text = str(architecture_snippet or "").strip()

        keywords: list[str] = []
        phrase_candidates = re.split(r"[，。；;、]", focus_text)

        for phrase in phrase_candidates:
            cleaned = phrase.strip()
            if not cleaned:
                continue
            cleaned = re.sub(r"^\s*(?:第\s*)?\d+\s*[-~—–至到]\s*\d+\s*章[：:]\s*", "", cleaned)
            cleaned = re.sub(r"^\s*第\s*\d+\s*章[：:]\s*", "", cleaned)
            cleaned = cleaned.strip()
            if not cleaned:
                continue

            if re.search(r"[\u4e00-\u9fff]{2,}", cleaned) and cleaned not in keywords:
                keywords.append(cleaned)

            for token in re.findall(r"[\u4e00-\u9fff]{2,4}", cleaned):
                if token in stopwords:
                    continue
                if token not in keywords:
                    keywords.append(token)

            if len(keywords) >= 8:
                break

        if not keywords:
            for token in re.findall(r"[\u4e00-\u9fff]{2,8}", focus_text):
                if token in stopwords:
                    continue
                if token not in keywords:
                    keywords.append(token)
                if len(keywords) >= 8:
                    break

        return keywords[:8]

    def _extract_section_block(self, chapter_content: str, section_num: int) -> str:
        start_match = re.search(
            rf"(?m)^\s*(?:##\s*)?{section_num}\.\s*[^\n]+$",
            chapter_content,
        )
        if not start_match:
            return ""

        tail = chapter_content[start_match.end():]
        next_match = re.search(r"(?m)^\s*(?:##\s*)?[1-7]\.\s*[^\n]+$", tail)
        if next_match:
            return tail[:next_match.start()].strip()
        return tail.strip()

    def _extract_progression_focus_text(self, chapter_content: str) -> str:
        labels = (
            "核心功能",
            "核心冲突点",
            "本章植入伏笔",
            "本章回收伏笔",
            "开场",
            "发展",
            "高潮",
            "收尾",
        )

        focus_lines: list[str] = []

        def _collect_lines(text: str) -> None:
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                normalized = re.sub(r"^\*+\s*", "", line)
                normalized = normalized.replace("**", "").strip()

                for label in labels:
                    if normalized.startswith(f"{label}：") or normalized.startswith(f"{label}:"):
                        value = re.sub(rf"^{label}[：:]\s*", "", normalized).strip()
                        if value:
                            focus_lines.append(value)
                        break

        _collect_lines(chapter_content)

        section_six = self._extract_section_block(chapter_content, 6)
        if section_six:
            _collect_lines(section_six)
            if len(focus_lines) < 4:
                for raw_line in section_six.splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    normalized = re.sub(r"^\*+\s*", "", line)
                    normalized = normalized.replace("**", "").strip()
                    normalized = re.sub(r"^(?:节点\d+|节点[一二三四五六七八九十])[：:]\s*", "", normalized)
                    normalized = re.sub(r"^(?:开场|发展|高潮|收尾)[：:]\s*", "", normalized)
                    if len(normalized) < 6:
                        continue
                    focus_lines.append(normalized)
                    if len(focus_lines) >= 10:
                        break

        if not focus_lines:
            fallback = [line.strip() for line in chapter_content.splitlines() if line.strip()]
            focus_lines = fallback[:8]

        return "\n".join(focus_lines[:12]).strip()

    def _extract_labeled_value(self, text: str, label: str) -> str:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            normalized = re.sub(r"^\*+\s*", "", line)
            normalized = normalized.replace("**", "").strip()
            if normalized.startswith(f"{label}：") or normalized.startswith(f"{label}:"):
                return re.sub(rf"^{label}[：:]\s*", "", normalized).strip()
        return ""

    def _normalize_consistency_anchor_keyword(self, keyword: str) -> str:
        text = str(keyword or "").strip()
        if not text:
            return ""
        text = re.sub(r"^[\-•·\s]*\d+\.\s*", "", text)
        text = re.sub(r"^\s*(?:第\s*)?\d+\s*[-~—–至到]\s*\d+\s*章[：:]\s*", "", text)
        text = text.strip(" \t，。；;、")
        return text

    def _inject_required_keywords_into_chapter(
        self,
        chapter_content: str,
        required_keywords: list[str],
        *,
        max_keywords: int = 3,
    ) -> tuple[str, int]:
        """
        本地兜底：向章节文本注入少量“架构锚点关键词”，降低一致性误杀导致的重试雪崩。
        """
        content = str(chapter_content or "").strip()
        if not content or not isinstance(required_keywords, list):
            return content, 0

        normalized_content = self._normalize_consistency_text(content)
        candidates: list[str] = []
        for raw_keyword in required_keywords:
            normalized_keyword = self._normalize_consistency_anchor_keyword(str(raw_keyword))
            if not normalized_keyword:
                continue
            if len(normalized_keyword) < 2:
                continue
            if normalized_keyword in candidates:
                continue
            if normalized_keyword in normalized_content:
                continue
            candidates.append(normalized_keyword)
            if len(candidates) >= max(1, int(max_keywords)):
                break

        if not candidates:
            return content, 0

        anchor_line = f"* **架构锚点补全**：{'；'.join(candidates)}"
        if "## 6. 剧情精要" in content:
            content = re.sub(
                r"(?m)^(##\s*7\.\s*衔接设计\s*)$",
                anchor_line + "\n\n" + r"\1",
                content,
                count=1,
            )
            if anchor_line not in content:
                content = content.rstrip() + "\n\n" + anchor_line
        else:
            content = content.rstrip() + "\n\n" + anchor_line

        return content.strip(), len(candidates)

    def _patch_consistency_keyword_gaps(
        self,
        batch_content: str,
        consistency_issues: list[dict[str, Any]],
    ) -> tuple[str, int]:
        """
        基于一致性问题列表，按章节注入关键词锚点。
        返回：(修补后的文本, 注入次数)
        """
        content = str(batch_content or "")
        if not content or not isinstance(consistency_issues, list):
            return content, 0

        injected_total = 0
        updated_content = content
        for issue in consistency_issues:
            if not isinstance(issue, dict):
                continue
            required_keywords = issue.get("required_keywords")
            if not isinstance(required_keywords, list) or not required_keywords:
                continue
            chapter_label = str(issue.get("chapter", ""))
            chapter_match = re.search(r"第\s*(\d+)\s*章", chapter_label)
            if not chapter_match:
                continue
            chapter_num = int(chapter_match.group(1))
            chapter_block = self._extract_single_chapter(updated_content, chapter_num)
            if not chapter_block:
                continue

            patched_block, injected_count = self._inject_required_keywords_into_chapter(
                chapter_block,
                required_keywords,
                max_keywords=3,
            )
            if injected_count <= 0 or not patched_block:
                continue

            updated_content = self._replace_chapter_content(updated_content, chapter_num, patched_block)
            injected_total += injected_count

        return updated_content, injected_total

    def _extract_progression_tokens(self, chapter_content: str, stopwords: set[str]) -> list[str]:
        focus_text = self._extract_progression_focus_text(chapter_content)
        normalized = self._normalize_consistency_text(focus_text)
        progression_noise = set(stopwords) | {
            "章节",
            "本章",
            "主角",
            "核心",
            "功能",
            "剧情",
            "冲突",
            "角色",
            "信息",
            "设计",
            "张力",
            "开场",
            "发展",
            "高潮",
            "收尾",
            "衔接",
            "说明",
            "定位",
            "字数",
            "目标",
            "涉及",
            "互动",
            "状态",
            "场景",
            "章节标题",
            "章节序号",
            "本章回收",
            "本章植入",
            "转场",
            "承上",
            "启下",
            "写法",
            "错误写法",
            "正确写法",
        }

        tokens: list[str] = []
        for token in re.findall(r"[\u4e00-\u9fff]{2,6}", normalized):
            if token in progression_noise:
                continue
            if token not in tokens:
                tokens.append(token)
            if len(tokens) >= 24:
                break

        return tokens

    def _compute_token_jaccard(self, tokens_a: list[str], tokens_b: list[str]) -> tuple[float, list[str]]:
        set_a = {token for token in tokens_a if token}
        set_b = {token for token in tokens_b if token}
        if not set_a or not set_b:
            return 0.0, []

        overlap = sorted(set_a & set_b, key=lambda token: (-len(token), token))
        union_size = len(set_a | set_b)
        if union_size <= 0:
            return 0.0, overlap
        return len(overlap) / union_size, overlap

    def _normalize_progression_clause(self, text: str) -> str:
        normalized = self._normalize_consistency_text(text)
        replacements = {
            "反杀": "反击",
            "反制": "反击",
            "盯上": "锁定",
            "被盯上": "遭锁定",
            "危机伏笔": "危机暗线",
            "隐患": "危机暗线",
        }
        for source, target in replacements.items():
            normalized = normalized.replace(source, target)

        normalized = normalized.strip(" \t，。；;、:：!！?？-—_()（）[]【】\"'“”‘’")
        normalized = re.sub(r"^(?:主角|秦昭野)(?:借|通过|利用)?", "", normalized)
        normalized = re.sub(r"^(?:完成|通过|并且|并|继续|再次|进一步|最终|成功|正式|实现|推动|推进|确立|打造|形成|借助|利用)+", "", normalized)
        normalized = re.sub(r"[的地得]$", "", normalized)
        return normalized.strip()

    def _extract_progression_clauses(self, text: str) -> list[str]:
        normalized_text = self._normalize_consistency_text(text)
        if not normalized_text:
            return []

        clauses: list[str] = []
        segments = re.split(r"[，。；;、\n]+", normalized_text)
        for segment in segments:
            candidate = segment.strip()
            if not candidate:
                continue

            sub_segments = re.split(r"(?:并且|并|以及|同时|然后|后续|从而|且)", candidate)
            for sub_segment in sub_segments:
                clause = self._normalize_progression_clause(sub_segment)
                if len(clause) < 4:
                    continue
                if not re.search(r"[\u4e00-\u9fff]{2,}", clause):
                    continue
                if clause not in clauses:
                    clauses.append(clause)
                if len(clauses) >= 12:
                    return clauses

        return clauses

    def _compute_clause_overlap(self, clauses_a: list[str], clauses_b: list[str]) -> list[str]:
        if not clauses_a or not clauses_b:
            return []

        repeated: list[str] = []
        used_indices: set[int] = set()
        for clause_a in clauses_a:
            best_idx = -1
            best_clause = ""
            best_score = 0.0
            for idx, clause_b in enumerate(clauses_b):
                if idx in used_indices:
                    continue
                similarity = difflib.SequenceMatcher(None, clause_a, clause_b).ratio()
                if clause_a in clause_b or clause_b in clause_a:
                    similarity = max(similarity, 0.74)
                if similarity > best_score:
                    best_score = similarity
                    best_idx = idx
                    best_clause = clause_b

            if best_idx >= 0 and best_score >= 0.72:
                used_indices.add(best_idx)
                repeated.append(best_clause)

        return repeated

    def _check_range_progression_uniqueness(
        self,
        range_progression_samples: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        lookback_window = 2
        for range_key, samples in range_progression_samples.items():
            if len(samples) < 2:
                continue

            ordered_samples = sorted(samples, key=lambda item: int(item.get("chapter_num", 0) or 0))
            for idx in range(1, len(ordered_samples)):
                curr_sample = ordered_samples[idx]
                curr_num = int(curr_sample.get("chapter_num", 0) or 0)
                if curr_num <= 0:
                    continue

                compare_start = max(0, idx - lookback_window)
                previous_candidates = ordered_samples[compare_start:idx]
                duplicate_issue: dict[str, Any] | None = None
                for prev_sample in reversed(previous_candidates):
                    prev_num = int(prev_sample.get("chapter_num", 0) or 0)
                    if prev_num <= 0:
                        continue

                    prev_tokens = [str(token) for token in prev_sample.get("tokens", [])]
                    curr_tokens = [str(token) for token in curr_sample.get("tokens", [])]
                    prev_core = str(prev_sample.get("core_function", "")).strip()
                    curr_core = str(curr_sample.get("core_function", "")).strip()

                    core_similarity = 0.0
                    if prev_core and curr_core:
                        core_similarity = difflib.SequenceMatcher(
                            None,
                            self._normalize_consistency_text(prev_core),
                            self._normalize_consistency_text(curr_core),
                        ).ratio()
                        if core_similarity >= 0.68:
                            duplicate_issue = {
                                "chapter": f"第{curr_num}章",
                                "description": (
                                    f"与第{prev_num}章核心功能高度重复"
                                    f"（相似度{core_similarity:.2f}），缺少章节级递进"
                                ),
                                "severity": "major",
                            }
                            break

                    token_similarity = 0.0
                    token_overlap: list[str] = []
                    if len(prev_tokens) >= 6 and len(curr_tokens) >= 6:
                        token_similarity, token_overlap = self._compute_token_jaccard(prev_tokens, curr_tokens)
                        if token_similarity >= 0.62 and len(token_overlap) >= 6:
                            duplicate_issue = {
                                "chapter": f"第{curr_num}章",
                                "description": (
                                    f"与第{prev_num}章在同一架构段内事件推进重复度过高"
                                    f"（相似度{token_similarity:.2f}），缺少章节级递进"
                                ),
                                "overlap_tokens": token_overlap[:10],
                                "architecture_focus": range_key[:120],
                                "severity": "major",
                            }
                            break

                    prev_progression_text = str(prev_sample.get("core_function", "") or "").strip()
                    curr_progression_text = str(curr_sample.get("core_function", "") or "").strip()
                    if not prev_progression_text:
                        prev_progression_text = str(prev_sample.get("focus_text", "") or "").strip()
                    if not curr_progression_text:
                        curr_progression_text = str(curr_sample.get("focus_text", "") or "").strip()

                    prev_clauses = self._extract_progression_clauses(prev_progression_text)
                    curr_clauses = self._extract_progression_clauses(curr_progression_text)
                    repeated_clauses = self._compute_clause_overlap(prev_clauses, curr_clauses)
                    repeated_clause_count = len(repeated_clauses)
                    min_clause_count = min(len(prev_clauses), len(curr_clauses))
                    clause_overlap_ratio = (
                        repeated_clause_count / min_clause_count if min_clause_count > 0 else 0.0
                    )
                    clause_duplicate_by_two_anchor_lock = (
                        repeated_clause_count == 2
                        and clause_overlap_ratio >= 0.9
                        and (
                            min_clause_count <= 2
                            or core_similarity >= 0.56
                            or token_similarity >= 0.5
                        )
                    )
                    if repeated_clause_count >= 3 or clause_duplicate_by_two_anchor_lock:
                        duplicate_issue = {
                            "chapter": f"第{curr_num}章",
                            "description": (
                                f"与第{prev_num}章在同一架构段内事件推进重复度过高"
                                f"（重复语义片段{repeated_clause_count}处），缺少章节级递进"
                            ),
                            "overlap_clauses": repeated_clauses[:6],
                            "clause_overlap_ratio": round(clause_overlap_ratio, 3),
                            "architecture_focus": range_key[:120],
                            "severity": "major",
                        }
                        break

                if duplicate_issue:
                    issues.append(duplicate_issue)

        return issues

    def _extract_legacy_section_excerpt(
        self,
        architecture_text: str,
        section_num: int,
        next_section_num: int | None = None,
        max_chars: int = 5000,
    ) -> str:
        if next_section_num is None:
            pattern = rf'#===\s*{section_num}\)[^\n]*\n?(.*)'
        else:
            pattern = rf'#===\s*{section_num}\)[^\n]*\n?(.*?)(?=#===\s*{next_section_num}\)|\Z)'
        match = re.search(pattern, architecture_text, re.DOTALL)
        if not match:
            return ""
        return match.group(0)[:max_chars].strip()

    def _extract_markdown_section_excerpt(
        self,
        architecture_text: str,
        section_numbers: tuple[int, ...] = (),
        title_keywords: tuple[str, ...] = (),
        max_chars: int = 5000,
    ) -> str:
        heading_pattern = re.compile(r"(?m)^##\s*(\d+)\.\s*([^\n]+?)\s*$")
        matches = list(heading_pattern.finditer(architecture_text))
        if not matches:
            return ""

        chunks: list[str] = []
        total_len = 0
        for idx, match in enumerate(matches):
            sec_num = int(match.group(1))
            sec_title = match.group(2).strip()
            by_number = bool(section_numbers and sec_num in section_numbers)
            by_keyword = bool(title_keywords and any(keyword in sec_title for keyword in title_keywords))
            if not by_number and not by_keyword:
                continue
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(architecture_text)
            block = architecture_text[start:end].strip()
            if not block:
                continue
            chunks.append(block)
            total_len += len(block)
            if total_len >= max_chars:
                break

        return "\n\n".join(chunks)[:max_chars]

    def _create_fallback_prompt(self, start_chapter: int, end_chapter: int,
                               architecture_text: str) -> str:
        """
        创建简化的降级prompt，用于主prompt失败时

        当主prompt因过长或复杂导致LLM返回空时，使用这个简化版本
        """
        extractor = DynamicArchitectureExtractor(architecture_text)
        relevant_volumes = extractor._find_relevant_volumes(start_chapter, end_chapter)
        core_architecture = "\n\n".join(
            str(item.get("content", "")) for item in relevant_volumes if item.get("content")
        ).strip()
        if not core_architecture:
            core_architecture = self._extract_legacy_section_excerpt(architecture_text, 5, 6, max_chars=5000)
        if not core_architecture:
            core_architecture = self._extract_markdown_section_excerpt(
                architecture_text,
                section_numbers=(15, 23, 30),
                title_keywords=("详细情节点", "情节点", "情节架构"),
                max_chars=5000,
            )
        if not core_architecture:
            core_architecture = architecture_text[:5000].strip()

        char_info = self._extract_legacy_section_excerpt(architecture_text, 3, 4, max_chars=3000)
        if not char_info:
            char_info = self._extract_markdown_section_excerpt(
                architecture_text,
                section_numbers=(5, 6),
                title_keywords=("角色", "女主", "反派"),
                max_chars=3000,
            )
        if not char_info:
            protagonist, female_leads = self._extract_architecture_entities(architecture_text)
            pieces = []
            if protagonist:
                pieces.append(f"主角实名：{protagonist}")
            if female_leads:
                pieces.append("关键女性角色：" + "、".join(female_leads[:6]))
            char_info = "\n".join(pieces)

        prompt = f"""
你是一位小说蓝图架构师。请为**第{start_chapter}章到第{end_chapter}章**生成详细的章节蓝图。

## 核心架构参考

### 情节架构（节选）：
{core_architecture[:3000]}

### 角色信息（节选）：
{char_info}

## 生成要求

每个章节必须包含完整的7个节：

1. **基础元信息** - 章节序号、标题、定位、核心功能、字数目标、出场角色
2. **张力与冲突** - 冲突类型、核心冲突点、紧张感曲线
3. **匠心思维应用** - 应用场景、思维模式、视觉化描述、经典台词
4. **伏笔与信息差** - 本章植入伏笔、本章回收伏笔、信息差控制
5. **暧昧与修罗场** - 女性角色互动（如不涉及必须写"本章不涉及女性角色互动"）
6. **剧情精要** - 开场、发展、高潮、收尾
7. **衔接设计** - 承上、转场、启下

## 输出格式

第{start_chapter}章 - [章节标题]

## 1. 基础元信息
* **章节序号**：第{start_chapter}章
* **章节标题**：[根据情节设计]
* **定位**：第N卷 [卷名] - 子幕N [子幕名]
* **核心功能**：[一句话概括]
* **字数目标**：3000-5000字
* **出场角色**：[列出角色]

## 2. 张力与冲突
* **冲突类型**：[生存/权力/情感/理念]
* **核心冲突点**：[具体描述]
* **紧张感曲线**：铺垫→爬升→爆发→回落

[继续第3-7节...]

---

⚠️ **重要**：
- 所有7个节都必须完整，不能省略
- 第5节"暧昧与修罗场"即使不涉及女性角色也必须保留
- 每章至少800字详细描述
- 严禁使用"..."或"略"等省略表达
- 严禁出现占位定位（如“第X卷/子幕X/卷名待定/TBD”）
- 标题必须与最近章节显著区分，禁止重复沿用旧标题

请开始生成第{start_chapter}章到第{end_chapter}章：
"""
        return prompt

    # 保留旧方法以兼容（如果不使用两阶段）
    def _create_strict_prompt(self, architecture_text: str, chapter_list: str,
                           start_chapter: int, end_chapter: int, user_guidance: str = "") -> str:
         raise RuntimeError("_create_strict_prompt 已废弃，请使用 _create_strict_prompt_with_guide")
         return ""

    def _generate_batch_with_retry(
        self,
        start_chapter: int,
        end_chapter: int,
        architecture_text: str,
        existing_content: str = "",
        filepath: str = "",
        full_architecture_text: str = "",
    ) -> str:
        """
        分批次生成，严格要求成功

        Args:
            filepath: 小说文件路径，用于生成LLM对话日志
        """
        batch_size = end_chapter - start_chapter + 1
        logging.info(f"开始生成批次：第{start_chapter}章到第{end_chapter}章，共{batch_size}章")

        # 🚨 初始化 LLM 对话日志
        if filepath:
            self._init_llm_log(filepath, start_chapter, end_chapter)
            self._log_separator(f"开始生成第{start_chapter}章到第{end_chapter}章")

        last_error_msg = ""
        retry_required_keywords: list[str] = []
        max_attempts = 5  # 最多重试5次
        context_guide_cache = ""
        batch_started_at = time.time()
        batch_telemetry: dict[str, Any] = {
            "chapter_range": f"{start_chapter}-{end_chapter}",
            "max_attempts": max_attempts,
            "attempts": [],
            "retry_reasons": [],
            "status": "running",
        }
        self._latest_batch_telemetry = {}
        runtime_architecture_text = str(architecture_text or "")
        consistency_architecture_text = runtime_architecture_text

        resolved_info: dict[str, Any] = {}
        try:
            resolved_info = self._resolve_architecture_text_for_batch(
                runtime_architecture_text=runtime_architecture_text,
                full_architecture_text=full_architecture_text,
                start_chapter=start_chapter,
                end_chapter=end_chapter,
            )
            consistency_architecture_text = str(
                resolved_info.get("architecture_text") or runtime_architecture_text
            )
        except ArchitectureMappingGapError as e:
            batch_telemetry["attempts"].append(
                {
                    "attempt": 1,
                    "status": "failed",
                    "context_guide_reused": False,
                    "phase1_seconds": 0.0,
                    "phase2_seconds": 0.0,
                    "total_seconds": round(time.time() - batch_started_at, 3),
                    "retry_reason": "mapping_gap",
                    "mapping_gap": e.diagnostics,
                }
            )
            batch_telemetry["attempt_count"] = 1
            batch_telemetry["status"] = "failed"
            batch_telemetry["total_seconds"] = round(time.time() - batch_started_at, 3)
            if "mapping_gap" not in batch_telemetry["retry_reasons"]:
                batch_telemetry["retry_reasons"].append("mapping_gap")
            self._latest_batch_telemetry = batch_telemetry

            try:
                gap_debug_file = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    f"blueprint_MAPPING_GAP_{start_chapter}_{end_chapter}.json",
                )
                with open(gap_debug_file, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "chapter_range": f"{start_chapter}-{end_chapter}",
                            "error": str(e),
                            "diagnostics": e.diagnostics,
                        },
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )
            except (OSError, json.JSONDecodeError):
                pass

            raise

        extractor = self._get_architecture_extractor(
            runtime_architecture_text or consistency_architecture_text
        )
        coverage_source = str(resolved_info.get("coverage_source") or "runtime")
        preflight_missing = (resolved_info.get("preflight") or {}).get("missing_chapters") or []
        resolved_cov_raw = resolved_info.get("resolved")
        resolved_cov = resolved_cov_raw if isinstance(resolved_cov_raw, dict) else {}
        coverage_resolved: dict[str, Any] = {
            "mapped_count": int(resolved_cov.get("mapped_count") or 0),
            "missing_count": int(resolved_cov.get("missing_count") or 0),
            "is_fully_covered": bool(resolved_cov.get("is_fully_covered")),
        }
        resolved_missing = resolved_cov.get("missing_chapters")
        if isinstance(resolved_missing, list):
            coverage_resolved["missing_chapters"] = [
                int(chapter)
                for chapter in resolved_missing
                if isinstance(chapter, int)
            ]

        for attempt in range(max_attempts):
            attempt_started_at = time.time()
            retry_reason = ""
            consistency_failed = False
            attempt_telemetry = {
                "attempt": attempt + 1,
                "status": "running",
                "context_guide_reused": bool(context_guide_cache),
                "phase1_seconds": 0.0,
                "phase2_seconds": 0.0,
                "total_seconds": 0.0,
                "retry_reason": "",
                "coverage_source": coverage_source,
                "missing_chapters_preflight": preflight_missing,
                "coverage_resolved": coverage_resolved,
            }
            try:
                logging.info(f"尝试第{attempt + 1}次生成...")

                # 动态调整指导语，加入上一次的失败反馈
                target_chapters = ", ".join([f"第{i}章" for i in range(start_chapter, end_chapter + 1)])
                current_guidance = f"🎯 你的任务是生成：【{target_chapters}】。\n请生成详细的章节目录，禁止任何形式的省略。"

                # 可选增强：注入逐章任务卡约束（若项目中存在逐章任务卡CSV）
                if filepath:
                    task_card_guidance = self._build_task_card_guidance(filepath, start_chapter, end_chapter)
                    if task_card_guidance:
                        current_guidance += "\n\n" + task_card_guidance
                
                if last_error_msg:
                    current_guidance += f"\n\n❌ 上一次尝试失败原因：\n{last_error_msg}\n👉 请针对性修正上述问题，确保不再犯同样的错误！"
                if retry_required_keywords:
                    anchors = "\n".join(f"- {kw}" for kw in retry_required_keywords[:8])
                    current_guidance += (
                        "\n\n🚨 架构一致性硬性词锚（本次必须逐字命中，并自然融入章节正文）：\n"
                        f"{anchors}\n"
                        "要求：上述词锚每个至少出现1次，优先放入‘基础元信息/剧情精要’，"
                        "禁止同义替换或只写近义表达。"
                    )

                # Phase 1: 语境萃取 (Context Extraction)
                # 利用LLM从完整架构中提取"定制化指南"
                if not context_guide_cache:
                    phase1_started_at = time.time()
                    logging.info("📚 Phase 1: 正在进行架构语境萃取...")
                    context_guide = self._run_with_heartbeat(
                        lambda: extractor.get_context_guide_via_llm(self.llm_adapter, start_chapter, end_chapter),
                        stage_name=f"语境萃取 第{start_chapter}-{end_chapter}章"
                    )
                    if not self._context_guide_is_usable(context_guide):
                        logging.warning("⚠️ 语境萃取结果不可用，改用架构文本兜底摘要")
                        context_guide = self._build_context_guide_fallback(
                            runtime_architecture_text,
                            start_chapter,
                            end_chapter,
                        )
                    if not self._context_guide_is_usable(context_guide):
                        raise RuntimeError("语境萃取不可用且兜底摘要失败，已阻断生成以避免模板污染")
                    context_guide_cache = context_guide
                    attempt_telemetry["phase1_seconds"] = round(time.time() - phase1_started_at, 3)
                else:
                    context_guide = context_guide_cache
                    logging.info("📚 Phase 1: 复用已萃取语境指南")

                # 将萃取出的guide整合进prompt
                # 注意：这里不再需要手动截断architecture_text，因为guide已经是精华了
                # 但为了保险，我们还是传入Architecture的核心部分（Section 0-1），+ guide
                
                phase2_prompt = self._create_strict_prompt_with_guide(
                     architecture_text=runtime_architecture_text, # 依然传入，但主要依赖guide
                     context_guide=context_guide,
                     chapter_list=self._extract_chapter_titles_only(existing_content[-5000:]) if existing_content else "", 
                     start_chapter=start_chapter,
                     end_chapter=end_chapter,
                     user_guidance=current_guidance,
                     project_path=filepath,
                )
                
                # Phase 2: 蓝图生成
                logging.info("✍️ Phase 2: 正在生成蓝图...")
                phase2_started_at = time.time()
                result = self._invoke_with_heartbeat(
                    phase2_prompt,
                    stage_name=f"蓝图生成 第{start_chapter}-{end_chapter}章"
                )
                attempt_telemetry["phase2_seconds"] = round(time.time() - phase2_started_at, 3)

                if not result or not result.strip():
                    logging.error(f"第{attempt + 1}次尝试：生成结果为空")

                    # 🆕 尝试降级策略：使用简化prompt（前两次尝试）
                    if attempt < 2:
                        logging.info("🔄 尝试使用简化prompt重新生成...")
                        try:
                            fallback_prompt = self._create_fallback_prompt(
                                start_chapter, end_chapter, runtime_architecture_text
                            )
                            result = self._invoke_with_heartbeat(
                                fallback_prompt,
                                stage_name=f"蓝图生成(简化Prompt) 第{start_chapter}-{end_chapter}章"
                            )
                            if result and result.strip():
                                logging.info("✅ 简化prompt生成成功！继续验证...")
                                # 跳过空结果检查，直接进入验证流程
                            else:
                                logging.warning("⚠️ 简化prompt也返回空结果")
                                # 保存空结果诊断
                                empty_debug_file = os.path.join(
                                    os.path.dirname(os.path.dirname(__file__)),
                                    f"blueprint_EMPTY_{start_chapter}_{end_chapter}_{attempt+1}.txt"
                                )
                                with open(empty_debug_file, 'w', encoding='utf-8') as f:
                                    f.write(f"LLM 返回空结果（包括简化prompt）\nresult type: {type(result)}\nresult repr: {repr(result)}")
                                logging.info(f"  📝 空结果诊断已保存: {empty_debug_file}")
                                retry_reason = "empty_result"
                                attempt_telemetry["status"] = "retry"
                                attempt_telemetry["retry_reason"] = retry_reason
                                attempt_telemetry["total_seconds"] = round(time.time() - attempt_started_at, 3)
                                batch_telemetry["attempts"].append(attempt_telemetry)
                                if retry_reason not in batch_telemetry["retry_reasons"]:
                                    batch_telemetry["retry_reasons"].append(retry_reason)
                                continue
                        except Exception as fallback_e:
                            logging.warning(f"⚠️ 简化prompt尝试失败: {fallback_e}")
                            # 继续执行下面的空结果保存逻辑
                    else:
                        # 保存空结果诊断
                        empty_debug_file = os.path.join(
                            os.path.dirname(os.path.dirname(__file__)),
                            f"blueprint_EMPTY_{start_chapter}_{end_chapter}_{attempt+1}.txt"
                        )
                        with open(empty_debug_file, 'w', encoding='utf-8') as f:
                            f.write(f"LLM 返回空结果\nresult type: {type(result)}\nresult repr: {repr(result)}")
                        logging.info(f"  📝 空结果诊断已保存: {empty_debug_file}")

                    # 如果降级策略后仍然为空，继续下一次重试
                    if not result or not result.strip():
                        retry_reason = "empty_result"
                        attempt_telemetry["status"] = "retry"
                        attempt_telemetry["retry_reason"] = retry_reason
                        attempt_telemetry["total_seconds"] = round(time.time() - attempt_started_at, 3)
                        batch_telemetry["attempts"].append(attempt_telemetry)
                        if retry_reason not in batch_telemetry["retry_reasons"]:
                            batch_telemetry["retry_reasons"].append(retry_reason)
                        continue

                # 先做结构兜底，再进入严格验证（不会绕过校验）
                result, normalized_fixes = self._normalize_missing_sections(result, start_chapter, end_chapter)
                if normalized_fixes > 0:
                    logging.info(f"🩹 结构兜底补齐完成：共补齐 {normalized_fixes} 个缺失节")

                # 严格验证
                validation = self._strict_validation(result, start_chapter, end_chapter)

                # 🆕 Schema 验证 (使用 Pydantic 模型)
                try:
                    from .schema_validator import SchemaValidator

                    # 创建验证器实例（如果需要角色白名单，可以传入）
                    validator = SchemaValidator()

                    # 验证蓝图格式
                    schema_validation = validator.validate_blueprint_format(result, start_chapter, end_chapter)

                    if not schema_validation["is_valid"]:
                        logging.warning(f"⚠️ Schema 验证发现问题: {', '.join(schema_validation['errors'])}")
                        # 合并到现有验证结果中
                        validation["is_valid"] = False
                        validation["errors"].extend(schema_validation["errors"])
                    else:
                        logging.info("✅ Schema 验证通过")
                except (ImportError, RuntimeError, ValueError, TypeError) as schema_e:
                    logging.warning(f"⚠️ Schema 验证异常: {schema_e}（不影响继续使用传统验证）")

                # 🆕 尝试自动修复缺失的节
                if not validation["is_valid"]:
                    result, was_fixed = self._auto_fix_missing_sections(result, validation)
                    if was_fixed:
                        # 自动修复后再做一次统一兜底，然后重新验证
                        result, normalized_fixes = self._normalize_missing_sections(result, start_chapter, end_chapter)
                        if normalized_fixes > 0:
                            logging.info(f"🩹 自动修复后补齐缺失节：{normalized_fixes}")
                        # 重新验证修复后的内容
                        validation = self._strict_validation(result, start_chapter, end_chapter)
                        logging.info(f"🔧 自动修复后重新验证...")

                if validation["is_valid"]:
                    title_conflicts = self._collect_recent_title_conflicts(
                        generated_content=result,
                        existing_content=existing_content,
                        lookback=120,
                    )
                    if title_conflicts:
                        validation["is_valid"] = False
                        validation["errors"].extend(title_conflicts)
                        logging.error("🚨 标题去重守卫未通过：")
                        for item in title_conflicts[:3]:
                            logging.error(f"  - {item}")

                if validation["is_valid"]:
                    consistency = self._check_architecture_consistency(
                        result,
                        consistency_architecture_text,
                    )
                    if not consistency["is_consistent"]:
                        patched_result, injected_keywords = self._patch_consistency_keyword_gaps(
                            result,
                            consistency.get("issues", []),
                        )
                        if injected_keywords > 0:
                            logging.warning(
                                "🩹 一致性关键词兜底注入：共注入%d个锚点，准备复检一致性",
                                injected_keywords,
                            )
                            patched_consistency = self._check_architecture_consistency(
                                patched_result,
                                consistency_architecture_text,
                            )
                            if patched_consistency.get("is_consistent", False):
                                logging.info("✅ 一致性关键词兜底复检通过")
                                result = patched_result
                                consistency = patched_consistency

                    if not consistency["is_consistent"]:
                        consistency_failed = True
                        retry_required_keywords = []
                        issue_preview = []
                        for issue in consistency.get("issues", [])[:3]:
                            chapter = issue.get("chapter", "未知章节")
                            desc = issue.get("description", "架构一致性异常")
                            required_keywords = issue.get("required_keywords") or []
                            matched_keywords = issue.get("matched_keywords") or []
                            for keyword in required_keywords:
                                normalized_keyword = str(keyword).strip()
                                if normalized_keyword and normalized_keyword not in retry_required_keywords:
                                    retry_required_keywords.append(normalized_keyword)
                            if required_keywords:
                                required_text = "、".join(str(kw) for kw in required_keywords[:6])
                                if matched_keywords:
                                    matched_text = "、".join(str(kw) for kw in matched_keywords[:6])
                                    issue_preview.append(
                                        f"{chapter}: {desc} | 必须命中关键词: {required_text} | 已命中: {matched_text}"
                                    )
                                else:
                                    issue_preview.append(
                                        f"{chapter}: {desc} | 必须命中关键词: {required_text}"
                                    )
                            else:
                                issue_preview.append(f"{chapter}: {desc}")
                        consistency_error = (
                            "🚨 架构一致性未通过: "
                            + (" | ".join(issue_preview) if issue_preview else "存在重大偏离")
                        )
                        validation["is_valid"] = False
                        validation["errors"].append(consistency_error)
                        logging.error(consistency_error)

                if validation["is_valid"]:
                    logging.info(f"✅ 批次生成成功：第{start_chapter}章到第{end_chapter}章")
                    attempt_telemetry["status"] = "success"
                    attempt_telemetry["retry_reason"] = ""
                    attempt_telemetry["total_seconds"] = round(time.time() - attempt_started_at, 3)
                    batch_telemetry["attempts"].append(attempt_telemetry)
                    batch_telemetry["attempt_count"] = len(batch_telemetry["attempts"])
                    batch_telemetry["success_attempt"] = attempt + 1
                    batch_telemetry["status"] = "success"
                    batch_telemetry["total_seconds"] = round(time.time() - batch_started_at, 3)
                    self._latest_batch_telemetry = batch_telemetry

                    # 🚨 记录 LLM 生成调用和验证结果
                    if filepath:
                        self._log_llm_call(
                            call_type=f"✅ 第{attempt + 1}次生成（成功）",
                            prompt=phase2_prompt,
                            response=result,
                            validation_result=validation,
                            metadata={
                                "尝试次数": attempt + 1,
                                "章节范围": f"{start_chapter}-{end_chapter}",
                                "响应长度": f"{len(result)} 字符",
                                "生成章节数": len(validation.get("generated_chapters", [])),
                                "语境缓存复用": "是" if attempt_telemetry.get("context_guide_reused") else "否",
                                "语境萃取耗时": f"{attempt_telemetry.get('phase1_seconds', 0.0):.2f}s",
                                "蓝图生成耗时": f"{attempt_telemetry.get('phase2_seconds', 0.0):.2f}s",
                                "本次耗时": f"{attempt_telemetry.get('total_seconds', 0.0):.2f}s",
                            }
                        )
                        # 完成日志并返回
                        self._finalize_llm_log(success=True)

                    result_with_newline = "\n" + result
                    return result_with_newline
                else:
                    retry_reason = "architecture_consistency_failed" if consistency_failed else "validation_failed"
                    logging.error(f"第{attempt + 1}次尝试验证失败：")
                    # 关键调试：打印失败的内容，以便分析
                    logging.warning(f"\n======== 失败的生成内容 START ========\n{result[:500]}...\n======== 失败的生成内容 END ========\n")
                    attempt_telemetry["status"] = "retry"
                    attempt_telemetry["retry_reason"] = retry_reason
                    attempt_telemetry["total_seconds"] = round(time.time() - attempt_started_at, 3)
                    attempt_telemetry["error_count"] = len(validation.get("errors", []))
                    batch_telemetry["attempts"].append(attempt_telemetry)
                    if retry_reason not in batch_telemetry["retry_reasons"]:
                        batch_telemetry["retry_reasons"].append(retry_reason)

                    # 🚨 记录失败的LLM调用
                    if filepath:
                        self._log_llm_call(
                            call_type=f"❌ 第{attempt + 1}次生成（验证失败）",
                            prompt=phase2_prompt,
                            response=result,
                            validation_result=validation,
                            metadata={
                                "尝试次数": attempt + 1,
                                "章节范围": f"{start_chapter}-{end_chapter}",
                                "响应长度": f"{len(result)} 字符",
                                "错误数量": len(validation.get("errors", [])),
                                "重试原因": retry_reason,
                                "语境缓存复用": "是" if attempt_telemetry.get("context_guide_reused") else "否",
                                "语境萃取耗时": f"{attempt_telemetry.get('phase1_seconds', 0.0):.2f}s",
                                "蓝图生成耗时": f"{attempt_telemetry.get('phase2_seconds', 0.0):.2f}s",
                                "本次耗时": f"{attempt_telemetry.get('total_seconds', 0.0):.2f}s",
                            }
                        )

                    # 🆕 保存失败内容到文件，便于诊断
                    debug_file = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                              f"blueprint_debug_attempt_{start_chapter}_{end_chapter}_{attempt+1}.txt")
                    try:
                        with open(debug_file, 'w', encoding='utf-8') as f:
                            f.write(f"=== 验证结果 ===\n{validation}\n\n=== 生成内容 ===\n{result}")
                        logging.info(f"  📝 失败内容已保存: {debug_file}")
                    except (OSError, UnicodeEncodeError) as save_err:
                        logging.warning(f"  无法保存调试文件: {save_err}")

                    error_list = []
                    for error in validation["errors"]:
                        logging.error(f"  - {error}")
                        error_list.append(error)

                    last_error_msg = "\n".join(error_list)

                    if attempt < max_attempts - 1:
                        # 🆕 指数退避策略：5秒 → 10秒 → 20秒 → 40秒
                        wait_time = 5 * (2 ** attempt)
                        logging.info(f"将进行第{attempt + 2}次重试（等待{wait_time}秒）...")
                        time.sleep(wait_time)

            except Exception as e:
                error_str = str(e)
                logging.error(f"第{attempt + 1}次尝试异常：{error_str}")
                retry_reason = "exception"
                if isinstance(e, TimeoutError):
                    retry_reason = "timeout"
                elif "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                    retry_reason = "rate_limited"

                attempt_telemetry["status"] = "retry"
                attempt_telemetry["retry_reason"] = retry_reason
                attempt_telemetry["total_seconds"] = round(time.time() - attempt_started_at, 3)
                attempt_telemetry["exception_type"] = type(e).__name__
                batch_telemetry["attempts"].append(attempt_telemetry)
                if retry_reason not in batch_telemetry["retry_reasons"]:
                    batch_telemetry["retry_reasons"].append(retry_reason)
                
                # 🆕 保存异常诊断
                import traceback
                exc_debug_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                              f"blueprint_EXCEPTION_{start_chapter}_{end_chapter}_{attempt+1}.txt")
                try:
                    with open(exc_debug_file, 'w', encoding='utf-8') as f:
                        f.write(f"异常类型: {type(e).__name__}\n异常信息: {error_str}\n\n完整堆栈:\n{traceback.format_exc()}")
                    logging.info(f"  📝 异常诊断已保存: {exc_debug_file}")
                except OSError:
                    pass
                
                # 特别处理 API 资源耗尽 (Quota Exceeded)
                if "RESOURCE_EXHAUSTED" in error_str or "429" in error_str:
                    wait_time = 60
                    logging.warning(f"⚠️ 检测到 API 配额耗尽 (Resource Exhausted)，将强制冷却 {wait_time} 秒...")
                    time.sleep(wait_time)
                else:
                    # 🆕 其他错误使用指数退避
                    wait_time = 5 * (2 ** min(attempt, 4))  # 最多80秒
                    logging.info(f"等待{wait_time}秒后重试...")
                    time.sleep(wait_time)

        # 如果所有尝试都失败，抛出异常而不是返回降级内容
        batch_telemetry["attempt_count"] = len(batch_telemetry.get("attempts", []))
        batch_telemetry["status"] = "failed"
        batch_telemetry["total_seconds"] = round(time.time() - batch_started_at, 3)
        self._latest_batch_telemetry = batch_telemetry

        # 🚨 完成日志（失败状态）
        if filepath:
            self._finalize_llm_log(success=False, error_message=f"经过{max_attempts}次尝试仍未成功")

        raise Exception(f"批次生成失败：第{start_chapter}章到第{end_chapter}章，经过{max_attempts}次尝试仍未成功")

    def _check_architecture_consistency(self, content: str, architecture_text: str) -> dict:
        """
        检查与架构的一致性（动态模式）
        仅基于当前架构文本提取的章节定义与关键词进行校验，不依赖固定人名/宗门。
        """
        issues = []
        chapter_checks = 0

        extractor = DynamicArchitectureExtractor(architecture_text)
        chapter_defs = extractor.structure.get("chapters", {})
        available_defs = len(chapter_defs)
        if available_defs == 0:
            issues.append(
                {
                    "chapter": "全局",
                    "description": "未提取到可校验章节映射，已阻断生成以避免架构漂移",
                    "severity": "critical",
                }
            )

        chapter_matches = list(
            re.finditer(
                r'(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*[^\n]*)?\s*(?:\*\*)?\s*$',
                content,
            )
        )
        if not chapter_matches:
            chapter_matches = list(re.finditer(r'第\s*(\d+)\s*章', content))
        if not chapter_matches:
            issues.append(
                {
                    "chapter": "全局",
                    "description": "未识别到可校验章节标题，已阻断生成",
                    "severity": "critical",
                }
            )

        stopwords = {
            "第", "章节", "核心", "功能", "内容", "剧情", "场景", "角色", "冲突",
            "发展", "高潮", "收尾", "本章", "必须", "要求", "设定", "描述", "信息",
            "以及", "进行", "通过", "出现", "相关", "如果", "可以", "回报", "代价",
            "功能", "卷末", "阶段", "升级", "推进", "关系", "线", "章", "提示",
            "读者", "立即", "入局", "主角", "章节锁定", "核心事件"
        }

        mapped_chapters = 0
        range_progression_samples: dict[str, list[dict[str, Any]]] = {}
        for idx, match in enumerate(chapter_matches):
            chapter_num = int(match.group(1))
            architecture_snippet = str(chapter_defs.get(chapter_num, ""))
            if not architecture_snippet.strip():
                continue

            architecture_focus = self._slice_architecture_event_focus(architecture_snippet)
            normalized_range_key = self._normalize_consistency_text(architecture_focus or architecture_snippet)

            mapped_chapters += 1
            start_idx = match.start()
            end_idx = chapter_matches[idx + 1].start() if idx + 1 < len(chapter_matches) else len(content)
            chapter_content = content[start_idx:end_idx]

            progression_tokens = self._extract_progression_tokens(chapter_content, stopwords)
            progression_focus = self._extract_progression_focus_text(chapter_content)
            core_function = self._extract_labeled_value(chapter_content, "核心功能")
            if normalized_range_key:
                range_progression_samples.setdefault(normalized_range_key, []).append(
                    {
                        "chapter_num": chapter_num,
                        "tokens": progression_tokens,
                        "core_function": core_function,
                        "focus_text": progression_focus,
                    }
                )

            keywords = self._extract_consistency_keywords(architecture_snippet, stopwords)

            if not keywords:
                issues.append(
                    {
                        "chapter": f"第{chapter_num}章",
                        "description": "架构片段可用关键词为空，无法建立有效对照",
                        "severity": "critical",
                    }
                )
                continue

            chapter_checks += 1
            normalized_chapter_content = self._normalize_consistency_text(chapter_content)
            overlap: list[str] = []
            for keyword in keywords:
                normalized_keyword = self._normalize_consistency_text(keyword)
                if not normalized_keyword:
                    continue

                matched = normalized_keyword in normalized_chapter_content
                if not matched:
                    token_candidates = [
                        token
                        for token in re.findall(r'[\u4e00-\u9fff]{2,4}', normalized_keyword)
                        if token not in stopwords
                    ]
                    if len(token_candidates) <= 1 and len(normalized_keyword) >= 4:
                        token_candidates.extend(
                            normalized_keyword[idx:idx + 2]
                            for idx in range(len(normalized_keyword) - 1)
                        )

                    compact_tokens: list[str] = []
                    for token in token_candidates:
                        if len(token) < 2 or token in stopwords:
                            continue
                        if token not in compact_tokens:
                            compact_tokens.append(token)

                    if compact_tokens:
                        token_hits = sum(1 for token in compact_tokens if token in normalized_chapter_content)
                        keyword_len = len(normalized_keyword)
                        if keyword_len <= 6:
                            required_hits = 1
                        else:
                            required_hits = 2 if len(compact_tokens) >= 3 else 1
                        matched = token_hits >= required_hits

                if matched:
                    overlap.append(keyword)
            overlap_count = len(overlap)
            match_rate = overlap_count / max(1, len(keywords))

            if overlap_count == 0:
                issues.append({
                    "chapter": f"第{chapter_num}章",
                    "description": "章节内容与架构定义语义重叠过低",
                    "required_keywords": keywords,
                    "matched_keywords": overlap,
                    "match_rate": match_rate,
                    "severity": "major"
                })
            elif overlap_count < (2 if len(keywords) >= 4 else 1):
                issues.append({
                    "chapter": f"第{chapter_num}章",
                    "description": "章节内容与架构定义重叠偏低",
                    "required_keywords": keywords,
                    "matched_keywords": overlap,
                    "match_rate": match_rate,
                    "severity": "minor"
                })

        progression_issues = self._check_range_progression_uniqueness(range_progression_samples)
        if progression_issues:
            issues.extend(progression_issues)

        if available_defs > 0 and mapped_chapters == 0:
            issues.append(
                {
                    "chapter": "全局",
                    "description": "本批次章节未命中任何架构章节映射，已阻断生成",
                    "severity": "critical",
                }
            )

        if available_defs > 0 and chapter_checks == 0:
            issues.append(
                {
                    "chapter": "全局",
                    "description": "未形成有效架构一致性校验，已阻断生成",
                    "severity": "critical",
                }
            )

        critical_violations = len([i for i in issues if i.get("severity") == "critical"])
        major_violations = len([i for i in issues if i.get("severity") == "major"])
        minor_violations = len([i for i in issues if i.get("severity") == "minor"])

        compliance_score = 1.0
        if chapter_checks > 0:
            compliance_score = 1.0 - (critical_violations * 0.5 + major_violations * 0.3 + minor_violations * 0.1)

        is_consistent = critical_violations == 0 and major_violations == 0

        if issues:
            logging.info(f"架构一致性检查: 发现 {len(issues)} 个问题 (合规分: {compliance_score:.2f})")
        else:
            logging.info("架构一致性检查: 通过 ✓")

        return {
            "is_consistent": is_consistent,
            "compliance_score": max(0, compliance_score),
            "issues": issues,
            "total_violations": len(issues),
            "critical_violations": critical_violations,
            "major_violations": major_violations,
            "minor_violations": minor_violations,
            "chapter_checks": chapter_checks,
            "mapped_chapters": mapped_chapters,
            "available_chapter_defs": available_defs,
        }

    def _extract_chapter_number_from_content(self, content: str) -> int:
        """从内容中提取章节编号"""
        import re

        # 尝试多种章节编号格式
        patterns = [
            r"第\s*(\d+)\s*章",
            r"chapter\s*(\d+)",
            r"(\d+)\s*、",
            r"【\s*第?\s*(\d+)\s*章\s*】"
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue

        return 1  # 默认返回第1章

    def _batch_quality_optimize(self, filepath: str, full_content: str,
                                 start_chapter: int, end_chapter: int,
                                 target_score: float = 80.0) -> str:
        """
        批次质量优化：检查并修复当前批次的低分章节
        
        Args:
            filepath: 项目路径
            full_content: 当前完整的蓝图内容
            start_chapter: 批次起始章节
            end_chapter: 批次结束章节
            
        Returns:
            优化后的完整蓝图内容
        """
        from quality_checker import QualityChecker
        from novel_generator.blueprint_repairer import BlueprintRepairer
        
        checker = QualityChecker(filepath)
        low_score_chapters = []
        
        # 1. 检查当前批次的每个章节
        for chapter_num in range(start_chapter, end_chapter + 1):
            chapter_content = self._extract_single_chapter(full_content, chapter_num)
            if not chapter_content:
                logging.warning(f"未能提取第{chapter_num}章内容，跳过质量检查")
                continue
            
            report = checker.check_chapter_quality(
                chapter_content, 
                {"chapter_number": chapter_num}
            )
            
            needs_repair = report.overall_score < target_score
            issues = [issue.description for issue in report.issues]

            # 边缘分章节触发毒舌评审（不全量，降低额外成本）
            critic_trigger_line = target_score - self.blueprint_critic_trigger_margin
            if self.enable_blueprint_critic and report.overall_score >= critic_trigger_line:
                critic_result = self._run_blueprint_critic(chapter_num, chapter_content)
                if critic_result.get("rejected"):
                    needs_repair = True
                    critic_issue = (
                        f"毒舌拒收: score={critic_result.get('critic_score', 0):.2f}; "
                        f"comment={critic_result.get('toxic_comment', '')}; "
                        f"demand={critic_result.get('improvement_demand', '')}"
                    )
                    issues.append(critic_issue)

            if needs_repair:
                trigger_reason = "低分" if report.overall_score < target_score else "毒舌拒收"
                low_score_chapters.append({
                    'chapter_number': chapter_num,
                    'content': chapter_content,
                    'score': report.overall_score,
                    'issues': issues
                })
                logging.info(f"  第{chapter_num}章: {report.overall_score:.1f}分 ({trigger_reason}，需优化)")
            else:
                logging.info(f"  第{chapter_num}章: {report.overall_score:.1f}分 ✓")
        
        # 2. 如果有低分章节，自动修复
        if low_score_chapters:
            logging.info(f"🔧 发现 {len(low_score_chapters)} 个低分章节，开始自动修复...")
            
            repairer = BlueprintRepairer(
                interface_format=self.interface_format,
                api_key=self.api_key,
                base_url=self.base_url,
                llm_model=self.llm_model,
                filepath=filepath,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout
            )
            
            for chapter_info in low_score_chapters:
                chapter_num = chapter_info['chapter_number']
                original_content = chapter_info['content']
                issues = chapter_info['issues']
                
                logging.info(f"  修复第{chapter_num}章 (原分: {chapter_info['score']:.1f})...")
                
                repaired = repairer.repair_single_chapter(
                    chapter_num, original_content, issues, max_retries=2
                )
                
                if repaired:
                    # 验证修复后的质量
                    new_report = checker.check_chapter_quality(
                        repaired, {"chapter_number": chapter_num}
                    )
                    improvement = new_report.overall_score - chapter_info['score']
                    logging.info(f"  第{chapter_num}章修复完成: {chapter_info['score']:.1f} → {new_report.overall_score:.1f} ({improvement:+.1f})")
                    
                    # 替换原内容
                    full_content = self._replace_chapter_content(
                        full_content, chapter_num, repaired
                    )
                else:
                    logging.warning(f"  第{chapter_num}章修复失败，保留原内容")
        else:
            logging.info("✅ 当前批次所有章节质量达标")
        
        return full_content

    def _extract_single_chapter(self, content: str, chapter_num: int) -> str:
        """从完整内容中提取单个章节"""
        if not content:
            return ""

        for num, start, end in self._iter_chapter_blocks(content):
            if num == chapter_num:
                return content[start:end].strip()
        return ""

    def _extract_chapter_range_content(self, content: str, start_chapter: int, end_chapter: int) -> str:
        """提取指定章节范围（含首尾）的目录文本。"""
        if not content:
            return ""
        start = int(start_chapter)
        end = int(end_chapter)
        if end < start:
            start, end = end, start

        selected_blocks: list[str] = []
        for num, block_start, block_end in self._iter_chapter_blocks(content):
            if start <= int(num) <= end:
                selected_blocks.append(content[block_start:block_end].strip())
        return "\n\n".join([blk for blk in selected_blocks if blk]).strip()

    def _rename_chapter_title_in_block(self, chapter_block: str, chapter_num: int, new_title: str) -> str:
        """在单章块内重命名章节标题（标题行 + 基础元信息中的章节标题字段）。"""
        block = str(chapter_block or "").strip()
        if not block:
            return block
        title_text = str(new_title or "").strip()
        if not title_text:
            return block

        header_pattern = re.compile(
            rf"(?m)^\s*(?:#+\s*)?(?:\*\*)?\s*第\s*{int(chapter_num)}\s*章(?:\s*[-–—:：]\s*[^\n*]+)?\s*(?:\*\*)?\s*$"
        )
        block, _ = header_pattern.subn(f"第{int(chapter_num)}章 - {title_text}", block, count=1)

        title_field_pattern = re.compile(
            r"(?m)^(\s*(?:[-*]\s*)?(?:\*\*)?\s*章节标题\s*(?:\*\*)?\s*[：:]\s*)(.+?)\s*$"
        )
        block, title_field_replaced = title_field_pattern.subn(rf"\1{title_text}", block, count=1)
        if title_field_replaced <= 0:
            block = re.sub(
                r"(?m)^(\s*(?:##\s*)?1\.\s*基础元信息\s*$)",
                rf"\1\n* **章节标题**：{title_text}",
                block,
                count=1,
            )
        return block.strip()

    def _force_resolve_duplicate_titles_locally(self, content: str) -> tuple[str, int]:
        """
        本地兜底修复重复标题（无需LLM）：
        - 保留首次出现的标题
        - 后续重复章自动重命名为 “原标题·第X章”
        """
        payloads = sorted(
            self._iter_chapter_payloads(content),
            key=lambda item: int(item.get("chapter", 0)),
        )
        if not payloads:
            return content, 0

        seen_titles: set[str] = set()
        updated_content = str(content or "")
        renamed_count = 0

        for payload in payloads:
            chapter_num = int(payload.get("chapter", 0))
            chapter_title = str(payload.get("title", "")).strip()
            if chapter_num <= 0 or not chapter_title:
                continue
            if chapter_title not in seen_titles:
                seen_titles.add(chapter_title)
                continue

            candidate = f"{chapter_title}·第{chapter_num}章"
            suffix_idx = 2
            while candidate in seen_titles:
                candidate = f"{chapter_title}·第{chapter_num}章({suffix_idx})"
                suffix_idx += 1

            chapter_block = self._extract_single_chapter(updated_content, chapter_num)
            if not chapter_block:
                continue

            renamed_block = self._rename_chapter_title_in_block(chapter_block, chapter_num, candidate)
            if not renamed_block or renamed_block == chapter_block:
                continue

            updated_content = self._replace_chapter_content(updated_content, chapter_num, renamed_block)
            seen_titles.add(candidate)
            renamed_count += 1

        return updated_content, renamed_count

    def _try_local_duplicate_title_fallback(
        self,
        filepath: str,
        filename_dir: str,
        content: str,
        expected_end: int,
        report: dict[str, Any],
    ) -> tuple[str, dict[str, Any], bool]:
        """
        当仅剩“重复标题”问题时，执行一次本地重命名兜底并复验。
        返回：(内容, 报告, 是否已通过)。
        """
        validation = self._strict_validation(content, 1, expected_end)
        errors = [str(err) for err in validation.get("errors", [])]
        report["last_errors"] = errors[:20]

        if validation.get("is_valid", False):
            report["success"] = True
            report["last_errors"] = []
            return content, report, True

        if not errors:
            return content, report, False

        duplicate_only = all("章节标题重复" in item for item in errors)
        if not duplicate_only:
            return content, report, False

        logging.warning("⚠️ 自动修复后仅剩重复标题问题，启用本地去重兜底...")
        deduped_content, renamed_count = self._force_resolve_duplicate_titles_locally(content)
        if renamed_count <= 0:
            logging.error("❌ 本地重复标题去重未产生改动")
            return content, report, False

        deduped_content, _ = self._format_cleanup_content(deduped_content)
        clear_file_content(filename_dir)
        save_string_to_txt(deduped_content.strip(), filename_dir)
        self._sync_split_directory_files(filepath, deduped_content, remove_stale=False)
        logging.info(f"🩹 本地重复标题去重完成：重命名{renamed_count}章")

        post_validation = self._strict_validation(deduped_content, 1, expected_end)
        post_errors = [str(err) for err in post_validation.get("errors", [])]
        report["last_errors"] = post_errors[:20]
        report["success"] = bool(post_validation.get("is_valid", False))
        return deduped_content, report, bool(post_validation.get("is_valid", False))

    def _is_blocking_resume_validation_error(self, error_text: str) -> bool:
        """判断断点续传前的校验错误是否属于不可自动修复类型。"""
        text = str(error_text or "").strip()
        if not text:
            return False

        blocking_keywords = (
            "生成内容为空",
            "未检测到章节标题",
            "缺失章节",
            "出现范围外章节",
            "检测到重复章节号",
        )
        return any(keyword in text for keyword in blocking_keywords)

    def _collect_resume_repair_issue_map(
        self,
        errors: list[str],
        max_chapter: int | None = None,
    ) -> dict[int, list[str]]:
        """从严格校验错误中提取“章节 -> 问题列表”映射，用于断点续传前自动修复。"""
        issue_map: dict[int, list[str]] = {}
        for raw_error in errors or []:
            error_text = str(raw_error or "").strip()
            if not error_text:
                continue

            chapter_nums = [int(num) for num in re.findall(r"第\s*(\d+)\s*章", error_text)]
            if not chapter_nums and "检测到重复章节号" in error_text:
                chapter_nums = [int(num) for num in re.findall(r"\d+", error_text)]

            for chapter_num in chapter_nums:
                if chapter_num <= 0:
                    continue
                if max_chapter is not None and chapter_num > int(max_chapter):
                    continue
                issue_map.setdefault(chapter_num, [])
                if error_text not in issue_map[chapter_num]:
                    issue_map[chapter_num].append(error_text)

        return issue_map

    def _auto_repair_existing_for_resume(
        self,
        filepath: str,
        filename_dir: str,
        existing_content: str,
        expected_end: int,
        max_rounds: int = 2,
    ) -> tuple[str, dict[str, Any]]:
        """
        断点续传前自动修复已有目录。
        目标：在不重开目录的前提下，优先修复可定位到具体章节的结构问题（如占位符、重复标题等）。
        """
        report: dict[str, Any] = {
            "success": False,
            "rounds_attempted": 0,
            "repaired_total": 0,
            "failed_total": 0,
            "blocking_errors": [],
            "last_errors": [],
        }

        content = str(existing_content or "").strip()
        if not content:
            report["last_errors"] = ["目录为空，无法自动修复"]
            return "", report

        # 先做一次无损格式整理，尽量消除可自动归一化的问题。
        try:
            normalized, cleanup_stats = self._format_cleanup_content(content)
            normalized = normalized.strip()
            if normalized and normalized != content:
                content = normalized
                clear_file_content(filename_dir)
                save_string_to_txt(content, filename_dir)
                self._sync_split_directory_files(filepath, content, remove_stale=False)
                logging.info(
                    "🧹 断点续传自动修复预整理：章节%d，清理冗余%d字符",
                    int(cleanup_stats.get("chapter_count", 0) or 0),
                    int(cleanup_stats.get("removed", 0) or 0),
                )
        except Exception as cleanup_e:
            logging.warning(f"⚠️ 断点续传自动修复预整理失败（继续尝试修复）: {cleanup_e}")

        from novel_generator.blueprint_repairer import BlueprintRepairer

        repairer: BlueprintRepairer | None = None
        for round_idx in range(1, max(1, int(max_rounds)) + 1):
            report["rounds_attempted"] = round_idx
            validation = self._strict_validation(content, 1, expected_end)
            if validation.get("is_valid", False):
                report["success"] = True
                report["last_errors"] = []
                return content, report

            errors = [str(err) for err in validation.get("errors", [])]
            report["last_errors"] = errors[:20]

            blocking_errors = [
                err for err in errors
                if self._is_blocking_resume_validation_error(err)
            ]
            if blocking_errors:
                report["blocking_errors"] = blocking_errors[:20]
                logging.error("❌ 断点续传自动修复遇到不可自动修复问题，停止修复")
                for item in blocking_errors[:10]:
                    logging.error(f"  - {item}")
                return content, report

            issue_map = self._collect_resume_repair_issue_map(errors, max_chapter=expected_end)
            if not issue_map:
                logging.error("❌ 断点续传自动修复无法定位问题章节，停止修复")
                return content, report

            if repairer is None:
                repairer = BlueprintRepairer(
                    interface_format=self.interface_format,
                    api_key=self.api_key,
                    base_url=self.base_url,
                    llm_model=self.llm_model,
                    filepath=filepath,
                    temperature=self.temperature,
                    max_tokens=min(int(self.max_tokens or 8000), 16000),
                    timeout=self.timeout,
                )

            repaired_this_round = 0
            failed_this_round = 0
            logging.info(
                f"🛠️ 断点续传自动修复第{round_idx}轮：尝试修复{len(issue_map)}个问题章节"
            )
            for chapter_num in sorted(issue_map.keys()):
                original_content = self._extract_single_chapter(content, chapter_num)
                if not original_content:
                    failed_this_round += 1
                    continue

                repaired = repairer.repair_single_chapter(
                    chapter_number=chapter_num,
                    original_content=original_content,
                    quality_issues=issue_map.get(chapter_num, []),
                    max_retries=2,
                )
                if not repaired:
                    failed_this_round += 1
                    continue

                repaired_single = self._extract_single_chapter(repaired, chapter_num) or repaired
                repaired_single = str(repaired_single or "").strip()
                if not repaired_single:
                    failed_this_round += 1
                    continue

                repaired_single, normalized_fixes = self._normalize_missing_sections(
                    repaired_single,
                    chapter_num,
                    chapter_num,
                )
                if normalized_fixes > 0:
                    logging.info(f"🩹 断点修复补齐第{chapter_num}章缺失节：{normalized_fixes}")

                chapter_validation = self._strict_validation(
                    repaired_single,
                    chapter_num,
                    chapter_num,
                )
                if not chapter_validation.get("is_valid", False):
                    failed_this_round += 1
                    continue

                content = self._replace_chapter_content(content, chapter_num, repaired_single)
                self._sync_single_split_directory_file(filepath, chapter_num, repaired_single)
                repaired_this_round += 1

            report["repaired_total"] = int(report.get("repaired_total", 0)) + repaired_this_round
            report["failed_total"] = int(report.get("failed_total", 0)) + failed_this_round

            if repaired_this_round <= 0:
                logging.error("❌ 断点续传自动修复未产生有效改动，停止修复")
                content, report, passed = self._try_local_duplicate_title_fallback(
                    filepath=filepath,
                    filename_dir=filename_dir,
                    content=content,
                    expected_end=expected_end,
                    report=report,
                )
                if passed:
                    return content, report
                return content, report

            content, _ = self._format_cleanup_content(content)
            clear_file_content(filename_dir)
            save_string_to_txt(content.strip(), filename_dir)
            self._sync_split_directory_files(filepath, content, remove_stale=False)
            logging.info(
                f"✅ 断点续传自动修复第{round_idx}轮完成：成功{repaired_this_round}章，失败{failed_this_round}章"
            )

        content, report, passed = self._try_local_duplicate_title_fallback(
            filepath=filepath,
            filename_dir=filename_dir,
            content=content,
            expected_end=expected_end,
            report=report,
        )
        if passed:
            return content, report
        return content, report

    def _run_blueprint_critic(self, chapter_num: int, chapter_content: str) -> dict:
        """执行蓝图毒舌评审，返回标准化结果。"""
        if not self.enable_blueprint_critic or not self.blueprint_critic_agent:
            return {"enabled": False, "triggered": False, "rejected": False}
        try:
            critique = self.blueprint_critic_agent.critique_chapter(chapter_content)
            critic_score = float(critique.get("score", 0.0))
            rating = str(critique.get("rating", "Pass"))
            rejected = (rating.lower() == "reject") or (critic_score < self.blueprint_critic_threshold)
            logging.info(
                f"😈 蓝图毒舌评审 第{chapter_num}章: rating={rating}, score={critic_score:.2f}, rejected={rejected}"
            )
            return {
                "enabled": True,
                "triggered": True,
                "rejected": rejected,
                "critic_score": critic_score,
                "rating": rating,
                "toxic_comment": critique.get("toxic_comment", ""),
                "improvement_demand": critique.get("improvement_demand", ""),
            }
        except Exception as e:
            logging.warning(f"第{chapter_num}章毒舌评审异常，跳过: {e}")
            return {"enabled": True, "triggered": True, "rejected": False, "error": str(e)}

    def _replace_chapter_content(self, full_content: str, chapter_num: int, new_content: str) -> str:
        """替换指定章节的内容"""
        if not full_content:
            return full_content

        replacement = new_content.strip()
        blocks = self._iter_chapter_blocks(full_content)
        for num, start, end in blocks:
            if num != chapter_num:
                continue

            before = full_content[:start].rstrip()
            after = full_content[end:].lstrip()
            parts = [part for part in (before, replacement, after) if part]
            return "\n\n".join(parts).strip() + "\n"

        return full_content

    def _write_postcheck_repair_report(self, filepath: str, report: dict) -> str:
        report_path = os.path.join(filepath, "postcheck_repair_report.json")
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.warning(f"⚠️ 写入定向修复报告失败: {e}")
        return report_path

    def _collect_postcheck_issue_map(
        self,
        full_content: str,
        target_score: float,
        gate_report: dict | None = None,
        compliance_result: dict | None = None,
    ) -> tuple[dict, dict]:
        issue_map: dict[int, list[str]] = {}
        score_map: dict[int, float] = {}

        chapter_nums = sorted(
            {
                int(num)
                for num in re.findall(
                    r"(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*[^\n]*)?\s*(?:\*\*)?\s*$",
                    full_content,
                )
            }
        )

        def _attach_reason(text: str):
            if not text:
                return
            for chap_num_str in re.findall(r"第\s*(\d+)\s*章", str(text)):
                chap_num = int(chap_num_str)
                issue_map.setdefault(chap_num, [])
                issue_map[chap_num].append(str(text))

        gate_reasons = list((gate_report or {}).get("hard_fail_reasons", []) or [])
        compliance_reasons = list((compliance_result or {}).get("hard_fail_reasons", []) or [])

        for reason in gate_reasons:
            _attach_reason(reason)
        for reason in compliance_reasons:
            _attach_reason(reason)

        placeholder_reasons = [
            str(reason).strip()
            for reason in gate_reasons
            if (
                "占位" in str(reason)
                or "省略" in str(reason)
                or "定位字段含占位符" in str(reason)
                or "第X卷" in str(reason)
                or "子幕X" in str(reason)
            )
        ]
        if placeholder_reasons and chapter_nums:
            placeholder_patterns = [
                r"\bTODO\b",
                r"\bTBD\b",
                r"待补",
                r"待完善",
                r"此处省略",
                r"【占位】",
                r"第\s*[XxＸｘ]\s*卷",
                r"子幕\s*[XxＸｘ]",
                r"卷名\s*待定",
            ]
            placeholder_chapters: list[int] = []
            for chap_num in chapter_nums:
                chapter_content = self._extract_single_chapter(full_content, chap_num)
                if not chapter_content:
                    continue
                if any(re.search(pattern, chapter_content, flags=re.IGNORECASE) for pattern in placeholder_patterns):
                    placeholder_chapters.append(chap_num)

            if not placeholder_chapters:
                placeholder_chapters = chapter_nums.copy()

            for chap_num in placeholder_chapters:
                issue_map.setdefault(chap_num, [])
                issue_map[chap_num].extend(placeholder_reasons)

        duplicate_title_reasons = [
            str(reason).strip()
            for reason in gate_reasons
            if "章节标题重复" in str(reason)
        ]
        if duplicate_title_reasons and chapter_nums:
            title_map: dict[str, list[int]] = {}
            for chap_num in chapter_nums:
                chapter_content = self._extract_single_chapter(full_content, chap_num)
                if not chapter_content:
                    continue
                header_match = re.search(
                    r"(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*([^\n*]+))?\s*(?:\*\*)?\s*$",
                    chapter_content,
                )
                if not header_match:
                    continue
                chapter_title = str(header_match.group(2) or "").strip()
                if not chapter_title:
                    continue
                title_map.setdefault(chapter_title, []).append(chap_num)

            duplicate_chapters: set[int] = set()
            for chapters in title_map.values():
                if len(chapters) <= 1:
                    continue
                duplicate_chapters.update(chapters)

            target_chapters = sorted(duplicate_chapters) if duplicate_chapters else chapter_nums.copy()
            for chap_num in target_chapters:
                issue_map.setdefault(chap_num, [])
                issue_map[chap_num].extend(duplicate_title_reasons)

        from quality_checker import QualityChecker

        checker = QualityChecker(filepath="")
        for chap_num in chapter_nums:
            chapter_content = self._extract_single_chapter(full_content, chap_num)
            if not chapter_content:
                continue
            try:
                report = checker.check_chapter_quality(chapter_content, {"chapter_number": chap_num})
                score_map[chap_num] = float(report.overall_score)
                if report.overall_score < target_score:
                    issue_map.setdefault(chap_num, [])
                    issue_map[chap_num].append(
                        f"质量分 {report.overall_score:.1f} 低于目标 {target_score:.1f}"
                    )
                    for issue in report.issues[:4]:
                        issue_map[chap_num].append(issue.description)
            except Exception as e:
                issue_map.setdefault(chap_num, [])
                issue_map[chap_num].append(f"质量检测异常: {e}")

        # 去重
        deduped = {}
        for chap_num, issues in issue_map.items():
            unique_issues = []
            for issue in issues:
                if issue and issue not in unique_issues:
                    unique_issues.append(issue)
            if unique_issues:
                deduped[chap_num] = unique_issues

        return deduped, score_map

    def _run_targeted_repair_after_postcheck(
        self,
        filepath: str,
        full_content: str,
        target_score: float,
        gate_report: dict | None = None,
        compliance_result: dict | None = None,
        max_chapters: int = 20,
    ) -> tuple[str, dict]:
        issue_map, score_map = self._collect_postcheck_issue_map(
            full_content=full_content,
            target_score=target_score,
            gate_report=gate_report,
            compliance_result=compliance_result,
        )
        target_chapters = sorted(issue_map.keys())[:max_chapters]
        report = {
            "target_score": float(target_score),
            "target_chapters": target_chapters,
            "issues_by_chapter": {str(k): v for k, v in issue_map.items()},
            "scores": {str(k): score_map.get(k) for k in sorted(score_map.keys())},
            "repaired": [],
            "failed": [],
        }

        if not target_chapters:
            report["attempted"] = False
            report["summary"] = "未识别到可定向修复章节"
            return full_content, report

        report["attempted"] = True
        from novel_generator.blueprint_repairer import BlueprintRepairer

        repairer = BlueprintRepairer(
            interface_format=self.interface_format,
            api_key=self.api_key,
            base_url=self.base_url,
            llm_model=self.llm_model,
            filepath=filepath,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
        )

        updated_content = full_content
        for chapter_num in target_chapters:
            original_content = self._extract_single_chapter(updated_content, chapter_num)
            if not original_content:
                report["failed"].append({"chapter": chapter_num, "reason": "章节内容提取失败"})
                continue

            repaired = repairer.repair_single_chapter(
                chapter_number=chapter_num,
                original_content=original_content,
                quality_issues=issue_map.get(chapter_num, []),
                max_retries=2,
            )
            if not repaired:
                report["failed"].append({"chapter": chapter_num, "reason": "LLM修复失败"})
                continue

            repaired_single = self._extract_single_chapter(repaired, chapter_num)
            if repaired_single:
                repaired = repaired_single
            else:
                report["failed"].append({"chapter": chapter_num, "reason": "修复结果未包含目标章节"})
                continue

            repaired, normalized_fixes = self._normalize_missing_sections(
                repaired,
                chapter_num,
                chapter_num,
            )
            if normalized_fixes > 0:
                logging.info(f"🩹 第{chapter_num}章修复结果补齐缺失节：{normalized_fixes}")

            repaired_validation = self._strict_validation(repaired, chapter_num, chapter_num)
            if not repaired_validation.get("is_valid", False):
                report["failed"].append(
                    {
                        "chapter": chapter_num,
                        "reason": "修复结果未通过结构校验",
                        "errors": repaired_validation.get("errors", [])[:10],
                    }
                )
                continue

            updated_content = self._replace_chapter_content(updated_content, chapter_num, repaired)
            report["repaired"].append(chapter_num)

        updated_content, _ = self._format_cleanup_content(updated_content)
        report["summary"] = (
            f"定向修复完成：成功 {len(report['repaired'])} 章，失败 {len(report['failed'])} 章"
        )
        return updated_content, report
    
    def _format_cleanup_content(self, content: str) -> tuple[str, dict]:
        """仅在内存中执行目录格式整理，返回清理后的内容与统计信息。"""
        import re as re_module

        if not content:
            return "", {
                "chapter_count": 0,
                "original_length": 0,
                "new_length": 0,
                "removed": 0,
                "separator_fixes": 0,
                "refs_fixed": False,
                "duplicate_section_fixes": 0,
            }

        original_length = len(content)
        deduped_required_sections = [0]

        def fix_chapter_references(text):
            # 将“启下：...第X章”替换为“启下：...下一章”
            return re_module.sub(
                r'(启下[：:][^\n]*?)第\s*\d+\s*章(?![\s-])',
                r'\1下一章',
                text,
                flags=re_module.MULTILINE
            )

        def normalize_header_formats(text):
            # 统一章节标题为：第X章 - 标题
            text = re_module.sub(
                r'(?m)^\s*#{1,6}\s*\*{0,2}\s*第\s*(\d+)\s*章\s*[-–—:：]\s*([^\n*]+?)\s*\*{0,2}\s*$',
                lambda m: f"第{m.group(1)}章 - {m.group(2).strip()}",
                text
            )
            # 统一7个节标题为：## N. 节名
            canonical_sections = [
                (1, "基础元信息"),
                (2, "张力与冲突"),
                (3, "匠心思维应用"),
                (4, "伏笔与信息差"),
                (5, "暧昧与修罗场"),
                (6, "剧情精要"),
                (7, "衔接设计"),
            ]
            for num, name in canonical_sections:
                text = re_module.sub(
                    rf'(?m)^\s*(?:#{{1,6}}\s*)?(?:\*{{1,2}}\s*)?(?:\d+)\s*[\.、]\s*{re_module.escape(name)}\s*(?:\*{{1,2}})?\s*$',
                    f"## {num}. {name}",
                    text
                )
            return text

        def ensure_required_sections(text):
            # 对每章做离线结构补全，避免缺节导致整体失败
            chapter_matches = list(re_module.finditer(
                r'(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*[^\n*]+)?\s*(?:\*\*)?\s*$',
                text
            ))
            if not chapter_matches:
                return text

            default_section_content = {
                1: "## 1. 基础元信息\n章节序号：第{chapter_num}章\n章节标题：[待补充]\n定位：[待补充]\n核心功能：[待补充]\n字数目标：5000字\n出场角色：[待补充]",
                2: "## 2. 张力与冲突\n冲突类型：[待补充]\n核心冲突点：[待补充]\n紧张感曲线：[铺垫→爬升→爆发→回落]",
                3: "## 3. 匠心思维应用\n应用场景：[待补充]\n思维模式：[待补充]\n视觉化描述：[待补充]\n经典台词：[待补充]",
                4: "## 4. 伏笔与信息差\n本章植入伏笔：[待补充]\n本章回收伏笔：[待补充]\n信息差控制：[待补充]",
                5: "## 5. 暧昧与修罗场\n涉及的女性角色互动：本章不涉及女性角色互动",
                6: "## 6. 剧情精要\n开场：[待补充]\n发展：[待补充]\n高潮：[待补充]\n收尾：[待补充]",
                7: "## 7. 衔接设计\n承上：[待补充]\n转场：[待补充]\n启下：[待补充]",
            }
            required_sections = [
                (1, "基础元信息"),
                (2, "张力与冲突"),
                (3, "匠心思维应用"),
                (4, "伏笔与信息差"),
                (5, "暧昧与修罗场"),
                (6, "剧情精要"),
                (7, "衔接设计"),
            ]

            rebuilt_blocks = []
            for idx, match in enumerate(chapter_matches):
                chapter_num = int(match.group(1))
                start = match.start()
                end = chapter_matches[idx + 1].start() if idx + 1 < len(chapter_matches) else len(text)
                block = text[start:end].strip()
                block, _ = self._promote_section1_metadata_block(block)
                block, deduped_count = self._dedupe_required_sections_in_block(block)
                if deduped_count > 0:
                    deduped_required_sections[0] += deduped_count
                for sec_num, sec_name in required_sections:
                    pattern = re_module.compile(
                        rf'(?m)^\s*(?:#{{1,6}}\s*)?(?:\*{{1,2}}\s*)?(?:\d+)\s*[\.、]\s*{re_module.escape(sec_name)}\s*(?:\*{{1,2}})?\s*$'
                    )
                    if not pattern.search(block):
                        block += "\n\n" + default_section_content[sec_num].format(chapter_num=chapter_num)
                rebuilt_blocks.append(block)
            return "\n\n".join(rebuilt_blocks)

        content_before_fix = content
        content = fix_chapter_references(content)
        refs_fixed = content != content_before_fix
        content = normalize_header_formats(content)
        content = ensure_required_sections(content)

        # 修复章节分隔符问题
        content = re_module.sub(
            r'([^\n])(第\s*\d+\s*章\s*[-–—:：][^\n]*\n\s*##\s*1\.\s*基础元信息)',
            r'\1\n\n\2',
            content,
        )

        chapter_header_pattern = re_module.compile(
            r'(?m)^(?:#+\s*)?(?:\*\*)?\s*第\s*(\d+)\s*章(?:\s*[-–—:：]\s*[^\n*]+)?\s*(?:\*\*)?\s*$'
        )
        chapter_headers = list(chapter_header_pattern.finditer(content))

        chapters_dict = {}
        for idx, match in enumerate(chapter_headers):
            chapter_num = int(match.group(1))
            start = match.start()
            end = chapter_headers[idx + 1].start() if idx + 1 < len(chapter_headers) else len(content)
            chapter_content = content[start:end].strip()
            if chapter_num not in chapters_dict or len(chapter_content) > len(chapters_dict[chapter_num]):
                chapters_dict[chapter_num] = chapter_content

        sorted_chapters = sorted(chapters_dict.keys())
        cleaned_content = "\n\n".join([chapters_dict[num] for num in sorted_chapters]) if sorted_chapters else content.strip()

        fixes_made = [0]
        pattern = r'([^\n])(?=\n第\s*\d+\s*章\s*-)'

        def add_newline_before_chapter(match):
            fixes_made[0] += 1
            return match.group(1) + '\n\n'

        cleaned_content = re.sub(pattern, add_newline_before_chapter, cleaned_content)

        pattern2 = r'(\*?\*?\s*启下[：:][^\n]*?第\s*\d+\s*章\s*-[^\n]*)'

        def split_qixia_and_chapter(match):
            value = match.group(1)
            chapter_pos = value.find('第')
            if chapter_pos > 0:
                fixes_made[0] += 1
                return value[:chapter_pos].rstrip() + '\n\n' + value[chapter_pos:]
            return value

        cleaned_content = re.sub(pattern2, split_qixia_and_chapter, cleaned_content)
        cleaned_content = re.sub(r'\n{4,}', '\n\n\n', cleaned_content).strip()

        new_length = len(cleaned_content)
        removed = original_length - new_length
        stats = {
            "chapter_count": len(sorted_chapters),
            "original_length": original_length,
            "new_length": new_length,
            "removed": removed,
            "separator_fixes": fixes_made[0],
            "refs_fixed": refs_fixed,
            "duplicate_section_fixes": deduped_required_sections[0],
        }
        return cleaned_content, stats

    def _format_cleanup(self, filepath: str) -> bool:
        """
        🆕 格式整理：清理重复内容、修复格式混乱、去除空白章节
        """
        logging.info("=" * 60)
        logging.info("🧹 开始格式整理...")
        
        filename_dir = os.path.join(filepath, "Novel_directory.txt")
        content = read_file(filename_dir)
        if not content:
            logging.warning("格式整理：文件为空")
            return False

        cleaned_content, stats = self._format_cleanup_content(content)
        if stats.get("refs_fixed"):
            logging.info("  🔧 已将'启下'中的具体章节号替换为'下一章'")
        if stats.get("separator_fixes", 0) > 0:
            logging.info(f"  🔧 自动修复了 {stats['separator_fixes']} 处章节分隔格式错误")
        
        # 保存清理后的内容
        clear_file_content(filename_dir)
        save_string_to_txt(cleaned_content.strip(), filename_dir)

        original_length = max(1, stats.get("original_length", 1))
        removed = stats.get("removed", 0)
        logging.info(f"  - 去重后章节数: {stats.get('chapter_count', 0)}")
        logging.info(f"  - 原始大小: {stats.get('original_length', 0):,} 字符")
        logging.info(f"  - 清理后大小: {stats.get('new_length', 0):,} 字符")
        logging.info(f"  - 清理冗余: {removed:,} 字符 ({removed/original_length*100:.1f}%)")
        logging.info("✅ 格式整理完成")
        
        return True

    def _full_quality_repair_loop(self, filepath: str, max_rounds: int = 3, 
                                   target_score: float = 80.0) -> dict:
        """
        🆕 全自动质量修复循环：检查所有章节，自动修复低分章节，直到达标或达到最大轮次
        
        Args:
            filepath: 项目路径
            max_rounds: 最大修复轮次
            target_score: 目标平均分
            
        Returns:
            修复报告
        """
        from quality_checker import QualityChecker
        from novel_generator.blueprint_repairer import BlueprintRepairer
        
        logging.info("=" * 60)
        logging.info("🔄 开始全自动质量修复循环...")
        logging.info(f"  - 最大轮次: {max_rounds}")
        logging.info(f"  - 目标平均分: {target_score}")
        
        filename_dir = os.path.join(filepath, "Novel_directory.txt")
        checker = QualityChecker(filepath)
        
        repair_stats = {
            "rounds_completed": 0,
            "total_repaired": 0,
            "initial_avg_score": 0,
            "final_avg_score": 0,
            "chapters_improved": [],
            "critic_reject_count": 0
        }
        chapter_pattern = r'(?m)(第\s*(\d+)\s*章\s*[-–—][^\n]*\n[\s\S]*?)(?=^第\s*\d+\s*章\s*[-–—]|\Z)'
        
        for round_num in range(1, max_rounds + 1):
            logging.info("-" * 50)
            logging.info(f"📊 第 {round_num}/{max_rounds} 轮质量检查...")
            
            # 重新读取内容
            content = read_file(filename_dir)
            if not content:
                break
            
            # 提取所有章节
            matches = list(re.finditer(chapter_pattern, content))
            
            all_scores = []
            low_score_chapters = []
            
            for match in matches:
                chapter_num = int(match.group(2))
                chapter_content = match.group(1).strip()
                
                try:
                    report = checker.check_chapter_quality(
                        chapter_content, {"chapter_number": chapter_num}
                    )
                    all_scores.append(report.overall_score)

                    needs_repair = report.overall_score < target_score
                    issues = [i.description for i in report.issues]

                    # 边缘分章节触发毒舌评审
                    critic_trigger_line = target_score - self.blueprint_critic_trigger_margin
                    if self.enable_blueprint_critic and report.overall_score >= critic_trigger_line:
                        critic_result = self._run_blueprint_critic(chapter_num, chapter_content)
                        if critic_result.get("rejected"):
                            needs_repair = True
                            repair_stats["critic_reject_count"] += 1
                            critic_issue = (
                                f"毒舌拒收: score={critic_result.get('critic_score', 0):.2f}; "
                                f"comment={critic_result.get('toxic_comment', '')}; "
                                f"demand={critic_result.get('improvement_demand', '')}"
                            )
                            issues.append(critic_issue)

                    if needs_repair:
                        low_score_chapters.append({
                            'chapter_number': chapter_num,
                            'content': chapter_content,
                            'score': report.overall_score,
                            'issues': issues
                        })
                except Exception as e:
                    logging.warning(f"  检查第{chapter_num}章失败: {e}")
            
            avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
            
            if round_num == 1:
                repair_stats["initial_avg_score"] = avg_score
            
            logging.info(f"  - 检查章节数: {len(matches)}")
            logging.info(f"  - 当前平均分: {avg_score:.1f}")
            logging.info(f"  - 低分章节数: {len(low_score_chapters)}")
            
            # 如果没有低分章节，退出循环
            if not low_score_chapters:
                logging.info(f"✅ 所有章节质量达标，退出修复循环")
                repair_stats["rounds_completed"] = round_num
                repair_stats["final_avg_score"] = avg_score
                break
            
            # 🆕 修复所有低分章节（不再限制50章）
            chapters_to_repair = low_score_chapters  # 修复所有低分章节
            logging.info(f"🔧 本轮修复 {len(chapters_to_repair)} 章...")
            
            repairer = BlueprintRepairer(
                interface_format=self.interface_format,
                api_key=self.api_key,
                base_url=self.base_url,
                llm_model=self.llm_model,
                filepath=filepath,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout
            )
            
            repaired_count = 0
            for chapter_info in chapters_to_repair:
                chapter_num = chapter_info['chapter_number']
                
                try:
                    repaired = repairer.repair_single_chapter(
                        chapter_num, 
                        chapter_info['content'], 
                        chapter_info['issues'],
                        max_retries=2
                    )
                    
                    if repaired:
                        # 验证修复后分数
                        new_report = checker.check_chapter_quality(
                            repaired, {"chapter_number": chapter_num}
                        )
                        
                        if new_report.overall_score > chapter_info['score']:
                            # 替换内容
                            content = self._replace_chapter_content(content, chapter_num, repaired)
                            repaired_count += 1
                            repair_stats["chapters_improved"].append({
                                "chapter": chapter_num,
                                "before": chapter_info['score'],
                                "after": new_report.overall_score
                            })
                            logging.info(f"    第{chapter_num}章: {chapter_info['score']:.1f} → {new_report.overall_score:.1f} ✓")
                        else:
                            logging.info(f"    第{chapter_num}章: 修复无改善，保留原内容")
                except Exception as e:
                    logging.warning(f"    第{chapter_num}章修复失败: {e}")
            
            # 保存本轮修复结果
            try:
                content, cleanup_stats = self._format_cleanup_content(content)
                if cleanup_stats.get("chapter_count", 0) > 0:
                    logging.info(
                        "  - 本轮修复后整理: "
                        f"章节{cleanup_stats.get('chapter_count', 0)}，"
                        f"分隔修复{cleanup_stats.get('separator_fixes', 0)}处"
                    )
            except Exception as cleanup_e:
                logging.warning(f"  - 本轮修复后整理异常（继续发布当前结果）: {cleanup_e}")

            clear_file_content(filename_dir)
            save_string_to_txt(content.strip(), filename_dir)
            
            repair_stats["total_repaired"] += repaired_count
            repair_stats["rounds_completed"] = round_num
            logging.info(f"  本轮修复完成: {repaired_count} 章")
            
            # 短暂等待避免 API 限流
            time.sleep(5)
        
        # 最终统计
        final_content = read_file(filename_dir)
        final_matches = list(re.finditer(chapter_pattern, final_content))
        final_scores = []
        for match in final_matches:
            chapter_num = int(match.group(2))
            chapter_content = match.group(1).strip()
            try:
                report = checker.check_chapter_quality(chapter_content, {"chapter_number": chapter_num})
                final_scores.append(report.overall_score)
            except:
                pass
        
        repair_stats["final_avg_score"] = sum(final_scores) / len(final_scores) if final_scores else 0
        
        logging.info("=" * 60)
        logging.info("🎯 全自动修复循环完成！")
        logging.info(f"  - 完成轮次: {repair_stats['rounds_completed']}/{max_rounds}")
        logging.info(f"  - 总修复章节: {repair_stats['total_repaired']}")
        logging.info(f"  - 毒舌拒收次数: {repair_stats['critic_reject_count']}")
        logging.info(f"  - 初始平均分: {repair_stats['initial_avg_score']:.1f}")
        logging.info(f"  - 最终平均分: {repair_stats['final_avg_score']:.1f}")
        logging.info(f"  - 分数提升: {repair_stats['final_avg_score'] - repair_stats['initial_avg_score']:+.1f}")
        
        return repair_stats

    def generate_complete_directory_strict(self, filepath: str, number_of_chapters: int,
                                        user_guidance: str = "", batch_size: int = 1,
                                        auto_optimize: bool = True,
                                        optimize_per_batch: bool = False,
                                        target_score: float = 80.0) -> bool:
        """
        严格的完整目录生成流程
        """
        import math
        from datetime import datetime

        if batch_size != 1:
            logging.warning(f"⚠️ 严格模式已强制单章批次：忽略传入 batch_size={batch_size}，改为 1")
        batch_size = 1
        
        total_batches = math.ceil(number_of_chapters / batch_size)
        logging.info("=" * 60)
        logging.info(f"📚 蓝图生成任务启动")
        logging.info(f"   总章节数: {number_of_chapters} | 每批: {batch_size}章 | 预计批次: {total_batches}")
        logging.info(f"   自动优化: {'开启' if auto_optimize else '关闭'}")
        logging.info(f"   批次内优化: {'开启' if optimize_per_batch else '关闭'}")
        logging.info(f"   质量目标分: {target_score:.1f}")
        logging.info(f"   蓝图毒舌评审: {'开启' if self.enable_blueprint_critic else '关闭'}")
        logging.info("=" * 60)

        # 检查架构文件
        arch_file = resolve_architecture_file(filepath)
        if not os.path.exists(arch_file):
            logging.error("❌ Novel_architecture.txt not found")
            return False

        full_architecture_text = read_file(arch_file).strip()
        if not full_architecture_text:
            logging.error("❌ 架构文件为空（Novel_architecture.txt）")
            return False
        architecture_text = build_runtime_architecture_view(full_architecture_text)
        if not architecture_text:
            logging.error("❌ 运行时架构切片为空（0-12, 88-136）")
            return False
        if contains_archive_sections(architecture_text):
            logging.error("❌ 运行时架构视图包含归档节（13-87），已阻断生成")
            return False
        architecture_hash = self._hash_text(full_architecture_text)

        # 检查现有目录
        filename_dir = os.path.join(filepath, "Novel_directory.txt")
        existing_content = ""

        if os.path.exists(filename_dir):
            existing_content = read_file(filename_dir).strip()
            if existing_content:
                logging.info("📂 检测到现有目录，将追加生成")
                try:
                    normalized_existing, existing_cleanup_stats = self._format_cleanup_content(existing_content)
                    normalized_existing = normalized_existing.strip()
                    if normalized_existing and normalized_existing != existing_content:
                        existing_content = normalized_existing
                        clear_file_content(filename_dir)
                        save_string_to_txt(existing_content, filename_dir)
                        logging.info(
                            "🧹 断点续传前已整理现有目录："
                            f"章节{existing_cleanup_stats.get('chapter_count', 0)}，"
                            f"清理冗余{existing_cleanup_stats.get('removed', 0)}字符"
                        )
                except Exception as existing_cleanup_e:
                    logging.warning(f"⚠️ 断点续传前整理失败（继续使用原内容）: {existing_cleanup_e}")

        run_state = self._load_state(filepath)
        old_architecture_hash = str(run_state.get("architecture_hash", "")).strip()

        existing_numbers_from_main = self._extract_directory_chapter_numbers(existing_content)
        existing_main_max = max(existing_numbers_from_main) if existing_numbers_from_main else 0
        split_progress = self._get_split_directory_progress(filepath)
        split_contiguous_end = int(split_progress.get("contiguous_end", 0) or 0)
        split_max = int(split_progress.get("max_chapter", 0) or 0)

        if split_contiguous_end > existing_main_max:
            if old_architecture_hash and old_architecture_hash != architecture_hash:
                logging.warning(
                    "⚠️ 检测到拆分目录进度更高（主目录第%d章 / 拆分连续到第%d章），"
                    "但当前架构哈希与历史状态不一致，跳过自动恢复。",
                    existing_main_max,
                    split_contiguous_end,
                )
            else:
                logging.warning(
                    "⚠️ 检测到主目录与拆分目录进度不一致："
                    "Novel_directory到第%d章，chapter_blueprints连续到第%d章（最大%d章）。"
                    "将自动恢复主目录后续写。",
                    existing_main_max,
                    split_contiguous_end,
                    split_max,
                )
                recovered_content, recovered_count = self._rebuild_directory_from_split_files(
                    filepath,
                    split_contiguous_end,
                )
                if recovered_count >= split_contiguous_end and recovered_content:
                    existing_content = recovered_content.strip()
                    clear_file_content(filename_dir)
                    save_string_to_txt(existing_content, filename_dir)
                    logging.info(
                        "🧩 已从拆分目录恢复汇总目录：第1-%d章（共%d章）",
                        split_contiguous_end,
                        recovered_count,
                    )
                else:
                    logging.error(
                        "❌ 拆分目录恢复失败：期望连续恢复到第%d章，实际恢复%d章",
                        split_contiguous_end,
                        recovered_count,
                    )

        if existing_content and old_architecture_hash and old_architecture_hash != architecture_hash:
            message = (
                "检测到架构文件已变更，禁止在旧目录上续写。"
                "请从头开始，或在UI中关闭“Step2检测架构变更时自动从头开始”后再续写。"
            )
            logging.error(f"❌ {message}")
            raise RuntimeError(message)
        if not old_architecture_hash:
            run_state["architecture_hash"] = architecture_hash

        # 确定起始章节（只匹配行首的章节标题，避免匹配正文中的章节引用）
        if existing_content:
            existing_numbers = self._extract_directory_chapter_numbers(existing_content)
            if existing_numbers:
                existing_max = max(existing_numbers)
                if self.enable_force_resume_skip_history_validation:
                    logging.warning(
                        "⚠️ 高风险强制续传已启用：跳过历史目录严格校验，"
                        f"将直接从第{existing_max + 1}章继续。"
                    )
                else:
                    baseline_validation = self._strict_validation(existing_content, 1, existing_max)
                    if not baseline_validation["is_valid"]:
                        baseline_errors = [str(err) for err in baseline_validation.get("errors", [])]
                        blocking_errors = [
                            err for err in baseline_errors
                            if self._is_blocking_resume_validation_error(err)
                        ]
                        if blocking_errors:
                            logging.error("❌ 现有目录在断点续传前未通过严格校验，且包含不可自动修复问题，已阻断追加生成")
                            for error in blocking_errors[:20]:
                                logging.error(f"  - {error}")
                            return False

                        if not self.enable_resume_auto_repair_existing:
                            logging.error("❌ 当前配置已关闭“断点续传自动修复”，现有目录未通过严格校验，已阻断追加生成")
                            for error in baseline_errors[:20]:
                                logging.error(f"  - {error}")
                            logging.error("  - 可选方案：在设置中开启“Step2断点续传时自动修复已有目录问题”后重试")
                            return False

                        logging.warning("⚠️ 现有目录未通过严格校验，启动断点续传自动修复后再继续")
                        repaired_content, repair_report = self._auto_repair_existing_for_resume(
                            filepath=filepath,
                            filename_dir=filename_dir,
                            existing_content=existing_content,
                            expected_end=existing_max,
                            max_rounds=2,
                        )
                        existing_content = str(repaired_content or "").strip()
                        existing_numbers = self._extract_directory_chapter_numbers(existing_content)
                        if not existing_numbers:
                            logging.error("❌ 断点续传自动修复后未识别到有效章节标题，已阻断追加生成")
                            return False

                        existing_max = max(existing_numbers)
                        baseline_validation = self._strict_validation(existing_content, 1, existing_max)
                        if not baseline_validation.get("is_valid", False):
                            logging.error("❌ 断点续传自动修复后仍未通过严格校验，已阻断追加生成")
                            for error in baseline_validation.get("errors", [])[:20]:
                                logging.error(f"  - {error}")
                            for error in repair_report.get("blocking_errors", [])[:10]:
                                logging.error(f"  - {error}")
                            return False

                        logging.info(
                            "✅ 断点续传自动修复成功："
                            f"修复{int(repair_report.get('repaired_total', 0))}章，"
                            f"轮次{int(repair_report.get('rounds_attempted', 0))}"
                        )
            start_chapter = max(existing_numbers) + 1 if existing_numbers else 1
            logging.info(f"📍 断点续传: 从第{start_chapter}章继续")
        else:
            start_chapter = 1

        if existing_content:
            # 断点续传前先补齐已存在章节的拆分文件，避免后续读取回退到整文件扫描。
            self._sync_split_directory_files(filepath, existing_content, remove_stale=False)

        if start_chapter > number_of_chapters:
            logging.info("✅ 检测到目录章节已覆盖目标范围，跳过增量生成并执行最终校验与发布闸门")
            current_hash = self._hash_text(existing_content)
            completed_target = int(
                run_state.get("completed_target_chapters")
                or run_state.get("target_chapters")
                or 0
            )
            completed_content_hash = str(run_state.get("completed_content_hash", "")).strip()
            state_marked_complete = bool(run_state.get("completed", False))
            if (
                state_marked_complete
                and completed_target == int(number_of_chapters)
                and old_architecture_hash == architecture_hash
                and completed_content_hash
                and completed_content_hash == current_hash
            ):
                quick_validation = self._strict_validation(existing_content, 1, number_of_chapters)
                if quick_validation["is_valid"]:
                    self._sync_split_directory_files(filepath, existing_content, remove_stale=True)
                    run_state.update(
                        {
                            "last_generated_chapter": int(number_of_chapters),
                            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }
                    )
                    self._save_state(filepath, run_state)
                    logging.info("✅ 检测到目录已发布且内容未变化，快速返回成功")
                    return True
                logging.warning("⚠️ 状态显示已完成，但快速校验未通过，改走完整发布闸门")

        final_blueprint = existing_content
        current_start = start_chapter
        batch_count = 0
        start_time = datetime.now()
        run_state.update({
            "architecture_hash": architecture_hash,
            "target_chapters": int(number_of_chapters),
            "last_generated_chapter": int(min(start_chapter - 1, number_of_chapters)),
            "completed_target_chapters": int(number_of_chapters),
            "completed_content_hash": "",
            "completed": False,
            "last_batch_telemetry": {},
            "batch_telemetry_history": [],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        self._save_state(filepath, run_state)

        # 分批生成
        while current_start <= number_of_chapters:
            current_end = min(current_start + batch_size - 1, number_of_chapters)
            batch_count += 1
            
            # 计算进度
            progress = current_end / number_of_chapters * 100
            remaining_batches = math.ceil((number_of_chapters - current_end) / batch_size)
            
            logging.info("-" * 50)
            logging.info(f"📝 批次 {batch_count}/{total_batches} | 第{current_start}-{current_end}章")
            logging.info(f"   进度: {progress:.1f}% | 剩余批次: {remaining_batches}")

            try:
                # 严格生成当前批次
                batch_result = self._generate_batch_with_retry(
                    current_start,
                    current_end,
                    architecture_text,
                    final_blueprint,
                    filepath,
                    full_architecture_text,
                )

                # 整合到最终结果
                if final_blueprint.strip():
                    final_blueprint += "\n\n" + batch_result.strip()
                else:
                    final_blueprint = batch_result.strip()

                # 先在内存中做格式整理，再一次性落盘，避免写盘-读盘-再写盘的重复IO
                try:
                    final_blueprint, cleanup_stats = self._format_cleanup_content(final_blueprint)
                    if cleanup_stats.get("separator_fixes", 0) > 0 or cleanup_stats.get("refs_fixed"):
                        logging.info(
                            f"🧹 第{batch_count}批内存整理完成：分隔修复{cleanup_stats.get('separator_fixes', 0)}处"
                        )
                except Exception as cleanup_e:
                    logging.warning(f"⚠️ 批次去重异常（不影响继续生成）: {cleanup_e}")

                # 立即保存当前进度（单次写盘）
                clear_file_content(filename_dir)
                save_string_to_txt(final_blueprint.strip(), filename_dir)
                latest_chapter_text = self._extract_single_chapter(final_blueprint, current_end) or batch_result
                self._sync_split_directory_files(filepath, latest_chapter_text, remove_stale=False)
                logging.info(f"✅ 第{batch_count}批已保存，进度：{current_end}/{number_of_chapters}")
                run_state["last_generated_chapter"] = int(current_end)
                self._append_run_batch_telemetry(run_state, self._latest_batch_telemetry)
                run_state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save_state(filepath, run_state)

                # === 分卷优化：默认关闭，避免与最终全量修复重复造成长时阻塞 ===
                if auto_optimize and optimize_per_batch:
                    try:
                        logging.info(f"🔍 正在检查第{current_start}章到第{current_end}章的质量...")
                        final_blueprint = self._batch_quality_optimize(
                            filepath, final_blueprint, current_start, current_end, target_score=target_score
                        )
                        # 重新保存优化后的内容
                        clear_file_content(filename_dir)
                        save_string_to_txt(final_blueprint.strip(), filename_dir)
                        latest_chapter_text = self._extract_single_chapter(final_blueprint, current_end)
                        if latest_chapter_text:
                            self._sync_split_directory_files(filepath, latest_chapter_text, remove_stale=False)
                    except Exception as opt_e:
                        logging.warning(f"⚠️ 批次优化异常（不影响继续生成）: {opt_e}")

                current_start = current_end + 1

            except Exception as e:
                logging.error(f"❌ 批次 {batch_count} 生成失败：{e}")
                # 严格模式下，任何批次失败都导致整体失败 (抛出异常以传递详细信息)
                raise Exception(f"第{batch_count}批次生成失败: {str(e)}")

        # 最终验证
        end_time = datetime.now()
        elapsed = end_time - start_time
        elapsed_minutes = elapsed.total_seconds() / 60
        
        logging.info("=" * 60)
        logging.info("🔎 进行最终验证...")
        final_content = read_file(filename_dir).strip()
        if final_content:
            validation_content = final_content
            validation_start = 1
            force_resume_mode = bool(
                self.enable_force_resume_skip_history_validation and start_chapter > 1
            )
            if force_resume_mode:
                validation_start = int(start_chapter)
                validation_content = self._extract_chapter_range_content(
                    final_content,
                    start_chapter,
                    number_of_chapters,
                )
                logging.warning(
                    "⚠️ 高风险强制续传模式：最终验证仅覆盖第%d-%d章，"
                    "历史章节校验与发布闸门将跳过。",
                    validation_start,
                    number_of_chapters,
                )

            final_validation = self._strict_validation(
                validation_content,
                validation_start,
                number_of_chapters,
            )

            if final_validation["is_valid"]:
                if force_resume_mode:
                    logging.warning(
                        "⚠️ 高风险强制续传模式已生效：本次任务按增量验证通过并完成，"
                        "但历史章节问题可能仍然存在。"
                    )
                    self._sync_split_directory_files(filepath, final_content, remove_stale=True)
                    run_state.update({
                        "completed": True,
                        "last_generated_chapter": int(number_of_chapters),
                        "completed_target_chapters": int(number_of_chapters),
                        "completed_content_hash": self._hash_text(final_content),
                        "last_run_elapsed_seconds": round(elapsed.total_seconds(), 3),
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "history_validation_skipped": True,
                        "history_validation_skipped_from_chapter": int(start_chapter),
                    })
                    self._save_state(filepath, run_state)
                    return True

                logging.info("=" * 60)
                logging.info("🎉 蓝图生成任务完成！")
                logging.info(f"   生成章节: 第1章 - 第{number_of_chapters}章")
                logging.info(f"   总批次数: {batch_count}")
                logging.info(f"   总耗时: {elapsed_minutes:.1f} 分钟")
                logging.info("=" * 60)
                
                # 🆕 Step 1: 格式整理（去重、排序、清理空行）
                try:
                    self._format_cleanup(filepath)
                except Exception as cleanup_e:
                    logging.warning(f"⚠️ 格式整理异常: {cleanup_e}")
                
                # 🆕 Step 2: 全自动质量修复循环
                if auto_optimize:
                    try:
                        repair_stats = self._full_quality_repair_loop(
                            filepath, 
                            max_rounds=3, 
                            target_score=target_score
                        )
                        logging.info(f"📊 修复统计: 初始{repair_stats['initial_avg_score']:.1f}分 → 最终{repair_stats['final_avg_score']:.1f}分")
                        try:
                            self._format_cleanup(filepath)
                        except Exception as post_repair_cleanup_e:
                            logging.warning(f"⚠️ 自动修复后格式整理异常: {post_repair_cleanup_e}")
                    except Exception as repair_e:
                        logging.warning(f"⚠️ 自动修复循环异常: {repair_e}")
                
                # 🆕 Step 3 + Step 4: 合规/闸门检查 + 失败后定向局部修复
                from novel_generator.architecture_compliance import ArchitectureComplianceChecker

                # Detect corpus name
                novel_corpus_name = ""
                try:
                    for item in os.listdir(filepath):
                        if os.path.isdir(os.path.join(filepath, item)):
                            if os.path.exists(resolve_architecture_file(os.path.join(filepath, item))):
                                novel_corpus_name = item
                                break
                except Exception as detect_e:
                    logging.warning(f"⚠️ 语料库名称检测失败，改用项目根目录: {detect_e}")

                checker = ArchitectureComplianceChecker(filepath, novel_corpus_name=novel_corpus_name)
                postcheck_max_repair_rounds = 2
                release_passed = False

                for check_round in range(1, postcheck_max_repair_rounds + 2):
                    logging.info(f"🔍 发布前校验轮次 {check_round}/{postcheck_max_repair_rounds + 1}")

                    try:
                        report_path = checker.generate_report_file()
                        logging.info(f"✅ 架构合规性报告已生成: {report_path}")
                        compliance_result = checker.check_compliance_result()
                    except Exception as compliance_e:
                        logging.error(f"❌ 自动架构合规性检查失败: {compliance_e}")
                        return False

                    try:
                        logging.info("🔒 正在执行目录质量最终校验闸门...")
                        gate_passed, gate_report = self._run_directory_quality_gate(filepath, filename_dir)
                    except Exception as gate_e:
                        logging.error(f"❌ 目录质量最终校验异常: {gate_e}")
                        return False

                    summary = gate_report.get("summary", {}) if isinstance(gate_report, dict) else {}
                    logging.info(
                        "📋 目录质量摘要: "
                        f"章节{summary.get('total_chapters', 0)} | "
                        f"占位符{summary.get('placeholder_count', 0)} | "
                        f"缺节章{summary.get('missing_section_chapter_count', 0)} | "
                        f"缺4节{summary.get('missing_section4_chapters', 0)} | "
                        f"缺5节{summary.get('missing_section5_chapters', 0)} | "
                        f"模板泄漏{summary.get('template_leak_count', 0)} | "
                        f"定位占位章{summary.get('location_placeholder_chapter_count', 0)} | "
                        f"重复标题组{summary.get('duplicate_title_group_count', 0)} | "
                        f"衔接风险{summary.get('transition_violation_count', 0)}"
                    )

                    compliance_passed = bool(compliance_result.get("passed", False))
                    if compliance_passed and gate_passed:
                        logging.info("✅ 架构合规与目录质量闸门均通过，可发布")
                        release_passed = True
                        break

                    compliance_reasons = compliance_result.get("hard_fail_reasons", []) or []
                    gate_reasons = gate_report.get("hard_fail_reasons", []) or []
                    rewrite_hints = gate_report.get("rewrite_hints", []) or []
                    logging.warning(
                        f"⚠️ 发布校验未通过：架构问题{len(compliance_reasons)}项，闸门问题{len(gate_reasons)}项"
                    )
                    if compliance_reasons:
                        logging.warning(f"  - 架构问题: {compliance_reasons}")
                    if gate_reasons:
                        logging.warning(f"  - 闸门问题: {gate_reasons}")
                    if rewrite_hints:
                        logging.warning(f"  - 建议: {rewrite_hints}")

                    if check_round > postcheck_max_repair_rounds:
                        logging.error("❌ 已达到发布前定向修复最大轮次，仍未通过校验")
                        break

                    current_content = read_file(filename_dir).strip()
                    repaired_content, repair_report = self._run_targeted_repair_after_postcheck(
                        filepath=filepath,
                        full_content=current_content,
                        target_score=target_score,
                        gate_report=gate_report,
                        compliance_result=compliance_result,
                        max_chapters=20,
                    )
                    repair_report["round"] = check_round
                    repair_report["compliance_reasons"] = compliance_reasons
                    repair_report["gate_reasons"] = gate_reasons
                    report_out = self._write_postcheck_repair_report(filepath, repair_report)
                    logging.info(f"🧾 已输出定向修复报告: {report_out}")

                    if not repair_report.get("attempted"):
                        logging.error("❌ 未识别到可定向修复章节，终止发布")
                        break
                    if len(repair_report.get("repaired", [])) == 0:
                        logging.error("❌ 定向修复未产生有效改动，终止发布")
                        break

                    clear_file_content(filename_dir)
                    save_string_to_txt(repaired_content.strip(), filename_dir)
                    self._sync_split_directory_files(filepath, repaired_content, remove_stale=False)
                    logging.info(
                        f"🔧 已完成第{check_round}轮定向修复："
                        f"成功{len(repair_report.get('repaired', []))}章，"
                        f"失败{len(repair_report.get('failed', []))}章"
                    )

                if not release_passed:
                    return False

                released_content = read_file(filename_dir).strip()
                self._sync_split_directory_files(filepath, released_content, remove_stale=True)
                run_state.update({
                    "completed": True,
                    "last_generated_chapter": int(number_of_chapters),
                    "completed_target_chapters": int(number_of_chapters),
                    "completed_content_hash": self._hash_text(released_content),
                    "last_run_elapsed_seconds": round(elapsed.total_seconds(), 3),
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "history_validation_skipped": False,
                    "history_validation_skipped_from_chapter": 0,
                })
                self._save_state(filepath, run_state)
                return True
            else:
                logging.error("❌ 最终验证失败：")
                for error in final_validation["errors"]:
                    logging.error(f"  - {error}")
                run_state.update({
                    "completed": False,
                    "completed_content_hash": "",
                    "last_run_elapsed_seconds": round(elapsed.total_seconds(), 3),
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "history_validation_skipped": False,
                    "history_validation_skipped_from_chapter": 0,
                })
                self._save_state(filepath, run_state)
                return False

        run_state.update({
            "completed": False,
            "completed_content_hash": "",
            "last_run_elapsed_seconds": round(elapsed.total_seconds(), 3),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "history_validation_skipped": False,
            "history_validation_skipped_from_chapter": 0,
        })
        self._save_state(filepath, run_state)
        return False

def Strict_Chapter_blueprint_generate(
    interface_format: str,
    api_key: str,
    base_url: str,
    llm_model: str,
    filepath: str,
    number_of_chapters: int,
    user_guidance: str = "",
    temperature: float = 0.8,
    max_tokens: int = 60000,
    timeout: int = 1800,
    batch_size: int = 1,
    auto_optimize: bool = True,
    optimize_per_batch: bool = False,
    target_score: float = 80.0,
    stage_timeout_seconds: int | None = None,
    heartbeat_interval_seconds: int = 30,
    enable_blueprint_critic: bool = False,
    blueprint_critic_threshold: float = 7.5,
    blueprint_critic_trigger_margin: float = 8.0,
    enable_resume_auto_repair_existing: bool = True,
    enable_force_resume_skip_history_validation: bool = False,
) -> None:
    """
    严格版本的章节蓝图生成函数
    
    Args:
        auto_optimize: 是否在每批次生成后自动进行质量检查和修复（默认True）
    """
    try:
        if batch_size != 1:
            logging.warning(f"⚠️ 严格蓝图入口已强制单章批次：忽略传入 batch_size={batch_size}，改为 1")
        batch_size = 1

        generator = StrictChapterGenerator(
            interface_format=interface_format,
            api_key=api_key,
            base_url=base_url,
            llm_model=llm_model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            stage_timeout_seconds=stage_timeout_seconds,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            enable_blueprint_critic=enable_blueprint_critic,
            blueprint_critic_threshold=blueprint_critic_threshold,
            blueprint_critic_trigger_margin=blueprint_critic_trigger_margin,
            enable_resume_auto_repair_existing=enable_resume_auto_repair_existing,
            enable_force_resume_skip_history_validation=enable_force_resume_skip_history_validation,
        )

        success = generator.generate_complete_directory_strict(
            filepath=filepath,
            number_of_chapters=number_of_chapters,
            user_guidance=user_guidance,
            batch_size=batch_size,
            auto_optimize=auto_optimize,
            optimize_per_batch=optimize_per_batch,
            target_score=target_score
        )

        if success:
            logging.info("🎉 严格章节目录生成成功完成")
        else:
            logging.error("❌ 严格章节目录生成失败 (未知原因，请检查日志)")
            raise RuntimeError("章节目录生成失败：验证未通过或未知错误")

    except Exception as e:
        error_msg = f"严格章节目录生成异常：{str(e)}"
        logging.error(error_msg)
        # 重新抛出包含详细信息的异常
        raise RuntimeError(error_msg) from e

if __name__ == "__main__":
    pass
