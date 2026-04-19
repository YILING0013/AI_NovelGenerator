# novel_generator/knowledge.py
# -*- coding: utf-8 -*-
"""
Knowledge file import to vector store (advanced_split_content, import_knowledge_file)
"""
import os
import logging
import re
import traceback
import nltk
import warnings
from utils import read_file
from novel_generator.vectorstore_utils import load_vector_store, init_vector_store
from langchain.docstore.document import Document

# Disable specific Torch warnings
warnings.filterwarnings('ignore', message='.*Torch was not compiled with flash attention.*')
os.environ["TOKENIZERS_PARALLELISM"] = "false"

logging.basicConfig(
    filename='app.log',
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def advanced_split_content(content: str, similarity_threshold: float = 0.7, max_length: int = 500) -> list:
    """Uses basic segmentation strategy."""
    # nltk.download('punkt', quiet=True)
    # nltk.download('punkt_tab', quiet=True)
    sentences = nltk.sent_tokenize(content)
    if not sentences:
        return []

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

def import_knowledge_file(
    embedding_api_key: str,
    embedding_url: str,
    embedding_interface_format: str,
    embedding_model_name: str,
    file_path: str,
    filepath: str
):
    logging.info(f"Starting knowledge base file import: {file_path}, Format: {embedding_interface_format}, Model: {embedding_model_name}")
    if not os.path.exists(file_path):
        logging.warning(f"Knowledge base file does not exist: {file_path}")
        return
    content = read_file(file_path)
    if not content.strip():
        logging.warning("Knowledge base file content is empty.")
        return
    paragraphs = advanced_split_content(content)
    from embedding_adapters import create_embedding_adapter
    embedding_adapter = create_embedding_adapter(
        embedding_interface_format,
        embedding_api_key,
        embedding_url if embedding_url else "http://localhost:11434/api",
        embedding_model_name
    )
    store = load_vector_store(embedding_adapter, filepath)
    if not store:
        logging.info("Vector store does not exist or load failed. Initializing a new one for knowledge import...")
        store = init_vector_store(embedding_adapter, paragraphs, filepath)
        if store:
            logging.info("Knowledge base file has been successfully imported into the vector store (Newly initialized).")
        else:
            logging.warning("Knowledge base import failed, skipping.")
    else:
        try:
            docs = [Document(page_content=str(p)) for p in paragraphs]
            store.add_documents(docs)
            logging.info("Knowledge base file has been successfully imported into the vector store (Append mode).")
        except Exception as e:
            logging.warning(f"Knowledge base import failed: {e}")
            traceback.print_exc()
