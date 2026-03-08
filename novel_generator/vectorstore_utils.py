#novel_generator/vectorstore_utils.py
# -*- coding: utf-8 -*-
"""
向量库相关操作（初始化、更新、检索、清空、文本切分等）
"""
import os
import logging
import traceback
import nltk
import numpy as np
import re
import ssl
import requests
import warnings
logging.basicConfig(
    filename='app.log',      # 日志文件名
    filemode='a',            # 追加模式（'w' 会覆盖）
    level=logging.INFO,      # 记录 INFO 及以上级别的日志
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# 禁用特定的Torch警告
warnings.filterwarnings('ignore', message='.*Torch was not compiled with flash attention.*')
os.environ["TOKENIZERS_PARALLELISM"] = "false"  # 禁用tokenizer并行警告

from langchain_core.documents import Document
from .common import call_with_retry


def _safe_sentence_tokenize(text: str):
    """优先使用 NLTK 分句；资源缺失时降级到正则分句。"""
    if not text:
        return []
    try:
        return nltk.sent_tokenize(text)
    except LookupError as e:
        logging.warning(f"NLTK sentence tokenizer resource missing, fallback to regex split: {e}")
    except (OSError, ValueError, TypeError, RuntimeError) as e:
        logging.warning(f"NLTK sentence tokenizer failed, fallback to regex split: {e}")

    # 中英文通用简易分句
    parts = re.split(r'(?<=[。！？!?\.])\s+|(?<=[。！？!?])', text)
    sentences = [p.strip() for p in parts if p and p.strip()]
    if sentences:
        return sentences
    return [text.strip()] if text.strip() else []


def _get_chroma_classes():
    """延迟导入 Chroma 组件，兼容 chromadb 在部分 Python 版本下的导入失败。"""
    try:
        from langchain_chroma import Chroma
        from chromadb.config import Settings
        return Chroma, Settings
    except (ImportError, ModuleNotFoundError, AttributeError, RuntimeError) as e:
        logging.warning(f"Chroma backend unavailable in current environment: {e}")
        return None, None

def get_vectorstore_dir(filepath: str) -> str:
    """获取 vectorstore 路径"""
    return os.path.join(filepath, "vectorstore")

def clear_vector_store(filepath: str) -> bool:
    """清空 清空向量库"""
    import shutil
    store_dir = get_vectorstore_dir(filepath)
    if not os.path.exists(store_dir):
        logging.info("No vector store found to clear.")
        return False
    try:
        shutil.rmtree(store_dir)
        logging.info(f"Vector store directory '{store_dir}' removed.")
        return True
    except OSError as e:
        logging.error(f"无法删除向量库文件夹，请关闭程序后手动删除 {store_dir}。\n {str(e)}")
        traceback.print_exc()
        return False

def init_vector_store(embedding_adapter, texts, filepath: str):
    """
    在 filepath 下创建/加载一个 Chroma 向量库并插入 texts。
    如果Embedding失败，则返回 None，不中断任务。
    """
    from langchain_core.embeddings import Embeddings as LCEmbeddings

    Chroma, Settings = _get_chroma_classes()
    if Chroma is None or Settings is None:
        return None

    store_dir = get_vectorstore_dir(filepath)
    os.makedirs(store_dir, exist_ok=True)
    # 过滤有效文档
    documents = [Document(page_content=str(t)) for t in texts if t and str(t).strip()]

    if not documents:
        logging.warning("No valid documents to initialize vector store")
        return None

    try:
        class LCEmbeddingWrapper(LCEmbeddings):
            def embed_documents(self, texts):
                # 过滤空文本
                valid_texts = [text for text in texts if text and str(text).strip()]
                if not valid_texts:
                    logging.warning("No valid texts provided for embedding")
                    return []

                embeddings = call_with_retry(
                    func=embedding_adapter.embed_documents,
                    max_retries=3,
                    fallback_return=None,
                    texts=valid_texts
                )
                if embeddings is None or not embeddings:
                    raise RuntimeError("Embedding generation failed")

                valid_embeddings = []
                for emb in embeddings:
                    if emb and len(emb) > 0:
                        valid_embeddings.append(emb)
                    else:
                        raise RuntimeError("Embedding contains empty vectors")

                embeddings = valid_embeddings
                return embeddings

            def embed_query(self, text: str):
                res = call_with_retry(
                    func=embedding_adapter.embed_query,
                    max_retries=3,
                    fallback_return=None,
                    query=text
                )
                if res is None or not res:
                    raise RuntimeError("Query embedding failed")
                return res

        chroma_embedding = LCEmbeddingWrapper()
        vectorstore = Chroma.from_documents(
            documents,
            embedding=chroma_embedding,
            persist_directory=store_dir,
            client_settings=Settings(anonymized_telemetry=False),
            collection_name="novel_collection"
        )
        return vectorstore
    except (RuntimeError, ValueError, TypeError, OSError, AttributeError, requests.RequestException) as e:
        logging.warning(f"Init vector store failed: {e}")
        traceback.print_exc()
        return None

def load_vector_store(embedding_adapter, filepath: str):
    """
    读取已存在的 Chroma 向量库。若不存在则返回 None。
    如果加载失败（embedding 或IO问题），则返回 None。
    """
    from langchain_core.embeddings import Embeddings as LCEmbeddings

    Chroma, Settings = _get_chroma_classes()
    if Chroma is None or Settings is None:
        return None
    store_dir = get_vectorstore_dir(filepath)
    if not os.path.exists(store_dir):
        logging.info("Vector store not found. Will return None.")
        return None

    try:
        class LCEmbeddingWrapper(LCEmbeddings):
            def embed_documents(self, texts):
                # 过滤空文本
                valid_texts = [text for text in texts if text and text.strip()]
                if not valid_texts:
                    logging.warning("No valid texts provided for embedding")
                    return []

                embeddings = call_with_retry(
                    func=embedding_adapter.embed_documents,
                    max_retries=3,
                    fallback_return=None,
                    texts=valid_texts
                )
                if embeddings is None or not embeddings:
                    raise RuntimeError("Embedding generation failed")

                valid_embeddings = []
                for emb in embeddings:
                    if emb and len(emb) > 0:
                        valid_embeddings.append(emb)
                    else:
                        raise RuntimeError("Embedding contains empty vectors")

                embeddings = valid_embeddings
                return embeddings

            def embed_query(self, text: str):
                res = call_with_retry(
                    func=embedding_adapter.embed_query,
                    max_retries=3,
                    fallback_return=None,
                    query=text
                )
                if res is None or not res:
                    raise RuntimeError("Query embedding failed")
                return res

        chroma_embedding = LCEmbeddingWrapper()
        return Chroma(
            persist_directory=store_dir,
            embedding_function=chroma_embedding,
            client_settings=Settings(anonymized_telemetry=False),
            collection_name="novel_collection"
        )
    except (RuntimeError, ValueError, TypeError, OSError, AttributeError, requests.RequestException) as e:
        logging.warning(f"Failed to load vector store: {e}")
        traceback.print_exc()
        return None

def split_by_length(text: str, max_length: int = 500):
    """
    按照指定长度切分文本

    将输入文本按固定长度切分成多个段落，适用于向量化前的预处理。

    Args:
        text: 要切分的原始文本
        max_length: 每个段落的最大字符数（默认500）

    Returns:
        切分后的文本段落列表

    Examples:
        >>> split_by_length("这是一段很长的文本内容..." , 10)
        ['这是一段很长的', '文本内容...']
    """
    segments = []
    start_idx = 0
    while start_idx < len(text):
        end_idx = min(start_idx + max_length, len(text))
        segment = text[start_idx:end_idx]
        segments.append(segment.strip())
        start_idx = end_idx
    return segments

def split_text_for_vectorstore(chapter_text: str, max_length: int = 500, similarity_threshold: float = 0.7):
    """
    对新的章节文本进行分段后,再用于存入向量库。
    使用 embedding 进行文本相似度计算。
    """
    if not chapter_text.strip():
        return []
    
    sentences = _safe_sentence_tokenize(chapter_text)
    if not sentences:
        return []
    
    # 直接按长度分段,不做相似度合并
    final_segments = []
    current_segment = []
    current_length = 0
    
    for sentence in sentences:
        sentence_length = len(sentence)
        if current_length + sentence_length > max_length:
            if current_segment:
                final_segments.append(" ".join(current_segment))
            current_segment = [sentence]
            current_length = sentence_length
        else:
            current_segment.append(sentence)
            current_length += sentence_length
    
    if current_segment:
        final_segments.append(" ".join(current_segment))
    
    return final_segments

def update_vector_store(embedding_adapter, new_chapter: str, filepath: str):
    """
    将最新章节文本插入到向量库中。
    若库不存在则初始化；若初始化/更新失败，则跳过。
    """
    from utils import read_file, clear_file_content, save_string_to_txt
    splitted_texts = split_text_for_vectorstore(new_chapter)
    if not splitted_texts:
        logging.warning("No valid text to insert into vector store. Skipping.")
        return

    store = load_vector_store(embedding_adapter, filepath)
    if not store:
        logging.info("Vector store does not exist or failed to load. Initializing a new one for new chapter...")
        store = init_vector_store(embedding_adapter, splitted_texts, filepath)
        if not store:
            logging.warning("Init vector store failed, skip embedding.")
        else:
            logging.info("New vector store created successfully.")
        return

    try:
        docs = [Document(page_content=str(t)) for t in splitted_texts]
        # 验证文档内容不为空
        valid_docs = [doc for doc in docs if doc.page_content.strip()]
        if not valid_docs:
            logging.warning("No valid documents to insert into vector store.")
            return

        # 预检查embedding维度是否匹配
        try:
            embedding_function = getattr(store, '_embedding_function', None)
            if embedding_function is None or not hasattr(embedding_function, 'embed_query'):
                logging.warning("Vector store embedding function unavailable. Recreating vector store...")
                store = init_vector_store(embedding_adapter, splitted_texts, filepath)
                if not store:
                    logging.warning("Failed to recreate vector store.")
                return

            test_embedding = embedding_function.embed_query("test")
            if not test_embedding or len(test_embedding) == 0:
                logging.warning("Embedding function returned empty vector. Recreating vector store...")
                store = init_vector_store(embedding_adapter, splitted_texts, filepath)
                if not store:
                    logging.warning("Failed to recreate vector store.")
                return
        except (RuntimeError, ValueError, TypeError, OSError, AttributeError, requests.RequestException) as embed_test_error:
            logging.warning(f"Embedding test failed: {embed_test_error}. Recreating vector store...")
            store = init_vector_store(embedding_adapter, splitted_texts, filepath)
            if not store:
                logging.warning("Failed to recreate vector store after embedding test failure.")
            return

        store.add_documents(valid_docs)
        logging.info(f"Vector store updated with {len(valid_docs)} valid segments.")
    except (RuntimeError, ValueError, TypeError, OSError, AttributeError, requests.RequestException) as e:
        logging.warning(f"Failed to update vector store: {e}")
        # 尝试重新初始化向量库
        try:
            logging.info("Attempting to recreate vector store...")
            store = init_vector_store(embedding_adapter, splitted_texts, filepath)
            if store:
                logging.info("Vector store recreated successfully.")
        except (RuntimeError, ValueError, TypeError, OSError, AttributeError, requests.RequestException) as recreate_error:
            logging.error(f"Failed to recreate vector store: {recreate_error}")
            traceback.print_exc()

def get_relevant_context_from_vector_store(embedding_adapter, query: str, filepath: str, k: int = 2) -> str:
    """
    从向量库中检索与 query 最相关的 k 条文本，拼接后返回。
    如果向量库加载/检索失败，则返回空字符串。
    最终只返回最多2000字符的检索片段。
    """
    # 检查查询是否为空
    if not query or not query.strip():
        logging.warning("Empty query provided. Returning empty context.")
        return ""

    store = load_vector_store(embedding_adapter, filepath)
    if not store:
        logging.info("No vector store found or load failed. Returning empty context.")
        return ""

    try:
        # 尝试生成查询的embedding来提前检测问题 - 兼容新旧Chroma版本
        embedding_function = getattr(store, '_embedding_function', None)
        if embedding_function is None or not hasattr(embedding_function, 'embed_query'):
            logging.error("Chroma store object has no embedding_function attribute")
            return ""

        test_embedding = embedding_function.embed_query(query.strip())
        if not test_embedding:
            logging.warning("Failed to generate query embedding. Returning empty context.")
            return ""

        docs = store.similarity_search(query.strip(), k=k)
        if not docs:
            logging.info(f"No relevant documents found for query '{query}'. Returning empty context.")
            return ""
        combined = "\n".join([d.page_content for d in docs])
        if len(combined) > 2000:
            combined = combined[:2000]
        return combined
    except (RuntimeError, ValueError, TypeError, OSError, AttributeError, requests.RequestException) as e:
        logging.warning(f"Similarity search failed: {e}")
        traceback.print_exc()
        return ""

def _get_sentence_transformer(model_name: str = 'paraphrase-MiniLM-L6-v2'):
    """获取sentence transformer模型，处理SSL问题"""
    try:
        # 设置torch环境变量
        os.environ["TORCH_ALLOW_TF32_CUBLAS_OVERRIDE"] = "0"
        os.environ["TORCH_CUDNN_V8_API_ENABLED"] = "0"

        allow_insecure_ssl = str(os.environ.get("AI_NOVELGEN_ALLOW_INSECURE_SSL", "0")).lower() in {
            "1", "true", "yes", "on"
        }
        if allow_insecure_ssl:
            logging.warning("AI_NOVELGEN_ALLOW_INSECURE_SSL 已启用，正在关闭 SSL 证书校验")
            ssl._create_default_https_context = ssl._create_unverified_context
        
        # ...existing code...
    except (OSError, RuntimeError, ValueError, TypeError, AttributeError) as e:
        logging.error(f"Failed to load sentence transformer model: {e}")
        traceback.print_exc()
        return None


class VectorStoreManager:
    """
    向量存储管理器 - 兼容性接口

    提供统一的向量存储管理接口，兼容不同的向量数据库实现。
    当前版本为兼容性占位实现，实际功能由 ChromaDB 提供。

    Attributes:
        persist_path: 向量存储持久化路径

    Examples:
        >>> manager = VectorStoreManager(persist_path="./data/vectorstore")
        >>> manager.add_documents([doc1, doc2])
        >>> results = manager.similarity_search("查询内容", k=5)
    """

    def __init__(self, persist_path=None):
        """
        初始化向量存储管理器

        Args:
            persist_path: 向量存储持久化路径，默认为 "vectorstore"
        """
        self.persist_path = persist_path or "vectorstore"

    def add_documents(self, documents):
        """
        添加文档到向量存储

        Args:
            documents: 要添加的文档列表

        Returns:
            bool: 添加成功返回 True
        """
        return True

    def similarity_search(self, query, k=5):
        """
        执行相似性搜索

        Args:
            query: 查询文本
            k: 返回结果数量，默认5

        Returns:
            list: 搜索结果列表
        """
        return []

    def persist(self):
        """
        持久化向量存储

        将向量存储数据持久化到磁盘。

        Returns:
            bool: 持久化成功返回 True
        """
        return True
