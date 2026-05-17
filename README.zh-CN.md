# AI Novel Generator

AI Novel Generator 是一个用于辅助小说创作的项目，当前仓库内主要包含：

- 基于 FastAPI 的后端接口，用于配置、小说、卷、上传和 AI 工作流相关能力
- 正在重构中的 Next.js 前端
- 可在 Windows 下同时拉起前后端的桌面启动器

## 当前状态

该项目目前仍处于重构过程中，尚未完成，也不应视为稳定版本。

- 接口、目录结构和工作流仍可能继续调整
- 旧功能有一部分可能尚未迁移完成，或处于临时不可用状态
- 如果你需要之前的版本，请查看 `main` 分支

## 运行前准备

需要先准备以下环境：

- Python 3
- MongoDB
- Node.js 与 npm（前端需要）

## 配置说明

项目运行时配置读取自 `backend/config/config.yaml`。

首次运行时，项目会自动确保以下文件存在：

- `backend/config/config_default.yaml`
- `backend/config/config.yaml`

如果要使用 AI 相关功能，请先在 `backend/config/config.yaml` 中补充或修改大模型配置，重点包括：

- `api_key`
- 部分提供商需要的 `base_url`
- `default_provider` 以及各工作流步骤对应的 provider 配置
- 如果你明确需要让 SDK 继承 Windows / 系统代理，可设置 `use_system_proxy: true`；默认值为 `false`

如果使用默认数据库配置，还需要确保本地 MongoDB 已启动。
后端现在直接使用 PyMongo Async。启动时会主动 ping MongoDB 并初始化索引，因此数据库配置错误会在启动阶段暴露，而不是等到第一次请求才失败。

MongoDB 相关配置包括：

- `mongodb_url`：MongoDB 连接串
- `mongo_database_name`：数据库名
- `mongo_timeout_ms`：服务选择超时时间，单位毫秒
- `mongo_transaction_mode`：事务模式，可选 `auto`、`required`、`disabled`；默认 `auto` 会在副本集/分片集启用事务，在单机 MongoDB 上降级为顺序写入

配置编辑可以在前端的设置界面进行，或直接编辑上述 YAML 文件。

阵营 API 现在必须带小说作用域，请使用 `/api/factions/novel/{novel_id}/...` 下的路径；旧的非作用域阵营路径已移除。

## 安装依赖

安装 Python 依赖：

```bash
pip install -r requirements.txt
```

安装前端依赖：

```bash
cd frontend
npm install
```

## 运行方式

### 方式一：Windows 启动器

Windows 下最直接的启动方式是：

```bat
start.bat
```

启动后可通过桌面启动器分别或同时启动：

- 后端：`http://127.0.0.1:8000`
- 接口文档：`http://127.0.0.1:8000/docs`
- 前端：`http://localhost:3000`

### 方式二：手动启动后端

```bash
python main.py
```

如果需要输出更完整的后端调试日志，并在控制台打印 AI 原始响应内容，可以这样启动：

```bash
python main.py --debug
```

如果通过 Windows 启动器启动，在启动后端前勾选 `后端调试日志` 即可。

### 方式三：手动启动前端

```bash
cd frontend
npm run dev
```

## 测试

可参考以下命令：

```bash
python -m tests.test_volumes
python -m tests.test_llm openai
```

部分测试依赖本地服务或有效的大模型密钥。

## 说明

本 README 只描述当前重构中的项目状态。如果你要查看更早期、相对完整的版本，请直接切换到 `main` 分支查看。
