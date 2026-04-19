# llm_adapters.py
# -*- coding: utf-8 -*-
import logging
from typing import Optional
import re
import requests
from langchain_openai import ChatOpenAI, AzureChatOpenAI
import google.generativeai as genai
from google.generativeai import types
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential
from azure.ai.inference.models import SystemMessage, UserMessage
from openai import OpenAI

def check_base_url(url: str) -> str:
    """
    Handle base_url rules:
    1. If url ends with #, remove # and use the provided url directly.
    2. Otherwise, check if /v1 suffix needs to be added.
    """
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
    Unified LLM interface base class, providing consistent method signatures for different backends.
    """
    def invoke(self, prompt: str) -> str:
        raise NotImplementedError("Subclasses must implement .invoke(prompt) method.")

class GenericOpenAIAdapter(BaseLLMAdapter):
    """
    Generic OpenAI-compatible interface adapter (uses langchain.ChatOpenAI).
    Applicable to OpenAI, DeepSeek, Ollama, ML Studio, Alibaba Cloud Bailian, Volcengine, SiliconFlow, Grok, etc.
    """
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600, adapter_name: str = "OpenAI"):
        self.base_url = check_base_url(base_url)
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.adapter_name = adapter_name

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
                logging.warning(f"No response from {self.adapter_name}Adapter.")
                return ""
            return response.content
        except Exception as e:
            logging.error(f"{self.adapter_name} API call failed: {e}")
            return ""

class GeminiAdapter(BaseLLMAdapter):
    """
    Adapter for Google Gemini (Google Generative AI) interface.
    """
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        genai.configure(api_key=self.api_key)
        self._model = genai.GenerativeModel(model_name=self.model_name)

    def invoke(self, prompt: str) -> str:
        try:
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            response = self._model.generate_content(
                prompt,
                generation_config=generation_config
            )
            if response and response.text:
                return response.text
            else:
                logging.warning("No text response from Gemini API.")
                return ""
        except Exception as e:
            logging.error(f"Gemini API call failed: {e}")
            return ""

class AzureOpenAIAdapter(BaseLLMAdapter):
    """
    Adapter for Azure OpenAI interface (uses langchain.ChatOpenAI).
    """
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
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
        try:
            response = self._client.invoke(prompt)
            if not response:
                logging.warning("No response from AzureOpenAIAdapter.")
                return ""
            return response.content
        except Exception as e:
            logging.error(f"Azure OpenAI API call failed: {e}")
            return ""

class AzureAIAdapter(BaseLLMAdapter):
    """
    Adapter for Azure AI Inference interface.
    """
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
        match = re.match(r'https://(.+?)\.services\.ai\.azure\.com(?:/models)?(?:/chat/completions)?(?:\?api-version=(.+))?', base_url)
        if match:
            self.endpoint = f"https://{match.group(1)}.services.ai.azure.com/models"
            self.api_version = match.group(2) if match.group(2) else "2024-05-01-preview"
        else:
            raise ValueError("Invalid Azure AI base_url format.")
        
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
            logging.error(f"Azure AI Inference API call failed: {e}")
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
    Factory function: Returns different adapter instances based on interface_format.
    """
    fmt = interface_format.strip().lower()

    # OpenAI compatible interface list
    openai_compatible = ["openai", "deepseek", "ollama", "ollama cloud", "ml studio", "aliyun", "volcengine", "siliconflow", "grok"]

    if fmt in openai_compatible:
        actual_api_key = api_key if api_key or (fmt != "ollama" and fmt != "ollama cloud") else "ollama"
        return GenericOpenAIAdapter(actual_api_key, base_url, model_name, max_tokens, temperature, timeout, interface_format)
    elif fmt == "azure openai":
        return AzureOpenAIAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "azure ai":
        return AzureAIAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    elif fmt == "gemini":
        return GeminiAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    else:
        raise ValueError(f"Unknown interface_format: {interface_format}")
