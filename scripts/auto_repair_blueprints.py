import os
import sys
import json
import logging
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from novel_generator.blueprint_repairer import repair_low_score_blueprints

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    print("DEBUG: Script main started", flush=True)
    config_path = project_root / "config.json"
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        return

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Get LLM config for blueprint generation
    llm_choice = config["choose_configs"]["chapter_outline_llm"]
    llm_config = config["llm_configs"][llm_choice]

    interface_format = llm_config["interface_format"]
    api_key = llm_config["api_key"]
    base_url = llm_config["base_url"]
    model_name = llm_config["model_name"]
    
    # Get target filepath
    filepath = config["other_params"]["filepath"]
    if not os.path.isabs(filepath):
        filepath = os.path.join(project_root, filepath)

    # Load quality report
    report_path = Path(filepath) / "chapter_quality_report.json"
    if not report_path.exists():
        logger.error(f"Quality report not found: {report_path}. Run batch_quality_check.py first.")
        return

    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    low_score_chapters = [item['chapter_number'] for item in report.get("low_score_chapters", [])]
    logger.info(f"Found {len(low_score_chapters)} low-score chapters.")

    if not low_score_chapters:
        logger.info("No low-score chapters to repair.")
        return

    # Run repair
    logger.info("Starting batch repair...")
    results = repair_low_score_blueprints(
        interface_format=interface_format,
        api_key=api_key,
        base_url=base_url,
        llm_model=model_name,
        filepath=filepath,
        low_score_chapters=low_score_chapters,
        progress_callback=lambda current, total, msg: logger.info(f"[{current}/{total}] {msg}"),
        max_chapters=500  # Repair all at once if possible or a large batch
    )

    logger.info("Repair complete.")
    logger.info(f"Success: {results['success']}, Failed: {results['failed']}")

if __name__ == "__main__":
    main()
