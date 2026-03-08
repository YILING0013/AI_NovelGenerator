# Contract tests for AI Novel Generator
# Tests API contracts and interface conformance

import pytest

pytestmark = pytest.mark.integration


class TestLLMAdapterContracts:
    """Test LLM adapter interface contracts."""

    def test_llm_adapter_interface_exists(self):
        """Test that LLM adapter interface is defined."""
        from llm_adapters import create_llm_adapter

        assert callable(create_llm_adapter)

    def test_llm_adapter_return_type(self):
        """Test that LLM adapter returns expected interface."""
        from unittest.mock import patch

        from llm_adapters import create_llm_adapter

        with patch("llm_adapters.OpenAIAdapter") as mock_adapter_class:
            mock_adapter = mock_adapter_class.return_value
            mock_adapter.invoke.return_value = "test response"

            adapter = create_llm_adapter(
                interface_format="openai",
                api_key="test-key",
                base_url="https://api.test.com",
                model_name="test-model",
            )

            # Adapter should have invoke method
            assert hasattr(adapter, "invoke")


class TestEmbeddingAdapterContracts:
    """Test embedding adapter interface contracts."""

    def test_embedding_adapter_interface_exists(self):
        """Test that embedding adapter interface is defined."""
        from embedding_adapters import create_embedding_adapter

        assert callable(create_embedding_adapter)


class TestConfigManagerContracts:
    """Test config manager interface contracts."""

    def test_load_config_signature(self):
        """Test load_config function signature."""
        from config_manager import load_config
        import inspect

        sig = inspect.signature(load_config)
        params = list(sig.parameters.keys())

        assert "config_file" in params or len(params) >= 1

    def test_save_config_signature(self):
        """Test save_config function signature."""
        from config_manager import save_config
        import inspect

        sig = inspect.signature(save_config)
        params = list(sig.parameters.keys())

        assert len(params) >= 2  # config_data and config_file


class TestPipelineContracts:
    """Test pipeline interface contracts."""

    def test_generation_context_interface(self):
        """Test GenerationContext interface."""
        from novel_generator.pipeline_interfaces import GenerationContext

        # Check required attributes - use correct parameter names
        context = GenerationContext(
            project_path="/test",
            chapter_number=1,
            total_chapters=10,
            interface_format="openai",
            api_key="test-key",
            base_url="https://api.test.com",
            model_name="test-model",
            temperature=0.7,
            max_tokens=1000,
            timeout=60,
        )

        assert hasattr(context, "chapter_number")
        assert hasattr(context, "project_path")

    def test_generation_result_interface(self):
        """Test GenerationResult interface."""
        from novel_generator.pipeline_interfaces import GenerationResult

        result = GenerationResult(success=True, stage="test", data={})

        assert hasattr(result, "success")
        assert hasattr(result, "stage")


class TestSchemaContracts:
    """Test schema validation contracts."""

    def test_schema_validator_interface(self):
        """Test SchemaValidator interface."""
        from novel_generator.schema_validator import SchemaValidator

        validator = SchemaValidator()

        assert hasattr(validator, "validate_blueprint_format")
