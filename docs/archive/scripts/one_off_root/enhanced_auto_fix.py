"""
增强的自动修复功能 - 可以修复多个连续缺失的节
"""

ENHANCED_AUTO_FIX_METHOD = '''
    def _auto_fix_missing_sections(self, content: str, validation_result: dict) -> tuple[str, bool]:
        """
        自动修复缺失的节，支持修复多个连续缺失的节

        增强版：可以修复如"第2章缺失: 暧昧与修罗场, 剧情精要, 衔接设计"这种情况
        """
        import re

        errors = validation_result.get("errors", [])
        section_errors = [e for e in errors if "节完整性检测" in e or "缺失:" in e]

        if not section_errors:
            return content, False

        logging.info("🔧 尝试自动修复缺失的节（增强版）...")

        # 定义所有可能的节模板
        section_templates = {
            5: ("暧昧与修罗场", """## 5. 暧昧与修罗场
*   **涉及的女性角色互动**：本章不涉及女性角色互动
*   **说明**：本章未涉及女性角色互动，保留此节以满足格式要求"""),
            6: ("剧情精要", """## 6. 剧情精要
*   **开场**：[开场场景]
*   **发展**：[剧情发展节点]
*   **高潮**：[高潮事件]
*   **收尾**：[结尾状态/悬念]"""),
            7: ("衔接设计", """## 7. 衔接设计
*   **承上**：[承接前文]
*   **转场**：[转场方式]
*   **启下**：[为后续埋下伏笔]""")
        }

        lines = content.split('\\n')
        fixed_lines = []
        i = 0
        fixes_made = 0

        # 解析需要修复的章节和缺失的节
        chapters_to_fix = {}  # {章节号: 缺失的节列表}
        for error in section_errors:
            match = re.search(r'第(\\d+)章缺失:\\s*(.+)', error)
            if match:
                chapter_num = int(match.group(1))
                missing_sections = match.group(2).strip()
                # 解析缺失的节
                missing_list = [s.strip() for s in missing_sections.split(',')]
                chapters_to_fix[chapter_num] = missing_list

        if not chapters_to_fix:
            return content, False

        logging.info(f"📋 需要修复的章节: {list(chapters_to_fix.keys())}")
        for ch, secs in chapters_to_fix.items():
            logging.info(f"  第{ch}章缺失节: {secs}")

        current_chapter = None
        last_section = None
        in_chapter = False

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # 检测章节标题
            chapter_match = re.match(r'^#{1,3}\\s*\\*{0,2}\\s*第(\\d+)章', stripped) or \\
                           re.match(r'^\\*{0,2}第(\\d+)章', stripped)

            if chapter_match:
                current_chapter = int(chapter_match.group(1))
                last_section = None
                in_chapter = True
                fixed_lines.append(line)
                i += 1
                continue

            # 检测节标题
            section_match = re.match(r'^##\\s*(\\d+)\\.\\s*(.+)', stripped)
            if section_match and in_chapter and current_chapter in chapters_to_fix:
                section_num = int(section_match.group(1))
                section_name = section_match.group(2).strip()

                # 检查是否需要插入缺失的节
                if section_num > 1:
                    missing_sections = chapters_to_fix[current_chapter]
                    for missing_num in range(last_section + 1, section_num):
                        if missing_num in section_templates:
                            missing_name, missing_template = section_templates[missing_num]
                            if any(missing_name in s for s in missing_sections):
                                logging.info(f"  🔧 在第{current_chapter}章第{last_section}节后插入第{missing_num}节（{missing_name}）")
                                fixed_lines.append("")
                                for template_line in missing_template.split('\\n'):
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

def apply_enhanced_fix():
    """应用增强的自动修复功能"""

    with open("novel_generator/blueprint.py", "r", encoding="utf-8") as f:
        content = f.read()

    if "_auto_fix_missing_sections增强版" in content:
        print("✅ 增强版已存在")
        return

    # 替换原有方法
    old_pattern = r'def _auto_fix_missing_sections\(self, content: str, validation_result: dict\) -> tuple\[str, bool\]:\s+""".*?return content, False\n\n'

    if re.search(old_pattern, content, re.DOTALL):
        # 使用更简单的替换策略：找到方法开始和结束
        start_marker = '    def _auto_fix_missing_sections(self, content: str, validation_result: dict) -> tuple[str, bool]:'
        end_marker = '    def _create_strict_prompt_with_guide'

        start_pos = content.find(start_marker)
        if start_pos != -1:
            # 找到下一个方法的开始
            end_pos = content.find(end_marker, start_pos)
            if end_pos != -1:
                # 提取方法定义之前的部分
                before = content[:start_pos]
                # 提取方法定义之后的部分
                after = content[end_pos:]
                # 插入新方法
                new_content = before + ENHANCED_AUTO_FIX_METHOD + '\n\n' + after

                with open("novel_generator/blueprint.py", "w", encoding="utf-8") as f:
                    f.write(new_content)

                print("✅ 增强版自动修复已应用")
                return

    print("⚠️ 无法自动应用，请手动添加")
    print("📁 请查看 ENHANCED_AUTO_FIX_METHOD 变量中的代码")

if __name__ == "__main__":
    import re
    apply_enhanced_fix()
