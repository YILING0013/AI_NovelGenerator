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

    # PenBo 修复新版本google-generativeai 不支持 Client 类问题；而是使用 GenerativeModel 类来访问API
    def __init__(self, api_key: str, base_url: str, model_name: str, max_tokens: int, temperature: float = 0.7, timeout: Optional[int] = 600):
        self.api_key = api_key
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        # 配置API密钥
        genai.configure(api_key=self.api_key)
        
        # 创建生成模型实例
        self._model = genai.GenerativeModel(model_name=self.model_name)

    def invoke(self, prompt: str) -> str:
        try:
            # 设置生成配置
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            
            # 生成内容
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
            logging.error(f"智谱AI API 调用参数 - api_key前缀: {self.api_key[:10] if self.api_key else 'None'}...")

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
    elif fmt == "智谱ai" or fmt == "智谱AI" or fmt == "zhipuai" or fmt == "zhipu":
        return ZhipuAdapter(api_key, base_url, model_name, max_tokens, temperature, timeout)
    else:
        raise ValueError(f"Unknown interface_format: {interface_format}")
