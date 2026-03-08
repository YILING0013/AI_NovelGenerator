
import sys
import os
import logging
import json

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from novel_generator.chapter import generate_chapter_draft
from utils import save_string_to_txt

# Configuration
config = {
    "api_key": "3c3f115ed8f547cc846269716f60d8ff.PEAkqW8RqIlMCYYX",
    "base_url": "https://open.bigmodel.cn/api/anthropic/v1/messages",
    "model_name": "glm-4.6",
    "interface_format": "智谱AI",
    "filepath": "C:/Users/tcui/Documents/GitHub/AI_NovelGenerator/wxhyj",
    "novel_number": 2,
    "word_number": 4500,
    "temperature": 0.7
}

# Bridging logic for the continuity error in Ch1
guidance = """
【重要剧情修正与衔接】
第1章结尾停留在主角即将被击杀的瞬间，且对手被错误描写为“萧尘”（原定应为管事赵四）。
请在本章开篇立即执行以下修正：
1. **完成反杀**：描述主角系统觉醒后，利用“力学死角”解析，瞬间反杀对手。
2. **身份修正（软补丁）**：在击杀对手后，主角发现这个“萧尘”其实是赵四利用“幻形符”伪装的（或者是赵四狐假虎威），或者这只是赵四，之前主角濒死产生了幻觉。
   *目的：避免第一章就真的杀死了最终BOSS萧尘，保留萧尘作为后续反派。*
3. **回归主线**：解决战斗后，衔接蓝图中的“拖着尸体返回外门”剧情。

【特别警告】
- **直接开始生成小说正文**，不要输出“好的”、“明白”或重复上述设定。
- **不要**在开头输出【绝对不可更改的核心设定】等提示词内容。
- 标题格式：第2章 逻辑崩坏，因果清算

风格保持：
继续保持“理性修仙”风格，用“清除异常”、“格式化”、“逻辑闭环”等术语描述战斗和思考。
"""

def main():
    logging.basicConfig(level=logging.INFO)
    print(f"Start generating Chapter {config['novel_number']}...")
    
    try:
        draft = generate_chapter_draft(
            api_key=config['api_key'],
            base_url=config['base_url'],
            model_name=config['model_name'],
            filepath=config['filepath'],
            novel_number=config['novel_number'],
            word_number=config['word_number'],
            temperature=0.8,
            interface_format=config['interface_format'],
            user_guidance=guidance,
            # Empty context fields as they will be filled by the function or are optional
            characters_involved="",
            key_items="",
            scene_location="",
            time_constraint="",
            # Embedding config
            embedding_api_key="sk-rbzzyacpjiigjrfziyobarphqpjcmfmmcngqvnkumnothnyo",
            embedding_url="https://api.siliconflow.cn/v1/embeddings",
            embedding_interface_format="SiliconFlow",
            embedding_model_name="Qwen/Qwen3-Embedding-8B"
        )
        
        output_dir = os.path.join(config['filepath'], "chapters")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"Chapter_{config['novel_number']}_v2.txt")
        
        save_string_to_txt(output_file, draft)
        print(f"Success! Chapter saved to: {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
