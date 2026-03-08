
import re
import sys

def diagnose():
    filename = "debug_llm_response_batch.txt"
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        return

    print(f"Content Length: {len(content)}")
    
    # Simulate strict validation logic
    REQUIRED_MODULES = {
        "基础元信息": ["【基础元信息】", "基础元信息"],
        "张力架构设计": ["【张力架构设计】", "张力架构"],
        "天书洞察应用": ["【天书洞察应用", "天书洞察"],
        "伏笔与信息差": ["【伏笔与信息差", "伏笔与信息差"],
        # "暧昧与修罗场": ["【暧昧与修罗场", "暧昧与修罗场"], 
        "情节精要蓝图": ["【情节精要蓝图】", "情节精要", "剧情精要", "开场 (Hook)", "发展 (Development)"],
        "系统机制整合": ["【系统机制整合】", "系统机制", "系统状态：", "奖励机制："],
        "质量检查清单": ["【质量检查清单", "质量检查", "逻辑闭环检查"]
    }

    print("\n--- Module Check ---")
    missing_modules = []
    
    chapter_pattern = r"(?m)^[#*\s]*第\s*(\d+)\s*章"
    chapters = re.split(chapter_pattern, content)
    
    if len(chapters) < 2:
        print("❌ No chapters detected by regex!")
    else:
        # Skip preamble (index 0)
        for i in range(1, len(chapters), 2):
            ch_num = chapters[i]
            ch_text = chapters[i+1]
            print(f"\nTargeting Chapter {ch_num}...")
            
            chapter_missing = []
            for module, keywords in REQUIRED_MODULES.items():
                if not any(kw in ch_text for kw in keywords):
                    chapter_missing.append(module)
            
            if chapter_missing:
                print(f"  ❌ Missing modules: {', '.join(chapter_missing)}")
                missing_modules.extend(chapter_missing)
            else:
                print("  ✅ All required modules found.")

    if not missing_modules and len(chapters) > 1:
        print("\n✅ DIAGNOSIS: Validation should have passed.")
    else:
        print(f"\n❌ DIAGNOSIS: Validation failed. Missing: {missing_modules}")

    print("\n--- Content Snippets ---")
    if len(chapters) >= 2:
        print(f"Preable: {chapters[0][:100]}...")
        for i in range(1, len(chapters), 2):
            print(f"\n[Chapter {chapters[i]}] Start:\n{chapters[i+1][:200]}")

if __name__ == "__main__":
    diagnose()
