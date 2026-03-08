import sys
import os
import json
import logging

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from novel_generator.critique_agent import PoisonousReaderAgent

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_critic():
    # 1. Load config
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("❌ config.json not found!")
        return

    # 2. Get LLM config (Prioritize critique_llm, fallback to quality_loop_llm)
    llm_name = config.get('choose_configs', {}).get('critique_llm')
    if not llm_name:
        llm_name = config.get('choose_configs', {}).get('quality_loop_llm', '智谱AI GLM-4.7')
        print(f"⚠️ 'critique_llm' not set, falling back to '{llm_name}'")
    else:
        print(f"🔧 Using configured Critic LLM: {llm_name}")
    llm_conf = config.get('llm_configs', {}).get(llm_name)
    
    if not llm_conf:
        print(f"❌ Configuration for {llm_name} not found!")
        return

    # 3. Initialize Agent
    agent = PoisonousReaderAgent(llm_conf)

    # 4. Read Chapter 30
    chapter_path = r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator\wxhyj\chapters\chapter_30.txt"
    try:
        with open(chapter_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ Chapter file not found: {chapter_path}")
        return

    print(f"📖 Reading Chapter 30 ({len(content)} chars)...")

    # 5. Critique!
    result = agent.critique_chapter(content)

    print("\n" + "="*50)
    print("📢 毒舌读者点评结果")
    print("="*50)
    print(f"判定: {result.get('rating')}")
    print(f"评分: {result.get('score')}")
    print(f"毒评: {result.get('toxic_comment')}")
    print(f"要求: {result.get('improvement_demand')}")
    print("="*50 + "\n")

if __name__ == "__main__":
    test_critic()
