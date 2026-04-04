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

项目运行时配置读取自 `application/config/config.yaml`。

首次运行时，项目会自动确保以下文件存在：

- `application/config/config_default.yaml`
- `application/config/config.yaml`

如果要使用 AI 相关功能，请先在 `application/config/config.yaml` 中补充或修改大模型配置，重点包括：

- `api_key`
- 部分提供商需要的 `base_url`
- `default_provider` 以及各工作流步骤对应的 provider 配置

如果使用默认数据库配置，还需要确保本地 MongoDB 已启动。

配置编辑可以在前端的设置界面进行，或直接编辑上述 YAML 文件。

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
