import os
from novel_generator import chapter as chap

class DummyAdapter:
    def __init__(self, *args, **kwargs):
        pass
    def invoke(self, prompt: str) -> str:
        return "这是模拟生成的章节正文。测试成功。\n\n（此为模拟输出，用于验证写入与返回逻辑。）"

# Monkeypatch 模拟 LLM
chap.create_llm_adapter = lambda *args, **kwargs: DummyAdapter()

if __name__ == '__main__':
    out_dir = 'test_output'
    os.makedirs(out_dir, exist_ok=True)
    content = chap.generate_chapter_draft(
        api_key='',
        base_url='',
        model_name='',
        filepath=out_dir,
        novel_number=1,
        word_number=200,
        temperature=0.7,
        user_guidance='测试生成草稿',
        characters_involved='',
        key_items='',
        scene_location='',
        time_constraint='',
        embedding_api_key='',
        embedding_url='',
        embedding_interface_format='',
        embedding_model_name='',
        embedding_retrieval_k=2,
        interface_format='openai',
        max_tokens=512,
        timeout=60,
        custom_prompt_text=None
    )
    print('DRAFT_LEN:', len(content))
    print(content)
