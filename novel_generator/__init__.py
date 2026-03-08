from importlib import import_module
from typing import Any, Dict, Tuple

__all__ = [
    "Novel_architecture_generate",
    "Chapter_blueprint_generate",
    "get_last_n_chapters_text",
    "summarize_recent_chapters",
    "get_filtered_knowledge_context",
    "build_chapter_prompt",
    "generate_chapter_draft",
    "generate_chapter_with_precise_word_count",
    "finalize_chapter",
    "enrich_chapter_text",
    "import_knowledge_file",
    "clear_vector_store",
    "invoke_text_generation",
    "build_llm_adapter",
    "schemas",
    "schema_validator",
    "error_handler",
    "pipeline_interfaces",
    "pipeline",
]

_ATTR_MAP: Dict[str, Tuple[str, str]] = {
    "Novel_architecture_generate": (".architecture", "Novel_architecture_generate"),
    "Chapter_blueprint_generate": (
        ".blueprint",
        "Strict_Chapter_blueprint_generate",
    ),
    "get_last_n_chapters_text": (".chapter", "get_last_n_chapters_text"),
    "summarize_recent_chapters": (".chapter", "summarize_recent_chapters"),
    "get_filtered_knowledge_context": (".chapter", "get_filtered_knowledge_context"),
    "build_chapter_prompt": (".chapter", "build_chapter_prompt"),
    "generate_chapter_draft": (".chapter", "generate_chapter_draft"),
    "generate_chapter_with_precise_word_count": (
        ".chapter",
        "generate_chapter_with_precise_word_count",
    ),
    "finalize_chapter": (".finalization", "finalize_chapter"),
    "enrich_chapter_text": (".finalization", "enrich_chapter_text"),
    "import_knowledge_file": (".knowledge", "import_knowledge_file"),
    "clear_vector_store": (".vectorstore_utils", "clear_vector_store"),
    "invoke_text_generation": (".llm_service", "invoke_text_generation"),
    "build_llm_adapter": (".llm_service", "build_llm_adapter"),
    "schemas": (".schemas", "__module__"),
    "schema_validator": (".schema_validator", "__module__"),
    "error_handler": (".error_handler", "__module__"),
    "pipeline_interfaces": (".pipeline_interfaces", "__module__"),
    "pipeline": (".pipeline", "__module__"),
}


def __getattr__(name: str) -> Any:
    if name not in _ATTR_MAP:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _ATTR_MAP[name]
    module = import_module(module_name, __name__)

    if attr_name == "__module__":
        value = module
    else:
        value = getattr(module, attr_name)

    globals()[name] = value
    return value
