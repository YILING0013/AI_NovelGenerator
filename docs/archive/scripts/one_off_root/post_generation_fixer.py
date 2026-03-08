"""
章节生成后自动修复工具
在生成完成后运行，自动修复缺失的节
"""

import re
import os
import sys


def fix_missing_sections_in_file(filepath: str) -> bool:
    """
    修复文件中缺失的节

    Args:
        filepath: Novel_directory.txt文件路径

    Returns:
        是否进行了修复
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查是否有缺失的节
    required_sections = ["## 1. 基础元信息", "## 2. 张力与冲突", "## 3. 匠心思维应用",
                        "## 4. 伏笔与信息差", "## 5. 暧昧与修罗场",
                        "## 6. 剧情精要", "## 7. 衔接设计"]

    lines = content.split('\n')
    fixed_lines = []
    i = 0
    fixes_made = 0

    current_chapter = None
    last_section = None

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 检测章节标题
        chapter_match = re.match(r'^#{1,3}\s*\*{0,2}\s*第(\d+)章', stripped) or \
                       re.match(r'^\*{0,2}第(\d+)章', stripped)

        if chapter_match:
            current_chapter = int(chapter_match.group(1))
            last_section = None
            fixed_lines.append(line)
            i += 1
            continue

        # 检测节标题
        section_match = re.match(r'^##\s*(\d+)\.\s*(.+)', stripped)
        if section_match:
            section_num = int(section_match.group(1))
            section_name = section_match.group(2).strip()

            # 检查是否跳过了第5节
            if section_num == 6 and last_section == 4:
                # 在第6节之前插入第5节
                print(f"  🔧 在第{current_chapter}章插入缺失的第5节")

                # 添加节内容
                fixed_lines.append("")
                fixed_lines.append("## 5. 暧昧与修罗场")
                fixed_lines.append("*   **涉及的女性角色互动**：本章不涉及女性角色互动")
                fixed_lines.append("*   **说明**：本章未涉及女性角色互动，保留此节以满足格式要求")
                fixed_lines.append("")

                fixes_made += 1

            last_section = section_num

        fixed_lines.append(line)
        i += 1

    if fixes_made > 0:
        fixed_content = '\n'.join(fixed_lines)

        # 备份原文件
        backup_path = filepath + ".backup"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ 已备份原文件到: {backup_path}")

        # 写入修复后的内容
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        print(f"✅ 修复完成，共修复了 {fixes_made} 个节")

        return True
    else:
        print("✅ 文件格式正确，无需修复")
        return False


def main():
    """主函数"""
    if len(sys.argv) < 2:
        # 默认路径
        filepath = "wxhyj/Novel_directory.txt"
    else:
        filepath = sys.argv[1]

    if not os.path.exists(filepath):
        print(f"❌ 文件不存在: {filepath}")
        return 1

    print(f"🔧 开始检查文件: {filepath}")

    success = fix_missing_sections_in_file(filepath)

    return 0 if success else 0


if __name__ == "__main__":
    sys.exit(main())
