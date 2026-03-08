
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

def analyze_56_chapters():
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
    
    print("Scanning 56 Chapters...")
    
    results = {}
    
    # 1. Fast Scan (Keyword based)
    low_score_candidates = []
    
    for i in range(1, 57):
        chap_file = os.path.join(chapters_dir, f"chapter_{i}.txt")
        if not os.path.exists(chap_file):
            continue
            
        content = read_file(chap_file)
        # Fast scan
        try:
            scores = analyzer.analyze_content(content, use_llm=False)
            total_score = scores.get('综合评分', 0)
            
            results[i] = {
                'chapter_num': i,
                'content_len': len(content),
                'keyword_score': total_score,
                'llm_score': None,
                'details': scores # Keyword details
            }
            
            low_score_candidates.append((i, total_score))
        except Exception as e:
            print(f"Error scanning Ch {i}: {e}")

        if i % 10 == 0:
            print(f"Scanned {i}/56...")

    # Sort by score to find worst 3
    low_score_candidates.sort(key=lambda x: x[1])
    worst_3 = [x[0] for x in low_score_candidates[:3]]
    
    # 2. Deep Dive (LLM based)
    # Strategy: 1, 2, 3 (Golden), Every 10th, Worst 3, Last One
    deep_dive_indices = set([1, 2, 3, 10, 20, 30, 40, 50, 56] + worst_3)
    # Ensure they exist
    deep_dive_indices = sorted([i for i in deep_dive_indices if i in results])
    
    print(f"\nPerforming Deep Analysis on Chapters: {deep_dive_indices}")
    
    for i in deep_dive_indices:
        chap_file = os.path.join(chapters_dir, f"chapter_{i}.txt")
        content = read_file(chap_file)
        
        try:
            # Deep scan
            llm_scores = analyzer.analyze_content(content, use_llm=True)
            results[i]['llm_score'] = llm_scores.get('综合评分', 0)
            results[i]['details'] = llm_scores # Overwrite with LLM details
            print(f"Deep Analysis Ch {i}: {results[i]['llm_score']}")
        except Exception as e:
            # Fallback to keyword if LLM fails
            print(f"Deep Analysis failed for Ch {i}, keeping keyword score: {e}")

    # 3. Report Generation
    print("\n" + "="*50)
    print("SUMMARY REPORT (Hybrid Analysis)")
    print("="*50)
    print(f"{'Chapter':<8} | {'Type':<8} | {'Score':<6} | {'Status'}")
    print("-" * 40)
    
    chapter_quality_groups = {"S": [], "A": [], "B": [], "C": []}
    
    for i in range(1, 57):
        if i not in results: continue
        
        res = results[i]
        score = res['llm_score'] if res['llm_score'] else res['keyword_score']
        score_type = "LLM" if res['llm_score'] else "Key"
        
        status = ""
        if score >= 9.0: 
            status = "🌟 S-Class"
            chapter_quality_groups["S"].append(i)
        elif score >= 8.0: 
            status = "✅ Good"
            chapter_quality_groups["A"].append(i)
        elif score >= 7.0: 
            status = "😐 Fair"
            chapter_quality_groups["B"].append(i)
        else: 
            status = "⚠️ Poor"
            chapter_quality_groups["C"].append(i)
            
        print(f"Ch {i:<5} | {score_type:<8} | {score:<6} | {status}")

    print("\n" + "="*50)
    print("DETAILED INSIGHTS (Deep Dived Chapters)")
    print("="*50)
    
    for i in deep_dive_indices:
        res = results[i]
        details = res['details']
        score = res['llm_score'] if res['llm_score'] else res['keyword_score']
        
        print(f"\n### Chapter {i} (Score: {score})")
        # Extract low dimensions
        low_dims = [k for k, v in details.items() if isinstance(v, (int, float)) and v < 8.0 and k != "综合评分"]
        if low_dims:
            print(f"📉 Weaknesses: {', '.join([f'{d}({details[d]})' for d in low_dims])}")
        else:
            print(f"✨ Strengths: All dimensions > 8.0")
            
        # Extract advice if available (LLM usually returns 'improvement_hint' or specific keys)
        genre = details.get('检测题材', 'Unknown')
        print(f"🏷️ Genre Detected: {genre}")

if __name__ == "__main__":
    analyze_56_chapters()
