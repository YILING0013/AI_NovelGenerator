# consistency_checker.py
# -*- coding: utf-8 -*-
from llm_adapters import create_llm_adapter
from novel_generator.common import log_llm_io

# ============== 增加对“剧情要点/未解决冲突”进行检查的可选引导 ==============
CONSISTENCY_PROMPT = """\
请检查下面的小说设定与最新章节是否存在明显冲突或不一致之处，如有请列出：
- 小说设定：
{novel_setting}

- 角色状态（可能包含重要信息）：
{character_state}

- 前文摘要：
{global_summary}

- 已记录的未解决冲突或剧情要点：
{plot_arcs}  # 若为空可能不输出

- 最新章节内容：
{chapter_text}

如果存在冲突或不一致，请说明；如果在未解决冲突中有被忽略或需要推进的地方，也请提及；否则请返回“无明显冲突”。
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
    调用模型做简单的一致性检查。可扩展更多提示或校验规则。
    新增: 会额外检查对“未解决冲突或剧情要点”（plot_arcs）的衔接情况。
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

    log_llm_io("ConsistencyChecker Prompt", prompt)

    response = llm_adapter.invoke(prompt)
    if not response:
        return "审校Agent无回复"
    
    log_llm_io("ConsistencyChecker Response", response)

    return response
