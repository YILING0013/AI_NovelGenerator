# -*- coding: utf-8 -*-
"""
LLM适配器测试 - 基于实际代码结构
"""
import pytest
from unittest.mock import Mock, patch
from llm_adapters import DeepSeekAdapter, OpenAIAdapter, create_llm_adapter

class TestLLMAdapters:
    """LLM适配器测试类"""

    def test_deepseek_adapter_creation(self):
        """测试DeepSeek适配器创建"""
        config = {
            "api_key": "test-key",
            "base_url": "https://api.deepseek.com/v1",
            "model_name": "deepseek-chat",
            "temperature": 0.7,
            "max_tokens": 8192,
            "timeout": 600
        }

        adapter = DeepSeekAdapter(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model_name=config["model_name"],
            max_tokens=config["max_tokens"],
            temperature=config["temperature"],
            timeout=config["timeout"]
        )

        assert adapter.api_key == "test-key"
        assert adapter.model_name == "deepseek-chat"

    @patch('llm_adapters.ChatOpenAI')
    def test_openai_adapter_creation(self, mock_chat_openai):
        """测试OpenAI适配器创建"""
        mock_chat_openai.return_value = Mock()

        config = {
            "api_key": "test-key",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-4",
            "temperature": 0.7,
            "max_tokens": 4096
        }

        adapter = OpenAIAdapter(
            api_key=config["api_key"],
            base_url=config["base_url"],
            model_name=config["model_name"],
            max_tokens=config["max_tokens"],
            temperature=config["temperature"]
        )

        assert adapter.api_key == "test-key"
        assert adapter.model_name == "gpt-4"

    def test_create_llm_adapter_deepseek(self):
        """测试创建DeepSeek适配器"""
        config = {
            "api_key": "test-key",
            "base_url": "https://api.deepseek.com/v1",
            "model_name": "deepseek-chat",
            "interface_format": "DeepSeek",
            "temperature": 0.7,
            "max_tokens": 8192,
            "timeout": 600
        }

        with patch('llm_adapters.DeepSeekAdapter') as mock_adapter:
            mock_adapter.return_value = Mock()
            adapter = create_llm_adapter(config)
            mock_adapter.assert_called_once()

    def test_create_llm_adapter_openai(self):
        """测试创建OpenAI适配器"""
        config = {
            "api_key": "test-key",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-4",
            "interface_format": "OpenAI",
            "temperature": 0.7,
            "max_tokens": 4096
        }

        with patch('llm_adapters.OpenAIAdapter') as mock_adapter:
            mock_adapter.return_value = Mock()
            adapter = create_llm_adapter(config)
            mock_adapter.assert_called_once()

    @pytest.mark.parametrize("interface_format", [
        "DeepSeek", "deepseek", "DEEPSEEK"
    ])
    def test_interface_format_case_insensitive(self, interface_format):
        """测试接口格式大小写不敏感"""
        config = {
            "api_key": "test-key",
            "base_url": "https://api.test.com/v1",
            "model_name": "test-model",
            "interface_format": interface_format,
            "temperature": 0.7,
            "max_tokens": 2000
        }

        with patch('llm_adapters.DeepSeekAdapter') as mock_adapter:
            mock_adapter.return_value = Mock()
            create_llm_adapter(config)
            mock_adapter.assert_called_once()