
import sys
import os
from pathlib import Path
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from chapter_quality_analyzer import ChapterQualityAnalyzer

def analyze_chapters():
    analyzer = ChapterQualityAnalyzer("wxhyj")
    
    output_lines = []
    # Added 'Genre' score to display as it's part of the new optimization
    output_lines.append(f"{'Chapter':<8} | {'Overall':<7} | {'Plot':<5} | {'Char':<5} | {'Write':<5} | {'Arch':<5} | {'Set':<5} | {'Word%':<5} | {'Tens':<5} | {'Genre':<5}")
    output_lines.append("-" * 100)

    results = []
    
    # Calculate averages
    total_scores = {
        'Overall': 0, 'Plot': 0, 'Char': 0, 'Write': 0, 
        'Arch': 0, 'Set': 0, 'Word%': 0, 'Tens': 0, 'Genre': 0
    }
    valid_count = 0

    # Range 1 to 28 inclusive
    for i in range(1, 29):
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
            
            # Extract genre score if available, otherwise default to 0
            if '题材维度' in scores and isinstance(scores['题材维度'], dict):
                 genres = scores['题材维度']
                 # Average of genre sub-scores
                 genre_vals = [v for v in genres.values() if isinstance(v, (int, float))]
                 genre = sum(genre_vals) / len(genre_vals) if genre_vals else 0
            else:
                 genre = scores.get('题材综合分', 0)

            output_lines.append(f"{i:<8} | {overall:<7.2f} | {plot:<5.1f} | {char:<5.1f} | {write:<5.1f} | {arch:<5.1f} | {setting:<5.1f} | {word_target:<5.1f} | {tension:<5.1f} | {genre:<5.1f}")
            
            total_scores['Overall'] += overall
            total_scores['Plot'] += plot
            total_scores['Char'] += char
            total_scores['Write'] += write
            total_scores['Arch'] += arch
            total_scores['Set'] += setting
            total_scores['Word%'] += word_target
            total_scores['Tens'] += tension
            total_scores['Genre'] += genre
            valid_count += 1
            
        except Exception as e:
            output_lines.append(f"Chapter {i} error: {e}")
            import traceback
            traceback.print_exc()

    if valid_count > 0:
        output_lines.append("-" * 100)
        output_lines.append(f"{'Average':<8} | {total_scores['Overall']/valid_count:<7.2f} | {total_scores['Plot']/valid_count:<5.1f} | {total_scores['Char']/valid_count:<5.1f} | {total_scores['Write']/valid_count:<5.1f} | {total_scores['Arch']/valid_count:<5.1f} | {total_scores['Set']/valid_count:<5.1f} | {total_scores['Word%']/valid_count:<5.1f} | {total_scores['Tens']/valid_count:<5.1f} | {total_scores['Genre']/valid_count:<5.1f}")

    # Write to file for reading
    output_path = "wxhyj/chapter_quality_report_1_28.txt"
    with open(output_path, "w", encoding='utf-8') as f:
        f.write("\n".join(output_lines))
        
    print(f"Analysis complete. Saved to {output_path}")

if __name__ == "__main__":
    analyze_chapters()
