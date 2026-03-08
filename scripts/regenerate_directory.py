
import os
import sys
import shutil
import logging

# Add parent directory to path to allow importing modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strict_blueprint_generator import StrictChapterGenerator

import argparse

def regenerate():
    parser = argparse.ArgumentParser(description='Regenerate novel directory.')
    parser.add_argument('--chapters', type=int, default=20, help='Total number of chapters to generate')
    parser.add_argument('--batch_size', type=int, default=2, help='Batch size for generation')
    args = parser.parse_args()

    # Configuration
    api_key = "3c3f115ed8f547cc846269716f60d8ff.PEAkqW8RqIlMCYYX"
    base_url = "https://open.bigmodel.cn/api/anthropic/v1/messages"
    llm_model = "glm-4.7"
    project_path = r"c:\Users\tcui\Documents\GitHub\AI_NovelGenerator\wxhyj"
    directory_file = os.path.join(project_path, "Novel_directory.txt")
    backup_file = os.path.join(project_path, "Novel_directory.bak.txt")
    
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("regexp_debug.log"),
            logging.StreamHandler()
        ]
    )
    
    # Backup existing directory
    if os.path.exists(directory_file):
        logging.info(f"Backing up {directory_file} to {backup_file}")
        shutil.copy2(directory_file, backup_file)
        
        # Clear existing directory to force clean generation
        logging.info("Clearing existing directory file to force regeneration")
        with open(directory_file, 'w', encoding='utf-8') as f:
            f.write("")
            
    # Initialize Generator
    generator = StrictChapterGenerator(
        interface_format="智谱AI",
        api_key=api_key,
        base_url=base_url,
        llm_model=llm_model,
        temperature=0.7,
        max_tokens=60000,
        timeout=1800
    )
    
    # Generate First Batch (Chapters 1-10)
    # This will ensure the critical opening chapters (including the ones the user complained about)
    # are completely rewritten with the new architecture.
    logging.info(f"Starting regeneration of chapters 1-{args.chapters} with batch size {args.batch_size}...")
    success = generator.generate_complete_directory_strict(
        filepath=project_path,
        number_of_chapters=args.chapters, 
        batch_size=args.batch_size
    )
    
    if success:
        logging.info("Regeneration successful!")
    else:
        logging.error("Regeneration failed.")

if __name__ == "__main__":
    regenerate()
