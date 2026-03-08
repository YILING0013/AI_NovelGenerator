
import re
import os

file_path = r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator\wxhyj\Novel_directory.txt"

def clean_file():
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Remove the specific intro headers
    # Matches "我是...架构师" and any following text up to the start of "第X章" or newline
    # But be careful not to delete "第X章".
    
    # Strategy: Replace the intro phrases with empty strings
    content = re.sub(r'我是您?的小说蓝图架构师.*?根据您提供的.*?。', '', content, flags=re.DOTALL)
    content = re.sub(r'我是蓝图架构师.*?根据您的.*?。', '', content, flags=re.DOTALL)
    
    # 2. Ensure each "第X章" starts on a new line
    # Find "第" followed by digits and "章", ensuring it has newlines before it
    content = re.sub(r'(?<!\n)\s*(第\d+章)', r'\n\n\1', content)

    # 3. Clean up extra newlines created
    content = re.sub(r'\n{3,}', '\n\n', content)
    
    # 4. Remove leading whitespace/newlines
    content = content.strip()

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Cleaned {file_path}")

if __name__ == "__main__":
    clean_file()
