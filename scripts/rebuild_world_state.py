# -*- coding: utf-8 -*-
import os
import sys
import logging
import argparse

# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from novel_generator.state_manager import WorldStateManager
from llm_adapters import create_llm_adapter
from config_manager import load_config # Corrected Import

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('rebuild_state.log', encoding='utf-8', mode='w')
    ]
)

def rebuild_state(novel_path: str, start_chapter: int = 1, end_chapter: int = 0):
    """
    Rebuild world_state.json by scanning existing chapters.
    """
    if not os.path.exists(novel_path):
        logging.error(f"Novel path not found: {novel_path}")
        return

    # Use default config file path
    config_path = os.path.join(novel_path, "config.json")
    if not os.path.exists(config_path):
         # Try default in root if not in novel path? 
         # Assuming execution from root or standard config location
         config_path = "config.json"

    # Load Config
    try:
        config = load_config(config_path)
    except Exception as e:
        logging.error(f"Failed to load config: {e}")
        return
    
    # Use a cheap/fast model for bulk scanning if possible, or the main one
    # Assuming 'default' or first available config for now
    llm_configs = config.get("llm_configs", {})
    if not llm_configs:
         logging.error("No LLM configs found in config.json")
         return

    # Prefer the user's selected 'final_chapter_llm' or 'prompt_draft_llm'
    preferred_model = config.get("choose_configs", {}).get("final_chapter_llm")
    
    if preferred_model and preferred_model in llm_configs:
         llm_config_name = preferred_model
    else:
         # Fallback to first available with a key?
         llm_config_name = list(llm_configs.keys())[0]
         
    logging.info(f"Using LLM Config: {llm_config_name}")
    
    llm_conf = llm_configs[llm_config_name]
    if not llm_conf.get("api_key"):
        logging.error(f"API Key for {llm_config_name} is empty! Please configure it in UI.")
        return
    llm_adapter = create_llm_adapter(
        interface_format=llm_conf.get("interface_format", "openai"),
        base_url=llm_conf.get("base_url"),
        model_name=llm_conf.get("model_name"),
        api_key=llm_conf.get("api_key"),
        max_tokens=1024,
        temperature=0.1,
        timeout=120
    )
    
    state_manager = WorldStateManager(novel_path)
    
    # Reset State if starting from 1
    if start_chapter == 1:
        logging.info("Resetting World State...")
        # Try to get protagonist name from directory or architecture
        # For now, default to "Protagonist" or keep existing if only doing range update?
        # Logic: If rebuilding from scratch, clear it.
        state_manager.initialize_state("", "Protagonist") 
    
    chapters_dir = os.path.join(novel_path, "chapters")
    if not os.path.exists(chapters_dir):
        logging.error(f"Chapters directory not found: {chapters_dir}")
        return

    # Determine max chapter if not specified
    if end_chapter == 0:
        files = os.listdir(chapters_dir)
        chapters = []
        for f in files:
            if f.startswith("chapter_") and f.endswith(".txt"):
                try:
                    num = int(f.split("_")[1].split(".")[0])
                    chapters.append(num)
                except:
                    pass
        if not chapters:
            logging.warning("No chapters found.")
            return
        end_chapter = max(chapters)
        
    logging.info(f"Starting Rebuild from Ch {start_chapter} to {end_chapter}...")
    
    for i in range(start_chapter, end_chapter + 1):
        chapter_path = os.path.join(chapters_dir, f"chapter_{i}.txt")
        if not os.path.exists(chapter_path):
            logging.warning(f"Chapter {i} missing, skipping.")
            continue
            
        logging.info(f"Scanning Chapter {i}...")
        try:
            with open(chapter_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Use the existing update logic
            state_manager.update_state_from_chapter(content, llm_adapter)
            
        except Exception as e:
            logging.error(f"Error processing Chapter {i}: {e}")
            
    logging.info("Rebuild Complete!")
    logging.info(f"Final State: {state_manager.get_state_snapshot()}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild World State from existing chapters")
    parser.add_argument("novel_path", help="Path to the novel directory")
    parser.add_argument("--start", type=int, default=1, help="Start chapter number")
    parser.add_argument("--end", type=int, default=0, help="End chapter number (0 for all)")
    
    args = parser.parse_args()
    
    rebuild_state(args.novel_path, args.start, args.end)
