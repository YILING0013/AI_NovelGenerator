# 🚀 cuitaochina-marketplace 安装指南

## 📖 概述

这是 cuitaochina 精选的 Claude Code 插件和 MCP 服务器配置市场，包含 15 个高质量插件和 10 个专业 MCP 服务器。

## 📊 统计信息

- **插件数量**: 15 个专业插件
- **MCP服务器**: 10 个生产力工具
- **分类数量**: 10 个专业分类
- **总工具数**: 25 个开发工具
- **质量评级**: A+
- **维护状态**: 活跃

## 🛠️ 插件分类

### 开发工具 (🛠️)
- `python-expert` - Python 专家级开发
- `backend-architect` - 后端系统架构设计
- `python-pro` - Python 现代开发实践
- `fastapi-pro` - FastAPI 高性能 API
- `django-pro` - Django 全栈开发
- `code-reviewer` - 代码质量审查
- `debugger` - 调试专家
- `database-performance-optimizer` - 数据库性能优化
- `code-architect` - 软件架构设计

### 测试工具 (🧪)
- `unit-testing` - 单元测试策略
- `api-testing-observability` - API 测试和监控

### 安全工具 (🔒)
- `enterprise-security-reviewer` - 企业级安全审计

### AI工具 (🤖)
- `ai-engineer` - AI/ML 项目专家

### 生产力工具 (📊)
- `document-skills` - Office 文档处理
- `example-skills` - 功能示例演示

## 🔍 MCP 服务器

### 搜索和知识
- `context7` - 文档知识库检索
- `open-websearch` - 多引擎网络搜索
- `mcp-deepwiki` - 深度 Wikipedia 集成
- `exa` - AI 驱动的代码搜索

### 生产力
- `spec-workflow` - 规格工作流管理
- `filesystem` - 文件系统访问
- `notion` - Notion 文档集成

### 监控和数据库
- `sentry` - 错误监控和性能追踪
- `supabase` - 数据库和后端服务

### 测试
- `Playwright` - 浏览器自动化测试

## ⭐ 精选推荐

1. **python-expert** - Python 开发必备
2. **backend-architect** - 系统设计神器
3. **code-reviewer** - 代码质量保证
4. **ai-engineer** - AI 项目开发
5. **context7** - 知识库检索
6. **open-websearch** - 网络搜索

## 📦 安装步骤

### 1. 添加市场

```bash
claude plugin marketplace add cuitaochina/marketplace
```

### 2. 验证市场

```bash
claude plugin marketplace list
```

### 3. 安装插件

```bash
# 安装精选插件
claude plugin install python-expert
claude plugin install backend-architect
claude plugin install code-reviewer
claude plugin install ai-engineer

# 安装文档处理
claude plugin install document-skills

# 安装示例
claude plugin install example-skills
```

### 4. 配置 MCP 服务器

```bash
# 文件系统访问 (需要指定路径)
claude mcp add filesystem npx @modelcontextprotocol/server-filesystem /your/path

# Notion 集成
claude mcp add notion npx @notionhq/notion-mcp-server

# Sentry 监控
claude mcp add sentry npx @sentry/mcp-server

# Supabase 数据库
claude mcp add supabase npx @supabase/mcp-server-supabase
```

### 5. 验证安装

```bash
# 查看已安装插件
claude plugin --help

# 查看已配置 MCP 服务器
claude mcp list
```

## 🔧 环境变量配置

某些 MCP 服务器需要环境变量：

```bash
# Exa 搜索引擎
export EXA_API_KEY="your_exa_api_key"

# 其他服务器根据需要配置
```

## 📋 使用示例

### Python 开发工作流

```bash
# 使用 python-expert 进行代码优化
/python-expert
请优化这个 Python 函数的性能

# 使用 code-reviewer 进行代码审查
/code-reviewer
审查这段代码的安全性和最佳实践
```

### AI 项目开发

```bash
# 使用 ai-engineer 构建应用
/ai-engineer
帮我设计一个 RAG 系统的架构

# 使用 context7 查找文档
/context7
搜索 Python 异步编程的最佳实践
```

## 🛠️ 故障排除

### 常见问题

1. **插件安装失败**
   ```bash
   claude plugin marketplace update cuitaochina/marketplace
   ```

2. **MCP 服务器连接失败**
   ```bash
   claude mcp remove server_name
   claude mcp add server_name command
   ```

3. **权限问题**
   ```bash
   claude doctor
   ```

### 获取帮助

- 官方文档: https://docs.anthropic.com/claude/code
- GitHub 仓库: https://github.com/cuitaochina/marketplace
- 问题报告: 在仓库中创建 Issue

## 🔄 更新维护

市场配置会定期更新，包含最新的插件和 MCP 服务器：

```bash
# 更新市场
claude plugin marketplace update cuitaochina/marketplace

# 更新插件
claude plugin update plugin_name
```

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

---

**维护者**: [cuitaochina](https://github.com/cuitaochina)

*最后更新: 2025-12-01*