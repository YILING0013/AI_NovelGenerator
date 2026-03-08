
import sys
import os
from pathlib import Path
import json

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from chapter_quality_analyzer import ChapterQualityAnalyzer

def analyze_chapters_1_to_10():
    analyzer = ChapterQualityAnalyzer("wxhyj")
    
    output_lines = []
    output_lines.append(f"{'Chapter':<8} | {'Overall':<7} | {'Plot':<5} | {'Char':<5} | {'Write':<5} | {'Arch':<5} | {'Set':<5} | {'Word%':<5} | {'Tens':<5} | {'Mech':<5}")
    output_lines.append("-" * 90)

    results = []

    for i in range(1, 11):
        try:
            scores = analyzer.analyze_chapter(i)
            overall = scores.get('综合评分', 0)
            plot = scores.get('剧情连贯性', 0)
            char = scores.get('角色一致性', 0)
            write = scores.get('写作质量', 0)
            arch = scores.get('架构遵循度', 0)
            setting = scores.get('设定遵循度', 0)
            word_target = scores.get('字数达标率', 0)
            tension = scores.get('情感张力', 0)
            mech = scores.get('系统机制', 0)
            
            output_lines.append(f"{i:<8} | {overall:<7.2f} | {plot:<5.1f} | {char:<5.1f} | {write:<5.1f} | {arch:<5.1f} | {setting:<5.1f} | {word_target:<5.1f} | {tension:<5.1f} | {mech:<5.1f}")
            
            scores['chapter_number'] = i
            results.append(scores)
            
        except Exception as e:
            output_lines.append(f"Chapter {i} error: {e}")

    # Write to file for reading
    with open("wxhyj/chapter_text_quality_report.txt", "w", encoding='utf-8') as f:
        f.write("\n".join(output_lines))
        
    print("Analysis complete. Saved to wxhyj/chapter_text_quality_report.txt")

if __name__ == "__main__":
    analyze_chapters_1_to_10()
