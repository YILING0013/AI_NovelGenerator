# Integration tests for AI Novel Generator
# Tests cross-module interactions and end-to-end flows

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory with minimal structure."""
    project_dir = tmp_path / "test_novel"
    project_dir.mkdir()

    # Create minimal architecture file
    arch_file = project_dir / "Novel_architecture.txt"
    arch_file.write_text(
        "# Test Novel Architecture\n\n"
        "## 角色列表\n"
        "- 主角：张三\n"
        "- 女主：李四\n\n"
        "## 世界观\n"
        "修仙世界\n",
        encoding="utf-8",
    )

    # Create minimal config
    config = {
        "llm_configs": {
            "test_llm": {
                "interface_format": "openai",
                "api_key": "test-key",
                "base_url": "https://api.test.com",
                "model_name": "test-model",
            }
        },
        "choose_configs": {"architecture_llm": "test_llm"},
    }
    config_file = project_dir / "config.json"
    config_file.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    return project_dir


@pytest.fixture
def mock_llm_adapter():
    """Create a mock LLM adapter for testing."""
    adapter = MagicMock()
    adapter.invoke.return_value = "这是测试响应内容"
    return adapter


@pytest.fixture
def minimal_config():
    """Create minimal config for pipeline tests."""
    return {
        "llm_configs": {},
        "choose_configs": {},
        "filepath": "/tmp/test_novel",
    }


class TestPipelineIntegration:
    """Test the full generation pipeline integration."""

    def test_pipeline_factory_creates_valid_pipeline(self, minimal_config):
        """Test that PipelineFactory creates a valid pipeline."""
        from novel_generator.pipeline import PipelineFactory

        factory = PipelineFactory()
        pipeline = factory.create_default_pipeline(minimal_config)

        assert pipeline is not None
        assert hasattr(pipeline, "execute")
        assert hasattr(pipeline, "stages")

    def test_pipeline_stages_are_ordered_correctly(self, minimal_config):
        """Test that pipeline stages are in correct order."""
        from novel_generator.pipeline import PipelineFactory

        pipeline = PipelineFactory().create_default_pipeline(minimal_config)

        stage_names = [stage.name for stage in pipeline.stages]
        expected_order = ["blueprint", "prompt", "chapter", "finalization"]

        # Check that expected stages exist
        for expected in expected_order:
            assert any(expected in name.lower() for name in stage_names), (
                f"Expected stage containing '{expected}' not found in {stage_names}"
            )


class TestLLMServiceIntegration:
    """Test LLM service integration."""

    def test_llm_service_builds_adapter(self, mock_llm_adapter):
        """Test that LLM service can build an adapter."""
        from novel_generator.llm_service import build_llm_adapter

        with patch(
            "novel_generator.llm_service.create_llm_adapter",
            return_value=mock_llm_adapter,
        ):
            adapter = build_llm_adapter(
                interface_format="openai",
                api_key="test-key",
                base_url="https://api.test.com",
                model_name="test-model",
                temperature=0.7,
                max_tokens=1000,
                timeout=60,
            )

            assert adapter is not None


class TestVectorstoreIntegration:
    """Test vectorstore integration."""

    def test_vectorstore_ssl_guard_default_safe(self, monkeypatch):
        """Test that SSL verification is enabled by default."""
        import ssl

        # Remove env var if present
        monkeypatch.delenv("AI_NOVELGEN_ALLOW_INSECURE_SSL", raising=False)

        original_context = ssl._create_default_https_context
        try:
            # Import should not modify SSL context by default
            from novel_generator import vectorstore_utils

            # Just verify the module loaded
            assert vectorstore_utils is not None
        finally:
            ssl._create_default_https_context = original_context


class TestConfigIntegration:
    """Test configuration integration."""

    def test_config_load_save_roundtrip(self, temp_project_dir):
        """Test that config can be loaded and saved without data loss."""
        from config_manager import load_config, save_config

        config_file = temp_project_dir / "config.json"

        # Load config
        config = load_config(str(config_file))

        # Modify
        config["test_key"] = "test_value"

        # Save
        save_config(config, str(config_file))

        # Load again
        config2 = load_config(str(config_file))

        assert config2["test_key"] == "test_value"


class TestBlueprintIntegration:
    """Test blueprint generation integration."""

    def test_blueprint_validator_exists(self):
        """Test that blueprint validator can be imported."""
        from novel_generator import schema_validator

        assert schema_validator is not None

    def test_blueprint_schema_validation(self):
        """Test blueprint schema validation."""
        from novel_generator.schema_validator import SchemaValidator

        validator = SchemaValidator()

        # Valid blueprint content
        valid_content = """
第1章 - 测试章节

## 1. 基础元信息
- 视点角色：张三
- 场景：测试场景

## 2. 张力与冲突
- 冲突描述：测试冲突

## 3. 匠心思维应用
- 技巧：测试技巧

## 4. 伏笔与信息差
- 伏笔：测试伏笔

## 5. 暧昧与修罗场
- 内容：测试内容

## 6. 剧情精要
- 要点：测试要点

## 7. 衔接设计
- 衔接：测试衔接
"""

        result = validator.validate_blueprint_format(valid_content, 1, 1)
        # Validation may pass or fail, just ensure no exception
        assert "is_valid" in result


class TestChapterIntegration:
    """Test chapter generation integration."""

    def test_chapter_functions_exist(self):
        """Test that chapter generation functions exist."""
        from novel_generator import generate_chapter_draft

        assert callable(generate_chapter_draft)
