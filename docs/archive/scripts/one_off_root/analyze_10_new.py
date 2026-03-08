
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

def analyze_new_10():
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
    
    print("Analyzing Newly Generated Chapters 1-10...")
    print("-" * 60)
    print(f"{'Ch':<4} | {'Score':<6} | {'Tension':<7} | {'Char':<6} | {'Writing':<7} | {'Genre'}")
    print("-" * 60)
    
    for i in range(1, 11):
        chap_file = os.path.join(chapters_dir, f"chapter_{i}.txt")
        if not os.path.exists(chap_file):
            print(f"{i:<4} | Not Found")
            continue
            
        content = read_file(chap_file)
        
        try:
            # Deep scan
            scores = analyzer.analyze_content(content, use_llm=True)
            total = scores.get('综合评分', 0)
            tension = scores.get('情感张力', 0)
            char = scores.get('角色一致性', 0)
            writing = scores.get('写作质量', 0)
            genre = scores.get('检测题材', 'Unknown')
            
            # Truncate genre if too long
            if len(genre) > 10: genre = genre[:10] + ".."
            
            print(f"{i:<4} | {total:<6} | {tension:<7} | {char:<6} | {writing:<7} | {genre}")

        except Exception as e:
            print(f"{i:<4} | Error: {e}")

if __name__ == "__main__":
    analyze_new_10()
