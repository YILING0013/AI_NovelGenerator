import sys
import os
import logging
from strict_blueprint_generator import StrictChapterGenerator
from prompt_definitions import ENHANCED_BLUEPRINT_TEMPLATE
from llm_adapters import create_llm_adapter
from utils import read_file
import time

# Configuration
API_KEY = "3c3f115ed8f547cc846269716f60d8ff.PEAkqW8RqIlMCYYX"
BASE_URL = "https://open.bigmodel.cn/api/anthropic/v1/messages"
MODEL = "glm-4.7"

# Force logging to stdout and file
root = logging.getLogger()
if root.handlers:
    for handler in root.handlers:
        root.removeHandler(handler)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Stdout handler
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)

# File handler (UTF-8)
file_handler = logging.FileHandler("manual_test_debug.log", encoding='utf-8', mode='w')
file_handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.DEBUG,
    handlers=[stream_handler, file_handler]
)

logger = logging.getLogger(__name__)

def generate_blueprint(start_chap, end_chap):
    print(f"DEBUG: Initializing generator for chapters {start_chap}-{end_chap}")
    generator = StrictChapterGenerator(
        interface_format="智谱AI",
        api_key=API_KEY,
        base_url=BASE_URL,
        llm_model=MODEL
    )
    
    # Read architecture
    arch_path = os.path.join(os.getcwd(), "wxhyj", "Novel_architecture.txt")
    if not os.path.exists(arch_path):
        logger.error("No architecture file found")
        return False
        
    architecture_text = read_file(arch_path)
    if not architecture_text:
        logger.error("Empty architecture text")
        return False
    
    # Read existing directory for context
    dir_path = os.path.join(os.getcwd(), "wxhyj", "Novel_directory.txt")
    existing_content = ""
    if os.path.exists(dir_path):
        existing_content = read_file(dir_path)
        
    if f"第{start_chap}章" in existing_content:
        print(f"✅ Chapter {start_chap} already exists in directory. Skipping generation.")
        return True

    try:
        # Using protected method as this is a manual test/control script
        new_content = generator._generate_batch_with_retry(
            start_chapter=start_chap,
            end_chapter=end_chap,
            architecture_text=architecture_text,
            existing_content=existing_content,
            filepath=os.path.join(os.getcwd(), "wxhyj")
        )
        
        if new_content:
            # Append new content to file
            # Ensure we start with a newline if file is not empty
            prefix = "\n\n" if existing_content.strip() else ""
            with open(dir_path, "a", encoding="utf-8") as f:
                f.write(prefix + new_content.strip())
            return True
        else:
            logger.error(f"No content generated for Chapter {start_chap}")
            return False
            
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        return False

def run_batch_generation():
    print("🚀 Starting Batch Generation for Chapters 2-50...")
    
    start_chapter = 2
    end_chapter = 50
    
    for i in range(start_chapter, end_chapter + 1):
        print(f"\n\n==================================================")
        print(f"🎬 Generating Chapter {i}...")
        print(f"==================================================\n")
        
        try:
            # Generate one chapter at a time
            result = generate_blueprint(start_chap=i, end_chap=i)
            
            if result:
                print(f"✅ Chapter {i} generated successfully.")
            else:
                print(f"❌ Failed to generate Chapter {i}. Stopping batch process.")
                break
                
            # Optional: Add a small delay to avoid hitting API rate limits too hard
            time.sleep(1)
            
        except Exception as e:
            print(f"❌ Critical error during Chapter {i} generation: {str(e)}")
            break

    print("\n🏁 Batch generation process finished.")

if __name__ == "__main__":
    run_batch_generation()
