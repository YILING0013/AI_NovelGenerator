from novel_generator.chapter import build_chapter_prompt

def run_test():
    try:
        prompt = build_chapter_prompt(
            api_key='',
            base_url='',
            model_name='',
            filepath='.',
            novel_number=1,
            word_number=500,
            temperature=0.7,
            user_guidance='测试：生成第一章提示词',
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
            max_tokens=1024,
            timeout=60
        )
        if prompt is None:
            print("<NO PROMPT> (None)")
        elif not prompt.strip():
            print("<EMPTY PROMPT>")
        else:
            print(prompt)
    except Exception as e:
        import traceback
        print("<EXCEPTION>")
        traceback.print_exc()

if __name__ == '__main__':
    run_test()
