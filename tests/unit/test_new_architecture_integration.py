# -*- coding: utf-8 -*-
"""Regression tests for ui.new_architecture_integration helpers."""

from ui.new_architecture_integration import NewArchitectureIntegration, add_new_architecture_options


class _DummyVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class _DummyGUI:
    def __init__(self):
        self.logs = []

    def safe_log(self, message):
        self.logs.append(str(message))


def test_add_new_architecture_options_gracefully_skips_without_parent_frame():
    gui = _DummyGUI()

    result = add_new_architecture_options(gui)

    assert result is None
    assert any("已跳过" in msg for msg in gui.logs)


def test_get_error_statistics_shape():
    gui = _DummyGUI()
    integration = NewArchitectureIntegration(gui)

    stats = integration.get_error_statistics()

    assert "total_errors" in stats
    assert "unique_errors" in stats
    assert "error_distribution" in stats
    assert "recent_errors_count" in stats


def test_use_new_pipeline_returns_disabled_when_switch_off():
    gui = _DummyGUI()
    integration = NewArchitectureIntegration(gui)
    integration.use_pipeline_architecture_var = _DummyVar(False)

    result = integration.use_new_pipeline_for_generation({})

    assert result["success"] is False
    assert result["reason"] == "管道架构未启用"


def test_validate_blueprint_skips_when_switch_off():
    gui = _DummyGUI()
    integration = NewArchitectureIntegration(gui)
    integration.enable_schema_validation_var = _DummyVar(False)

    result = integration.validate_blueprint_with_schema("/tmp/nonexistent")

    assert result["is_valid"] is True
    assert result["skipped"] is True
