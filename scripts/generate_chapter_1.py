
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
    "novel_number": 1,
    "word_number": 4500,
    "temperature": 0.7
}

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
            temperature=config['temperature'],
            interface_format=config['interface_format'],
            user_guidance="",
            characters_involved="",
            key_items="",
            scene_location="",
            time_constraint="",
            embedding_api_key="sk-rbzzyacpjiigjrfziyobarphqpjcmfmmcngqvnkumnothnyo",
            embedding_url="https://api.siliconflow.cn/v1/embeddings",
            embedding_interface_format="SiliconFlow",
            embedding_model_name="Qwen/Qwen3-Embedding-8B"
        )
        
        output_dir = os.path.join(config['filepath'], "chapters")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"Chapter_{config['novel_number']}.txt")
        
        save_string_to_txt(output_file, draft)
        print(f"Success! Chapter saved to: {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
