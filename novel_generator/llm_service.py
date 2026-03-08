from llm_adapters import create_llm_adapter
from novel_generator.common import write_llm_interaction_log


def build_llm_adapter(
    *,
    interface_format: str,
    base_url: str,
    model_name: str,
    api_key: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
):
    return create_llm_adapter(
        interface_format=interface_format,
        base_url=base_url,
        model_name=model_name,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )


def invoke_text_generation(
    prompt: str,
    *,
    interface_format: str,
    base_url: str,
    model_name: str,
    api_key: str,
    temperature: float,
    max_tokens: int,
    timeout: int,
) -> str:
    adapter = build_llm_adapter(
        interface_format=interface_format,
        base_url=base_url,
        model_name=model_name,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    response = adapter.invoke(prompt)
    result_text = response if isinstance(response, str) else str(response or "")
    write_llm_interaction_log(
        prompt=prompt,
        response=result_text,
        stage="invoke_text_generation",
        extra_meta={
            "model_name": model_name,
            "interface_format": interface_format,
        },
    )
    return result_text
