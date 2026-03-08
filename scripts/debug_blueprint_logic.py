import os
import re

def debug_logic():
    # Simulate user input path (Project Root)
    filepath = r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator"
    print(f"DEBUG: Initial filepath: {filepath}")

    # ==========================================
    # 1. Replicate Architecture Finding Logic
    # ==========================================
    arch_file = os.path.join(filepath, "Novel_architecture.txt")
    if not os.path.exists(arch_file):
        found = False
        print("DEBUG: Novel_architecture.txt not in root. Walking...")
        for root, dirs, files in os.walk(filepath):
            if "Novel_architecture.txt" in files:
                arch_file = os.path.join(root, "Novel_architecture.txt")
                filepath = root 
                print(f"DEBUG: Auto-detected architecture in subdirectory: {filepath}")
                print(f"DEBUG: Arch file found at: {arch_file}")
                found = True
                break
        if not found:
            print(f"ERROR: Novel_architecture.txt not found in {filepath} or subdirectories")
            return
            
    # Read architecture
    try:
        with open(arch_file, 'r', encoding='utf-8') as f:
            arch_text = f.read().strip()
        print(f"DEBUG: Architecture file read. Size: {len(arch_text)} bytes")
        if not arch_text:
            print("ERROR: Architecture file empty")
            return
    except Exception as e:
        print(f"ERROR reading architecture: {e}")
        return

    # ==========================================
    # 2. Replicate Directory/Start Chapter Logic
    # ==========================================
    filename_dir = os.path.join(filepath, "Novel_directory.txt")
    print(f"DEBUG: Looking for Directory file at: {filename_dir}")
    
    start_chapter = 1
    existing_content = ""
    
    if os.path.exists(filename_dir):
        print("DEBUG: Directory file exists.")
        try:
            with open(filename_dir, 'r', encoding='utf-8') as f:
                existing_content = f.read().strip()
            print(f"DEBUG: Directory content size: {len(existing_content)} bytes")
            
            if existing_content:
                chapter_pattern = r"第\s*(\d+)\s*章"
                existing_chapters = re.findall(chapter_pattern, existing_content)
                existing_numbers = [int(x) for x in existing_chapters if x.isdigit()]
                print(f"DEBUG: Found {len(existing_numbers)} existing chapters.")
                if existing_numbers:
                    print(f"DEBUG: Max chapter found: {max(existing_numbers)}")
                    start_chapter = max(existing_numbers) + 1
                else:
                    print("DEBUG: No chapter numbers found in directory file.")
        except Exception as e:
            print(f"ERROR reading directory file: {e}")
            return
    else:
        print("DEBUG: Directory file DOES NOT exist.")

    print(f"DEBUG: Calculated Start Chapter: {start_chapter}")

    # ==========================================
    # 3. Simulate Logic Check
    # ==========================================
    # Assume user asks for 50 chapters
    number_of_chapters = 50 
    print(f"DEBUG: Target number_of_chapters (simulated): {number_of_chapters}")

    if start_chapter > number_of_chapters:
        print("RESULT: SUCCESS (True) - All chapters already generated.")
    else:
        print("RESULT: WOULD INVALIDATE - Start chapter <= number of chapters. Logic would proceed to generation.")
        print("      If this proceeds and fails, it means LLM call failed or file write failed.")

if __name__ == "__main__":
    debug_logic()
