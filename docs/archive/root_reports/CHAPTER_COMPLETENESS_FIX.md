# 🔧 章节混叠问题修复总结

## 用户反馈问题

**现象**：第1章内容里出现了第2章的标题，导致格式混乱。

**用户原话**："第一章里面为什么会有次层的第1-2章呢？这不乱了么"

## 问题示例

```
第1章 - 致命死局与系统觉醒

1. 基础元信息
章节序号：第1章
章节标题：致命死局与系统觉醒
张力评级：★★★★☆ (S级开局)
目标字数：3500字

## 1. 基础元信息          ← 突然又出现标题
章节序号：第2章             ← 第2章的元信息
章节标题：洞悉本源与首杀
...
```

**问题分析**：
1. 第1章内容只有几行，不完整
2. 第2章的标题过早出现（与第1章标题距离<100行）
3. 第1章内容被第2章打断

## 修复方案

### 改进章节标题检测

**位置**：`novel_generator/blueprint.py:213-229`

**修复前**（只检测行首）：
```python
chapter_match = re.match(r'^第\s*(\d+)\s*章', line)
if chapter_match:
    chapter_num = int(chapter_match.group(1))
```

**问题**：只能匹配行首的"第X章"，无法匹配"章节序号：第X章"这种格式。

**修复后**（支持多种格式）：
```python
chapter_patterns = [
    r'^第\s*(\d+)\s*章',                      # 行首：第X章
    r'章节[序号标题]*[:：]\s*第\s*(\d+)\s*章',  # "章节序号：第X章"
    r'\*\*章节\*\*[:：]\s*第\s*(\d+)\s*章',    # "**章节**: 第X章"
]

chapter_num = None
for pattern in chapter_patterns:
    match = re.search(pattern, line)
    if match:
        chapter_num = int(match.group(1))
        break
```

### 添加章节完整性检查

**位置**：`novel_generator/blueprint.py:236-259`

**新增逻辑**：
```python
# 检查章节完整性
incomplete_chapters = []
for chapter_num in expected_numbers:
    if chapter_num in chapter_sections:
        start_line, end_line, content_length = chapter_sections[chapter_num]

        # 检查1：内容长度是否足够（至少50行）
        if content_length < 50:
            incomplete_chapters.append(f"第{chapter_num}章（仅{content_length}行，不完整）")

        # 检查2：下一个章节是否过早出现
        if chapter_num < expected_end:
            next_chapter = chapter_num + 1
            if next_chapter in chapter_sections:
                next_start = chapter_sections[next_chapter][0]
                # 如果距离小于100行，认为是内容混叠
                if next_start - start_line < 100:
                    incomplete_chapters.append(
                        f"第{chapter_num}章内容被第{next_chapter}章中断（第{next_start}行过早出现）"
                    )

if incomplete_chapters:
    result["is_valid"] = False
    result["errors"].append(f"🚨 章节结构不完整：{'; '.join(incomplete_chapters)}")
```

## 检测维度

新的验证逻辑从3个维度检测章节质量：

### 维度1：内容长度
- 规则：每个章节至少50行
- 违规：少于50行认为不完整
- 示例：第1章只有5行 → 拒绝 ❌

### 维度2：章节间距
- 规则：相邻章节标题之间距离应≥100行
- 违规：距离<100行认为内容混叠
- 示例：第1章到第2章只有8行 → 拒绝 ❌

### 维度3：重复检测
- 规则：同一章节号出现≤2次
- 违规：出现>2次认为过度重复
- 示例：第1章出现3次 → 拒绝 ❌

## 测试验证

### 测试脚本：test_chapter_completeness.py

```bash
$ python test_chapter_completeness.py

检测章节标题:
  行0: 第1章 - 致命死局与系统觉醒 (第1章)
  行3: 章节序号：第1章 (第1章)
  行8: 章节序号：第2章 (第2章)

章节统计:
  第1章: 起始行0, 结束行7, 长度5行
  第2章: 起始行8, 结束行12, 长度5行

验证结果:
  🚨 验证失败：
    - 第1章（仅5行，不完整）
    - 第1章内容被第2章中断（第8行过早出现）
    - 第2章（仅5行，不完整）
```

## 检测的章节格式

新的验证逻辑可以检测以下格式：

| 格式 | 示例 | 检测 |
|------|------|------|
| 行首标题 | `第1章 - 标题` | ✅ |
| 序号字段 | `章节序号：第1章` | ✅ |
| Markdown加粗 | `**章节**: 第1章` | ✅ |
| 标题字段 | `章节标题：第1章` | ✅ |
| 内容引用 | `[第1章的伏笔]` | ❌ (不检测) |

## 验证流程

```
LLM生成内容
    ↓
章节标题检测（多种格式）
    ↓
章节结构分析
    ├─ 内容长度检查（<50行？）
    ├─ 章节间距检查（<100行？）
    └─ 重复检测（>2次？）
    ↓
综合判断
    ├─ 全部通过 → 接受 ✅
    └─ 任何失败 → 拒绝并重试 ❌
```

## 文件变更

### 修改的文件
`novel_generator/blueprint.py`
- 第213-229行：改进章节标题检测（支持多种格式）
- 第236-259行：添加章节完整性检查（长度+间距）

### 创建的文件
- `test_chapter_completeness.py` - 章节完整性验证测试

## 预期效果

### 修复前
```
第1章内容（5行）→ 第2章突然出现 → 验证通过 ❌
```

### 修复后
```
第1章内容（5行）→ 第2章突然出现 → 检测到问题 → 验证失败 → 要求重试 ✅
```

## 错误提示示例

当检测到章节混叠时，用户会看到：

```
🚨 验证失败：第1批次生成失败

原因：
  🚨 章节结构不完整：
    - 第1章（仅5行，不完整）
    - 第1章内容被第2章中断（第8行过早出现）
    - 第2章（仅5行，不完整）

系统将自动重试，请稍候...
```

## 配置参数

可以根据实际情况调整阈值：

```python
# 内容长度阈值
MIN_CONTENT_LENGTH = 50  # 最少行数

# 章节间距阈值
MIN_CHAPTER_DISTANCE = 100  # 最小行间距

# 重复次数阈值
MAX_DUPLICATE_COUNT = 2  # 最大重复次数
```

## 总结

**问题**：LLM生成了不完整或混叠的章节。

**解决**：添加3维度的章节质量检查。

**效果**：
- ✅ 正确检测章节混叠
- ✅ 正确检测内容不完整
- ✅ 给出明确的错误提示
- ✅ 自动要求LLM重试

---

**修复时间**：2026-01-04 19:00
**状态**：✅ 已完成并测试
**原则**：多层次验证，确保章节质量
