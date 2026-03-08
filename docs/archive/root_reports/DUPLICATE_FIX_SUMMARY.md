# 🔧 Novel_directory.txt 重复章节问题修复总结

## 问题描述

用户报告：`Novel_directory.txt` 仍然存在格式混乱和重复章节的问题。

## 根本原因分析

### 问题1：去重函数执行时机不当
- **现象**：`_format_cleanup`去重函数存在，但只在**所有批次完成后**才执行（第1130行）
- **影响**：如果生成过程被中断，重复章节会残留在文件中
- **发现**：实际生成了110个章节，但只有105个唯一章节，存在5组重复

### 问题2：正则表达式匹配不准确
- **现象**：原正则`r'(第\s*(\d+)\s*章\s*[-–—]\s*[^\n]+\n[\s\S]*?)(?=第\s*\d+\s*章\s*[-–—]|\Z)'`会匹配章节内容中的"第X章"引用
- **影响**：导致去重不准确，误将内容引用当作章节标题
- **发现**：清理后文件仍有480个"章节标题"，但实际上只有105个章节

### 问题3：批次生成后未立即去重
- **现象**：每个批次生成后直接追加到文件（第1085-1087行）
- **影响**：如果LLM在同一批次或跨批次生成了重复章节，会累积在文件中
- **发现**：第1章、第2章、第17章、第27章、第42章、第87章各有2个版本

## 修复措施

### 修复1：每个批次生成后立即去重
**位置**：`novel_generator/blueprint.py:1089-1096`

```python
# 🆕 立即执行去重，防止累积重复
try:
    self._format_cleanup(filepath)
    # 重新读取去重后的内容
    final_blueprint = read_file(filename_dir).strip()
    logging.info(f"🧹 第{batch_count}批已去重")
except Exception as cleanup_e:
    logging.warning(f"⚠️ 批次去重异常（不影响继续生成）: {cleanup_e}")
```

**效果**：确保每个批次生成后立即去重，而不是等到所有批次完成后

### 修复2：改进去重正则表达式
**位置**：`novel_generator/blueprint.py:800`

**修复前**：
```python
chapter_pattern = r'(第\s*(\d+)\s*章\s*[-–—]\s*[^\n]+\n[\s\S]*?)(?=第\s*\d+\s*章\s*[-–—]|\Z)'
matches = list(re.finditer(chapter_pattern, content))
```

**修复后**：
```python
# 🆕 改进的正则：只匹配行首的章节标题，避免匹配内容中的引用
# 使用多行模式，^匹配行首
chapter_pattern = r'(?:^|\n)(第\s*(\d+)\s*章[^\n]*?\n(?:[\s\S]*?))(?=\n第\s*\d+\s*章[^\n]*?\n|\Z)'
matches = list(re.finditer(chapter_pattern, content, re.MULTILINE))
```

**改进点**：
1. 添加`(?:^|\n)`确保只匹配行首
2. 使用`re.MULTILINE`模式
3. 移除对破折号`[-–—]`的强制要求，支持更多格式
4. 前瞻模式改为匹配`\n第`而不是直接`第`，更精确

### 修复3：手动清理现有重复
**操作**：运行`test_dedup.py`清理现有文件
**结果**：
- 原始：110个章节（5组重复）
- 清理后：105个唯一章节
- 备份：`wxhyj/Novel_directory.txt.backup_20260104_HHMMSS`

## 验证结果

```
============================================================
📊 Novel_directory.txt 验证报告
============================================================
总章节数: 105
唯一章节: 105
章节范围: 第1章 - 第105章
重复章节: 0个

✅ 无重复章节！
✅ 格式正确：所有章节都使用「第X章」格式（无空格）
============================================================
```

## 发现的重复章节详情

| 章节 | 版本1长度 | 版本2长度 | 保留版本 | 原因分析 |
|------|-----------|-----------|----------|----------|
| 第1章 | 1792字符 | 3508字符 | 版本2 | 旧版本（炼尸炉版）vs 新版本（乱葬岗版） |
| 第2章 | 1162字符 | 2883字符 | 版本2 | 旧版本（妖女）vs 新版本（赵四） |
| 第17章 | 1896字符 | 1476字符 | 版本1 | 内容更完整 |
| 第27章 | 2761字符 | 4087字符 | 版本2 | 内容更完整 |
| 第42章 | 3298字符 | 1368字符 | 版本1 | 内容更完整 |
| 第87章 | 920字符 | 3392字符 | 版本2 | 内容更完整 |

## 技术要点

### 正则表达式说明
```regex
(?:^|\n)              # 匹配行首或换行后
(                     # 开始捕获组
  第\s*(\d+)\s*章      # 匹配"第X章"，允许空格
  [^\n]*?\n            # 匹配标题和换行
  (?:[\s\S]*?)         # 非贪婪匹配所有内容（包括换行）
)                     # 结束捕获组
(?=                   # 正向前瞻
  \n第\s*\d+\s*章[^\n]*?\n  # 下一个章节标题
  |                   # 或
  \Z                  # 文件结尾
)
```

### 去重逻辑
```python
chapters_dict = {}
for match in matches:
    chapter_num = int(match.group(2))
    chapter_content = match.group(1).strip()
    # 保留内容更长的版本（通常是更完整的版本）
    if chapter_num not in chapters_dict or len(chapter_content) > len(chapters_dict[chapter_num]):
        chapters_dict[chapter_num] = chapter_content
```

## 文件变更记录

### 修改的文件
1. `novel_generator/blueprint.py`
   - 第800行：改进去重正则表达式
   - 第1089-1096行：添加批次后立即去重逻辑

### 创建的文件
1. `test_dedup.py` - 去重测试脚本
2. `wxhyj/Novel_directory.txt.backup_*` - 原文件备份
3. `DUPLICATE_FIX_SUMMARY.md` - 本修复总结文档

### 清理的文件
- `wxhyj/Novel_directory.txt` - 从110个章节清理到105个唯一章节

## 后续建议

### 1. 继续生成时
- 每个批次生成后会自动去重
- 如果发现重复，会保留内容更长的版本
- 日志中会显示"🧹 第X批已去重"

### 2. 验证生成结果
- 可以运行`python test_dedup.py`检查是否有重复
- 查看日志中的"去重后章节数"信息

### 3. 如果仍然出现重复
- 检查LLM是否在单次生成中就产生了重复
- 查看对应批次的LLM对话日志
- 检查prompt是否被正确执行

## 关键代码位置

| 功能 | 文件 | 行号 |
|------|------|------|
| 批次后立即去重 | blueprint.py | 1089-1096 |
| 去重正则表达式 | blueprint.py | 800 |
| 去重函数定义 | blueprint.py | 782-829 |
| 最终去重调用 | blueprint.py | 1130 |

## 测试验证

### 测试脚本
```bash
# 运行去重测试
python test_dedup.py

# 验证当前文件
python -c "
import re
with open('wxhyj/Novel_directory.txt', 'r', encoding='utf-8') as f:
    content = f.read()
pattern = r'(?:^|\n)第\s*(\d+)\s*章'
chapters = re.findall(pattern, content, re.MULTILINE)
print(f'总章节: {len(chapters)}, 唯一: {len(set(chapters))}')
"
```

---

**修复时间**：2026-01-04
**修复版本**：blueprint.py (修改时间 16:53, 18:30)
**状态**：✅ 已完成并验证
