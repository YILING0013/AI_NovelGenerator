#!/usr/bin/env python3
# 自动生成的清理脚本
# 生成时间: 2025-11-09T00:49:24.227220

from cleanup_temp_files import TempFileCleaner
import sys

def main():
    project_root = r"C:\Users\tcui\Documents\GitHub\AI_NovelGenerator"
    cleaner = TempFileCleaner(project_root)

    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        print("⚠️  完整清理模式 - 将删除所有临时文件")
        response = input("确认继续? (y/N): ")
        if response.lower() == 'y':
            cleaner.safe_cleanup()
    else:
        print("🔍 试运行模式 - 仅分析文件")
        cleaner.dry_run()
        print(r"\n要执行实际清理，请运行: python scripts\auto_cleanup.py --full")

if __name__ == "__main__":
    main()
