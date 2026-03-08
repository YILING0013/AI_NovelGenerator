
import re
import os

def verify_blueprints(file_path, start_chapter, end_chapter):
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Regex patterns equivalent to StrictChapterGenerator._strict_validation
    chapter_patterns = [
        r"###\s*(?:\*\*)?\s*第\s*(\d+)\s*章",  # ### **第81章** or ### 第81章
        r"##\s*(?:\*\*)?\s*第\s*(\d+)\s*章",   # ## **第81章** or ## 第81章
        r"(?:\*\*)?\s*第\s*(\d+)\s*章",        # **第81章** or 第81章
        r"^\s*(\d+)\s*[\.、]\s*[^\n]*",        # 81. 标题 or 81、标题
    ]

    found_chapters = set()
    for pattern in chapter_patterns:
        matches = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0] # Take the first capturing group if multiple
            try:
                 # Check if match is a tuple or string (re.findall behavior varies with groups)
                if isinstance(match, str):
                    found_chapters.add(int(match))
                else: 
                     # If generic group match
                    found_chapters.add(int(match))
            except ValueError:
                pass

    print(f"Found chapters: {sorted(list(found_chapters))}")

    missing = []
    for i in range(start_chapter, end_chapter + 1):
        if i not in found_chapters:
            missing.append(i)

    if missing:
        print(f"FAILED: Missing chapters in range {start_chapter}-{end_chapter}: {missing}")
    else:
        print(f"SUCCESS: All chapters {start_chapter}-{end_chapter} found.")

if __name__ == "__main__":
    # Adjust path if needed
    file_path = r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator\wxhyj\Novel_directory.txt"
    verify_blueprints(file_path, 6, 25)
