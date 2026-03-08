
import logging
import sys
from strict_blueprint_generator import Strict_Chapter_blueprint_generate

# Configure logging
logging.basicConfig(
    level=logging.INFO, # Back to INFO to reduce noise
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("batch_gen_retry.log", encoding='utf-8', mode='w')
    ]
)

# Configuration
API_KEY = "3c3f115ed8f547cc846269716f60d8ff.PEAkqW8RqIlMCYYX"
BASE_URL = "https://open.bigmodel.cn/api/anthropic/v1/messages"
MODEL = "glm-4.7"

def run_batch():
    print("🚀 Starting Batch Generation for Chapters 1-50 (Retry)...")
    
    try:
        Strict_Chapter_blueprint_generate(
            interface_format="智谱AI",
            api_key=API_KEY,
            base_url=BASE_URL,
            llm_model=MODEL,
            filepath=".",
            number_of_chapters=50,  
            batch_size=1,          # Single chapter per batch for maximum stability
            user_guidance=""
        )
        print("✅ Batch Generation Completed Successfully!")
    except Exception as e:
        print(f"❌ Batch Generation Failed: {e}")

if __name__ == "__main__":
    run_batch()
