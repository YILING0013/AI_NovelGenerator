
import re
import os

filename_dir = r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator\wxhyj\Novel_directory.txt"

def test_regex():
    with open(filename_dir, 'r', encoding='utf-8') as f:
        existing_content = f.read().strip()
    
    chapter_pattern = r"(?m)^第\s*(\d+)\s*章\s*-\s*"
    existing_chapters = re.findall(chapter_pattern, existing_content)
    print(f"Matches: {existing_chapters}")
    
    existing_numbers = [int(x) for x in existing_chapters if x.isdigit()]
    start_chapter = max(existing_numbers) + 1 if existing_numbers else 1
    print(f"Start Chapter: {start_chapter}")

if __name__ == "__main__":
    test_regex()
