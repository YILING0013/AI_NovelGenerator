# AI Novel Generator

[中文文档](./README.zh-CN.md) | English

AI Novel Generator is an AI-assisted novel creation project. The repository currently contains:

- a FastAPI backend for configuration, novel, volume, upload, and AI workflow APIs
- a Next.js frontend that is being rebuilt
- a Windows desktop launcher that can start the backend and frontend together

## Current Status

This project is still under an ongoing refactor and is not yet considered feature-complete.

- interfaces, folder structure, and workflows may continue to change
- some features from earlier iterations may be incomplete or temporarily unavailable
- if you need the previous version, please check the `main` branch

## Requirements

- Python 3
- MongoDB
- Node.js and npm for the frontend

## Configuration

Application configuration is loaded from `backend/config/config.yaml`.

On first run, the project will ensure the following files exist:

- `backend/config/config_default.yaml`
- `backend/config/config.yaml`

Before running AI-related features, update the LLM provider settings in `backend/config/config.yaml`, especially:

- `api_key`
- `base_url` where applicable
- `default_provider` and workflow provider mapping
- `use_system_proxy` if you explicitly want the SDK to inherit your Windows/system proxy. The default is `false`.

You should also make sure MongoDB is running locally if you use the default database settings.
The backend uses PyMongo Async directly. On startup it pings MongoDB and initializes indexes, so invalid MongoDB settings fail early instead of surfacing during the first request.

MongoDB-related settings:

- `mongodb_url`: MongoDB connection string
- `mongo_database_name`: database name
- `mongo_timeout_ms`: server selection timeout in milliseconds
- `mongo_transaction_mode`: `auto`, `required`, or `disabled`; `auto` uses transactions on replica set/sharded deployments and falls back to ordered writes on standalone MongoDB

Configuration can be edited through the frontend settings interface or by directly modifying the YAML files mentioned above.

Faction APIs are scoped by novel. Use paths under `/api/factions/novel/{novel_id}/...`; older unscoped faction paths are intentionally removed.

## Install

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

## Run

### Option 1: Windows launcher

The quickest Windows entry point is:

```bat
start.bat
```

This starts the desktop launcher, which can then start:

- backend: `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`
- frontend: `http://localhost:3000`

### Option 2: Run backend manually

```bash
python main.py
```

Enable backend debug logging and raw AI response output:

```bash
python main.py --debug
```

When you use the Windows launcher, you can enable the backend checkbox labeled `后端调试日志` before starting the backend.

### Option 3: Run frontend manually

```bash
cd frontend
npm run dev
```

## Tests

Example test commands:

```bash
python -m tests.test_volumes
python -m tests.test_llm openai
```

Some tests require local services or valid model credentials.

## Notes

This README intentionally documents the current refactor state only. If the current branch does not match the workflow you expect, review the `main` branch for the earlier implementation.
