#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一字数标准 - 修复批量生成中的字数统计和自动扩写逻辑
"""

import os
import re

def create_wordcount_utils():
    """创建统一的字数统计工具函数"""

    print("🧠 Ultra-Think 统一字数标准方案")
    print("=" * 60)

    print("📋 问题分析:")
    print("1. 文件包含行号前缀 (如 '1→', '123→')")
    print("2. 统计方式不统一，导致用户困惑")
    print("3. 自动扩写逻辑基于错误的字数统计")
    print("4. 所有章节实际都少于5000中文字符")

    print("\n🛠️ 解决方案:")

    # 生成新的字数统计函数
    utils_code = '''# novel_generator/wordcount_utils.py
# -*- coding: utf-8 -*-
"""
统一的字数统计工具
"""

import re

def count_chapter_words(text_or_path, count_type='chinese'):
    """
    统计章节字数的标准函数

    Args:
        text_or_path: 文本内容或文件路径
        count_type: 统计类型
            - 'chinese': 仅统计中文字符（推荐）
            - 'all': 统计所有字符（不含行号）
            - 'file': 文件大小（字节）

    Returns:
        dict: 包含各种统计结果
    """

    # 如果是文件路径，读取内容
    if isinstance(text_or_path, str) and os.path.exists(text_or_path):
        with open(text_or_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = text_or_path

    # 去除行号前缀
    lines = content.split('\\n')
    clean_lines = []
    for line in lines:
        clean_line = re.sub(r'^\\s*\\d+→\\s*', '', line)
        clean_lines.append(clean_line)

    clean_text = '\\n'.join(clean_lines).strip()

    # 统计各种字数
    chinese_chars = len(re.findall(r'[\\u4e00-\\u9fff]', clean_text))
    all_chars = len(clean_text.replace('\\n', ''))

    # 如果是文件路径，获取文件大小
    file_size = 0
    if isinstance(text_or_path, str) and os.path.exists(text_or_path):
        file_size = os.path.getsize(text_or_path)

    return {
        'chinese_chars': chinese_chars,      # 中文字符数（推荐标准）
        'all_chars': all_chars,             # 所有字符数
        'file_size': file_size,             # 文件大小
        'lines_count': len(clean_lines),     # 行数
        'clean_text': clean_text             # 清理后的文本
    }

def should_auto_enrich(content_or_path, target_words, min_words, auto_enrich_enabled):
    """
    判断是否应该触发自动扩写

    Args:
        content_or_path: 章节内容或文件路径
        target_words: 期望字数
        min_words: 最低字数
        auto_enrich_enabled: 是否启用自动扩写

    Returns:
        dict: 判断结果和建议
    """

    if not auto_enrich_enabled:
        return {
            'should_enrich': False,
            'reason': '自动扩写未启用',
            'current_words': 0,
            'target_ratio': 0
        }

    stats = count_chapter_words(content_or_path)
    current_words = stats['chinese_chars']

    # 基于中文字符数的智能扩写逻辑
    target_threshold = 0.8 * target_words  # 期望字数的80%
    min_threshold = 0.7 * min_words       # 最低字数的70%

    should_enrich = False
    reason = ""

    if current_words < min_threshold:
        should_enrich = True
        reason = f"字数({current_words})低于最低字数({min_words})的70%"
    elif current_words < target_threshold:
        should_enrich = True
        reason = f"字数({current_words})低于期望字数({target_words})的80%"
    else:
        reason = f"字数({current_words})符合要求"

    target_ratio = current_words / target_words if target_words > 0 else 0

    return {
        'should_enrich': should_enrich,
        'reason': reason,
        'current_words': current_words,
        'target_words': target_words,
        'target_ratio': target_ratio,
        'stats': stats
    }
'''

    print("1. 创建新的字数统计工具:")
    print("   novel_generator/wordcount_utils.py")
    print("   统一使用中文字符数作为标准")

    print("\n2. 修复批量生成逻辑:")
    batch_fix_code = '''# 在 ui/generation_handlers.py 中的修改
from novel_generator.wordcount_utils import should_auto_enrich

# 替换原有的扩写逻辑
enrichment_check = should_auto_enrich(
    content_or_path=chapter_path,  # 或者使用 draft_text
    target_words=word,
    min_words=min,
    auto_enrich_enabled=auto_enrich
)

if enrichment_check['should_enrich']:
    self.safe_log(f"第{i}章{enrichment_check['reason']}，正在扩写...")
    self.safe_log(f"当前字数: {enrichment_check['current_words']}, 目标: {enrichment_check['target_words']}")

    enriched = enrich_chapter_text(
        chapter_text=draft_text,
        word_number=word,
        # ... 其他参数
    )
    draft_text = enriched
else:
    self.safe_log(f"第{i}章{enrichment_check['reason']}，无需扩写")
'''

    print("3. 改进UI显示:")
    ui_improvement = '''# 在UI中显示更详细的字数信息
def show_chapter_in_textbox(self, content):
    """显示章节内容并添加字数统计"""
    from novel_generator.wordcount_utils import count_chapter_words

    stats = count_chapter_words(content)

    # 在文本框上方添加字数信息
    word_info = f"当前章节: {stats['chinese_chars']}中文字符 (总计{stats['all_chars']}字符)"
    self.word_count_label.configure(text=word_info)

    # 显示内容
    self.chapter_text.delete("1.0", "end")
    self.chapter_text.insert("1.0", content)
'''

    print("\n💡 实施建议:")
    print("1. 立即实施: 创建字数统计工具，修复扩写逻辑")
    print("2. 用户教育: 明确说明字数标准（中文字符数）")
    print("3. UI改进: 显示详细的字数统计信息")
    print("4. 测试验证: 确保自动扩写功能正常工作")

    print("\n🎯 修复后的预期效果:")
    print("✅ 统一使用中文字符数作为标准")
    print("✅ 自动扩写基于正确的字数统计触发")
    print("✅ 用户看到清晰的字数信息")
    print("✅ 第18章(2871字)在设置期望5000字时会触发扩写")

    # 保存工具文件
    utils_file = r"C:\Users\tcui\Documents\GitHub\AI_NovelGenerator\novel_generator\wordcount_utils.py"

    print(f"\n📝 是否创建统一的字数统计工具文件?")
    print(f"   保存位置: {utils_file}")

    return utils_code, batch_fix_code, ui_improvement

if __name__ == "__main__":
    utils_code, batch_fix, ui_improvement = create_wordcount_utils()

    print(f"\n" + "="*60)
    print(f"🔧 代码已准备完成，可以开始实施修复!")