"""
插入自动修复方法到blueprint.py
"""

# 要插入的方法代码
AUTO_FIX_METHOD = '''
    def _auto_fix_missing_sections(self, content: str, validation_result: dict) -> tuple[str, bool]:
        """
        自动修复缺失的节，特别是"暧昧与修罗场"节
        """
        import re

        errors = validation_result.get("errors", [])
        section_errors = [e for e in errors if "节完整性检测" in e or "缺失:" in e]

        if not section_errors:
            return content, False

        logging.info("🔧 尝试自动修复缺失的节...")

        section_templates = {
            "暧昧与修罗场": "## 5. 暧昧与修罗场\\n*   **涉及的女性角色互动**：本章不涉及女性角色互动\\n*   **说明**：本章未涉及女性角色互动，保留此节以满足格式要求"
        }

        lines = content.split('\\n')
        fixed_lines = []
        i = 0
        fixes_made = 0

        chapters_to_fix = set()
        for error in section_errors:
            match = re.search(r'第(\\d+)章缺失:', error)
            if match:
                chapters_to_fix.add(int(match.group(1)))

        logging.info(f"📋 需要修复的章节: {sorted(chapters_to_fix)}")

        current_chapter = None
        last_section = None

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            chapter_match = re.match(r'^#{1,3}\\s*\\*{0,2}\\s*第(\\d+)章', stripped) or re.match(r'^\\*{0,2}第(\\d+)章', stripped)

            if chapter_match:
                current_chapter = int(chapter_match.group(1))
                last_section = None
                fixed_lines.append(line)
                i += 1
                continue

            section_match = re.match(r'^##\\s*(\\d+)\\.\\s*(.+)', stripped)
            if section_match and current_chapter in chapters_to_fix:
                section_num = int(section_match.group(1))

                if section_num == 6 and last_section == 4:
                    logging.info(f"  🔧 在第{current_chapter}章插入第5节")
                    fixed_lines.append("")
                    for template_line in section_templates["暧昧与修罗场"].split('\\n'):
                        fixed_lines.append(template_line)
                    fixed_lines.append("")
                    fixes_made += 1

                last_section = section_num

            fixed_lines.append(line)
            i += 1

        if fixes_made > 0:
            fixed_content = '\\n'.join(fixed_lines)
            logging.info(f"✅ 自动修复完成，共修复了 {fixes_made} 个节")
            return fixed_content, True
        else:
            logging.warning("⚠️ 无法自动修复")
            return content, False
'''

def main():
    with open("novel_generator/blueprint.py", "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 检查是否已存在
    content = "".join(lines)
    if "_auto_fix_missing_sections" in content:
        print("✅ 方法已存在，无需添加")
        return

    # 在第543行（空行，在return ""之后，def _create_strict_prompt_with_guide之前）插入
    # 找到插入位置
    insert_index = None
    for i, line in enumerate(lines):
        if line.strip() == 'return ""':
            # 检查下一行是否是空行，再下一行是否是def _create_strict_prompt_with_guide
            if i + 2 < len(lines):
                if lines[i + 1].strip() == "" and "def _create_strict_prompt_with_guide" in lines[i + 2]:
                    insert_index = i + 1  # 在空行位置插入
                    break

    if insert_index is None:
        print("❌ 无法找到插入位置")
        return

    # 插入方法
    lines.insert(insert_index, AUTO_FIX_METHOD + "\n")

    # 写回文件
    with open("novel_generator/blueprint.py", "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"✅ 成功在第{insert_index + 1}行插入自动修复方法")
    print("📝 已添加方法: _auto_fix_missing_sections")

if __name__ == "__main__":
    main()
