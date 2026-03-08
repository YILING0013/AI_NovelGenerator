from __future__ import annotations

import json

from config_manager import (
    load_config,
    normalize_config_data,
    normalize_quality_policy,
    save_config,
)


def test_normalize_quality_policy_clamps_and_parses_types():
    policy = normalize_quality_policy(
        {
            "default_quality_threshold": "99",
            "max_iterations": "0",
            "min_word_count_before_expand": "-1",
            "target_word_count_after_expand": "1200",
            "stagnation_count_limit": "0",
            "parse_failure_streak_limit": "9",
            "enable_compression": "true",
            "force_critic_logging_each_iteration": "false",
        },
        fallback_threshold=8.8,
    )

    assert policy["default_quality_threshold"] == 10.0
    assert policy["max_iterations"] == 1
    assert policy["min_word_count_before_expand"] == 3500
    assert policy["target_word_count_after_expand"] == 3500
    assert policy["stagnation_count_limit"] == 1
    assert policy["parse_failure_streak_limit"] == 9
    assert policy["enable_compression"] is True
    assert policy["force_critic_logging_each_iteration"] is False


def test_normalize_config_data_normalizes_other_params_and_llm_policy():
    normalized = normalize_config_data(
        {
            "other_params": {
                "quality_threshold": "9.7",
                "post_batch_runtime_audit_enabled": "true",
                "post_batch_runtime_audit_sample_size": "-5",
                "architecture_context_ignore_budget": "0",
                "enable_chapter_contract_guard": "1",
                "chapter_contract_hard_gate": "false",
                "enable_state_ledger_writeback": "true",
                "state_ledger_hard_gate": "0",
                "enable_next_opening_anchor_guard": "1",
                "next_opening_anchor_hard_gate": "false",
                "blueprint_full_auto_mode": "true",
                "blueprint_auto_restart_on_arch_change": "0",
                "blueprint_resume_auto_repair_existing": "false",
                "blueprint_force_resume_skip_history_validation": "1",
                "batch_partial_resume_allow_fallback": "false",
                "batch_precheck_deep_scan": "0",
                "batch_precheck_auto_continue_on_warning": "1",
                "architecture_context_budget_chapter_prompt": "-1",
                "architecture_context_budget_consistency": "abc",
                "architecture_context_budget_quality_loop": "130000",
            },
            "llm_configs": {
                "demo": {
                    "quality_policy": {
                        "default_quality_threshold": "abc",
                        "parse_failure_streak_limit": "5",
                    }
                }
            },
        }
    )

    assert normalized["other_params"]["quality_threshold"] == 9.7
    assert normalized["other_params"]["post_batch_runtime_audit_enabled"] is True
    assert normalized["other_params"]["post_batch_runtime_audit_sample_size"] == 0
    assert normalized["other_params"]["architecture_context_ignore_budget"] is False
    assert normalized["other_params"]["enable_chapter_contract_guard"] is True
    assert normalized["other_params"]["chapter_contract_hard_gate"] is False
    assert normalized["other_params"]["enable_state_ledger_writeback"] is True
    assert normalized["other_params"]["state_ledger_hard_gate"] is False
    assert normalized["other_params"]["enable_next_opening_anchor_guard"] is True
    assert normalized["other_params"]["next_opening_anchor_hard_gate"] is False
    assert normalized["other_params"]["blueprint_full_auto_mode"] is True
    assert normalized["other_params"]["blueprint_auto_restart_on_arch_change"] is False
    assert normalized["other_params"]["blueprint_resume_auto_repair_existing"] is False
    assert normalized["other_params"]["blueprint_force_resume_skip_history_validation"] is True
    assert normalized["other_params"]["batch_partial_resume_allow_fallback"] is False
    assert normalized["other_params"]["batch_precheck_deep_scan"] is False
    assert normalized["other_params"]["batch_precheck_auto_continue_on_warning"] is True
    assert normalized["other_params"]["architecture_context_budget_chapter_prompt"] == 18000
    assert normalized["other_params"]["architecture_context_budget_consistency"] == 22000
    assert normalized["other_params"]["architecture_context_budget_quality_loop"] == 120000
    assert normalized["llm_configs"]["demo"]["quality_policy"]["default_quality_threshold"] == 9.7
    assert normalized["llm_configs"]["demo"]["quality_policy"]["parse_failure_streak_limit"] == 5


def test_save_and_load_config_keep_normalized_quality_policy(tmp_path):
    config_file = tmp_path / "config.json"
    save_ok = save_config(
        {
            "other_params": {
                "quality_threshold": "8.6",
                "architecture_context_budget_consistency": "3000",
            },
            "llm_configs": {
                "demo": {
                    "quality_policy": {
                        "default_quality_threshold": "11",
                        "enable_timeline_check": "false",
                        "parse_failure_streak_limit": "4",
                    }
                }
            },
        },
        str(config_file),
    )
    assert save_ok is True

    raw = json.loads(config_file.read_text(encoding="utf-8"))
    assert raw["llm_configs"]["demo"]["quality_policy"]["default_quality_threshold"] == 10.0
    assert raw["llm_configs"]["demo"]["quality_policy"]["enable_timeline_check"] is False
    assert raw["llm_configs"]["demo"]["quality_policy"]["parse_failure_streak_limit"] == 4
    assert raw["other_params"]["architecture_context_budget_consistency"] == 4000

    loaded = load_config(str(config_file))
    assert loaded["llm_configs"]["demo"]["quality_policy"]["default_quality_threshold"] == 10.0
    assert loaded["llm_configs"]["demo"]["quality_policy"]["enable_timeline_check"] is False
    assert loaded["other_params"]["architecture_context_budget_consistency"] == 4000
