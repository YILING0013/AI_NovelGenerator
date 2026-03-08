import os
import re
import sys

# Add parent directory to path so we can import novel_generator modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from novel_generator.common import clean_llm_output
from fix_chapter_title_duplication import ensure_single_title

def fix_chapter_content(filepath, chapter_num):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    print(f"Processing Chapter {chapter_num}...")
    
    # 1. Cleaner LLM Output (Removing meta commentary)
    cleaned = clean_llm_output(content)
    
    # 2. Fix Title Duplication
    # Special handling for Chapter 11 which is mislabeled as Chapter 12
    if chapter_num == 11 and "第12章" in cleaned:
        print("  - Fixing Chapter 11 mislabeling (12 -> 11)...")
        cleaned = cleaned.replace("第12章", "第11章")
        
    cleaned = ensure_single_title(cleaned, chapter_num, f"第{chapter_num}章")
    
    # 3. Final trim
    cleaned = cleaned.strip()
    
    # Check if content changed
    if cleaned != content:
        print(f"  - Content modified. Saving...")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(cleaned)
    else:
        print(f"  - No changes needed.")

def main():
    base_dir = r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator\wxhyj\chapters"
    print(f"Starting cleanup in: {base_dir}")
    
    for i in range(1, 17):
        filename = f"chapter_{i}.txt"
        filepath = os.path.join(base_dir, filename)
        
        if os.path.exists(filepath):
            try:
                fix_chapter_content(filepath, i)
            except Exception as e:
                print(f"Error processing {filename}: {e}")
        else:
            print(f"Skipping {filename} (Not found)")

if __name__ == "__main__":
    main()
