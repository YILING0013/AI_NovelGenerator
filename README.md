# AI Novel Generator

一个基于 LLM 的智能网文创作辅助系统，旨在通过结构化的工作流生成高质量、长篇幅的小说内容。

## 核心功能

- **自动化章节生成**: 基于详细的章节蓝图，自动生成数千字的正文内容。
- **质量闭环控制**: 内置自动评分与反馈机制，确保生成内容符合质量标准（如逻辑连贯、角色一致）。
- **动态架构支持**: 能够读取并遵循特定的小说架构设定（如《五行混元诀》的程序员修仙体系）。
- **多维度评估**: 从剧情、角色、文笔、爽点密度等多个维度对章节进行深度分析。

## 快速开始

1.  配置 `config/config.json` 中的 LLM API 密钥。
2.  运行 `main.py` 启动图形界面。
3.  导入或生成小说架构文件 (`Novel_architecture.txt`)。
4.  开始生成章节蓝图与正文。

## 技术栈

- **Core**: Python
- **GUI**: CustomTkinter
- **LLM Integration**: OpenAI Interface (Compatible with DeepSeek, Gemini, etc.)

## 许可证

MIT License

