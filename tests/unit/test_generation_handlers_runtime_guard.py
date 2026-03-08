from __future__ import annotations

import ast
import inspect
from pathlib import Path
import threading
import textwrap

import pytest

import ui.generation_handlers as generation_handlers
from config_manager import create_config
from ui.generation_handlers import (
    _apply_hard_gate_repairs,
    _ask_yes_no_on_main_thread,
    _load_post_batch_runtime_audit_options,
    _load_runtime_architecture_text,
    _run_post_batch_runtime_audit,
    _safe_float,
    _safe_int,
    _runtime_architecture_precheck,
    _should_raise_hard_gate_after_repair,
    do_consistency_check,
)


def test_runtime_architecture_precheck_passes_when_required_sections_exist(tmp_path):
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

    ok, issues = _runtime_architecture_precheck(str(tmp_path))

    assert ok is True
    assert issues == []


def test_runtime_architecture_precheck_fails_when_required_section_missing(tmp_path):
    (tmp_path / "Novel_architecture.txt").write_text(
        """
## 0. Meta
keep-0

## 13. Archive
drop-13
""".strip(),
        encoding="utf-8",
    )

    ok, issues = _runtime_architecture_precheck(str(tmp_path))

    assert ok is False
    assert any("关键节：88" in issue for issue in issues)


def test_load_runtime_architecture_text_filters_archive_sections(tmp_path):
    (tmp_path / "Novel_architecture.txt").write_text(
        """
## 0. Meta
keep-0

## 13. Archive
drop-13

## 88. Runtime
keep-88
""".strip(),
        encoding="utf-8",
    )

    runtime_text = _load_runtime_architecture_text(str(tmp_path))

    assert "## 0." in runtime_text
    assert "## 88." in runtime_text
    assert "## 13." not in runtime_text


def test_load_post_batch_runtime_audit_options_defaults():
    enabled, sample_size = _load_post_batch_runtime_audit_options({})

    assert enabled is False
    assert sample_size == 20


def test_load_post_batch_runtime_audit_options_normalizes_values():
    enabled, sample_size = _load_post_batch_runtime_audit_options(
        {
            "other_params": {
                "post_batch_runtime_audit_enabled": True,
                "post_batch_runtime_audit_sample_size": "15",
            }
        }
    )
    fallback_enabled, fallback_sample_size = _load_post_batch_runtime_audit_options(
        {
            "other_params": {
                "post_batch_runtime_audit_enabled": True,
                "post_batch_runtime_audit_sample_size": "invalid",
            }
        }
    )
    full_enabled, full_sample_size = _load_post_batch_runtime_audit_options(
        {
            "other_params": {
                "post_batch_runtime_audit_enabled": True,
                "post_batch_runtime_audit_sample_size": -5,
            }
        }
    )

    assert enabled is True
    assert sample_size == 15
    assert fallback_enabled is True
    assert fallback_sample_size == 20
    assert full_enabled is True
    assert full_sample_size == 0


def test_load_post_batch_runtime_audit_options_parses_string_switch():
    enabled, sample_size = _load_post_batch_runtime_audit_options(
        {
            "other_params": {
                "post_batch_runtime_audit_enabled": "false",
                "post_batch_runtime_audit_sample_size": "7",
            }
        }
    )
    assert enabled is False
    assert sample_size == 7


def test_safe_float_returns_none_for_invalid_input_types():
    assert _safe_float("3.5") == 3.5
    assert _safe_float(None) is None
    assert _safe_float("abc") is None


def test_safe_int_returns_none_for_invalid_input_types():
    assert _safe_int("7") == 7
    assert _safe_int(None) is None
    assert _safe_int("xyz") is None


def test_run_post_batch_runtime_audit_detects_archive_leak(tmp_path):
    log_file = tmp_path / "llm_logs" / "chapter_1" / "gen_initial.md"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(
        "## Prompt\n\n```\n## 0. Meta\nkeep-0\n\n## 13. Archive\nleak\n```\n",
        encoding="utf-8",
    )

    report = _run_post_batch_runtime_audit(str(tmp_path), sample_size=20)

    assert report["files_scanned"] == 1
    assert len(report["violations"]) == 1
    assert report["violations"][0]["archive_sections"] == [13]


def test_run_post_batch_runtime_audit_raises_for_invalid_project_dir(tmp_path):
    with pytest.raises(ValueError):
        _run_post_batch_runtime_audit(str(tmp_path / "missing"), sample_size=20)


def test_ask_yes_no_on_main_thread_direct_when_called_from_main_thread(monkeypatch):
    calls: list[tuple[str, str]] = []

    def _fake_askyesno(title: str, message: str) -> bool:
        calls.append((title, message))
        return True

    monkeypatch.setattr(generation_handlers.messagebox, "askyesno", _fake_askyesno)

    class _DummyMaster:
        def __init__(self) -> None:
            self.after_calls = 0

        def after(self, _delay: int, _callback) -> None:
            self.after_calls += 1

    class _DummyUI:
        def __init__(self) -> None:
            self.master = _DummyMaster()

    ui = _DummyUI()
    result = _ask_yes_no_on_main_thread(ui, "确认", "继续")

    assert result is True
    assert calls == [("确认", "继续")]
    assert ui.master.after_calls == 0


def test_ask_yes_no_on_main_thread_marshals_worker_thread_to_main_loop(monkeypatch):
    calls: list[tuple[str, str]] = []

    def _fake_askyesno(title: str, message: str) -> bool:
        calls.append((title, message))
        return False

    monkeypatch.setattr(generation_handlers.messagebox, "askyesno", _fake_askyesno)

    class _DummyMaster:
        def __init__(self) -> None:
            self.after_calls = 0

        def after(self, _delay: int, callback) -> None:
            self.after_calls += 1
            callback()

    class _DummyUI:
        def __init__(self) -> None:
            self.master = _DummyMaster()

    ui = _DummyUI()
    result_holder: dict[str, bool] = {}

    worker = threading.Thread(
        target=lambda: result_holder.setdefault("result", _ask_yes_no_on_main_thread(ui, "警告", "继续?"))
    )
    worker.start()
    worker.join(timeout=2)

    assert worker.is_alive() is False
    assert result_holder["result"] is False
    assert calls == [("警告", "继续?")]
    assert ui.master.after_calls == 1


def test_do_consistency_check_blocks_when_runtime_precheck_fails(monkeypatch, tmp_path):
    warning_calls: list[tuple[str, str]] = []

    def _fake_showwarning(title: str, message: str) -> None:
        warning_calls.append((title, message))

    monkeypatch.setattr(generation_handlers.messagebox, "showwarning", _fake_showwarning)
    monkeypatch.setattr(
        generation_handlers,
        "_runtime_architecture_precheck",
        lambda _path: (False, ["缺少关键节：88"]),
    )

    class _DummyVar:
        def __init__(self, value: str) -> None:
            self._value = value

        def get(self) -> str:
            return self._value

    class _DummyUI:
        def __init__(self, path: str) -> None:
            self.filepath_var = _DummyVar(path)
            self.logs: list[str] = []

        def safe_log(self, message: str) -> None:
            self.logs.append(message)

    ui = _DummyUI(str(tmp_path))
    do_consistency_check(ui)

    assert any("运行时架构守卫阻断" in line for line in ui.logs)
    assert warning_calls
    assert warning_calls[0][0] == "架构守卫阻断"
    assert "缺少关键节：88" in warning_calls[0][1]


def test_create_config_includes_post_batch_runtime_audit_defaults(tmp_path):
    config_path = tmp_path / "config.json"

    config = create_config(str(config_path))

    assert config["other_params"]["post_batch_runtime_audit_enabled"] is False
    assert config["other_params"]["post_batch_runtime_audit_sample_size"] == 20
    assert config["other_params"]["blueprint_full_auto_mode"] is True
    assert config["other_params"]["blueprint_auto_restart_on_arch_change"] is True
    assert config["other_params"]["blueprint_resume_auto_repair_existing"] is True
    assert config["other_params"]["blueprint_force_resume_skip_history_validation"] is False
    assert config["other_params"]["batch_partial_resume_allow_fallback"] is True
    assert config["other_params"]["batch_precheck_deep_scan"] is True
    assert config["other_params"]["batch_precheck_auto_continue_on_warning"] is True


def test_apply_hard_gate_repairs_returns_early_without_issues():
    text, unresolved, used_llm = _apply_hard_gate_repairs(
        chapter_text="chapter",
        issues=[],
        auto_fix_fn=lambda content, _issues: content + "-auto",
        llm_fix_fn=lambda content: content + "-llm",
        collect_issues_fn=lambda _content: ["unexpected"],
    )

    assert text == "chapter"
    assert unresolved == []
    assert used_llm is False


def test_apply_hard_gate_repairs_runs_llm_path_for_llm_conflicts():
    calls: list[str] = []

    def _auto_fix(content: str, _issues: list[str]) -> str:
        calls.append("auto")
        return content + "-auto"

    def _llm_fix(content: str) -> str:
        calls.append("llm")
        return content + "-llm"

    def _collect(_content: str) -> list[str]:
        calls.append("collect")
        return []

    text, unresolved, used_llm = _apply_hard_gate_repairs(
        chapter_text="chapter",
        issues=["LLM深度一致性冲突: 冲突A"],
        auto_fix_fn=_auto_fix,
        llm_fix_fn=_llm_fix,
        collect_issues_fn=_collect,
    )

    assert text == "chapter-auto-llm-auto"
    assert unresolved == []
    assert used_llm is True
    assert calls == ["auto", "llm", "auto", "collect"]


def test_should_raise_hard_gate_after_repair_respects_stop_flag():
    assert _should_raise_hard_gate_after_repair(True, ["issue"]) is True
    assert _should_raise_hard_gate_after_repair(True, []) is False
    assert _should_raise_hard_gate_after_repair(False, ["issue"]) is False


def test_generate_chapter_batch_initializes_finalize_llm_vars_before_consistency_repair_closure():
    source = inspect.getsource(generation_handlers.generate_batch_ui)
    module = ast.parse(textwrap.dedent(source))

    generate_batch_ui_node = next(
        node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "generate_batch_ui"
    )
    generate_chapter_batch_node = next(
        node
        for node in generate_batch_ui_node.body
        if isinstance(node, ast.FunctionDef) and node.name == "generate_chapter_batch"
    )
    repair_closure_line = next(
        node.lineno
        for node in generate_chapter_batch_node.body
        if isinstance(node, ast.FunctionDef) and node.name == "_repair_llm_consistency_conflicts"
    )

    required_finalize_vars = {
        "finalize_interface_format",
        "finalize_api_key",
        "finalize_base_url",
        "finalize_model_name",
        "finalize_temperature",
        "finalize_max_tokens",
        "finalize_timeout",
    }
    first_assignment_line_by_name: dict[str, int] = {}

    for node in generate_chapter_batch_node.body:
        if isinstance(node, ast.Assign):
            target_names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = [node.target.id]
        else:
            continue

        for target_name in target_names:
            if target_name in required_finalize_vars and target_name not in first_assignment_line_by_name:
                first_assignment_line_by_name[target_name] = node.lineno

    assert required_finalize_vars.issubset(first_assignment_line_by_name.keys())
    assert all(
        first_assignment_line_by_name[var_name] < repair_closure_line
        for var_name in required_finalize_vars
    )


def test_generation_handlers_has_no_generic_exception_catch_blocks():
    source = Path("ui/generation_handlers.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                pytest.fail("ui/generation_handlers.py contains generic except Exception block")
