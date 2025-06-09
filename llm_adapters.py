# llm_adapters.py
# -*- coding: utf-8 -*-
import logging
from typing import Optional
from langchain_openai import ChatOpenAI, AzureChatOpenAI
# from google import genai
import google.generativeai as genai
# from google.genai import types
from google.generativeai import types
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.inference.models import SystemMessage, UserMessage
from openai import OpenAI
import requests


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

    def invoke(self, prompt: str) -> str:
        response = self._client.invoke(prompt)
        if not response:
            logging.warning("No response from OpenAIAdapter.")
            return ""
        return response.content

class GeminiAdapter(BaseLLMAdapter):
    """
    适配 Google Gemini (Google Generative AI) 接口
    """
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        # gemini超时时间是毫秒
        self.timeout = timeout * 1000

        self._client = genai.Client(api_key=self.api_key,http_options=types.HttpOptions(base_url=base_url,timeout=self.timeout))

    def invoke(self, prompt: str) -> str:
        try:
            response = self._client.models.generate_content(
                model = self.model_name,
                contents = prompt,
                config = types.GenerateContentConfig(
                    max_output_tokens=self.max_tokens,
                    temperature=self.temperature,
                ),
            )
            if response and response.text:
                return response.text
            else:
                logging.warning("No text response from Gemini API.")
                return ""
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
        self.base_url = check_base_url(base_url)
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

def create_llm_adapter(
    interface_format: str,
    base_url: str,
    model_name: str,
    api_key: str,
    temperature: float,
    max_tokens: int,
    timeout: int
) -> BaseLLMAdapter:
    """
    工厂函数：根据 interface_format 返回不同的适配器实例。
    """
    fmt = interface_format.strip().lower()
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
        return GeminiAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "阿里云百炼":
        return OpenAIAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "火山引擎":
        return VolcanoEngineAIAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "硅基流动":
        return SiliconFlowAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "grok":
        return GrokAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    else:
        raise ValueError(f"Unknown interface_format: {interface_format}")
