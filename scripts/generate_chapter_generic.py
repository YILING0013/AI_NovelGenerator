
import sys
import os
import logging
import argparse

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from novel_generator.chapter import generate_chapter_draft
from utils import save_string_to_txt

# Default Configuration
DEFAULT_CONFIG = {
    "api_key": "3c3f115ed8f547cc846269716f60d8ff.PEAkqW8RqIlMCYYX",
    "base_url": "https://open.bigmodel.cn/api/anthropic/v1/messages",
    "model_name": "glm-4.6",
    "interface_format": "智谱AI",
    "filepath": "C:/Users/tcui/Documents/GitHub/AI_NovelGenerator/wxhyj",
    "word_number": 4500,
    "temperature": 0.7,
    "embedding_api_key": "sk-rbzzyacpjiigjrfziyobarphqpjcmfmmcngqvnkumnothnyo",
    "embedding_url": "https://api.siliconflow.cn/v1/embeddings",
    "embedding_interface_format": "SiliconFlow",
    "embedding_model_name": "Qwen/Qwen3-Embedding-8B"
}

def main():
    parser = argparse.ArgumentParser(description="Generate a novel chapter.")
    parser.add_argument("novel_number", type=int, help="The chapter number to generate")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    print(f"Start generating Chapter {args.novel_number}...")
    
    try:
        draft = generate_chapter_draft(
            api_key=DEFAULT_CONFIG['api_key'],
            base_url=DEFAULT_CONFIG['base_url'],
            model_name=DEFAULT_CONFIG['model_name'],
            filepath=DEFAULT_CONFIG['filepath'],
            novel_number=args.novel_number,
            word_number=DEFAULT_CONFIG['word_number'],
            temperature=DEFAULT_CONFIG['temperature'],
            interface_format=DEFAULT_CONFIG['interface_format'],
            user_guidance="",
            characters_involved="",
            key_items="",
            scene_location="",
            time_constraint="",
            embedding_api_key=DEFAULT_CONFIG["embedding_api_key"],
            embedding_url=DEFAULT_CONFIG["embedding_url"],
            embedding_interface_format=DEFAULT_CONFIG["embedding_interface_format"],
            embedding_model_name=DEFAULT_CONFIG["embedding_model_name"]
        )
        
        output_dir = os.path.join(DEFAULT_CONFIG['filepath'], "chapters")
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"Chapter_{args.novel_number}.txt")
        
        save_string_to_txt(output_file, draft)
        print(f"Success! Chapter saved to: {output_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
