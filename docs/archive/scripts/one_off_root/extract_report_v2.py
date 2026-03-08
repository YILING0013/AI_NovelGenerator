
import json

try:
    with open('wxhyj/chapter_quality_report.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    chapter_details = data.get('chapter_details', [])
    target_chapters = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    
    print(f"{'Chapter':<8} | {'Score':<6} | {'Level':<10} | {'Format Compliance'}")
    print("-" * 60)
    
    found_chapters = {}
    for ch in chapter_details:
        c_num = ch.get('chapter_number')
        if c_num in target_chapters:
            found_chapters[c_num] = ch

    format_issues = {i['chapter_number']: i['compliance_score'] for i in data.get('format_issues', [])}

    for ch_num in target_chapters:
        ch = found_chapters.get(ch_num)
        if ch:
            score = ch.get('score', 0)
            level = ch.get('quality_level', 'N/A')
            fmt = format_issues.get(ch_num, 100.0) # Default to 100 if not in format_issues
            print(f"{ch_num:<8} | {score:<6.2f} | {level:<10} | {fmt:.1f}%")
        else:
            print(f"{ch_num:<8} | NOT FOUND IN DETAILS")

except Exception as e:
    print(f"Error: {e}")
