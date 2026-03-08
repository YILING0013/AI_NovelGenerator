# llm_adapters.py
# -*- coding: utf-8 -*-
import logging
import os
from typing import Optional
from urllib.parse import urlparse
import openai
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.inference.models import SystemMessage, UserMessage
from openai import OpenAI
import requests

if not hasattr(openai, "ChatCompletion"):
    class _ChatCompletionCompat:
        @staticmethod
        def create(*args, **kwargs):
            raise NotImplementedError("openai.ChatCompletion is not available in this SDK version")

    setattr(openai, "ChatCompletion", _ChatCompletionCompat)

# 🆕 延迟导入智能重试装饰器（避免循环导入）
_intelligent_retry_cache = None

def get_intelligent_retry():
    """延迟导入装饰器以避免循环依赖"""
    global _intelligent_retry_cache
    if _intelligent_retry_cache is None:
        from novel_generator.error_handler import intelligent_retry
        _intelligent_retry_cache = intelligent_retry
    return _intelligent_retry_cache

def with_intelligent_retry(max_attempts=3):
    """装饰器工厂函数，延迟应用智能重试装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # 手动实现重试逻辑以避免装饰器复杂性
            import time
            import random
            last_exception = None

            def _compute_wait_time(attempt_index: int) -> float:
                """指数退避 + 抖动等待时间。"""
                base_wait = min(2 ** attempt_index, 60)
                jitter = random.uniform(0, 0.5)  # 50%抖动
                return base_wait * (1 + jitter)

            for attempt in range(max_attempts):
                try:
                    result = func(*args, **kwargs)
                    # 某些适配器会在失败时返回空字符串而不是抛异常，这里也按可重试处理
                    if isinstance(result, str) and not result.strip():
                        if attempt < max_attempts - 1:
                            wait_time = _compute_wait_time(attempt)
                            logging.warning(
                                f"⚠️ API返回空响应 (尝试 {attempt + 1}/{max_attempts})，"
                                f"{wait_time:.1f}秒后重试..."
                            )
                            time.sleep(wait_time)
                            continue
                    return result
                except Exception as e:
                    last_exception = e
                    # 检查是否应该重试
                    error_msg = str(e).lower()
                    should_retry = (
                        'timeout' in error_msg or
                        '429' in error_msg or
                        'rate limit' in error_msg or
                        'resource exhausted' in error_msg or
                        '500' in error_msg or
                        '502' in error_msg or
                        '503' in error_msg or
                        '504' in error_msg or
                        'internal server error' in error_msg or
                        'service unavailable' in error_msg or
                        'bad gateway' in error_msg or
                        'gateway timeout' in error_msg or
                        'connection' in error_msg or
                        'network' in error_msg
                    )

                    if not should_retry:
                        # 不可重试的错误，直接抛出
                        raise

                    if attempt < max_attempts - 1:
                        wait_time = _compute_wait_time(attempt)
                        if (
                            '500' in error_msg
                            or '502' in error_msg
                            or '503' in error_msg
                            or '504' in error_msg
                            or 'internal server error' in error_msg
                            or 'service unavailable' in error_msg
                            or 'bad gateway' in error_msg
                            or 'gateway timeout' in error_msg
                        ):
                            wait_time = min(wait_time * 2, 120)
                        logging.warning(f"⚠️ API调用失败 (尝试 {attempt + 1}/{max_attempts}): {e}，{wait_time:.1f}秒后重试...")
                        time.sleep(wait_time)
                    else:
                        # 最后一次尝试失败
                        raise

            # 如果所有尝试都失败
            if last_exception:
                raise last_exception
        return wrapper
    return decorator


_PROXY_ENV_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
)


def normalize_proxy_env() -> None:
    for key in _PROXY_ENV_KEYS:
        proxy_value = os.environ.get(key)
        if not proxy_value:
            continue
        normalized = proxy_value.strip()
        if normalized.lower().startswith("socks://"):
            normalized = "socks5://" + normalized[len("socks://"):]
            os.environ[key] = normalized
            logging.warning("Proxy scheme normalized from socks:// to socks5:// for %s", key)


def check_base_url(url: str) -> str:
    """
    处理base_url的规则：
    1. 如果url以#结尾，则移除#并直接使用用户提供的url
    2. 否则检查是否需要添加/v1后缀
    """
    import re
    url = url.strip()
    if not url:
        return url
        
    if url.endswith('#'):
        return url.rstrip('#')
        
    if not re.search(r'/v\d+$', url):
        if '/v1' not in url:
            url = url.rstrip('/') + '/v1'
    return url


def validate_ollama_base_url(url: str) -> str:
    """为 Ollama 校验 base_url，并在本地 HTTPS 误配时给出清晰提示。"""
    normalized = check_base_url(url)
    if not normalized:
        return normalized

    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme == "https" and hostname in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError(
            "检测到 Ollama 本地地址使用了 HTTPS。Ollama 默认监听 HTTP，请将 Base URL 改为 "
            "http://localhost:11434/v1 或 http://127.0.0.1:11434/v1"
        )
    return normalized


def _create_genai_client(api_key: str):
    try:
        from google import genai

        client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        return client, "google_genai"
    except ImportError as primary_import_error:
        try:
            import google.generativeai as legacy_genai
        except ImportError as legacy_import_error:
            raise ImportError(
                "Gemini adapter requires `google-genai` or `google-generativeai`. "
                "Install with `pip install google-genai`."
            ) from primary_import_error

        legacy_genai.configure(api_key=api_key)
        logging.warning("Using deprecated google-generativeai SDK fallback for Gemini adapter.")
        return legacy_genai, "google_generativeai"


def _extract_genai_text(response) -> str:
    if not response:
        return ""

    text = getattr(response, "text", "")
    if isinstance(text, str) and text.strip():
        return text

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        chunks = [getattr(part, "text", "") for part in parts if getattr(part, "text", "")]
        if chunks:
            return "".join(chunks)
    return ""


class BaseLLMAdapter:
    """
    统一的 LLM 接口基类，为不同后端（OpenAI、Ollama、ML Studio、Gemini等）提供一致的方法签名。
    """
    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("Subclasses must implement .invoke(prompt) method.")

class DeepSeekAdapter(BaseLLMAdapter):
    """
    适配官方/OpenAI兼容接口（使用 langchain.ChatOpenAI）
    """
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
        self.base_url = check_base_url(base_url)
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        self._client = ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            timeout=self.timeout
        )

    @with_intelligent_retry(max_attempts=3)
    def invoke(self, prompt: str) -> str:
        response = self._client.invoke(prompt)
        if not response:
            logging.warning("No response from DeepSeekAdapter.")
            return ""
        return response.content

class OpenAIAdapter(BaseLLMAdapter):
    """
    适配官方/OpenAI兼容接口（使用 langchain.ChatOpenAI）
    """
    def __init__(self, api_key, base_url: str = "", model_name: str = "", max_tokens: int = 2000, temperature: float = 0.7, timeout: Optional[int] = 600):
        self._legacy_mode = isinstance(api_key, dict)
        if self._legacy_mode:
            config = dict(api_key)
            self.config = config
            self.api_key = config.get("api_key", "")
            self.base_url = check_base_url(config.get("base_url", "https://api.openai.com/v1"))
            self.model_name = config.get("model_name", "gpt-4o-mini")
            self.max_tokens = config.get("max_tokens", 2000)
            self.temperature = config.get("temperature", 0.7)
            self.timeout = config.get("timeout", 600)
            self._client = None
            return

        self.base_url = check_base_url(base_url)
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.config = {
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model_name": self.model_name,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "timeout": self.timeout,
            "interface_format": "OpenAI",
        }

        self._client = ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            timeout=self.timeout
        )

    @staticmethod
    def _is_cloudflare_block_error(error: Exception) -> bool:
        text = str(error).lower()
        return (
            "cloudflare" in text
            or "attention required" in text
            or "you have been blocked" in text
            or ("<!doctype html" in text and "devaicode.dev" in text)
        )

    def _invoke_via_responses_http(self, prompt: str) -> str:
        request_url = self.base_url.rstrip("/") + "/responses"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model_name,
            "input": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": self.temperature,
        }

        response = requests.post(
            request_url,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )

        if response.status_code >= 400:
            body_preview = (response.text or "").replace("\n", " ")[:280]
            raise RuntimeError(
                f"HTTP {response.status_code} from {request_url}: {body_preview}"
            )

        try:
            data = response.json()
        except Exception as json_error:
            body_preview = (response.text or "").replace("\n", " ")[:280]
            raise RuntimeError(
                f"Non-JSON response from {request_url}: {body_preview}"
            ) from json_error

        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        output = data.get("output")
        if isinstance(output, list):
            chunks = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        text = block.get("text")
                        if isinstance(text, str) and text.strip():
                            chunks.append(text)
                elif isinstance(content, str) and content.strip():
                    chunks.append(content)
            if chunks:
                return "\n".join(chunks).strip()

        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            choice = choices[0] if isinstance(choices[0], dict) else {}
            message = choice.get("message") if isinstance(choice, dict) else {}
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content

        raise RuntimeError("Responses API returned no text content.")

    @with_intelligent_retry(max_attempts=3)
    def invoke(self, prompt: str) -> str:
        if self._legacy_mode:
            chat_completion = getattr(openai, "ChatCompletion")
            response = chat_completion.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )
            if not response:
                logging.warning("No response from OpenAIAdapter.")
                return ""
            choices = response.get("choices", []) if isinstance(response, dict) else []
            if not choices:
                return ""
            message = choices[0].get("message", {})
            return message.get("content", "")

        if self._client is None:
            return ""

        try:
            response = self._client.invoke(prompt)
        except Exception as sdk_error:
            if self._is_cloudflare_block_error(sdk_error):
                logging.warning(
                    "OpenAI SDK request blocked by Cloudflare, retrying via direct /responses HTTP call."
                )
                return self._invoke_via_responses_http(prompt)
            raise

        if not response:
            logging.warning("No response from OpenAIAdapter.")
            return ""
        return str(response.content)

class GeminiAdapter(BaseLLMAdapter):
    """
    适配 Google Gemini（google-genai SDK）
    """

    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        self._client, self._gemini_sdk = _create_genai_client(self.api_key)

    @with_intelligent_retry(max_attempts=3)
    def invoke(self, prompt: str) -> str:
        try:
            if self._gemini_sdk == "google_genai":
                from google.genai import types as genai_types

                config = genai_types.GenerateContentConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                )

                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config,
                )
            else:
                generation_config = self._client.types.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                )
                model = self._client.GenerativeModel(model_name=self.model_name)
                response = model.generate_content(
                    contents=prompt,
                    generation_config=generation_config,
                )

            text = _extract_genai_text(response)
            if not text:
                logging.warning("No text response from Gemini API.")
                return ""
            return text
        except Exception as e:
            logging.error(f"Gemini API 调用失败: {e}")
            return ""

class AzureOpenAIAdapter(BaseLLMAdapter):
    """
    适配 Azure OpenAI 接口（使用 langchain.ChatOpenAI）
    """
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
        import re
        match = re.match(r'https://(.+?)/openai/deployments/(.+?)/chat/completions\?api-version=(.+)', base_url)
        if match:
            self.azure_endpoint = f"https://{match.group(1)}"
            self.azure_deployment = match.group(2)
            self.api_version = match.group(3)
        else:
            raise ValueError("Invalid Azure OpenAI base_url format")
        
        self.api_key = api_key
        self.model_name = self.azure_deployment
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        self._client = AzureChatOpenAI(
            azure_endpoint=self.azure_endpoint,
            azure_deployment=self.azure_deployment,
            api_version=self.api_version,
            api_key=self.api_key,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            timeout=self.timeout
        )

    @with_intelligent_retry(max_attempts=3)
    def invoke(self, prompt: str) -> str:
        response = self._client.invoke(prompt)
        if not response:
            logging.warning("No response from AzureOpenAIAdapter.")
            return ""
        return response.content

class OllamaAdapter(BaseLLMAdapter):
    """
    Ollama 同样有一个 OpenAI-like /v1/chat 接口，可直接使用 ChatOpenAI。
    """
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
        self.base_url = validate_ollama_base_url(base_url)
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        if self.api_key == '':
            self.api_key= 'ollama'

        self._client = ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            timeout=self.timeout
        )

    @with_intelligent_retry(max_attempts=3)
    def invoke(self, prompt: str) -> str:
        response = self._client.invoke(prompt)
        if not response:
            logging.warning("No response from OllamaAdapter.")
            return ""
        return response.content

class MLStudioAdapter(BaseLLMAdapter):
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
        self.base_url = check_base_url(base_url)
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        self._client = ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.base_url,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            timeout=self.timeout
        )

    @with_intelligent_retry(max_attempts=3)
    def invoke(self, prompt: str) -> str:
        try:
            response = self._client.invoke(prompt)
            if not response:
                logging.warning("No response from MLStudioAdapter.")
                return ""
            return response.content
        except Exception as e:
            logging.error(f"ML Studio API 调用超时或失败: {e}")
            return ""

class AzureAIAdapter(BaseLLMAdapter):
    """
    适配 Azure AI Inference 接口，用于访问Azure AI服务部署的模型
    使用 azure-ai-inference 库进行API调用
    """
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
        import re
        # 匹配形如 https://xxx.services.ai.azure.com/models/chat/completions?api-version=xxx 的URL
        match = re.match(r'https://(.+?)\.services\.ai\.azure\.com(?:/models)?(?:/chat/completions)?(?:\?api-version=(.+))?', base_url)
        if match:
            # endpoint需要是形如 https://xxx.services.ai.azure.com/models 的格式
            self.endpoint = f"https://{match.group(1)}.services.ai.azure.com/models"
            # 如果URL中包含api-version参数，使用它；否则使用默认值
            self.api_version = match.group(2) if match.group(2) else "2024-05-01-preview"
        else:
            raise ValueError("Invalid Azure AI base_url format. Expected format: https://<endpoint>.services.ai.azure.com/models/chat/completions?api-version=xxx")
        
        self.base_url = self.endpoint  # 存储处理后的endpoint URL
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        self._client = ChatCompletionsClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.api_key),
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout
        )

    @with_intelligent_retry(max_attempts=3)
    def invoke(self, prompt: str) -> str:
        try:
            response = self._client.complete(
                messages=[
                    SystemMessage("You are a helpful assistant."),
                    UserMessage(prompt)
                ]
            )
            if response and response.choices:
                return response.choices[0].message.content
            else:
                logging.warning("No response from AzureAIAdapter.")
                return ""
        except Exception as e:
            logging.error(f"Azure AI Inference API 调用失败: {e}")
            return ""

# 火山引擎实现
class VolcanoEngineAIAdapter(BaseLLMAdapter):
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
        self.base_url = check_base_url(base_url)
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        self._client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout  # 添加超时配置
        )
    def invoke(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "你是DeepSeek，是一个 AI 人工智能助手"},
                    {"role": "user", "content": prompt},
                ],
                timeout=self.timeout  # 添加超时参数
            )
            if not response:
                logging.warning("No response from DeepSeekAdapter.")
                return ""
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"火山引擎API调用超时或失败: {e}")
            return ""

class SiliconFlowAdapter(BaseLLMAdapter):
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
        self.base_url = check_base_url(base_url)
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        self._client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout  # 添加超时配置
        )
    def invoke(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "你是DeepSeek，是一个 AI 人工智能助手"},
                    {"role": "user", "content": prompt},
                ],
                timeout=self.timeout  # 添加超时参数
            )
            if not response:
                logging.warning("No response from DeepSeekAdapter.")
                return ""
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"硅基流动API调用超时或失败: {e}")
            return ""
# grok實現
class GrokAdapter(BaseLLMAdapter):
    """
    适配 xAI Grok API
    """
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
        self.base_url = check_base_url(base_url)
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        self._client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout
        )

    def invoke(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are Grok, created by xAI."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                timeout=self.timeout
            )
            if response and response.choices:
                return response.choices[0].message.content
            else:
                logging.warning("No response from GrokAdapter.")
                return ""
        except Exception as e:
            logging.error(f"Grok API 调用失败: {e}")
            return ""

class ZhipuAdapter(BaseLLMAdapter):
    """
    适配智谱AI GLM API接口
    智谱AI使用OpenAI兼容的API格式，但需要特殊的API Key格式和headers
    """
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
        # 智谱AI需要特殊处理，不能使用check_base_url因为它会添加/v1
        self.base_url = self._process_zhipu_base_url(base_url)
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        # 智谱AI需要特殊的默认headers
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            default_headers={
                "Content-Type": "application/json"
            }
        )

    def _process_zhipu_base_url(self, url: str) -> str:
        """
        智谱AI专用的URL处理逻辑 - 支持新旧API端点
        """
        url = url.strip()
        if not url:
            return url

        if url.endswith('#'):
            return url.rstrip('#')

        # 支持新的anthropic端点 - 直接使用
        if '/anthropic/v1/messages' in url:
            return url.rstrip('/')

        # 支持旧版本v4端点 - 需要OpenAI兼容接口
        if '/api/paas/v4' in url:
            return url.rstrip('/') if not url.endswith('/v4') else url

        # 如果URL已经包含chat/completions，直接返回
        if url.endswith('/chat/completions'):
            return url

        # 智谱AI标准接口应该是 /api/paas/v4
        if '/v4' in url:
            # 确保不会重复添加/v4
            if not url.endswith('/v4'):
                if '/v4/' in url:
                    url = url.split('/v4/')[0] + '/v4'
                else:
                    url = url.split('/v4')[0] + '/v4'
            return url

        # 默认情况下，添加智谱AI标准路径
        return url.rstrip('/') + '/api/paas/v4'

    @with_intelligent_retry(max_attempts=3)
    def invoke(self, prompt: str) -> str:
        try:
            logging.info(f"智谱AI API 调用 - 模型: {self.model_name}, base_url: {self.base_url}")
            logging.info(f"请求参数 - max_tokens: {self.max_tokens}, temperature: {self.temperature}, timeout: {self.timeout}")

            # 根据base_url判断使用哪种API格式
            if '/anthropic/v1/messages' in self.base_url:
                # 使用Anthropic格式API
                return self._invoke_anthropic_api(prompt)
            else:
                # 使用OpenAI兼容格式API
                return self._invoke_openai_api(prompt)

        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            logging.error(f"智谱AI API 调用失败 - 错误类型: {error_type}, 错误信息: {error_msg}")
            logging.error(
                "智谱AI API 调用参数 - api_key已配置: %s, key_length: %s",
                bool(self.api_key),
                len(self.api_key) if self.api_key else 0,
            )

            # 特殊处理常见错误
            if "429" in error_msg or "rate limit" in error_msg.lower():
                logging.error("智谱AI 速率限制错误 - 请稍后重试或检查账户余额")
            elif "404" in error_msg:
                logging.error("智谱AI 404错误 - 请检查模型名称或API地址是否正确")
            elif "401" in error_msg:
                logging.error("智谱AI 认证错误 - 请检查API Key是否有效")

            return ""

    def _invoke_anthropic_api(self, prompt: str) -> str:
        """使用Anthropic格式API调用"""
        try:
            import requests

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"
            }

            data = {
                "model": self.model_name,
                "max_tokens": self.max_tokens,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": self.temperature
            }

            response = requests.post(
                self.base_url,
                headers=headers,
                json=data,
                timeout=self.timeout
            )

            response.raise_for_status()
            result = response.json()

            if "content" in result and result["content"]:
                if isinstance(result["content"], list) and result["content"]:
                    content = result["content"][0].get("text", "")
                elif isinstance(result["content"], str):
                    content = result["content"]
                else:
                    content = str(result["content"])

                logging.info(f"智谱AI Anthropic API 成功获取响应: {content[:100]}...")
                return content
            else:
                logging.warning("智谱AI Anthropic API 响应为空或无content")
                return ""

        except Exception as e:
            logging.error(f"智谱AI Anthropic API 调用失败: {e}")
            raise

    def _invoke_openai_api(self, prompt: str) -> str:
        """使用OpenAI兼容格式API调用"""
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "你是智谱AI训练的大语言模型，请遵循用户的指示提供帮助。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                timeout=self.timeout
            )

            logging.info(f"智谱AI OpenAI API 响应: {response}")

            if response and response.choices:
                content = response.choices[0].message.content
                logging.info(f"智谱AI OpenAI API 成功获取响应: {content[:100]}...")
                return content
            else:
                logging.warning("智谱AI OpenAI API 响应为空或无choices")
                return ""

        except Exception as e:
            logging.error(f"智谱AI OpenAI API 调用失败: {e}")
            raise


class Gemini3Adapter(GeminiAdapter):
    """
    Gemini 3 兼容别名，复用 GeminiAdapter 的 google-genai 实现。
    """
    pass

def create_llm_adapter(
    interface_format,
    base_url: str = "",
    model_name: str = "",
    api_key: str = "",
    temperature: float = 0.7,
    max_tokens: int = 2000,
    timeout: int = 600
) -> BaseLLMAdapter:
    """
    工厂函数：根据 interface_format 返回不同的适配器实例。
    """
    normalize_proxy_env()
    config_input = interface_format if isinstance(interface_format, dict) else None
    if config_input is not None:
        interface_format = config_input.get("interface_format", "OpenAI")
        base_url = config_input.get("base_url", "")
        model_name = config_input.get("model_name", "")
        api_key = config_input.get("api_key", "")
        temperature = config_input.get("temperature", 0.7)
        max_tokens = config_input.get("max_tokens", 2000)
        timeout = config_input.get("timeout", 600)

    fmt = str(interface_format).strip().lower()
    if fmt == "deepseek":
        if not base_url:
            base_url = "https://api.deepseek.com/v1"
        if not model_name:
            model_name = "deepseek-chat"
    elif fmt == "openai":
        if not base_url:
            base_url = "https://api.openai.com/v1"
        if not model_name:
            model_name = "gpt-4o-mini"

    if fmt == "deepseek":
        return DeepSeekAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "openai":
        return OpenAIAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "azure openai":
        return AzureOpenAIAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "azure ai":
        return AzureAIAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "ollama":
        return OllamaAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "ml studio":
        return MLStudioAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "gemini":
        if "gemini-3" in model_name.lower() or "gemini 3" in model_name.lower():
            return Gemini3Adapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
        return GeminiAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif "gemini 3" in fmt or "google genai" in fmt:
        return Gemini3Adapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "阿里云百炼":
        return OpenAIAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "火山引擎":
        return VolcanoEngineAIAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "硅基流动":
        return SiliconFlowAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "grok":
        return GrokAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "智谱ai" or fmt == "智谱AI" or fmt == "zhipuai" or fmt == "zhipu":
        return ZhipuAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    else:
        raise ValueError(f"Unknown interface_format: {interface_format}")


class LLMAdapterFactory:
    @staticmethod
    def create_adapter(config: dict) -> BaseLLMAdapter:
        adapter = create_llm_adapter(config)
        adapter.config = dict(config)
        return adapter
