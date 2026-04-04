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

Application configuration is loaded from `application/config/config.yaml`.

On first run, the project will ensure the following files exist:

- `application/config/config_default.yaml`
- `application/config/config.yaml`

Before running AI-related features, update the LLM provider settings in `application/config/config.yaml`, especially:

- `api_key`
- `base_url` where applicable
- `default_provider` and workflow provider mapping

You should also make sure MongoDB is running locally if you use the default database settings.

Configuration can be edited through the frontend settings interface or by directly modifying the YAML files mentioned above.

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
