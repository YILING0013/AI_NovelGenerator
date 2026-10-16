"""应用默认文件路径；旧路径只由启动迁移读取。"""
from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 测试和显式独立实例可指定数据根；普通启动始终使用项目 user_data。
USER_DATA_DIR = Path(os.environ.get("NOVEL_GENERATOR_USER_DATA_DIR") or PROJECT_ROOT / "user_data").absolute()
CONFIG_DIR = USER_DATA_DIR / "config"
TASK_FLOWS_DIR = USER_DATA_DIR / "task_flows"
STATIC_DIR = USER_DATA_DIR / "static"
COVERS_DIR = STATIC_DIR / "covers"
LOGS_DIR = USER_DATA_DIR / "logs"
EXPORTS_DIR = USER_DATA_DIR / "exports"
BACKUPS_DIR = USER_DATA_DIR / "backups"
