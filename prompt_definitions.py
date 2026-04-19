# prompt_definitions.py
# -*- coding: utf-8 -*-
import os
import json

def load_prompts():
    """Loads prompts from the English JSON file."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_file = os.path.join(base_dir, 'prompts', 'en_US.json')

    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading prompts: {e}")
        return {}

# Load English prompts
_prompts = load_prompts()

# Map dictionary keys to global variables for compatibility with existing code
summarize_recent_chapters_prompt = _prompts.get('summarize_recent_chapters_prompt', '')
knowledge_search_prompt = _prompts.get('knowledge_search_prompt', '')
knowledge_filter_prompt = _prompts.get('knowledge_filter_prompt', '')
core_seed_prompt = _prompts.get('core_seed_prompt', '')
character_dynamics_prompt = _prompts.get('character_dynamics_prompt', '')
world_building_prompt = _prompts.get('world_building_prompt', '')
plot_architecture_prompt = _prompts.get('plot_architecture_prompt', '')
chapter_blueprint_prompt = _prompts.get('chapter_blueprint_prompt', '')
chunked_chapter_blueprint_prompt = _prompts.get('chunked_chapter_blueprint_prompt', '')
summary_prompt = _prompts.get('summary_prompt', '')
create_character_state_prompt = _prompts.get('create_character_state_prompt', '')
update_character_state_prompt = _prompts.get('update_character_state_prompt', '')
first_chapter_draft_prompt = _prompts.get('first_chapter_draft_prompt', '')
next_chapter_draft_prompt = _prompts.get('next_chapter_draft_prompt', '')
Character_Import_Prompt = _prompts.get('Character_Import_Prompt', '')
