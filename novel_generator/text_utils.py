# novel_generator/text_utils.py
# -*- coding: utf-8 -*-
"""
轻量文本切分工具。
"""
import logging
import re


def fallback_sentence_split(text: str) -> list[str]:
    """在 NLTK 数据包不可用时，用中英文常见句末标点做保守切分。"""
    stripped_text = (text or "").strip()
    if not stripped_text:
        return []

    parts = re.split(r"(?<=[。！？!?；;])\s*|(?<=[.!?])\s+", stripped_text)
    sentences = [part.strip() for part in parts if part and part.strip()]
    return sentences or [stripped_text]


def split_sentences(text: str) -> list[str]:
    """优先使用 NLTK 分句；缺少资源或依赖时退回到纯文本切分。"""
    stripped_text = (text or "").strip()
    if not stripped_text:
        return []

    try:
        import nltk

        sentences = nltk.sent_tokenize(stripped_text)
        if sentences:
            return sentences
    except (LookupError, ImportError, OSError) as exc:
        logging.warning("NLTK sentence tokenizer unavailable, using fallback splitter: %s", exc)

    return fallback_sentence_split(stripped_text)
