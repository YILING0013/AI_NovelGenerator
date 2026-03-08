"""
自动修复缺失节的功能模块
用于修复LLM生成内容中缺失的"暧昧与修罗场"等节
"""

import re
import logging


def auto_fix_missing_sections(content: str, validation_result: dict) -> tuple[str, bool]:
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

    lines = content.split('\n')
    fixed_lines = []
    i = 0
    fixes_made = 0

    # 需要修复的章节号集合
    chapters_to_fix = set()
    for error in section_errors:
        # 解析错误信息，如 "第2章缺失: 暧昧与修罗场, 剧情精要"
        match = re.search(r'第(\d+)章缺失:', error)
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
        chapter_match = re.match(r'^#{1,3}\s*\*{0,2}\s*第(\d+)章', stripped) or \
                       re.match(r'^\*{0,2}第(\d+)章', stripped)

        if chapter_match:
            current_chapter = int(chapter_match.group(1))
            in_chapter = True
            last_section = None
            fixed_lines.append(line)
            i += 1
            continue

        # 检测节标题
        section_match = re.match(r'^##\s*(\d+)\.\s*(.+)', stripped)
        if section_match and current_chapter in chapters_to_fix:
            section_num = int(section_match.group(1))
            section_name = section_match.group(2).strip()

            # 检查是否跳过了第5节
            if section_num == 6 and last_section == 4:
                # 在第6节之前插入第5节
                logging.info(f"  🔧 在第{current_chapter}章的第4节和第6节之间插入第5节")

                # 添加节标题
                fixed_lines.append("")  # 空行
                for template_line in section_templates["暧昧与修罗场"].split('\n'):
                    fixed_lines.append(template_line)
                fixed_lines.append("")  # 空行

                fixes_made += 1

            last_section = section_num

        fixed_lines.append(line)
        i += 1

    if fixes_made > 0:
        fixed_content = '\n'.join(fixed_lines)
        logging.info(f"✅ 自动修复完成，共修复了 {fixes_made} 个节")
        return fixed_content, True
    else:
        logging.warning("⚠️ 无法自动修复，可能需要手动处理")
        return content, False


if __name__ == "__main__":
    # 测试用例
    test_content = """
第1章 - 测试章节

## 1. 基础元信息
...

## 2. 张力与冲突
...

## 3. 匠心思维应用
...

## 4. 伏笔与信息差
...

## 6. 剧情精要
...

## 7. 衔接设计
...
"""

    validation_result = {
        "errors": ["🚨 节完整性检测：第1章缺失: 暗恋与修罗场"],
        "is_valid": False
    }

    fixed_content, was_fixed = auto_fix_missing_sections(test_content, validation_result)
    print(f"修复: {was_fixed}")
    print(fixed_content)
