# -*- coding: utf-8 -*-
"""
LLM适配器测试 - 基于实际代码结构
"""
import pytest
from unittest.mock import Mock, patch
from llm_adapters import DeepSeekAdapter, OpenAIAdapter, GeminiAdapter, create_llm_adapter

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

    @patch('llm_adapters.requests.post')
    @patch('llm_adapters.ChatOpenAI')
    def test_openai_adapter_cloudflare_fallback(self, mock_chat_openai, mock_requests_post):
        mock_client = Mock()
        mock_client.invoke.side_effect = Exception("Attention Required! | Cloudflare")
        mock_chat_openai.return_value = mock_client

        mock_http_resp = Mock()
        mock_http_resp.status_code = 200
        mock_http_resp.text = '{"ok": true}'
        mock_http_resp.json.return_value = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "OK"}
                    ]
                }
            ]
        }
        mock_requests_post.return_value = mock_http_resp

        adapter = OpenAIAdapter(
            api_key="test-key",
            base_url="https://proxy.example.dev",
            model_name="gpt-5.3-codex",
            max_tokens=4096,
            temperature=0.7,
            timeout=60,
        )

        result = adapter.invoke("Please reply 'OK'")

        assert result == "OK"
        mock_requests_post.assert_called_once()
        request_url = mock_requests_post.call_args.args[0]
        request_payload = mock_requests_post.call_args.kwargs["json"]
        assert request_url.endswith("/v1/responses")
        assert request_payload["input"][0]["role"] == "user"

    @patch('llm_adapters._create_genai_client')
    def test_gemini_adapter_legacy_sdk_fallback(self, mock_create_client):
        class FakeLegacyTypes:
            class GenerationConfig:
                def __init__(self, temperature, max_output_tokens):
                    self.temperature = temperature
                    self.max_output_tokens = max_output_tokens

        class FakeLegacyModel:
            def __init__(self, model_name):
                self.model_name = model_name

            def generate_content(self, contents, generation_config=None):
                return type("Resp", (), {"text": "legacy-ok"})()

        class FakeLegacyClient:
            types = FakeLegacyTypes

            @staticmethod
            def GenerativeModel(model_name):
                return FakeLegacyModel(model_name)

        mock_create_client.return_value = (FakeLegacyClient(), "google_generativeai")

        adapter = GeminiAdapter(
            api_key="test-key",
            base_url="https://generativelanguage.googleapis.com",
            model_name="gemini-3-flash-preview",
            max_tokens=1024,
            temperature=0.6,
            timeout=60,
        )

        result = adapter.invoke("ping")
        assert result == "legacy-ok"
