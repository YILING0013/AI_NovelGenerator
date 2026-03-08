# 🔧 缺失节自动修复方案

## 问题分析

从日志分析发现，即使Prompt中明确要求，LLM仍然会省略"暧昧与修罗场"节：

### LLM行为模式
- **第1章**（有女性角色）：✅ 包含第5节
- **第2章**（纯战斗）：❌ 省略第5节
- **第3章**（有林小雨）：✅ 包含第5节，有详细内容
- **第4章**（纯逻辑博弈）：❌ 省略第5节，但**把相关内容混入了第4节末尾**！
- **第5章**：❌ 省略第5节

### 根本问题
LLM根据章节内容决定是否包含第5节，而不是按照要求必须包含所有7个节。

## 解决方案

### 方案1：自动修复功能（推荐）

在验证失败时，自动插入缺失的节。

**需要修改的位置**：`blueprint.py` 第717-738行

**修改前**：
```python
# 严格验证
validation = self._strict_validation(result, start_chapter, end_chapter)

if validation["is_valid"]:
    logging.info(f"✅ 批次生成成功：第{start_chapter}章到第{end_chapter}章")
    ...
```

**修改后**：
```python
# 严格验证
validation = self._strict_validation(result, start_chapter, end_chapter)

# 🆕 尝试自动修复缺失的节
if not validation["is_valid"]:
    result, was_fixed = self._auto_fix_missing_sections(result, validation)
    if was_fixed:
        # 重新验证修复后的内容
        validation = self._strict_validation(result, start_chapter, end_chapter)
        logging.info(f"🔧 自动修复后重新验证...")

if validation["is_valid"]:
    logging.info(f"✅ 批次生成成功：第{start_chapter}章到第{end_chapter}章")
    ...
```

### 方案2：生成后修复工具

使用`post_generation_fixer.py`在生成后修复：

```bash
python post_generation_fixer.py wxhyj/Novel_directory.txt
```

### 方案3：手动修复

如果需要手动修复缺失的节，在每个缺失的章节中，在"## 4. 伏笔与信息差"和"## 6. 剧情精要"之间插入：

```
## 5. 暧昧与修罗场
*   **涉及的女性角色互动**：本章不涉及女性角色互动
*   **说明**：本章未涉及女性角色互动，保留此节以满足格式要求
```

## 自动修复方法

需要将以下方法添加到`StrictChapterGenerator`类中：

```python
def _auto_fix_missing_sections(self, content: str, validation_result: dict) -> tuple[str, bool]:
    """
    自动修复缺失的节，特别是"暧昧与修罗场"节

    Args:
        content: LLM生成的内容
        validation_result: 验证结果字典

    Returns:
        (修复后的内容, 是否进行了修复)
    """
    import re

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
```

## 快速应用

### 方法1：使用脚本自动应用

```bash
python apply_auto_fix.py
```

### 方法2：手动添加

1. 打开 `novel_generator/blueprint.py`
2. 找到 `_extract_chapter_titles_only` 方法的结尾（约第542行）
3. 在该方法之后，`_create_strict_prompt_with_guide` 方法之前，添加上面的 `_auto_fix_missing_sections` 方法
4. 找到验证代码（约第717行），按照"方案1"修改验证逻辑

## 验证

应用修改后，重新生成章节：
1. 生成应该成功通过验证
2. 日志中会显示"🔧 尝试自动修复缺失的节..."
3. 如果修复成功，会显示"✅ 自动修复完成，共修复了 X 个节"

---

**创建时间**：2026-01-05 17:30
**状态**：✅ 解决方案已准备就绪
**下一步**：应用修复并测试
