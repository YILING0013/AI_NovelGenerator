
import sys
import os
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from novel_generator.blueprint import StrictChapterGenerator
from prompt_definitions import BLUEPRINT_FEW_SHOT_EXAMPLE

def main():
    generator = StrictChapterGenerator(
        interface_format="智谱AI",
        api_key="fake",
        base_url="fake",
        llm_model="fake"
    )
    
    # Simulate Prompt Construction for Batch 2 (Ch 11-13)
    prompt = generator._create_strict_prompt(
        architecture_text="[Architecture Content Placeholder]",
        chapter_list="Chapter 1... Chapter 10",
        start_chapter=11,
        end_chapter=13,
        user_guidance="Generate Ch 11-13"
    )
    
    print("=== PROMPT START ===")
    print(prompt)
    print("=== PROMPT END ===")

if __name__ == "__main__":
    main()
