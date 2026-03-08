# 🎯 章节概览格式问题的根本修复

## 问题描述

用户报告第6-10章生成失败，错误信息：
```
Exception: 第2批次生成失败: 批次生成失败：第6章到第10章，经过5次尝试仍未成功
Validation error: 🚨 节完整性检测：第10章缺失: 暗恋与修罗场
```

## 🔍 根本原因分析

### 问题链路

1. **`wxhyj/Novel_directory.txt` 包含旧格式的章节**
   - 该文件中的章节使用旧格式（如【基础元信息】、【张力架构设计】等）
   - 不是当前标准的7节格式（`## 1. 基础元信息`, `## 2. 张力与冲突`等）

2. **代码读取旧内容并展示给LLM**
   - 代码位置：`blueprint.py:608`
   - 原逻辑：`chapter_list=existing_content[-2000:] if existing_content else ""`
   - 效果：将最后2000字符的旧格式内容直接展示给LLM

3. **LLM模仿错误格式**
   - LLM看到"已有章节概览"中的旧格式内容
   - 实例优先原则：LLM优先模仿具体实例，而不是抽象规则
   - 结果：生成的章节不符合标准7节格式

4. **验证失败**
   - 验证器检查生成的章节是否包含所有7个节
   - 由于生成格式不符合标准，验证失败
   - 重试5次后仍然失败

### 代码证据

**旧格式示例**（`wxhyj/Novel_directory.txt`）：
```
第1章 - 破碎的瓷娃娃

1. 基础元信息
章节序号：第1章
章节名：破碎的瓷娃娃
张力评级：★★★☆☆

2. 张力架构
- **核心冲突**：张昊（前世宗师）vs 现状（废柴弃徒/濒死肉身）
...
```

**标准格式要求**：
```
### **第X章 - [章节标题]**

## 1. 基础元信息
*   **章节序号**：第X章
*   **章节标题**：[章节标题]
...

## 2. 张力与冲突
...
## 3. 匠心思维应用
...
## 4. 伏笔与信息差
...
## 5. 暧昧与修罗场
...
## 6. 剧情精要
...
## 7. 衔接设计
...
```

## 🛠️ 修复方案

### 实施的修复

#### 修复1：添加章节标题提取函数

**位置**：`blueprint.py:459`

**新增函数**：`_extract_chapter_titles_only(self, existing_content: str, max_chapters: int = 10) -> str`

**功能**：
- 从已有内容中仅提取章节标题（如"第1章 - 破碎的瓷娃娃"）
- 不提取章节的具体内容，避免展示旧格式
- 支持多种标题格式的识别
- 自动去重，避免重复章节

#### 修复2：修改chapter_list生成逻辑

**位置**：`blueprint.py:668`

**原代码**：
```python
chapter_list=existing_content[-2000:] if existing_content else ""
```

**修复后**：
```python
chapter_list=self._extract_chapter_titles_only(existing_content[-5000:]) if existing_content else ""
```

**改进**：
- 使用新的`_extract_chapter_titles_only()`函数
- 只提取标题，不包含内容
- 增加了读取范围（2000→5000字符）以确保能提取到足够的标题

### 修复效果

**修复前**：
```
### 已有章节概览
第1章 - 破碎的瓷娃娃

1. 基础元信息
章节序号：第1章
...（完整的旧格式内容，包含所有节的详细信息）
```

LLM看到这个完整的旧格式内容，模仿其结构。

**修复后**：
```
### 已有章节概览
以下是已生成章节的标题列表（仅用于了解剧情连贯性）：
第1章 - 破碎的瓷娃娃
第2章 - 修复魔门妖女的"破身"之劫
第3章 - ...
```

LLM只看到标题列表，了解剧情顺序但不会模仿错误格式。

## 📊 技术细节

### 章节标题识别模式

```python
patterns = [
    r'^(第\d+章[：\s\-——]+.+?)(?:\n|$)',  # 第1章：标题 或 第1章 - 标题
    r'^第(\d+)章[：\s\-——]*(.+?)(?:\n|$)',  # 第1章标题
    r'^【(.+?)】.*?章节.*?[:：](.+?)(?:\n|$)',  # 【基础元信息】章节标题：xxx
]
```

### 去重逻辑

使用`seen_chapters`集合记录已提取的章节号，避免重复：
```python
chapter_match = re.search(r'第(\d+)章', title)
if chapter_match:
    chapter_num = chapter_match.group(1)
    if chapter_num not in seen_chapters:
        seen_chapters.add(chapter_num)
        titles.append(title)
```

## ✅ 验证方法

1. **测试章节标题提取**：
   ```python
   # 测试脚本
   from novel_generator.blueprint import StrictChapterGenerator

   generator = StrictChapterGenerator(...)
   with open('wxhyj/Novel_directory.txt', 'r', encoding='utf-8') as f:
       content = f.read()
   titles = generator._extract_chapter_titles_only(content[-5000:])
   print(titles)
   ```

2. **运行章节生成**：
   - 生成第6-10章
   - 检查生成的章节是否符合标准7节格式
   - 验证是否通过

3. **检查日志文件**：
   - 查看`wxhyj/llm_conversation_logs/`中的最新日志
   - 确认"已有章节概览"部分只显示标题列表

## 📝 相关文件

| 文件 | 修改内容 | 状态 |
|------|----------|------|
| `novel_generator/blueprint.py:459` | 添加`_extract_chapter_titles_only()`函数 | ✅ 已完成 |
| `novel_generator/blueprint.py:668` | 修改`chapter_list`生成逻辑 | ✅ 已完成 |

## 🔗 相关问题

本修复是**多处模板冲突**系列修复的一部分：

1. ✅ **Few-shot示例与Prompt不一致** - 已在`prompt_definitions.py`中修复
2. ✅ **架构文件Section 9与Prompt不一致** - 已在`Novel_architecture.txt`中修复
3. ✅ **已有章节概览展示错误格式** - 本次修复

## 📌 后续建议

### 建议1：统一Novel_directory.txt格式

考虑将`wxhyj/Novel_directory.txt`中的旧格式章节全部转换为新的7节标准格式。这样即使展示完整内容，也不会造成格式混乱。

### 建议2：添加格式验证

在生成蓝图时，添加对已有章节格式的验证：
- 检测章节是否符合标准格式
- 如果不符合，发出警告
- 提供自动转换选项

### 建议3：单一数据源

考虑实现"单一数据源"原则：
- 章节格式只在一个地方定义
- 其他所有地方都引用这个定义
- 避免多处定义导致不一致

## 总结

**问题根源**：`Novel_directory.txt`包含旧格式章节，代码将这些内容展示给LLM作为"已有章节概览"，LLM模仿错误格式。

**解决方案**：修改代码，只提取和展示章节标题，不展示完整内容。

**修复效果**：
- ✅ LLM不再看到错误格式的实例
- ✅ LLM只能通过标题了解剧情顺序
- ✅ 强制LLM按照Prompt中定义的标准格式生成
- ✅ 验证通过率应该大幅提高

---

**修复时间**：2026-01-05 02:25
**状态**：✅ 修复已完成，等待用户验证
**原则**：避免展示错误格式的实例，防止LLM模仿
