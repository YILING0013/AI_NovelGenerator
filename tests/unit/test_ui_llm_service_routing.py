from pathlib import Path


def test_generation_handlers_uses_service_layer_for_llm_calls():
    source = Path("ui/generation_handlers.py").read_text(encoding="utf-8")

    assert "from llm_adapters import create_llm_adapter" not in source
    assert "from novel_generator import" in source
    assert "invoke_text_generation" in source
    assert "build_llm_adapter" in source
