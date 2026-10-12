# AI Novel Generator

**用 AI 辅助规划故事、管理设定与创作长篇小说。**

[English](README.md) · [快速开始](#快速开始) · [问题反馈](https://github.com/YILING0013/AI_NovelGenerator/issues/new/choose) · [参与贡献](.github/CONTRIBUTING.md)

AI Novel Generator 是一个本地运行的小说创作应用，将故事规划、世界设定和章节写作整合到同一个工作区。项目使用 Next.js 构建前端、FastAPI 提供后端接口、MongoDB 存储作品资料，并通过你配置的模型服务完成 AI 生成。

当前 `main` 分支为重构后的版本，仍在持续迭代。重构前的旧版保留在 [`old`](https://github.com/YILING0013/AI_NovelGenerator/tree/old) 分支。两个版本的数据结构不同，切换到新版时请使用独立数据库。

## 核心功能

| 功能 | 说明 |
| --- | --- |
| 故事规划 | 按小说、卷、篇章、场景与章节逐层组织创作计划。 |
| 设定管理 | 管理角色、势力、地点、物品、世界规则、关系与伏笔。 |
| 章节写作 | 编写和保存正文，查看历史版本，并结合相关规划与故事记录继续创作。 |
| AI 工作流 | 配置生成步骤、提示词、模型服务，以及结构化输入和输出。 |
| 模型接入 | 配置 OpenAI、DeepSeek、Gemini、Claude，以及对应适配器支持的兼容接口。 |
| 创作工作区 | 支持中英文切换、明暗主题与响应式布局。 |
| 桌面启动器 | 管理前后端服务、端口、前端构建与运行日志。 |

## 工作方式

```text
浏览器 / Next.js ── HTTP ── FastAPI ── MongoDB
                              │
                              └──── 你配置的 AI 模型服务

桌面启动器 ── 管理本机前端和后端进程
```

作品资料存放在你配置的数据库和本机存储中。执行 AI 操作时，应用会将所选上下文发送给对应模型服务；模型调用费用和数据处理规则由该服务提供方决定。

## 环境要求

- **Python 3.13 或 3.14**，使用对应系列的最新补丁版本。
- **Node.js 20.9 及以上**的受支持版本，以及 **npm**。
- **MongoDB**；推荐使用副本集，以支持多文档事务。
- **Docker** 为可选项，用于运行下方提供的本地 MongoDB 配置。
- 桌面启动器面向 **Windows**；也可以手动启动前后端。

## 快速开始

### 1. 安装依赖

```powershell
git clone https://github.com/YILING0013/AI_NovelGenerator.git
cd AI_NovelGenerator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
cd ..
```

macOS 和 Linux 的虚拟环境解释器路径为 `.venv/bin/python`。

### 2. 启动数据库

可以使用已有的 MongoDB，也可以使用项目提供的 Docker 配置。使用 Docker 前先确认端口 `27017` 空闲：

```powershell
docker compose -f compose.mongodb.yaml up -d
docker compose -f compose.mongodb.yaml exec mongodb mongosh --quiet --eval 'rs.initiate({_id: "rs0", members: [{_id: 0, host: "localhost:27017"}]})'
docker compose -f compose.mongodb.yaml ps
```

`rs.initiate` **只在新建数据卷后执行一次**。容器显示 `healthy` 后，单节点副本集即可使用。此配置不设置数据库账号密码，只向 `127.0.0.1` 开放端口，数据保存在 Docker 命名卷中。

如果 `backend/config/config.yaml` 尚不存在，先从同目录的 `config_default.yaml` 复制一份。使用上述副本集时，修改以下配置：

```yaml
mongodb_url: "mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true"
mongo_database_name: "novel_generator"
mongo_transaction_mode: "required"
```

使用普通单机 MongoDB 时，可保留 `mongo_transaction_mode: "auto"`；此时采用顺序写入，不提供多文档事务。修改数据库连接后需要重启后端。

### 3. 启动应用

Windows 用户双击 **`start.bat`**，在启动器中启动服务。生产模式在首次启动或相关源码、配置变化后自动构建前端。关闭启动器时，会停止由它启动的服务。

| 服务 | 默认地址 |
| --- | --- |
| 前端页面 | <http://127.0.0.1:3300> |
| 后端接口 | <http://127.0.0.1:8200> |
| API 文档 | <http://127.0.0.1:8200/docs> |

服务停止时可在启动器中修改端口。遇到端口占用，请先确认已有进程用途，避免重复启动。

### 4. 配置模型并开始创作

打开**设置**，填写模型服务的 API Key、接口地址和模型名称，并启用对应配置。之后创建小说、完成初始设定、规划卷与篇章，再进入场景和章节写作。AI 生成的候选内容可以先修改，再确认保存。

项目不附带 API Key。模型配置保存在本机的 `backend/config/config.yaml` 中。

## 手动启动

在项目根目录启动后端：

```powershell
.\.venv\Scripts\python.exe main.py
```

另开终端启动前端：

```powershell
cd frontend
npm run build
npm run start -- --hostname 127.0.0.1 --port 3300
```

自定义后端地址时，需在前端构建**之前**设置 `NEXT_PUBLIC_API_BASE`；桌面启动器会根据其管理的端口自动设置。环境变量 `NOVEL_GENERATOR_MONGODB_URL` 和 `NOVEL_GENERATOR_MONGO_DATABASE_NAME` 可覆盖对应的数据库配置。

## 数据、安全与升级

本项目按本机使用设计，不提供面向公网的用户认证。不要将应用服务或未认证的 MongoDB 直接暴露到公网。

升级前请备份以下内容：

| 位置 | 内容 |
| --- | --- |
| MongoDB | 小说及相关项目资料 |
| `backend/config/config.yaml` | 本机配置与模型服务凭据 |
| `data/` | 本地工作流文件及其他运行状态 |
| `static/` | 上传的封面等资源 |

先停止服务，再更新源码和重新安装依赖。密钥、本机数据、日志与生成产物不应提交到 Git；公开反馈前，请移除 API Key、数据库凭据、Cookie、个人路径和私密正文。

旧版与新版属于不同代码实现，**不应假定数据库和配置可以直接兼容**。请保留旧版备份，为新版创建独立数据库，不要直接连接仍在使用的旧版数据库。

## 项目结构

```text
backend/               FastAPI 应用、数据访问和运行时提示词
frontend/              Next.js 应用及构建配置
desktop_launcher/      桌面界面与服务管理
.github/               Issue 表单、PR 模板和贡献说明
main.py                后端启动入口
launcher.py            桌面启动器入口
start.bat              Windows 启动脚本
compose.mongodb.yaml   本地 MongoDB 配置
requirements.txt       Python 运行依赖
```

## 反馈与贡献

请通过 [Issue 表单](https://github.com/YILING0013/AI_NovelGenerator/issues/new/choose) 报告可复现的问题或提出功能建议，并提供版本、环境、复现步骤和脱敏后的相关信息。PR 请基于最新 `main` 创建，并遵循[贡献说明](.github/CONTRIBUTING.md)。

重构前的 Issue 和 PR 已随版本切换统一关闭，这不代表其中每个问题都已逐一修复。如果当前版本仍有相同问题，请重新提交，并链接原讨论。

## 许可证

本项目采用 **GNU Affero General Public License v3.0**。完整条款见 [LICENSE](LICENSE)。
