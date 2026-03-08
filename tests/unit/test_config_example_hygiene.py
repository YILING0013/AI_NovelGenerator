from __future__ import annotations

import json
from pathlib import Path


def test_config_example_has_no_embedded_api_keys():
    config_path = Path("config.example.json")
    data = json.loads(config_path.read_text(encoding="utf-8"))

    llm_configs = data.get("llm_configs", {})
    assert isinstance(llm_configs, dict)
    assert llm_configs, "config.example.json must include llm_configs"

    for model_name, cfg in llm_configs.items():
        assert isinstance(cfg, dict), f"{model_name} config must be an object"
        assert str(cfg.get("api_key", "")) == "", f"{model_name} api_key must be empty in example config"


def test_config_example_quality_policy_keys_exist():
    config_path = Path("config.example.json")
    data = json.loads(config_path.read_text(encoding="utf-8"))
    llm_configs = data.get("llm_configs", {})
    assert isinstance(llm_configs, dict)

    required_policy_keys = {
        "default_quality_threshold",
        "max_iterations",
        "min_word_count_before_expand",
        "target_word_count_after_expand",
        "parse_failure_streak_limit",
        "enable_llm_consistency_check",
        "consistency_hard_gate",
        "enable_timeline_check",
        "timeline_hard_gate",
    }
    for model_name, cfg in llm_configs.items():
        policy = cfg.get("quality_policy", {}) if isinstance(cfg, dict) else {}
        assert isinstance(policy, dict), f"{model_name} quality_policy must be an object"
        missing = required_policy_keys.difference(policy.keys())
        assert not missing, f"{model_name} quality_policy missing keys: {sorted(missing)}"


def test_config_example_contains_architecture_context_budgets():
    config_path = Path("config.example.json")
    data = json.loads(config_path.read_text(encoding="utf-8"))

    other_params = data.get("other_params", {})
    assert isinstance(other_params, dict)

    required_budget_keys = {
        "architecture_context_ignore_budget",
        "enable_chapter_contract_guard",
        "chapter_contract_hard_gate",
        "enable_state_ledger_writeback",
        "state_ledger_hard_gate",
        "enable_next_opening_anchor_guard",
        "next_opening_anchor_hard_gate",
        "batch_partial_resume_allow_fallback",
        "batch_precheck_deep_scan",
        "batch_precheck_auto_continue_on_warning",
        "architecture_context_budget_chapter_prompt",
        "architecture_context_budget_consistency",
        "architecture_context_budget_quality_loop",
    }
    missing = required_budget_keys.difference(other_params.keys())
    assert not missing, f"other_params missing architecture budget keys: {sorted(missing)}"
