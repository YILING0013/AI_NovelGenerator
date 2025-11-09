# -*- coding: utf-8 -*-
"""
LLM适配器测试
"""
import pytest
from unittest.mock import Mock, patch
from llm_adapters import LLMAdapterFactory, OpenAIAdapter, DeepSeekAdapter

class TestLLMAdapters:
    """LLM适配器测试类"""

    def test_factory_creation(self):
        """测试工厂模式创建适配器"""
        config = {
            "api_key": "test-key",
            "base_url": "https://api.test.com",
            "model_name": "test-model",
            "interface_format": "OpenAI",
            "temperature": 0.7,
            "max_tokens": 2000,
            "timeout": 60
        }

        adapter = LLMAdapterFactory.create_adapter(config)
        assert isinstance(adapter, OpenAIAdapter)
        assert adapter.config == config

    def test_adapter_invoke(self):
        """测试适配器调用"""
        config = {
            "api_key": "test-key",
            "interface_format": "OpenAI"
        }

        with patch('openai.ChatCompletion.create') as mock_create:
            mock_create.return_value = {
                "choices": [{"message": {"content": "测试响应"}}]
            }

            adapter = OpenAIAdapter(config)
            result = adapter.invoke("测试提示")
            assert result == "测试响应"

    def test_deepseek_adapter(self):
        """测试DeepSeek适配器"""
        config = {
            "api_key": "test-key",
            "interface_format": "DeepSeek"
        }

        adapter = LLMAdapterFactory.create_adapter(config)
        assert isinstance(adapter, DeepSeekAdapter)

    @pytest.mark.parametrize("interface_format,expected_class", [
        ("OpenAI", OpenAIAdapter),
        ("openai", OpenAIAdapter),
        ("DeepSeek", DeepSeekAdapter),
        ("deepseek", DeepSeekAdapter),
    ])
    def test_interface_format_case_insensitive(self, interface_format, expected_class):
        """测试接口格式大小写不敏感"""
        config = {
            "api_key": "test-key",
            "interface_format": interface_format
        }

        adapter = LLMAdapterFactory.create_adapter(config)
        assert isinstance(adapter, expected_class)
