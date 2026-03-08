#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
临时文件和调试代码清理工具

这个脚本用于分析和清理项目中的临时文件、调试代码和冗余文件。
它会安全地评估每个文件，并将有用的文件重新组织到合适的目录中。

使用方法:
python cleanup_temp_files.py

操作模式:
1. dry_run: 仅分析，不删除任何文件
2. safe_cleanup: 安全清理，只删除明确无用的文件
3. full_cleanup: 完整清理（需要确认）
"""

import os
import shutil
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Set
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cleanup.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class TempFileCleaner:
    """临时文件清理器"""

    def __init__(self, project_root: str):
        """
        初始化清理器

        Args:
            project_root: 项目根目录
        """
        self.project_root = Path(project_root)
        self.analysis_results = {
            'debug_files': [],
            'fix_files': [],
            'test_files': [],
            'backup_files': [],
            'temp_files': [],
            'redundant_files': []
        }

        # 文件分类规则
        self.file_patterns = {
            'debug_files': [
                r'^debug_.*\.py$',
                r'^test_debug.*\.py$'
            ],
            'fix_files': [
                r'^fix_.*\.py$',
                r'^repair_.*\.py$',
                r'^patch_.*\.py$'
            ],
            'test_files': [
                r'^test_.*\.py$',
                r'^spec_.*\.py$'
            ],
            'backup_files': [
                r'.*\.backup_.*',
                r'.*\.bak$',
                r'.*\.old$'
            ],
            'temp_files': [
                r'^temp_.*\.py$',
                r'^tmp_.*\.py$',
                r'.*\.tmp$',
                r'^quick_.*\.py$'
            ],
            'redundant_files': [
                r'.*_v\d+\.py$',
                r'.*_copy.*\.py$',
                r'.*_duplicate.*\.py$'
            ]
        }

        # 保留文件（不删除）
        self.keep_files = {
            'test_single_chapter.py',  # 重要的功能测试
            'test_auto_consistency.py',  # 一致性测试
            'test_blueprint_fix.py',  # 蓝图修复测试
            'main.py',  # 主程序
            'requirements.txt',  # 依赖文件
            'README.md',  # 说明文档
            'CLAUDE.md'  # 项目文档
        }

        # 有用的修复工具（保留但移动到utils目录）
        self.useful_fixes = {
            'fix_vector_dimension.py'  # 向量维度修复工具
        }

    def analyze_files(self) -> Dict[str, List[Path]]:
        """分析项目中的临时文件"""
        logger.info("开始分析项目文件...")

        all_files = list(self.project_root.rglob("*.py"))
        all_files.extend(list(self.project_root.rglob("*.txt")))
        all_files.extend(list(self.project_root.rglob("*.md")))

        for file_path in all_files:
            if self._should_ignore_file(file_path):
                continue

            file_category = self._categorize_file(file_path)
            if file_category:
                self.analysis_results[file_category].append(file_path)

        # 打印分析结果
        self._print_analysis_results()

        return self.analysis_results

    def _should_ignore_file(self, file_path: Path) -> bool:
        """判断是否应该忽略文件"""
        # 忽略的目录
        ignore_dirs = {'.git', '__pycache__', 'node_modules', '.idea', '.vscode', 'venv', 'env'}
        if any(ignore_dir in file_path.parts for ignore_dir in ignore_dirs):
            return True

        # 忽略的文件
        file_name = file_path.name
        if file_name in self.keep_files or file_name.startswith('.'):
            return True

        # 忽略子目录中的文件（只处理根目录级别的临时文件）
        if file_path.parent != self.project_root and not any(parent.name == 'test_novel' for parent in file_path.parents):
            return True

        return False

    def _categorize_file(self, file_path: Path) -> str:
        """对文件进行分类"""
        import re

        file_name = file_path.name

        for category, patterns in self.file_patterns.items():
            for pattern in patterns:
                if re.match(pattern, file_name, re.IGNORECASE):
                    return category

        return ''

    def _print_analysis_results(self) -> None:
        """打印分析结果"""
        print("\n📊 文件分析结果:")
        print("=" * 50)

        total_files = 0
        for category, files in self.analysis_results.items():
            count = len(files)
            total_files += count

            if count > 0:
                category_name = {
                    'debug_files': '调试文件',
                    'fix_files': '修复工具',
                    'test_files': '测试文件',
                    'backup_files': '备份文件',
                    'temp_files': '临时文件',
                    'redundant_files': '冗余文件'
                }.get(category, category)

                print(f"📁 {category_name}: {count}个文件")
                for file_path in files[:5]:  # 只显示前5个
                    print(f"   - {file_path.name}")
                if count > 5:
                    print(f"   ... 还有{count-5}个文件")
                print()

        print(f"📈 总计: {total_files}个临时/调试文件")

    def dry_run(self) -> None:
        """试运行模式，仅分析不删除"""
        logger.info("🔍 试运行模式 - 仅分析，不删除任何文件")

        self.analyze_files()

        # 生成清理建议
        self._generate_cleanup_suggestions()

    def _generate_cleanup_suggestions(self) -> None:
        """生成清理建议"""
        print("\n💡 清理建议:")
        print("=" * 50)

        suggestions = []

        # 分析各类文件的处理建议
        for category, files in self.analysis_results.items():
            if not files:
                continue

            if category == 'debug_files':
                suggestions.append(("调试文件", "建议删除大部分，保留可能有用的调试工具", "delete_most"))
            elif category == 'fix_files':
                useful_fixes = [f for f in files if f.name in self.useful_fixes]
                other_fixes = [f for f in files if f.name not in self.useful_fixes]
                if useful_fixes:
                    suggestions.append(("有用的修复工具", f"移动到utils目录: {', '.join([f.name for f in useful_fixes])}", "move_to_utils"))
                if other_fixes:
                    suggestions.append(("其他修复文件", f"建议删除: {', '.join([f.name for f in other_fixes])}", "delete"))
            elif category == 'test_files':
                important_tests = [f for f in files if f.name in self.keep_files]
                other_tests = [f for f in files if f.name not in self.keep_files]
                if other_tests:
                    suggestions.append(("测试文件", f"保留重要测试，删除临时测试: {', '.join([f.name for f in other_tests])}", "delete_most"))
            elif category == 'backup_files':
                suggestions.append(("备份文件", "如果不再需要可以删除", "delete_if_old"))
            elif category == 'temp_files':
                suggestions.append(("临时文件", "建议全部删除", "delete_all"))
            elif category == 'redundant_files':
                suggestions.append(("冗余文件", "建议删除重复版本", "delete"))

        for i, (title, description, action) in enumerate(suggestions, 1):
            action_emoji = {
                "delete_all": "🗑️",
                "delete_most": "🗑️",
                "delete": "🗑️",
                "delete_if_old": "⚠️",
                "move_to_utils": "📁"
            }.get(action, "❓")

            print(f"{i}. {action_emoji} {title}")
            print(f"   {description}")
            print()

    def safe_cleanup(self) -> None:
        """安全清理模式"""
        logger.info("🧹 安全清理模式 - 只删除明确无用的文件")

        # 创建备份目录
        backup_dir = self.project_root / "cleanup_backup" / datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"📦 备份目录: {backup_dir}")

        moved_files = []
        deleted_files = []

        # 处理临时文件（明确删除）
        for file_path in self.analysis_results['temp_files']:
            try:
                # 先移动到备份目录
                backup_path = backup_dir / file_path.name
                shutil.move(str(file_path), str(backup_path))
                deleted_files.append(file_path.name)
                logger.info(f"🗑️ 删除临时文件: {file_path.name}")
            except Exception as e:
                logger.error(f"删除文件失败 {file_path}: {e}")

        # 处理冗余文件
        for file_path in self.analysis_results['redundant_files']:
            try:
                backup_path = backup_dir / file_path.name
                shutil.move(str(file_path), str(backup_path))
                deleted_files.append(file_path.name)
                logger.info(f"🗑️ 删除冗余文件: {file_path.name}")
            except Exception as e:
                logger.error(f"删除文件失败 {file_path}: {e}")

        # 处理调试文件（保留有用的）
        utils_dir = self.project_root / "utils"
        utils_dir.mkdir(exist_ok=True)

        for file_path in self.analysis_results['debug_files']:
            if file_path.name in ['debug_blueprint.py', 'debug_regex.py']:  # 保留有用的调试文件
                try:
                    backup_path = backup_dir / file_path.name
                    shutil.move(str(file_path), str(backup_path))
                    deleted_files.append(file_path.name)
                    logger.info(f"🗑️ 删除调试文件: {file_path.name}")
                except Exception as e:
                    logger.error(f"删除文件失败 {file_path}: {e}")

        # 移动有用的修复工具到utils目录
        for file_path in self.analysis_results['fix_files']:
            if file_path.name in self.useful_fixes:
                try:
                    new_path = utils_dir / file_path.name
                    shutil.move(str(file_path), str(new_path))
                    moved_files.append(file_path.name)
                    logger.info(f"📁 移动修复工具到utils: {file_path.name}")
                except Exception as e:
                    logger.error(f"移动文件失败 {file_path}: {e}")
            else:
                try:
                    backup_path = backup_dir / file_path.name
                    shutil.move(str(file_path), str(backup_path))
                    deleted_files.append(file_path.name)
                    logger.info(f"🗑️ 删除修复文件: {file_path.name}")
                except Exception as e:
                    logger.error(f"删除文件失败 {file_path}: {e}")

        # 生成清理报告
        self._generate_cleanup_report(backup_dir, moved_files, deleted_files)

    def _generate_cleanup_report(self, backup_dir: Path, moved_files: List[str], deleted_files: List[str]) -> None:
        """生成清理报告"""
        report = {
            'cleanup_time': datetime.now().isoformat(),
            'backup_directory': str(backup_dir),
            'moved_files': moved_files,
            'deleted_files': deleted_files,
            'total_files_processed': len(moved_files) + len(deleted_files)
        }

        report_path = backup_dir / "cleanup_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n📋 清理完成!")
        print(f"📦 备份位置: {backup_dir}")
        print(f"📁 移动文件: {len(moved_files)}个")
        print(f"🗑️ 删除文件: {len(deleted_files)}个")
        print(f"📊 总计处理: {report['total_files_processed']}个文件")
        print(f"📄 详细报告: {report_path}")

    def create_cleanup_script(self) -> None:
        """创建可执行的清理脚本"""
        script_content = f'''#!/usr/bin/env python3
# 自动生成的清理脚本
# 生成时间: {datetime.now().isoformat()}

from cleanup_temp_files import TempFileCleaner
import sys

def main():
    project_root = r"{self.project_root}"
    cleaner = TempFileCleaner(project_root)

    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        print("⚠️  完整清理模式 - 将删除所有临时文件")
        response = input("确认继续? (y/N): ")
        if response.lower() == 'y':
            cleaner.safe_cleanup()
    else:
        print("🔍 试运行模式 - 仅分析文件")
        cleaner.dry_run()
        print("\\n要执行实际清理，请运行: python {__file__} --full")

if __name__ == "__main__":
    main()
'''

        script_path = self.project_root / "auto_cleanup.py"
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)

        # 设置执行权限
        os.chmod(script_path, 0o755)

        print(f"📝 清理脚本已创建: {script_path}")
        print("使用方法:")
        print("  python auto_cleanup.py          # 试运行")
        print("  python auto_cleanup.py --full    # 执行清理")

def main():
    """主函数"""
    import sys

    # 获取项目根目录
    if len(sys.argv) > 1:
        project_root = sys.argv[1]
    else:
        # 使用当前脚本所在目录作为项目根目录
        project_root = os.path.dirname(os.path.abspath(__file__))

    cleaner = TempFileCleaner(project_root)

    if len(sys.argv) > 2 and sys.argv[2] == "--cleanup":
        cleaner.safe_cleanup()
    else:
        cleaner.dry_run()
        cleaner.create_cleanup_script()

if __name__ == "__main__":
    main()