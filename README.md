# AI Novel Generator

**Plan, organize, and write long-form fiction with AI.**

[中文文档](README.zh-CN.md) · [Quick start](#quick-start) · [Report an issue](https://github.com/YILING0013/AI_NovelGenerator/issues/new/choose) · [Contributing](.github/CONTRIBUTING.md)

AI Novel Generator is a locally hosted writing application that brings story planning, worldbuilding, and chapter drafting into one workspace. A Next.js interface connects to a FastAPI backend, MongoDB stores your project, and your chosen model provider handles AI generation.

The current `main` branch contains the rewritten application and continues to evolve. The previous version is preserved on [`old`](https://github.com/YILING0013/AI_NovelGenerator/tree/old). The two versions have different data structures; use a separate database when moving to the current version.

## Features

| Area | Capabilities |
| --- | --- |
| Story planning | Organize a novel into volumes, arcs, scenes, and chapter plans. |
| Worldbuilding | Manage characters, factions, locations, items, world rules, relationships, and foreshadowing. |
| Chapter writing | Draft and save chapter text, review revisions, and use related planning and story records. |
| AI workflows | Configure generation steps, prompts, model providers, and structured inputs and outputs. |
| Model integration | Configure OpenAI, DeepSeek, Gemini, Claude, and compatible endpoints supported by their adapters. |
| Writing workspace | Switch between Chinese and English, use light or dark mode, and work across responsive layouts. |
| Desktop launcher | Start and stop services, configure ports, build the frontend, and inspect backend and frontend logs. |

## Architecture

```text
Browser / Next.js ── HTTP ── FastAPI ── MongoDB
                               │
                               └──── Configured AI providers

Desktop launcher ── manages the local frontend and backend
```

Application data stays in your configured database and local storage. AI actions send the selected context to the model provider you configure; model usage, billing, and provider data policies apply separately.

## Requirements

- **Python 3.13 or 3.14**, with the latest patch release in that series.
- **Node.js 20.9 or later**, using a supported Node.js release, and **npm**.
- **MongoDB**. A replica set is recommended for multi-document transactions.
- **Docker** is optional; it provides the local MongoDB setup below.
- The desktop launcher targets **Windows**. Services can also be started manually.

## Quick start

### 1. Install dependencies

```powershell
git clone https://github.com/YILING0013/AI_NovelGenerator.git
cd AI_NovelGenerator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
cd ..
```

On macOS and Linux, the virtual environment interpreter is `.venv/bin/python`.

### 2. Start MongoDB

You can use an existing MongoDB deployment or the included Docker configuration. For Docker, ensure port `27017` is available:

```powershell
docker compose -f compose.mongodb.yaml up -d
docker compose -f compose.mongodb.yaml exec mongodb mongosh --quiet --eval 'rs.initiate({_id: "rs0", members: [{_id: 0, host: "localhost:27017"}]})'
docker compose -f compose.mongodb.yaml ps
```

Run `rs.initiate` **only once for a newly created data volume**. The single-node replica set is ready when the container reports `healthy`. It has no database credentials and publishes its port only on `127.0.0.1`. Data persists in Docker named volumes.

Copy `backend/config/config_default.yaml` to `backend/config/config.yaml` if the latter does not exist. For the bundled replica set, set:

```yaml
mongodb_url: "mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true"
mongo_database_name: "novel_generator"
mongo_transaction_mode: "required"
```

With standalone MongoDB, keep `mongo_transaction_mode: "auto"`; the application uses ordered writes without multi-document transactions. Restart the backend after changing its database connection.

### 3. Launch the application

On Windows, double-click **`start.bat`** and start the services from the launcher. Production mode builds the frontend on first use and when relevant source or configuration changes. Closing the launcher stops the services it started.

| Service | Default address |
| --- | --- |
| Frontend | <http://127.0.0.1:3300> |
| Backend | <http://127.0.0.1:8200> |
| API documentation | <http://127.0.0.1:8200/docs> |

Configure ports in the launcher while services are stopped. If a port is occupied, identify the existing service before starting another instance.

### 4. Configure a model and begin writing

Open **Settings**, add your provider's API key, endpoint and model name, and enable the provider. Then create a novel, complete its initial settings, plan volumes and arcs, and move on to scenes and chapter writing. You can edit generated candidates before saving them.

No API keys are included. Provider settings are stored in your local `backend/config/config.yaml`.

## Manual startup

From the project root, start the backend:

```powershell
.\.venv\Scripts\python.exe main.py
```

In a separate terminal, start the frontend:

```powershell
cd frontend
npm run build
npm run start -- --hostname 127.0.0.1 --port 3300
```

For a custom backend address, set `NEXT_PUBLIC_API_BASE` **before** building the frontend. The desktop launcher sets it for the ports it manages. `NOVEL_GENERATOR_MONGODB_URL` and `NOVEL_GENERATOR_MONGO_DATABASE_NAME` override the matching database configuration values.

## Data, security, and upgrades

The application is intended for local use and does not provide public-facing user authentication. Do not directly expose its services or an unauthenticated MongoDB deployment to the internet.

Back up the following before upgrading:

| Location | Purpose |
| --- | --- |
| MongoDB | Novel records and related project data |
| `backend/config/config.yaml` | Local configuration and provider credentials |
| `data/` | Local workflow files and other runtime state |
| `static/` | Uploaded assets, including covers |

Stop services before updating source and reinstalling dependencies. Keep credentials, local data, logs, and generated files out of Git. Redact API keys, database credentials, cookies, personal paths, and private writing from public reports.

The legacy version is a separate codebase. Its database and configuration are **not assumed to be compatible** with the rewritten version; preserve a backup and use a new database rather than pointing the new application at legacy data.

## Project structure

```text
backend/               FastAPI application, data access, and runtime prompts
frontend/              Next.js application and build configuration
desktop_launcher/      Desktop UI and service management
.github/               Issue forms, PR template, and contribution guide
main.py                Backend entry point
launcher.py            Desktop launcher entry point
start.bat              Windows startup script
compose.mongodb.yaml   Local MongoDB configuration
requirements.txt       Python runtime dependencies
```

## Contributing and support

Use the [Issue forms](https://github.com/YILING0013/AI_NovelGenerator/issues/new/choose) to report reproducible problems or propose improvements. Include your version, environment, reproduction steps, and redacted evidence. Base pull requests on current `main` and read the [contribution guide](.github/CONTRIBUTING.md).

Issues and pull requests from before the rewrite have been closed as part of the version transition. This does not mean every historical report was individually fixed. If a problem remains, open a current-version report and link the earlier discussion.

## License

This project is licensed under the **GNU Affero General Public License v3.0**. See [LICENSE](LICENSE) for the full text.
