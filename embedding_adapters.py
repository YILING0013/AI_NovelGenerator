# embedding_adapters.py
# -*- coding: utf-8 -*-
import logging
import traceback
from typing import List
import requests
from google import genai
from langchain_openai import AzureOpenAIEmbeddings, OpenAIEmbeddings

def ensure_openai_base_url_has_v1(url: str) -> str:
    """
    若用户输入的 url 不包含 '/v1'，则在末尾追加 '/v1'。
    """
    import re
    url = url.strip()
    if not url:
        return url
    if not re.search(r'/v\d+$', url):
        if '/v1' not in url:
            url = url.rstrip('/') + '/v1'
    return url

class BaseEmbeddingAdapter:
    """
    Embedding 接口统一基类
    """
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def embed_query(self, query: str) -> List[float]:
        raise NotImplementedError

class OpenAIEmbeddingAdapter(BaseEmbeddingAdapter):
    """
    基于 OpenAIEmbeddings（或兼容接口）的适配器
    """
    def __init__(self, api_key: str, base_url: str, model_name: str):
        self._embedding = OpenAIEmbeddings(
            openai_api_key=api_key,
            openai_api_base=ensure_openai_base_url_has_v1(base_url),
            model=model_name
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embedding.embed_documents(texts)

    def embed_query(self, query: str) -> List[float]:
        return self._embedding.embed_query(query)

class AzureOpenAIEmbeddingAdapter(BaseEmbeddingAdapter):
    """
    基于 AzureOpenAIEmbeddings（或兼容接口）的适配器
    """
    def __init__(self, api_key: str, base_url: str, model_name: str):
        import re
        match = re.match(r'https://(.+?)/openai/deployments/(.+?)/embeddings\?api-version=(.+)', base_url)
        if match:
            self.azure_endpoint = f"https://{match.group(1)}"
            self.azure_deployment = match.group(2)
            self.api_version = match.group(3)
        else:
            raise ValueError("Invalid Azure OpenAI base_url format")
        
        self._embedding = AzureOpenAIEmbeddings(
            azure_endpoint=self.azure_endpoint,
            azure_deployment=self.azure_deployment,
            openai_api_key=api_key,
            api_version=self.api_version,
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embedding.embed_documents(texts)

    def embed_query(self, query: str) -> List[float]:
        return self._embedding.embed_query(query)

class OllamaEmbeddingAdapter(BaseEmbeddingAdapter):
    """
    其接口路径为 /api/embeddings
    """
    def __init__(self, model_name: str, base_url: str):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            vec = self._embed_single(text)
            embeddings.append(vec)
        return embeddings

    def embed_query(self, query: str) -> List[float]:
        return self._embed_single(query)

    def _embed_single(self, text: str) -> List[float]:
        """
        调用 Ollama 本地服务 /api/embeddings 接口，获取文本 embedding
        """
        url = self.base_url.rstrip("/")
        if "/api/embeddings" not in url:
            if "/api" in url:
                url = f"{url}/embeddings"
            else:
                if "/v1" in url:
                    url = url[:url.index("/v1")]
                url = f"{url}/api/embeddings"

        data = {
            "model": self.model_name,
            "prompt": text
        }
        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            result = response.json()
            if "embedding" not in result:
                raise ValueError("No 'embedding' field in Ollama response.")
            return result["embedding"]
        except requests.exceptions.RequestException as e:
            logging.error(f"Ollama embeddings request error: {e}\n{traceback.format_exc()}")
            return []

class MLStudioEmbeddingAdapter(BaseEmbeddingAdapter):
    """
    基于 LM Studio 的 embedding 适配器
    """
    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.url = ensure_openai_base_url_has_v1(base_url)
        if not self.url.endswith('/embeddings'):
            self.url = f"{self.url}/embeddings"
        
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.model_name = model_name

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        try:
            payload = {
                "input": texts,
                "model": self.model_name
            }
            response = requests.post(self.url, json=payload, headers=self.headers)
            response.raise_for_status()
            result = response.json()
            if "data" not in result:
                logging.error(f"Invalid response format from LM Studio API: {result}")
                return [[]] * len(texts)
            return [item.get("embedding", []) for item in result["data"]]
        except requests.exceptions.RequestException as e:
            logging.error(f"LM Studio API request failed: {str(e)}")
            return [[]] * len(texts)
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logging.error(f"Error parsing LM Studio API response: {str(e)}")
            return [[]] * len(texts)

    def embed_query(self, query: str) -> List[float]:
        try:
            payload = {
                "input": query,
                "model": self.model_name
            }
            response = requests.post(self.url, json=payload, headers=self.headers)
            response.raise_for_status()
            result = response.json()
            if "data" not in result or not result["data"]:
                logging.error(f"Invalid response format from LM Studio API: {result}")
                return []
            return result["data"][0].get("embedding", [])
        except requests.exceptions.RequestException as e:
            logging.error(f"LM Studio API request failed: {str(e)}")
            return []
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logging.error(f"Error parsing LM Studio API response: {str(e)}")
            return []

class GeminiEmbeddingAdapter(BaseEmbeddingAdapter):
    """
    基于 Google Generative AI (Gemini) 接口的 Embedding 适配器
    使用 google-genai SDK。
    """
    def __init__(self, api_key: str, model_name: str, base_url: str):
        """
        :param api_key: 传入的 Google API Key
        :param model_name: 这里一般是 "text-embedding-004"
        :param base_url: e.g. https://generativelanguage.googleapis.com/v1beta/models (已弃用，SDK会自动处理)
        """
        self.api_key = api_key
        self.model_name = model_name
        self._client = genai.Client(api_key=self.api_key)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        try:
            response = self._client.models.embed_content(
                model=self.model_name,
                contents=texts
            )
            return [emb.values for emb in response.embeddings]
        except Exception as e:
            logging.error(f"Gemini embed_documents error: {e}")
            return [[]] * len(texts)

    def embed_query(self, query: str) -> List[float]:
        return self._embed_single(query)

    def _embed_single(self, text: str) -> List[float]:
        """
        使用 google-genai SDK 获取文本 embedding
        """
        try:
            response = self._client.models.embed_content(
                model=self.model_name,
                contents=text
            )
            if response and response.embeddings:
                return response.embeddings[0].values
            return []
        except Exception as e:
            logging.error(f"Gemini _embed_single error: {e}")
            return []

class SiliconFlowEmbeddingAdapter(BaseEmbeddingAdapter):
    """
    基于 SiliconFlow 的 embedding 适配器
    """
    def __init__(self, api_key: str, base_url: str, model_name: str):
        # 自动为 base_url 添加 scheme（如果缺失）
        if not base_url.startswith("http://") and not base_url.startswith("https://"):
            base_url = "https://" + base_url
        self.url = base_url if base_url else "https://api.siliconflow.cn/v1/embeddings"

        self.payload = {
            "model": model_name,
            "input": "Silicon flow embedding online: fast, affordable, and high-quality embedding services. come try it out!",
            "encoding_format": "float"
        }
        self.headers = {
            "Authorization": "Bearer {api_key}".format(api_key=api_key),
            "Content-Type": "application/json"
        }

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            try:
                self.payload["input"] = text
                response = requests.post(self.url, json=self.payload, headers=self.headers)
                response.raise_for_status()
                result = response.json()
                if not result or "data" not in result or not result["data"]:
                    logging.error(f"Invalid response format from SiliconFlow API: {result}")
                    embeddings.append([])
                    continue
                emb = result["data"][0].get("embedding", [])
                embeddings.append(emb)
            except requests.exceptions.RequestException as e:
                logging.error(f"SiliconFlow API request failed: {str(e)}")
                embeddings.append([])
            except (KeyError, IndexError, ValueError, TypeError) as e:
                logging.error(f"Error parsing SiliconFlow API response: {str(e)}")
                embeddings.append([])
        return embeddings

    def embed_query(self, query: str) -> List[float]:
        try:
            self.payload["input"] = query
            response = requests.post(self.url, json=self.payload, headers=self.headers)
            response.raise_for_status()
            result = response.json()
            if not result or "data" not in result or not result["data"]:
                logging.error(f"Invalid response format from SiliconFlow API: {result}")
                return []
            return result["data"][0].get("embedding", [])
        except requests.exceptions.RequestException as e:
            logging.error(f"SiliconFlow API request failed: {str(e)}")
            return []
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logging.error(f"Error parsing SiliconFlow API response: {str(e)}")
            return []

def create_embedding_adapter(
    interface_format: str,
    api_key: str,
    base_url: str,
    model_name: str
) -> BaseEmbeddingAdapter:
    """
    工厂函数：根据 interface_format 返回不同的 embedding 适配器实例
    """
    fmt = interface_format.strip().lower()
    if fmt == "openai":
        return OpenAIEmbeddingAdapter(api_key, base_url, model_name)
    elif fmt == "azure openai":
        return AzureOpenAIEmbeddingAdapter(api_key, base_url, model_name)
    elif fmt == "ollama":
        return OllamaEmbeddingAdapter(model_name, base_url)
    elif fmt == "ml studio":
        return MLStudioEmbeddingAdapter(api_key, base_url, model_name)
    elif fmt == "gemini":
        return GeminiEmbeddingAdapter(api_key, model_name, base_url)
    elif fmt == "siliconflow":
        return SiliconFlowEmbeddingAdapter(api_key, base_url, model_name)
    else:
        raise ValueError(f"Unknown embedding interface_format: {interface_format}")
