# 第518章蓝图生成失败 - 修复指南

## 问题概述
- **失败章节**: 第518章
- **错误类型**: LLM返回空内容
- **重试次数**: 5次全部失败

## 方案一：紧急修复 - 手动生成第518章

### 步骤1：检查上下文
查看第517章和第519章（如果已存在），了解剧情衔接点：
```bash
grep -A 20 "第517章\|第519章" wxhyj/Novel_chapter_directory.txt
```

### 步骤2：查看架构定义
找到第518章在架构中的定义：
```bash
grep -B 5 -A 10 "第518章" wxhyj/Novel_architecture.txt
```

### 步骤3：手动创建蓝图
根据架构定义，手动创建第518章的7个小节蓝图，格式如下：
```
第518章：[章节标题]

第1节：[场景/事件描述]
第2节：[场景/事件描述]
...
第7节：[场景/事件描述]
```

### 步骤4：插入到目录
将手动创建的蓝图插入到 `Novel_chapter_directory.txt` 的正确位置。

---

## 方案二：修改代码增强容错

### 修改 `blueprint.py` 中的空结果处理

在 `novel_generator/blueprint.py:828` 附近添加降级策略：

```python
# Phase 2: 蓝图生成
logging.info("✍️ Phase 2: 正在生成蓝图...")
result = invoke_with_cleaning(self.llm_adapter, phase2_prompt)

if not result or not result.strip():
    logging.error(f"第{attempt + 1}次尝试：生成结果为空")

    # 🆕 尝试降级策略：使用简化prompt
    if attempt < 2:  # 前两次尝试简化版本
        logging.info("🔄 尝试使用简化prompt重新生成...")
        simplified_prompt = self._create_fallback_prompt(
            start_chapter, end_chapter, architecture_text
        )
        result = invoke_with_cleaning(self.llm_adapter, simplified_prompt)
        if result and result.strip():
            logging.info("✅ 简化prompt生成成功")

    if not result or not result.strip():
        # 保存空结果诊断
        empty_debug_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            f"blueprint_EMPTY_{start_chapter}_{end_chapter}_{attempt+1}.txt"
        )
        with open(empty_debug_file, 'w', encoding='utf-8') as f:
            f.write(f"LLM 返回空结果\nresult type: {type(result)}\nresult repr: {repr(result)}")
        logging.info(f"  📝 空结果诊断已保存: {empty_debug_file}")
        continue
```

### 添加简化prompt方法

```python
def _create_fallback_prompt(self, start_chapter, end_chapter, architecture_text):
    """创建简化的降级prompt"""
    # 只提取最核心的架构信息
    core_section = re.search(
        r'#=== 5\) 情节架构.*?(?=#=== 6\))',
        architecture_text, re.DOTALL
    )
    core_architecture = core_section.group(0) if core_section else architecture_text[:5000]

    prompt = f"""
请为第{start_chapter}章到第{end_chapter}章生成详细的章节蓝图。

每章必须包含7个节，每个节都要有具体内容，不能省略。

架构参考：
{core_architecture[:3000]}

请按以下格式输出：

第{start_chapter}章：[标题]
第1节：[具体内容]
第2节：[具体内容]
...
第7节：[具体内容]

（如果有第{start_chapter+1}章，继续相同格式）
"""
    return prompt
```

---

## 方案三：配置优化

### 1. 检查API配置

检查 `config.json` 中的配置：
```json
{
  "llm_config": {
    "interface_format": "anthropic",
    "api_key": "your_key_here",
    "base_url": "https://open.bigmodel.cn/api/anthropic/v1/messages",
    "model": "glm-4.6",
    "max_tokens": 60000,
    "temperature": 0.8,
    "timeout": 1800
  }
}
```

### 2. 增加超时时间
如果遇到超时，可以将 `timeout` 从 1800 增加到 3600

### 3. 检查API配额
登录智谱AI控制台，确认：
- Token配额是否充足
- 请求频率限制
- 账户状态是否正常

---

## 方案四：分段生成策略

修改 `generate_complete_directory_strict` 方法，支持从失败点恢复：

```python
def resume_generation_from(self, start_chapter: int, total_chapters: int):
    """从指定章节恢复生成"""
    # 读取已有的蓝图内容
    existing_content = read_file(filename_dir)

    # 找到已生成的最后一章
    last_chapter = self._find_last_generated_chapter(existing_content)

    if last_chapter < start_chapter - 1:
        logging.warning(f"检测到第{last_chapter+1}到{start_chapter-1}章缺失")

    # 从start_chapter开始生成
    return self.generate_complete_directory_strict(
        number_of_chapters=total_chapters,
        start_from_chapter=start_chapter,
        existing_content=existing_content
    )
```

---

## 预防措施

### 1. 添加checkpoint机制
每生成50章自动保存checkpoint

### 2. 实现指数退避重试
第一次失败等待5秒，第二次10秒，第三次20秒...

### 3. 添加prompt长度检查
在发送前检查prompt长度，超过阈值自动截断

### 4. 监控API响应
记录每次API调用的响应时间和状态

---

## 立即操作建议

1. **检查API状态**：登录智谱AI控制台确认配额
2. **查看完整日志**：检查是否有更多错误信息
3. **尝试手动生成**：使用方案一为第518章手动创建蓝图
4. **应用代码修复**：使用方案二增强容错能力
5. **调整配置**：根据实际情况增加timeout或调整其他参数

---

**注意**: 如果问题持续出现，建议联系LLM服务提供商确认API状态。
