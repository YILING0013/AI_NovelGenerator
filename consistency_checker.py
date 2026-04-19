# consistency_checker.py
# -*- coding: utf-8 -*-
from llm_adapters import create_llm_adapter

# ============== Consistency checking prompt ==============
CONSISTENCY_PROMPT = """\
Please check if there are any obvious conflicts or inconsistencies between the novel settings below and the latest chapter. If any, please list them:
- Novel Setting:
{novel_setting}

- Character State (may contain important information):
{character_state}

- Global Summary:
{global_summary}

- Recorded unresolved conflicts or plot points:
{plot_arcs}

- Latest Chapter Content:
{chapter_text}

If there are conflicts or inconsistencies, please explain them. If there are unresolved conflicts that have been ignored or need further progression, please mention them as well; otherwise, please return "No obvious conflicts".
"""

def check_consistency(
    novel_setting: str,
    character_state: str,
    global_summary: str,
    chapter_text: str,
    api_key: str,
    base_url: str,
    model_name: str,
    temperature: float = 0.3,
    plot_arcs: str = "",
    interface_format: str = "OpenAI",
    max_tokens: int = 2048,
    timeout: int = 600
) -> str:
    """
    Calls the model to perform a simple consistency check. Can be extended with more prompts or validation rules.
    Additional: Also checks for consistency with "unresolved conflicts or plot points" (plot_arcs).
    """
    prompt = CONSISTENCY_PROMPT.format(
        novel_setting=novel_setting,
        character_state=character_state,
        global_summary=global_summary,
        plot_arcs=plot_arcs,
        chapter_text=chapter_text
    )

    llm_adapter = create_llm_adapter(
        interface_format=interface_format,
        base_url=base_url,
        model_name=model_name,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout
    )

    # Debug log
    print("\n[ConsistencyChecker] Prompt >>>", prompt)

    response = llm_adapter.invoke(prompt)
    if not response:
        return "Review agent returned no response"
    
    # Debug log
    print("[ConsistencyChecker] Response <<<", response)

    return response
