# -*- coding: utf-8 -*-
"""Tests for batch helper utilities in ui.generation_handlers."""

import json

import pytest

import ui.generation_handlers as generation_handlers
from ui.generation_handlers import (
    _DEFAULT_BATCH_SETTINGS,
    _build_batch_precheck_risk_snapshot,
    _build_quality_loop_runtime_config,
    _build_drift_ledger_record,
    _collect_opening_anchor_issues,
    _detect_existing_blueprint_end,
    _emit_quality_loop_score_events,
    _estimate_step2_repair_eta_seconds,
    _extract_llm_runtime_settings,
    _format_eta_duration,
    _inject_role_library_profiles,
    _load_architecture_context_budgets,
    _load_blueprint_runtime_options,
    _load_blueprint_state_file,
    _inspect_existing_blueprint_progress,
    _load_batch_settings,
    _normalize_batch_settings,
    _normalize_quality_loop_result,
    _parse_step2_repair_progress_line,
    _parse_batch_chapter_range,
    _parse_batch_runtime_request,
    _require_llm_config,
    _read_drift_state_ledger_record,
    _restore_runtime_state_for_partial_batch,
    _resolve_quality_score,
    _resolve_quality_threshold,
    _run_quality_loop_with_reporting,
    _run_batch_precheck,
    _safe_bool,
    _save_batch_settings,
    _sync_blueprint_state_for_resume,
    _write_chapter_hard_gate_report,
    _write_drift_state_ledger_record,
)


def test_parse_batch_chapter_range_supports_single_field_range():
    assert _parse_batch_chapter_range("1-5", "") == (1, 5)
    assert _parse_batch_chapter_range("3到7", "") == (3, 7)


def test_detect_existing_blueprint_end_prefers_split_progress_when_main_file_truncated(tmp_path):
    # 主目录仅到43章
    lines = [f"第{i}章 - 主目录{i}" for i in range(1, 44)]
    (tmp_path / "Novel_directory.txt").write_text("\n".join(lines), encoding="utf-8")

    # 拆分目录已到763章
    split_dir = tmp_path / "chapter_blueprints"
    split_dir.mkdir(parents=True, exist_ok=True)
    chapter_template = "第{n}章 - 拆分目录{n}\n## 1. 基础元信息\n* **章节序号**：第{n}章\n"
    for chapter_num in range(1, 764):
        (split_dir / f"chapter_{chapter_num}.txt").write_text(
            chapter_template.format(n=chapter_num),
            encoding="utf-8",
        )

    assert _detect_existing_blueprint_end(str(tmp_path)) == 763


def test_inspect_existing_blueprint_progress_reports_both_sources(tmp_path):
    (tmp_path / "Novel_directory.txt").write_text(
        "\n".join([f"第{i}章 - 主目录{i}" for i in range(1, 44)]),
        encoding="utf-8",
    )
    split_dir = tmp_path / "chapter_blueprints"
    split_dir.mkdir(parents=True, exist_ok=True)
    for chapter_num in range(1, 101):
        (split_dir / f"chapter_{chapter_num}.txt").write_text(
            f"第{chapter_num}章 - 拆分目录{chapter_num}\n",
            encoding="utf-8",
        )

    probe = _inspect_existing_blueprint_progress(str(tmp_path))
    assert probe["main_max"] == 43
    assert probe["split_contiguous_end"] == 100
    assert probe["split_max"] == 100
    assert probe["split_count"] == 100
    assert probe["detected_end"] == 100


def test_detect_existing_blueprint_end_uses_contiguous_split_prefix(tmp_path):
    split_dir = tmp_path / "chapter_blueprints"
    split_dir.mkdir(parents=True, exist_ok=True)
    for chapter_num in [1, 2, 4]:
        (split_dir / f"chapter_{chapter_num}.txt").write_text(
            f"第{chapter_num}章 - 测试{chapter_num}\n",
            encoding="utf-8",
        )

    # 拆分目录存在断点时，应按连续前缀到2章
    assert _detect_existing_blueprint_end(str(tmp_path)) == 2

    # 若主目录更高，仍以主目录为准
    (tmp_path / "Novel_directory.txt").write_text(
        "\n".join([f"第{i}章 - 主目录{i}" for i in range(1, 6)]),
        encoding="utf-8",
    )
    assert _detect_existing_blueprint_end(str(tmp_path)) == 5


def test_parse_step2_repair_progress_line_round_start_and_chapter_success():
    state: dict[str, object] = {}
    event_start = _parse_step2_repair_progress_line(
        "2026-03-04 23:24:52 - root - INFO - 🛠️ 断点续传自动修复第1轮：尝试修复85个问题章节",
        state,
    )
    assert event_start and event_start["event"] == "round_start"
    assert event_start["round"] == 1
    assert event_start["total"] == 85

    event_done = _parse_step2_repair_progress_line(
        "2026-03-04 23:25:42 - novel_generator.blueprint_repairer - INFO - 第72章修复成功",
        state,
    )
    assert event_done and event_done["event"] == "chapter_done"
    assert event_done["chapter"] == 72
    assert event_done["completed"] == 1
    assert event_done["total"] == 85


def test_parse_step2_repair_progress_line_round_done_and_finish():
    state: dict[str, object] = {"round": 1, "total": 85, "completed_chapters": set(), "failed_chapters": set()}

    event_round_done = _parse_step2_repair_progress_line(
        "2026-03-04 23:41:00 - root - INFO - ✅ 断点续传自动修复第1轮完成：成功70章，失败15章",
        state,
    )
    assert event_round_done and event_round_done["event"] == "round_done"
    assert event_round_done["completed"] == 85
    assert event_round_done["success"] == 70
    assert event_round_done["failed"] == 15

    event_finish = _parse_step2_repair_progress_line(
        "2026-03-04 23:41:03 - root - INFO - ✅ 断点续传自动修复成功：修复72章，轮次2",
        state,
    )
    assert event_finish and event_finish["event"] == "repair_finished"
    assert event_finish["repaired"] == 72
    assert event_finish["round"] == 2


def test_format_eta_duration_outputs_human_readable_text():
    assert _format_eta_duration(None) == "计算中"
    assert _format_eta_duration(0) == "即将完成"
    assert _format_eta_duration(9) == "9s"
    assert _format_eta_duration(83) == "1m23s"
    assert _format_eta_duration(3700) == "1h01m"


def test_estimate_step2_repair_eta_seconds_uses_round_start_timestamp(monkeypatch):
    monkeypatch.setattr(generation_handlers.time, "time", lambda: 200.0)
    state = {"round_started_at": 100.0}
    eta = _estimate_step2_repair_eta_seconds(state, completed=10, total=25)
    # 100秒完成10章 => 10秒/章，剩余15章 => ETA 150秒
    assert eta == pytest.approx(150.0)


def test_parse_batch_chapter_range_supports_separate_start_end_fields():
    assert _parse_batch_chapter_range("2", "8") == (2, 8)


def test_parse_batch_chapter_range_rejects_conflicting_end_value():
    with pytest.raises(ValueError, match="不一致"):
        _parse_batch_chapter_range("1-5", "6")


def test_parse_batch_chapter_range_requires_end_when_not_range():
    with pytest.raises(ValueError, match="请填写结束章节"):
        _parse_batch_chapter_range("1", "")


def test_batch_settings_loads_defaults_when_file_missing(tmp_path):
    logs: list[str] = []
    loaded = _load_batch_settings(str(tmp_path), logs.append)
    assert loaded == _DEFAULT_BATCH_SETTINGS
    assert logs == []


def test_normalize_batch_settings_handles_legacy_string_values():
    normalized = _normalize_batch_settings(
        {
            "word_count": "6200",
            "min_word_count": "0",
            "auto_enrich": "false",
            "optimization": "1",
        }
    )
    assert normalized["word_count"] == 6200
    assert normalized["min_word_count"] == _DEFAULT_BATCH_SETTINGS["min_word_count"]
    assert normalized["auto_enrich"] is False
    assert normalized["optimization"] is True


def test_batch_settings_save_and_load_merge_defaults(tmp_path):
    logs: list[str] = []
    _save_batch_settings(str(tmp_path), {"word_count": 6000}, logs.append)
    loaded = _load_batch_settings(str(tmp_path), logs.append)

    assert loaded["word_count"] == 6000
    assert loaded["min_word_count"] == _DEFAULT_BATCH_SETTINGS["min_word_count"]
    assert loaded["optimization"] is _DEFAULT_BATCH_SETTINGS["optimization"]

    raw = json.loads((tmp_path / "batch_settings.json").read_text(encoding="utf-8"))
    assert raw["word_count"] == 6000
    assert raw["auto_enrich"] is True
    assert raw["optimization"] is True


def test_sync_blueprint_state_for_resume_updates_hash_and_progress(tmp_path):
    synced, message = _sync_blueprint_state_for_resume(
        str(tmp_path),
        current_arch_hash="abc123",
        existing_end=88,
        target_chapters=120,
    )
    assert synced is True
    assert "已同步续写状态" in message

    state = _load_blueprint_state_file(str(tmp_path))
    assert state["architecture_hash"] == "abc123"
    assert state["last_generated_chapter"] == 88
    assert state["target_chapters"] == 120
    assert state["completed"] is False


def test_sync_blueprint_state_for_resume_rejects_empty_hash(tmp_path):
    synced, message = _sync_blueprint_state_for_resume(
        str(tmp_path),
        current_arch_hash="",
        existing_end=12,
        target_chapters=100,
    )
    assert synced is False
    assert "架构哈希为空" in message


def test_restore_runtime_state_for_partial_batch_fallback_without_snapshot(tmp_path):
    project_path = str(tmp_path)
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    (chapters_dir / "chapter_1.txt").write_text("c1", encoding="utf-8")
    (chapters_dir / "chapter_2.txt").write_text("c2", encoding="utf-8")
    (chapters_dir / "chapter_3.txt").write_text("c3", encoding="utf-8")
    (chapters_dir / "chapter_4.txt").write_text("c4", encoding="utf-8")
    (chapters_dir / "chapter_5.txt").write_text("c5", encoding="utf-8")
    (tmp_path / "global_summary.txt").write_text("summary", encoding="utf-8")
    (tmp_path / "character_state.txt").write_text("state", encoding="utf-8")

    ok, msg, restored_items = _restore_runtime_state_for_partial_batch(project_path, 4)

    assert ok is True
    assert "降级回滚" in msg
    assert any("global_summary.txt" in item for item in restored_items)
    assert not (tmp_path / "global_summary.txt").exists()
    assert not (tmp_path / "character_state.txt").exists()
    assert (chapters_dir / "chapter_3.txt").exists()
    assert not (chapters_dir / "chapter_4.txt").exists()
    assert not (chapters_dir / "chapter_5.txt").exists()


def test_restore_runtime_state_for_partial_batch_fallback_requires_anchor_chapter(tmp_path):
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    (chapters_dir / "chapter_1.txt").write_text("c1", encoding="utf-8")
    (chapters_dir / "chapter_2.txt").write_text("c2", encoding="utf-8")

    ok, msg, restored_items = _restore_runtime_state_for_partial_batch(str(tmp_path), 4)

    assert ok is False
    assert "缺少第3章正文" in msg
    assert restored_items == []


def test_restore_runtime_state_for_partial_batch_strict_mode_blocks_without_snapshot(tmp_path):
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    (chapters_dir / "chapter_1.txt").write_text("c1", encoding="utf-8")
    (chapters_dir / "chapter_2.txt").write_text("c2", encoding="utf-8")
    (chapters_dir / "chapter_3.txt").write_text("c3", encoding="utf-8")
    (chapters_dir / "chapter_4.txt").write_text("c4", encoding="utf-8")

    ok, msg, restored_items = _restore_runtime_state_for_partial_batch(
        str(tmp_path),
        4,
        allow_fallback_without_snapshot=False,
    )

    assert ok is False
    assert "未找到第3章运行态快照" in msg
    assert restored_items == []
    assert (chapters_dir / "chapter_4.txt").exists()


def test_write_chapter_hard_gate_report_uses_continue_policy_wording(tmp_path):
    report_path = _write_chapter_hard_gate_report(
        filepath=str(tmp_path),
        chapter_num=3,
        error_text="HARD_GATE_BLOCK: 时间线冲突 -> 角色时间倒置",
        timestamp="2026-03-04 10:00:00",
        traceback_text="traceback",
        stop_on_hard_gate=False,
    )
    content = report_path and (tmp_path / "hard_gate_reports" / "第3章.md").read_text(encoding="utf-8")
    assert "批量策略: 命中硬阻断后不中断，继续后续章节" in content
    assert "批量任务未停止，继续执行后续章节" in content


def test_write_chapter_hard_gate_report_uses_stop_policy_wording(tmp_path):
    report_path = _write_chapter_hard_gate_report(
        filepath=str(tmp_path),
        chapter_num=4,
        error_text="HARD_GATE_BLOCK: 一致性冲突 -> 修为越阶",
        timestamp="2026-03-04 10:01:00",
        traceback_text="traceback",
        stop_on_hard_gate=True,
    )
    content = report_path and (tmp_path / "hard_gate_reports" / "第4章.md").read_text(encoding="utf-8")
    assert "批量策略: 命中硬阻断后终止当前批次" in content
    assert "批量任务已停止（命中硬阻断即停策略）" in content


def test_load_batch_settings_normalizes_legacy_payload(tmp_path):
    payload = {
        "word_count": "6800",
        "min_word_count": "3000",
        "auto_enrich": "false",
        "optimization": "true",
    }
    (tmp_path / "batch_settings.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = _load_batch_settings(str(tmp_path), lambda _msg: None)
    assert loaded["word_count"] == 6800
    assert loaded["min_word_count"] == 3000
    assert loaded["auto_enrich"] is False
    assert loaded["optimization"] is True


def test_inject_role_library_profiles_replaces_placeholder(tmp_path):
    role_lib_dir = tmp_path / "角色库"
    role_lib_dir.mkdir(parents=True, exist_ok=True)
    (role_lib_dir / "主角.txt").write_text("主角设定：李青", encoding="utf-8")
    (role_lib_dir / "师父.txt").write_text("师父设定：玄尘", encoding="utf-8")

    prompt = "核心人物：{characters_involved}\n其他段落"
    result = _inject_role_library_profiles(
        prompt_text=prompt,
        role_names=["主角", "师父"],
        role_lib_path=str(role_lib_dir),
        log_func=lambda _msg: None,
    )

    assert "{characters_involved}" not in result
    assert "主角设定：李青" in result
    assert "师父设定：玄尘" in result


def test_emit_quality_loop_score_events_normalizes_payload():
    class _DummyUI:
        def __init__(self) -> None:
            self.events = []

        def safe_log_quality_score_event(self, event):
            self.events.append(event)

    ui = _DummyUI()
    _emit_quality_loop_score_events(
        ui,
        chapter_num=9,
        logs=[
            {"iteration": 2, "raw_score": 7.8, "score": 8.1, "trigger_reasons": ["low_score"]},
            "invalid-item",
        ],
    )

    assert len(ui.events) == 1
    event = ui.events[0]
    assert event["event_type"] == "score_round"
    assert event["chapter"] == 9
    assert event["iteration"] == 2
    assert event["final_score"] == 8.1


def test_require_llm_config_returns_selected_entry():
    loaded_config = {
        "llm_configs": {
            "A": {"model_name": "demo"},
        }
    }
    assert _require_llm_config(loaded_config, "A") == {"model_name": "demo"}


def test_require_llm_config_raises_for_missing_entry():
    with pytest.raises(KeyError):
        _require_llm_config({"llm_configs": {}}, "missing")


def test_safe_bool_parses_string_values():
    assert _safe_bool("true") is True
    assert _safe_bool("FALSE") is False
    assert _safe_bool("1") is True
    assert _safe_bool("0") is False
    assert _safe_bool("unknown", default=True) is True


def test_resolve_quality_threshold_clamps_and_falls_back():
    assert _resolve_quality_threshold("9.5", 8.0) == 9.5
    assert _resolve_quality_threshold("invalid", 8.0) == 8.0
    assert _resolve_quality_threshold("99", 8.0) == 10.0


def test_build_quality_loop_runtime_config_normalizes_policy_flags():
    loop_cfg, threshold = _build_quality_loop_runtime_config(
        loaded_config={
            "llm_configs": {
                "Q": {
                    "quality_policy": {
                        "default_quality_threshold": "11",
                        "enable_compression": "false",
                        "force_critic_logging_each_iteration": "true",
                        "parse_failure_streak_limit": "5",
                    }
                },
                "C": {},
            }
        },
        quality_loop_llm_name="Q",
        consistency_review_llm_name="C",
        draft_defaults={
            "api_key": "k",
            "base_url": "u",
            "model_name": "m",
            "max_tokens": 4096,
            "timeout": 60,
            "interface_format": "OpenAI",
        },
        other_params={
            "force_critic_logging_each_iteration": False,
            "architecture_context_budget_quality_loop": "130000",
        },
        min_word_count=3500,
        target_word_count=4000,
        enable_llm_consistency_check=True,
        consistency_hard_gate=True,
        enable_timeline_check=True,
        timeline_hard_gate=True,
        default_quality_threshold=9.0,
    )
    policy = loop_cfg["quality_policy"]
    assert threshold == 10.0
    assert policy["enable_compression"] is False
    assert policy["force_critic_logging_each_iteration"] is True
    assert policy["parse_failure_streak_limit"] == 5
    assert loop_cfg["architecture_context_max_chars"] == 120000
    assert loop_cfg["architecture_context_ignore_budget"] is True


def test_load_architecture_context_budgets_normalizes_and_clamps():
    budgets = _load_architecture_context_budgets(
        {
            "other_params": {
                "architecture_context_budget_chapter_prompt": "3000",
                "architecture_context_budget_consistency": "bad",
                "architecture_context_budget_quality_loop": "130000",
            }
        }
    )
    assert budgets == {
        "chapter_prompt": 4000,
        "consistency": 22000,
        "quality_loop": 120000,
        "ignore_budget": True,
    }


def test_parse_batch_runtime_request_normalizes_boolean_switches():
    parsed = _parse_batch_runtime_request(
        {
            "start": "2",
            "end": "6",
            "word": "5000",
            "min": "3000",
            "auto_enrich": "false",
            "optimization": "1",
        }
    )
    assert parsed == (2, 6, 5000, 3000, False, True)


def test_parse_batch_runtime_request_rejects_invalid_range():
    with pytest.raises(ValueError, match="起始章节不能大于结束章节"):
        _parse_batch_runtime_request(
            {
                "start": "8",
                "end": "2",
                "word": "5000",
                "min": "3000",
                "auto_enrich": True,
                "optimization": True,
            }
        )


def test_run_batch_precheck_returns_false_when_user_cancels(monkeypatch):
    class _DummyUI:
        def __init__(self) -> None:
            self.logs: list[str] = []

        def safe_log(self, msg: str) -> None:
            self.logs.append(msg)

    monkeypatch.setattr(generation_handlers, "_ask_yes_no_on_main_thread", lambda *_args, **_kwargs: False)
    ui = _DummyUI()
    should_continue = _run_batch_precheck(
        ui,
        filepath="/tmp/project",
        start_chapter=1,
        end_chapter=3,
        pre_check_runner=lambda *_args, **_kwargs: {
            "summary": {"passed_checks": 4, "total_checks": 5, "warnings_count": 1},
            "warnings": ["warning-a"],
        },
    )
    assert should_continue is False
    assert any("用户取消批量生成" in item for item in ui.logs)


def test_run_batch_precheck_returns_true_on_runner_exception():
    class _DummyUI:
        def __init__(self) -> None:
            self.logs: list[str] = []

        def safe_log(self, msg: str) -> None:
            self.logs.append(msg)

    ui = _DummyUI()
    should_continue = _run_batch_precheck(
        ui,
        filepath="/tmp/project",
        start_chapter=1,
        end_chapter=3,
        pre_check_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert should_continue is True
    assert any("预检查失败" in item for item in ui.logs)


def test_run_batch_precheck_deep_scan_auto_continue_logs_risks(tmp_path):
    class _DummyUI:
        def __init__(self) -> None:
            self.logs: list[str] = []

        def safe_log(self, msg: str) -> None:
            self.logs.append(msg)

    ui = _DummyUI()
    should_continue = _run_batch_precheck(
        ui,
        filepath=str(tmp_path),
        start_chapter=1,
        end_chapter=6,
        pre_check_runner=lambda *_args, **_kwargs: {
            "summary": {"passed_checks": 4, "total_checks": 4, "warnings_count": 0},
            "warnings": [],
            "deep_checks": {
                "placeholder": {"count": 3, "chapters_affected": 2},
                "structure": {"chapters_affected": 1},
                "duplicate": {"pairs_found": 2},
                "consistency": {"chapters_affected": 4},
            },
        },
        deep_scan=True,
        auto_continue_on_warning=True,
    )
    assert should_continue is True
    assert any("预检深扫" in item for item in ui.logs)
    assert any("自动放行" in item for item in ui.logs)
    assert (tmp_path / "batch_precheck_report.json").exists()


def test_run_batch_precheck_report_persists_merged_deep_warnings(tmp_path):
    class _DummyUI:
        def __init__(self) -> None:
            self.logs: list[str] = []

        def safe_log(self, msg: str) -> None:
            self.logs.append(msg)

    ui = _DummyUI()
    should_continue = _run_batch_precheck(
        ui,
        filepath=str(tmp_path),
        start_chapter=1,
        end_chapter=6,
        pre_check_runner=lambda *_args, **_kwargs: {
            "summary": {"passed_checks": 4, "total_checks": 4, "warnings_count": 0},
            "warnings": [],
            "deep_checks": {
                "placeholder": {"count": 1, "chapters_affected": 1},
                "structure": {"chapters_affected": 0},
                "duplicate": {"pairs_found": 0},
                "consistency": {"chapters_affected": 0},
            },
        },
        deep_scan=True,
        auto_continue_on_warning=True,
    )

    assert should_continue is True
    report = json.loads((tmp_path / "batch_precheck_report.json").read_text(encoding="utf-8"))
    warnings = report.get("warnings", [])
    assert any("深扫发现占位符问题" in str(item) for item in warnings)
    assert int(report.get("summary", {}).get("warnings_count", 0)) >= 1


def test_run_batch_precheck_deep_scan_fallbacks_for_legacy_runner():
    class _DummyUI:
        def __init__(self) -> None:
            self.logs: list[str] = []

        def safe_log(self, msg: str) -> None:
            self.logs.append(msg)

    calls = {"count": 0}

    def _legacy_runner(filepath, start_chapter, end_chapter, print_report=False):
        calls["count"] += 1
        assert print_report is False
        return {
            "summary": {"passed_checks": 3, "total_checks": 3, "warnings_count": 0},
            "warnings": [],
        }

    ui = _DummyUI()
    should_continue = _run_batch_precheck(
        ui,
        filepath="/tmp/project",
        start_chapter=1,
        end_chapter=3,
        pre_check_runner=_legacy_runner,
        deep_scan=True,
    )
    assert should_continue is True
    assert calls["count"] == 1


def test_build_batch_precheck_risk_snapshot_marks_high_when_placeholder_exists():
    snapshot = _build_batch_precheck_risk_snapshot(
        {
            "chapter_range": "1-10",
            "summary": {"passed_checks": 4, "total_checks": 5, "warnings_count": 1},
            "warnings": ["占位符问题"],
            "deep_checks": {
                "placeholder": {"count": 2},
                "structure": {"chapters_affected": 0},
                "duplicate": {"pairs_found": 0},
                "consistency": {"chapters_affected": 1},
            },
        }
    )

    assert snapshot["risk_level"] == "high"
    assert snapshot["risk_label"].startswith("🔴")
    assert snapshot["metrics"]["placeholder_count"] == 2


def test_run_batch_precheck_emits_precheck_risk_event(tmp_path):
    class _DummyUI:
        def __init__(self) -> None:
            self.logs: list[str] = []
            self.events: list[dict] = []

        def safe_log(self, msg: str) -> None:
            self.logs.append(msg)

        def safe_log_precheck_risk_event(self, event: dict) -> None:
            self.events.append(event)

    ui = _DummyUI()
    should_continue = _run_batch_precheck(
        ui,
        filepath=str(tmp_path),
        start_chapter=1,
        end_chapter=5,
        pre_check_runner=lambda *_args, **_kwargs: {
            "chapter_range": "1-5",
            "summary": {"passed_checks": 4, "total_checks": 4, "warnings_count": 0},
            "warnings": [],
            "deep_checks": {
                "placeholder": {"count": 0},
                "structure": {"chapters_affected": 0},
                "duplicate": {"pairs_found": 0},
                "consistency": {"chapters_affected": 0},
            },
        },
        deep_scan=True,
    )

    assert should_continue is True
    assert ui.events
    assert ui.events[-1]["event_type"] == "batch_precheck_risk"
    assert ui.events[-1]["risk_level"] == "low"


def test_load_blueprint_runtime_options_parses_string_flags_and_bounds():
    options = _load_blueprint_runtime_options(
        other_params={
            "blueprint_target_score": "85.5",
            "blueprint_optimize_per_batch": "true",
            "blueprint_enable_critic": "false",
            "blueprint_critic_threshold": "7.2",
            "blueprint_critic_trigger_margin": "8.8",
            "blueprint_stage_timeout": "-1",
            "blueprint_heartbeat_interval": "0",
            "blueprint_full_auto_mode": "1",
            "blueprint_auto_restart_on_arch_change": "false",
            "blueprint_resume_auto_repair_existing": "no",
            "blueprint_force_resume_skip_history_validation": "true",
        },
        timeout_fallback=600,
    )
    assert options["blueprint_batch_size"] == 1
    assert options["blueprint_target_score"] == 85.5
    assert options["optimize_per_batch"] is True
    assert options["enable_blueprint_critic"] is False
    assert options["blueprint_critic_threshold"] == 7.2
    assert options["blueprint_critic_trigger_margin"] == 8.8
    assert options["blueprint_stage_timeout"] == 900
    assert options["blueprint_heartbeat_interval"] == 30
    assert options["blueprint_full_auto_mode"] is True
    assert options["blueprint_auto_restart_on_arch_change"] is False
    assert options["blueprint_resume_auto_repair_existing"] is False
    assert options["blueprint_force_resume_skip_history_validation"] is True


def test_load_blueprint_runtime_options_defaults_to_full_auto_mode():
    options = _load_blueprint_runtime_options(
        other_params={},
        timeout_fallback=600,
    )
    assert options["blueprint_full_auto_mode"] is True
    assert options["blueprint_auto_restart_on_arch_change"] is True
    assert options["blueprint_resume_auto_repair_existing"] is True
    assert options["blueprint_force_resume_skip_history_validation"] is False


def test_normalize_quality_loop_result_handles_invalid_payload():
    normalized = _normalize_quality_loop_result(
        {
            "content": 123,
            "final_score": "not-number",
            "iterations": "-5",
            "logs": "invalid",
            "status": "",
            "hard_gate_blocked": "true",
            "parse_failure_guard_engaged": "1",
        },
        fallback_content="fallback",
        fallback_score=7.2,
    )
    assert normalized["content"] == "fallback"
    assert normalized["final_score"] == 7.2
    assert normalized["iterations"] == 0
    assert normalized["logs"] == []
    assert normalized["status"] == "unknown"
    assert normalized["hard_gate_blocked"] is True
    assert normalized["parse_failure_guard_engaged"] is True


def test_extract_llm_runtime_settings_normalizes_numeric_fields():
    settings = _extract_llm_runtime_settings(
        {
            "interface_format": "OpenAI",
            "api_key": "k",
            "base_url": "u",
            "model_name": "m",
            "temperature": "0.35",
            "max_tokens": "0",
            "timeout": "-1",
        },
        default_max_tokens=4096,
        default_timeout=120,
    )
    assert settings["temperature"] == 0.35
    assert settings["max_tokens"] == 4096
    assert settings["timeout"] == 120


def test_resolve_quality_score_falls_back_to_dimension_average():
    score = _resolve_quality_score(
        {
            "综合评分": "invalid",
            "剧情连贯性": 8.0,
            "角色一致性": 7.0,
            "写作质量": 9.0,
        },
        default=2.0,
    )
    assert score == 8.0


def test_run_quality_loop_with_reporting_emits_events_and_logs_guard():
    class _DummyController:
        @staticmethod
        def execute_quality_loop(**_kwargs):
            return {
                "content": "new-content",
                "final_score": 8.8,
                "iterations": 2,
                "logs": [{"iteration": 1, "score": 8.0}],
                "parse_failure_guard_engaged": True,
            }

    class _DummyUI:
        def __init__(self) -> None:
            self.logs: list[str] = []
            self.events: list[dict] = []

        def safe_log(self, msg: str) -> None:
            self.logs.append(msg)

        def safe_log_quality_score_event(self, event):
            self.events.append(event)

    ui = _DummyUI()
    result = _run_quality_loop_with_reporting(
        ui,
        controller=_DummyController(),
        chapter_num=3,
        initial_content="old-content",
        threshold=9.0,
        progress_callback=None,
        stage_label="第3章闭环",
        fallback_score=0.0,
    )

    assert result["content"] == "new-content"
    assert result["final_score"] == 8.8
    assert len(ui.events) == 1
    assert any("评分解析失败保护模式" in item for item in ui.logs)


def test_run_quality_loop_with_reporting_returns_fallback_when_controller_missing():
    class _DummyUI:
        def __init__(self) -> None:
            self.logs: list[str] = []
            self.events: list[dict] = []

        def safe_log(self, msg: str) -> None:
            self.logs.append(msg)

        def safe_log_quality_score_event(self, event):
            self.events.append(event)

    ui = _DummyUI()
    result = _run_quality_loop_with_reporting(
        ui,
        controller=None,
        chapter_num=1,
        initial_content="fallback-content",
        threshold=9.0,
        progress_callback=None,
        stage_label="第1章重新闭环",
        fallback_score=6.6,
    )

    assert result["content"] == "fallback-content"
    assert result["final_score"] == 6.6
    assert ui.events == []
    assert any("控制器不可用" in item for item in ui.logs)


def test_build_drift_ledger_record_extracts_opening_and_ending_anchors():
    record = _build_drift_ledger_record(
        chapter_num=3,
        chapter_text="林舟在青石镇夜行。\n\n他握紧天书残页，准备迎敌。",
        chapter_contract={
            "required_terms": {
                "characters": ["林舟", "苏璃"],
                "key_items": ["天书残页"],
                "locations": ["青石镇"],
            }
        },
    )
    assert record["chapter"] == 3
    assert "林舟" in record["opening_anchor_terms"]
    assert "天书残页" in record["ending_anchor_terms"]


def test_write_and_read_drift_state_ledger_record_roundtrip(tmp_path):
    _write_drift_state_ledger_record(
        filepath=str(tmp_path),
        chapter_num=1,
        chapter_text="林舟踏入青石镇。\n\n他看见天书残页微光闪烁。",
        chapter_contract={
            "required_terms": {
                "characters": ["林舟"],
                "key_items": ["天书残页"],
                "locations": ["青石镇"],
            }
        },
    )
    record = _read_drift_state_ledger_record(str(tmp_path), 1)
    assert record.get("chapter") == 1
    assert "天书残页" in record.get("ending_anchor_terms", [])


def test_collect_opening_anchor_issues_detects_missing_opening_anchors():
    issues = _collect_opening_anchor_issues(
        chapter_num=2,
        chapter_text="夜色沉沉，风声呜咽。\n\n远处钟声回荡。",
        chapter_contract={
            "required_terms": {
                "characters": ["林舟", "苏璃"],
                "locations": ["青石镇"],
            }
        },
        previous_ledger_record={
            "ending_anchor_terms": ["天书残页", "青石镇"],
            "ending_preview": "林舟收起天书残页，转身离开青石镇。",
        },
    )
    assert any("开篇锚点漂移" in item for item in issues)


def test_collect_opening_anchor_issues_passes_when_opening_has_transition_and_anchor():
    issues = _collect_opening_anchor_issues(
        chapter_num=2,
        chapter_text="片刻后，林舟回到青石镇，心神仍系着天书残页。\n\n他抬头望向城门。",
        chapter_contract={
            "required_terms": {
                "characters": ["林舟"],
                "locations": ["青石镇"],
            }
        },
        previous_ledger_record={
            "ending_anchor_terms": ["天书残页"],
        },
    )
    assert issues == []
