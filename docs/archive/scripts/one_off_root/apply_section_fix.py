"""
应用缺失节自动修复功能到blueprint.py
"""
import re

def apply_fix():
    """应用自动修复功能"""

    blueprint_path = "novel_generator/blueprint.py"

    print(f"📖 读取文件: {blueprint_path}")
    with open(blueprint_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查是否已经添加过
    if '_auto_fix_missing_sections' in content:
        print("✅ 自动修复方法已存在，无需重复添加")
        return True

    # 要添加的方法
    new_method = '''
    def _auto_fix_missing_sections(self, content: str, validation_result: dict) -> tuple[str, bool]:
        """
        自动修复缺失的节，特别是"暧昧与修罗场"节

        Args:
            content: LLM生成的内容
            validation_result: 验证结果字典

        Returns:
            (修复后的内容, 是否进行了修复)
        """
        # 检查是否有节完整性错误
        errors = validation_result.get("errors", [])
        section_errors = [e for e in errors if "节完整性检测" in e or "缺失:" in e]

        if not section_errors:
            return content, False

        logging.info("🔧 尝试自动修复缺失的节...")

        # 定义要插入的标准节内容
        section_templates = {
            "暧昧与修罗场": """## 5. 暧昧与修罗场
*   **涉及的女性角色互动**：本章不涉及女性角色互动
*   **说明**：本章未涉及女性角色互动，保留此节以满足格式要求"""
        }

        lines = content.split('\\n')
        fixed_lines = []
        i = 0
        fixes_made = 0

        # 需要修复的章节号集合
        chapters_to_fix = set()
        for error in section_errors:
            # 解析错误信息，如 "第2章缺失: 暧昧与修罗场, 剧情精要"
            match = re.search(r'第(\\d+)章缺失:', error)
            if match:
                chapters_to_fix.add(int(match.group(1)))

        logging.info(f"📋 需要修复的章节: {sorted(chapters_to_fix)}")

        current_chapter = None
        in_chapter = False
        last_section = None

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # 检测章节标题
            chapter_match = re.match(r'^#{1,3}\\s*\\*{0,2}\\s*第(\\d+)章', stripped) or \\
                           re.match(r'^\\*{0,2}第(\\d+)章', stripped)

            if chapter_match:
                current_chapter = int(chapter_match.group(1))
                in_chapter = True
                last_section = None
                fixed_lines.append(line)
                i += 1
                continue

            # 检测节标题
            section_match = re.match(r'^##\\s*(\\d+)\\.\\s*(.+)', stripped)
            if section_match and current_chapter in chapters_to_fix:
                section_num = int(section_match.group(1))
                section_name = section_match.group(2).strip()

                # 检查是否跳过了第5节
                if section_num == 6 and last_section == 4:
                    # 在第6节之前插入第5节
                    logging.info(f"  🔧 在第{current_chapter}章的第4节和第6节之间插入第5节")

                    # 添加节标题
                    fixed_lines.append("")  # 空行
                    for template_line in section_templates["暧昧与修罗场"].split('\\n'):
                        fixed_lines.append(template_line)
                    fixed_lines.append("")  # 空行

                    fixes_made += 1

                last_section = section_num

            fixed_lines.append(line)
            i += 1

        if fixes_made > 0:
            fixed_content = '\\n'.join(fixed_lines)
            logging.info(f"✅ 自动修复完成，共修复了 {fixes_made} 个节")
            return fixed_content, True
        else:
            logging.warning("⚠️ 无法自动修复，可能需要手动处理")
            return content, False
'''

    # 在"return ""\n\n    def _create_strict_prompt_with_guide"之间插入
    pattern = r'(return ""\\n)(\\n    def _create_strict_prompt_with_guide)'

    if re.search(pattern, content):
        new_content = re.sub(pattern, r'\1' + new_method + r'\2', content)

        # 写回文件
        with open(blueprint_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        print("✅ 成功添加自动修复方法到blueprint.py")
        print("📝 已添加方法: _auto_fix_missing_sections")
        return True
    else:
        print("❌ 无法找到插入位置，请手动添加")
        print("📋 请在 _extract_chapter_titles_only 方法后添加新方法")
        return False

if __name__ == "__main__":
    apply_fix()
