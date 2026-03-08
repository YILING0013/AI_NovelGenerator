import ssl

from novel_generator import vectorstore_utils


def test_sentence_transformer_does_not_disable_ssl_by_default(monkeypatch):
    monkeypatch.delenv("AI_NOVELGEN_ALLOW_INSECURE_SSL", raising=False)
    original_context = ssl._create_default_https_context

    try:
        vectorstore_utils._get_sentence_transformer()
        assert ssl._create_default_https_context is original_context
    finally:
        ssl._create_default_https_context = original_context


def test_sentence_transformer_allows_insecure_ssl_only_with_flag(monkeypatch):
    monkeypatch.setenv("AI_NOVELGEN_ALLOW_INSECURE_SSL", "1")
    original_context = ssl._create_default_https_context

    try:
        vectorstore_utils._get_sentence_transformer()
        assert ssl._create_default_https_context is ssl._create_unverified_context
    finally:
        ssl._create_default_https_context = original_context
