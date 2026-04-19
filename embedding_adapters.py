# embedding_adapters.py
# -*- coding: utf-8 -*-
import logging
import traceback
from typing import List
import requests
import re
from langchain_openai import AzureOpenAIEmbeddings, OpenAIEmbeddings

def ensure_openai_base_url_has_v1(url: str) -> str:
    """
    If the user-provided url does not contain '/v1', append '/v1' to the end.
    """
    url = url.strip()
    if not url:
        return url
    if not re.search(r'/v\d+$', url):
        if '/v1' not in url:
            url = url.rstrip('/') + '/v1'
    return url

class BaseEmbeddingAdapter:
    """
    Base class for unified Embedding interfaces.
    """
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def embed_query(self, query: str) -> List[float]:
        raise NotImplementedError

class OpenAIEmbeddingAdapter(BaseEmbeddingAdapter):
    """
    Adapter based on OpenAIEmbeddings (or compatible interfaces).
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
    Adapter based on AzureOpenAIEmbeddings (or compatible interfaces).
    """
    def __init__(self, api_key: str, base_url: str, model_name: str):
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
    Interface path is /api/embeddings.
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
        Call local Ollama service /api/embeddings interface to get text embedding.
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
    Embedding adapter based on LM Studio.
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
    Embedding adapter based on Google Generative AI (Gemini) interface.
    Uses direct POST request method.
    Example URL: https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key=YOUR_API_KEY
    """
    def __init__(self, api_key: str, model_name: str, base_url: str):
        """
        :param api_key: Google API Key
        :param model_name: e.g., "text-embedding-004"
        :param base_url: e.g., https://generativelanguage.googleapis.com/v1beta/models
        """
        self.api_key = api_key
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
        Directly call Google Generative Language API (Gemini) interface to get text embedding.
        """
        url = f"{self.base_url}/{self.model_name}:embedContent?key={self.api_key}"
        payload = {
            "model": self.model_name,
            "content": {
                "parts": [
                    {"text": text}
                ]
            }
        }

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            result = response.json()
            embedding_data = result.get("embedding", {})
            return embedding_data.get("values", [])
        except requests.exceptions.RequestException as e:
            logging.error(f"Gemini embed_content request error: {e}\n{traceback.format_exc()}")
            return []
        except Exception as e:
            logging.error(f"Gemini embed_content parse error: {e}\n{traceback.format_exc()}")
            return []

class SiliconFlowEmbeddingAdapter(BaseEmbeddingAdapter):
    """
    Embedding adapter based on SiliconFlow.
    """
    def __init__(self, api_key: str, base_url: str, model_name: str):
        # Automatically add scheme to base_url if missing
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
    Factory function: Returns different embedding adapter instances based on interface_format.
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
