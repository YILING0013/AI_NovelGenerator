import ast
from pathlib import Path

from novel_generator import vectorstore_utils


class _FailingEmbeddingAdapter:
    def embed_documents(self, texts):
        return None

    def embed_query(self, query):
        return None


class _FakeSettings:
    def __init__(self, anonymized_telemetry=False):
        self.anonymized_telemetry = anonymized_telemetry


class _FakeChromaInit:
    @staticmethod
    def from_documents(documents, embedding, persist_directory, client_settings, collection_name):
        embedding.embed_documents([doc.page_content for doc in documents])
        return object()


class _FakeChromaLoad:
    def __init__(self, persist_directory, embedding_function, client_settings, collection_name):
        embedding_function.embed_query("probe")


def test_init_vector_store_fails_closed_when_embeddings_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(vectorstore_utils, "_get_chroma_classes", lambda: (_FakeChromaInit, _FakeSettings))
    adapter = _FailingEmbeddingAdapter()

    store = vectorstore_utils.init_vector_store(adapter, ["sample text"], str(tmp_path))

    assert store is None


def test_load_vector_store_fails_closed_when_query_embedding_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(vectorstore_utils, "_get_chroma_classes", lambda: (_FakeChromaLoad, _FakeSettings))
    adapter = _FailingEmbeddingAdapter()
    vectorstore_dir = tmp_path / "vectorstore"
    vectorstore_dir.mkdir()

    store = vectorstore_utils.load_vector_store(adapter, str(tmp_path))

    assert store is None


def test_vectorstore_utils_has_no_generic_exception_catch_blocks():
    source = Path("novel_generator/vectorstore_utils.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                raise AssertionError("novel_generator/vectorstore_utils.py contains generic except Exception block")
