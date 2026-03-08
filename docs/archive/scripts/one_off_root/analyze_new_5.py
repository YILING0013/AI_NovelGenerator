
import os
import sys
import json
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.getcwd())

from novel_generator.quality_loop_controller import ChapterQualityAnalyzer
from utils import read_file

# Configure logging to error only to keep stdout clean
logging.basicConfig(level=logging.ERROR)

def analyze_new_chapters():
    novel_path = os.path.join(os.getcwd(), "wxhyj")
    chapters_dir = os.path.join(novel_path, "chapters")
    
    # Load Config
    llm_config = {
         "api_key": os.environ.get("OPENAI_API_KEY", "sk-antigravity-key"), 
         "base_url": "https://api.openai.com/v1",
         "model_name": "gpt-4"
    } 
    if os.path.exists("config.json"):
        with open("config.json", 'r', encoding='utf-8') as f:
            llm_config.update(json.load(f))
    
    # Initialize Analyzer
    analyzer = ChapterQualityAnalyzer(novel_path, llm_config=llm_config)
    
    print("Analyzing Newly Generated Chapters 1-5...")
    
    for i in range(1, 6):
        chap_file = os.path.join(chapters_dir, f"chapter_{i}.txt")
        if not os.path.exists(chap_file):
            print(f"Chapter {i} not found.")
            continue
            
        content = read_file(chap_file)
        print(f"\nAnalyzing Ch {i} ({len(content)} chars)...")
        
        try:
            # Deep scan
            scores = analyzer.analyze_content(content, use_llm=True)
            total = scores.get('综合评分', 0)
            
            print(f"✅ Score: {total}")
            
            # Print Details
            print("  --- Dimensions ---")
            for dim in ["剧情连贯性", "角色一致性", "情感张力", "写作质量", "系统机制"]:
                if dim in scores:
                    print(f"  {dim}: {scores[dim]}")
            
            # Check for genre info
            if "检测题材" in scores:
                print(f"  🏷️ Genre: {scores['检测题材']}")
            if "题材改进建议" in scores and scores['题材改进建议']:
                print(f"  💡 Suggestions: {scores['题材改进建议']}")
                
        except Exception as e:
            print(f"Error analyzing Ch {i}: {e}")

if __name__ == "__main__":
    analyze_new_chapters()
