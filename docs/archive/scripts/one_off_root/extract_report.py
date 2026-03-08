
import json

try:
    with open('wxhyj/chapter_quality_report.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    chapter_details = data.get('chapter_details', [])
    target_chapters = range(1, 11)
    
    print(f"{'Chapter':<8} | {'Score':<6} | {'Level':<10} | {'Issues'}")
    print("-" * 60)
    
    for ch in chapter_details:
        c_num = ch.get('chapter_number')
        if c_num in target_chapters:
            score = ch.get('score', 0)
            level = ch.get('quality_level', 'N/A')
            issues = ch.get('issues', [])
            print(f"{c_num:<8} | {score:<6.2f} | {level:<10} | {len(issues)} issues: {issues[:1]}")

except Exception as e:
    print(f"Error: {e}")
