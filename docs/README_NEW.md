# AI小说生成工具 (AI Novel Generator)

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Framework](https://img.shields.io/badge/framework-CustomTkinter-orange.svg)](https://customtkinter.com)

一个基于大语言模型的智能小说生成工具，支持全自动一致性验证、多模型适配和可视化操作界面。

## 🌟 特色功能

### 🎯 全自动一致性验证系统
- **零容忍策略**：完全禁止省略号生成，确保内容完整性
- **智能重试机制**：最多5次自动重试，确保生成质量
- **多维度检查**：叙事流畅性、角色弧光、情节推进、世界构建一致性
- **实时监控**：自动检测剧情矛盾与逻辑冲突

### 🤖 多模型LLM适配器
- **支持模型**：OpenAI GPT系列、DeepSeek V3、Gemini 2.5 Pro、智谱AI GLM-4.6
- **统一接口**：适配器模式设计，易于扩展新模型
- **智能切换**：支持热切换不同LLM服务
- **频率管理**：智能频率限制器，避免API调用超限

### 📚 智能章节生成
- **24字段目录**：详细的章节规划系统
- **向量检索**：基于ChromaDB的长程上下文管理
- **语义关联**：自动维护角色状态和剧情连贯性
- **知识库集成**：支持外部文档参考和世界观设定

### 🎨 现代化GUI界面
- **CustomTkinter**：现代化界面设计，支持深色/浅色主题
- **多标签页**：功能模块清晰分离
- **实时预览**：生成过程实时可视化
- **批量操作**：支持批量章节生成和管理

## 🚀 快速开始

### 系统要求
- Python 3.8+
- Windows 10/11 (推荐)
- 8GB+ 内存
- 稳定的网络连接

### 安装步骤

1. **克隆仓库**
```bash
git clone https://github.com/your-username/AI_NovelGenerator.git
cd AI_NovelGenerator
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **配置API密钥**
```bash
# 复制配置模板
cp config.example.json config.json

# 编辑配置文件，添加您的API密钥
notepad config.json  # Windows
```

4. **启动应用**
```bash
python main.py
```

### 配置示例

在 `config.json` 中配置您的LLM服务：

```json
{
  "last_interface_format": "OpenAI",
  "llm_configs": {
    "DeepSeek V3": {
      "api_key": "your_api_key_here",
      "base_url": "https://api.deepseek.com/v1",
      "model_name": "deepseek-chat",
      "temperature": 0.7,
      "max_tokens": 8192,
      "timeout": 600,
      "interface_format": "OpenAI"
    },
    "GLM-4.6": {
      "api_key": "your_api_key_here",
      "base_url": "https://open.bigmodel.cn/api/paas/v4",
      "model_name": "glm-4.6",
      "temperature": 0.8,
      "max_tokens": 60000,
      "timeout": 600,
      "interface_format": "智谱AI"
    }
  }
}
```

## 📖 使用指南

### 基本工作流程

1. **设定生成** → 创建世界观、角色设定、剧情蓝图
2. **目录生成** → 基于设定生成章节标题和详细提示
3. **章节草稿** → 结合向量检索生成本章大纲和正文
4. **章节定稿** → 更新全局摘要、角色状态和向量库
5. **一致性检查** → 检测剧情矛盾与逻辑冲突

### 主要功能模块

| 模块 | 功能描述 |
|------|----------|
| **设定标签页** | 世界观构建、角色创建、情节设计 |
| **目录标签页** | 章节规划、结构设计、时间线管理 |
| **章节标签页** | 内容生成、编辑、质量检查 |
| **角色标签页** | 角色状态追踪、关系网络管理 |
| **摘要标签页** | 全局概览、一致性监控 |

## 🏗️ 技术架构

### 核心组件

```
AI_NovelGenerator/
├── main.py                      # 应用入口
├── config_manager.py            # 配置管理系统
├── llm_adapters.py              # LLM适配器工厂
├── embedding_adapters.py        # 向量生成适配器
├── chapter_directory_parser.py  # 章节目录解析器
├── novel_generator/             # 核心生成逻辑
│   ├── architecture.py         # 世界观生成
│   ├── blueprint.py            # 剧情蓝图生成
│   ├── chapter.py              # 章节内容生成
│   ├── vectorstore_utils.py    # 向量数据库操作
│   └── common.py               # 通用工具和重试机制
├── ui/                          # 图形界面模块
│   ├── main_window.py          # 主窗口
│   ├── generation_handlers.py  # 生成处理器
│   └── [various_tabs].py       # 各功能标签页
└── test*.py                     # 测试文件
```

### 设计模式

- **适配器模式**：统一不同LLM服务的接口
- **MVC模式**：分离业务逻辑、数据和界面
- **工厂模式**：动态创建适配器实例
- **策略模式**：不同的一致性检查策略

### 技术栈

- **GUI框架**：CustomTkinter 5.2.2+
- **LLM接口**：OpenAI、DeepSeek、Gemini、智谱AI
- **向量存储**：ChromaDB 1.0.20
- **文本处理**：LangChain、transformers
- **配置管理**：JSON，支持热重载

## 📦 打包部署

### 开发环境运行
```bash
python main.py
```

### 打包为可执行文件
```bash
# 安装打包工具
pip install pyinstaller

# 执行打包
pyinstaller main.spec

# 可执行文件位于 dist/ 目录
```

生成的可执行文件包含所有依赖，可在无Python环境的Windows系统上运行。

## 🔧 高级配置

### 频率限制设置
针对不同LLM服务的频率限制：

```python
rate_limits = {
    "glm-4.6": {
        "requests_per_5h": 600,
        "calls_per_request": 20,
        "min_interval": 33  # 秒
    }
}
```

### 向量数据库配置
```python
vectorstore_config = {
    "persist_directory": "./vectorstore",
    "collection_name": "novel_chapters",
    "embedding_model": "text-embedding-ada-002"
}
```

### 自动化设置
- **自动保存**：每30秒自动保存进度
- **自动重试**：API失败时自动重试，最多5次
- **自动验证**：生成内容自动进行一致性检查

## 🐛 常见问题

### Q: 章节生成时只有标题没有内容？
A: 检查temperature设置（建议0.7-0.8），系统会自动检测省略内容并重试。

### Q: API调用频率超限怎么办？
A: 系统已集成智能频率限制器，建议合理设置调用间隔。

### Q: 如何备份我的小说项目？
A: 重要文件包括：
- `config.json` - 配置文件
- 生成的小说文件（在配置的filepath目录）
- `vectorstore/` - 向量数据库

### Q: 支持哪些语言的小说生成？
A: 主要支持中文，也可配置其他语言。优化了中文小说生成的特殊需求。

## 🤝 贡献指南

我们欢迎所有形式的贡献！

### 开发环境设置
1. Fork项目到您的GitHub
2. 克隆到本地：`git clone your-fork-url`
3. 创建功能分支：`git checkout -b feature/your-feature`
4. 安装开发依赖：`pip install -r requirements.txt`
5. 开始开发！

### 代码规范
- 遵循PEP 8编码规范
- 使用类型注解
- 编写单元测试
- 更新相关文档

### 提交流程
1. 确保测试通过：`python -m pytest`
2. 提交代码：`git commit -m "feat: add your feature"`
3. 推送分支：`git push origin feature/your-feature`
4. 创建Pull Request

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)。

## 🙏 致谢

感谢以下开源项目和服务：
- [CustomTkinter](https://customtkinter.com/) - 现代化GUI框架
- [ChromaDB](https://www.trychroma.com/) - 向量数据库
- [LangChain](https://langchain.com/) - LLM应用框架
- 各大LLM服务提供商

## 📞 联系我们

- 📧 Email: [your-email@example.com]
- 🐛 Issues: [GitHub Issues](https://github.com/your-username/AI_NovelGenerator/issues)
- 💬 讨论: [GitHub Discussions](https://github.com/your-username/AI_NovelGenerator/discussions)

---

⭐ 如果这个项目对您有帮助，请给我们一个Star！