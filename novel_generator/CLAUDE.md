[根目录](../../CLAUDE.md) > **novel_generator**

# novel_generator 模块文档

## 模块职责

novel_generator模块是AI小说生成工具的核心业务逻辑层，负责小说创作的全流程管理，包括架构生成、蓝图规划、章节创作、向量存储和一致性验证等功能。

## 入口与启动

### 主要导出函数
```python
from novel_generator import (
    Novel_architecture_generate,    # 小说架构生成
    Chapter_blueprint_generate,      # 章节蓝图生成
    get_last_n_chapters_text,        # 获取最近章节文本
    summarize_recent_chapters,       # 章节摘要生成
    get_filtered_knowledge_context,  # 知识库上下文检索
    build_chapter_prompt,            # 章节提示词构建
    generate_chapter_draft,          # 章节草稿生成
    finalize_chapter,                # 章节定稿
    enrich_chapter_text,             # 章节内容丰富
    import_knowledge_file,           # 知识库导入
    clear_vector_store               # 清空向量存储
)
```

### 核心工作流程
1. **架构生成** → 2. **蓝图规划** → 3. **章节生成** → 4. **定稿处理** → 5. **向量化存储**

## 对外接口

### 架构生成器 (`architecture.py`)
- `Novel_architecture_generate()`: 生成小说整体架构
- 支持世界观、角色设定、主线剧情规划
- 返回结构化的架构数据

### 蓝图生成器 (`blueprint.py`)
- `Strict_Chapter_blueprint_generate()`: 严格模式章节蓝图生成
- 零容忍省略策略，确保内容完整性
- 支持分批次生成（每批50章）

### 章节生成器 (`chapter.py`)
- `generate_chapter_draft()`: 章节草稿生成
- `get_last_n_chapters_text()`: 获取历史章节上下文
- `summarize_recent_chapters()`: 生成章节摘要
- `get_filtered_knowledge_context()`: 向量检索相关内容

### 定稿处理器 (`finalization.py`)
- `finalize_chapter()`: 章节最终定稿
- `enrich_chapter_text()`: 内容丰富和完善
- 自动更新全局状态和角色信息

### 向量存储 (`vectorstore_utils.py`)
- ChromaDB集成，支持语义检索
- `clear_vector_store()`: 清空向量数据库
- 自动嵌入生成和相似度搜索

### 知识库管理 (`knowledge.py`)
- `import_knowledge_file()`: 导入外部知识文档
- 支持参考材料和背景设定管理
- 智能内容检索和推荐

## 关键依赖与配置

### 内部依赖
- `common.py`: 通用工具函数（重试、日志）
- `wordcount_utils.py`: 字数统计和分析

### 外部依赖
- ChromaDB: 向量数据库
- LangChain: 文本处理和LLM集成
- sentence-transformers: 文本嵌入
- OpenAI/其他LLM: 内容生成

### 配置要求
- LLM服务配置（api_key、model、temperature等）
- 向量存储路径配置
- 日志级别和输出配置

## 数据模型

### 章节结构
```python
{
    "chapter_number": int,        # 章节编号
    "chapter_title": str,         # 章节标题
    "chapter_content": str,       # 章节内容
    "word_count": int,           # 字数统计
    "summary": str,              # 章节摘要
    "characters": List[str],     # 涉及角色
    "keywords": List[str],       # 关键词
    "creation_time": datetime    # 创建时间
}
```

### 架构模型
```python
{
    "worldview": str,            # 世界观设定
    "main_characters": List[dict], # 主要角色
    "plot_outline": str,         # 剧情大纲
    "themes": List[str],         # 主题标签
    "style_guide": str          # 写作风格指导
}
```

## 测试与质量

### 单元测试覆盖
- ✅ 章节生成逻辑测试
- ✅ 向量存储操作测试
- ✅ 字数统计功能测试
- ⚠️ 蓝图生成测试（部分覆盖）
- ❌ 架构生成测试（待完善）

### 测试文件
- `test_single_chapter.py`: 单章节生成测试
- `test_blueprint_fix.py`: 蓝图修复测试
- `test_auto_consistency.py`: 一致性验证测试

### 质量保证机制
- 自动重试机制（最多5次）
- 省略内容零容忍策略
- 逻辑一致性验证
- 字数和格式规范检查

## 常见问题 (FAQ)

### Q: 章节生成时出现省略号怎么办？
A: 系统采用零容忍策略，自动重试直到生成完整内容。

### Q: 如何提高生成速度？
A: 可以调整批处理大小，使用本地LLM服务，或优化向量检索参数。

### Q: 向量数据库占用空间过大？
A: 定期清理无用向量，使用嵌入压缩技术，或调整检索精度。

### Q: 如何确保角色一致性？
A: 利用向量存储追踪角色状态，定期运行一致性检查器。

## 相关文件清单

### 核心文件
- `__init__.py`: 模块导出定义
- `common.py`: 通用工具函数
- `architecture.py`: 小说架构生成
- `blueprint.py`: 章节蓝图生成
- `chapter.py`: 章节内容生成
- `finalization.py`: 章节定稿处理
- `vectorstore_utils.py`: 向量数据库操作
- `knowledge.py`: 知识库管理
- `wordcount_utils.py`: 字数统计工具

### 配置文件
- `config.json`: 主配置文件
- `prompt_definitions.py`: 提示词定义

### 测试文件
- `test_single_chapter.py`
- `test_blueprint_fix.py`
- `test_auto_consistency.py`

## 变更记录 (Changelog)

### 2025-11-09
- 初始化模块文档
- 添加接口说明和依赖关系
- 建立导航面包屑

### 历史更新
详见项目根目录CHANGELOG

---

**注意**: 本模块是整个系统的核心，任何修改都需要充分测试，特别是涉及向量存储和一致性验证的功能。