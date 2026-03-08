
import sys
import os
import json
import logging
from pathlib import Path
import re

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from chapter_quality_analyzer import ChapterQualityAnalyzer

import sys
import os
from pathlib import Path
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from novel_generator.text_optimizer import ChapterTextOptimizer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if __name__ == "__main__":
    # Example usage: Optimize Chapter 5
    optimizer = ChapterTextOptimizer("wxhyj")
    optimizer.optimize_chapter_file(5)
