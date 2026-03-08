from __future__ import annotations

from typing import cast

from novel_generator.quality_loop_controller import (
    PARSE_FAILURE_STREAK_LIMIT,
    QualityLoopController,
    QualityLoopPolicy,
    _normalize_initial_content,
    _normalize_quality_loop_inputs,
    _resolve_overall_score,
    _safe_bool,
)


def test_load_policy_supports_force_critic_logging_switch():
    controller = cast(QualityLoopController, cast(object, object()))
    policy = QualityLoopController._load_policy(
        controller,
        {"quality_policy": {"force_critic_logging_each_iteration": True}},
    )
    assert policy.force_critic_logging_each_iteration is True


def test_should_invoke_critic_when_forced_below_threshold():
    controller = cast(
        QualityLoopController,
        cast(
            object,
            type(
                "_DummyController",
                (),
                {
                    "critic_agent": object(),
                    "policy": QualityLoopPolicy(force_critic_logging_each_iteration=True),
                },
            )(),
        ),
    )
    assert QualityLoopController._should_invoke_critic(controller, overall_score=6.2, threshold=8.5)


def test_should_not_invoke_critic_without_force_below_threshold():
    controller = cast(
        QualityLoopController,
        cast(
            object,
            type(
                "_DummyController",
                (),
                {
                    "critic_agent": object(),
                    "policy": QualityLoopPolicy(force_critic_logging_each_iteration=False),
                },
            )(),
        ),
    )
    assert not QualityLoopController._should_invoke_critic(
        controller,
        overall_score=6.2,
        threshold=8.5,
    )


def test_safe_bool_parses_string_values():
    assert _safe_bool("true") is True
    assert _safe_bool("false") is False
    assert _safe_bool("0") is False
    assert _safe_bool("1") is True
    assert _safe_bool("unknown", default=True) is True


def test_load_policy_parses_boolean_switches_from_strings():
    controller = cast(QualityLoopController, cast(object, object()))
    policy = QualityLoopController._load_policy(
        controller,
        {
            "quality_policy": {
                "enable_llm_consistency_check": "false",
                "consistency_hard_gate": "0",
                "enable_timeline_check": "no",
                "timeline_hard_gate": "off",
                "enable_compression": "true",
                "force_critic_logging_each_iteration": "yes",
            }
        },
    )

    assert policy.enable_llm_consistency_check is False
    assert policy.consistency_hard_gate is False
    assert policy.enable_timeline_check is False
    assert policy.timeline_hard_gate is False
    assert policy.enable_compression is True
    assert policy.force_critic_logging_each_iteration is True


def test_normalize_quality_loop_inputs_clamps_values():
    policy = QualityLoopPolicy(
        default_quality_threshold=9.0,
        min_word_count_before_expand=3500,
        target_word_count_after_expand=4000,
    )
    threshold, min_words, target_words = _normalize_quality_loop_inputs(
        threshold=99,
        min_word_count=-1,
        target_word_count=1200,
        policy=policy,
    )

    assert threshold == 10.0
    assert min_words == 3500
    assert target_words == 3500


def test_load_policy_caps_max_iterations_for_safety():
    controller = cast(QualityLoopController, cast(object, object()))
    policy = QualityLoopController._load_policy(
        controller,
        {"quality_policy": {"max_iterations": 999}},
    )
    assert policy.max_iterations == 50


def test_load_policy_parses_parse_failure_streak_limit():
    controller = cast(QualityLoopController, cast(object, object()))
    policy = QualityLoopController._load_policy(
        controller,
        {"quality_policy": {"parse_failure_streak_limit": "7"}},
    )
    assert policy.parse_failure_streak_limit == 7


def test_load_policy_uses_default_parse_failure_streak_limit():
    controller = cast(QualityLoopController, cast(object, object()))
    policy = QualityLoopController._load_policy(controller, {"quality_policy": {}})
    assert policy.parse_failure_streak_limit == PARSE_FAILURE_STREAK_LIMIT


def test_resolve_overall_score_falls_back_to_dimension_average():
    score = _resolve_overall_score(
        {
            "综合评分": "invalid",
            "剧情连贯性": 8.0,
            "角色一致性": 9.0,
            "写作质量": 7.0,
            "架构遵循度": 8.0,
            "设定遵循度": 9.0,
            "情感张力": 8.0,
            "系统机制": 7.0,
        }
    )
    assert score == 8.0


def test_normalize_initial_content_handles_none_and_trims():
    assert _normalize_initial_content(None) == ""
    assert _normalize_initial_content("  abc  ") == "abc"


def test_execute_quality_loop_returns_invalid_input_for_empty_content():
    dummy = cast(
        QualityLoopController,
        cast(
            object,
            type(
                "_DummyController",
                (),
                {
                    "policy": QualityLoopPolicy(),
                    "novel_path": ".",
                },
            )(),
        ),
    )

    result = QualityLoopController.execute_quality_loop(
        dummy,
        initial_content="   ",
        chapter_num=1,
    )

    assert result["status"] == "invalid_input"
    assert result["iterations"] == 0
    assert result["final_score"] == 0.0
    assert result["parse_failure_guard_engaged"] is False
