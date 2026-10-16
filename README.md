<div align="center">

# AI Novel Generator

**English** · [简体中文](README.zh-CN.md)

Turn a story idea into a world, volumes, arcs, scenes, and manuscript.

[Watch the demo](#watch-the-demo) · [Install and run](#install-and-run) · [Explore the interface](#explore-the-interface) · [Backups and upgrades](#backups-and-upgrades)

</div>

AI Novel Generator is a writing workspace that runs on your computer. Write by hand or ask AI for a candidate, then review, edit, and save it. Characters, factions, relationships, story plans, and prose live in one project, with a progress panel to guide the next step.

Thanks to members of the [LINUX DO community](https://linux.do/) for providing community-run API resources that supported generation workflow testing during development.

## Watch the demo

These clips follow the fictional project *Tidal Archives* from creation to its first saved chapter, recorded in the current application. **The demo uses preset model responses to show the workflow, not model quality.**

**01 · Create a novel: idea → story direction → review and save**

![Enter an idea, generate novel information, and confirm the result](.github/assets/readme/demo-01-create.gif)

<details>
<summary><strong>02 · Build the cast: factions, characters, and relationships</strong> (expand to play)</summary>

Generate and save core material, then explore character relationships and faction membership in the graph.

![Generate factions and characters, confirm relationships, and open the graph](.github/assets/readme/demo-02-characters.gif)

</details>

<details>
<summary><strong>03 · Plan in layers: volume → arc → scene → chapter plan</strong> (expand to play)</summary>

Plan the volumes, develop the current volume, and confirm its participants. Then manually detail the first arc, scene, and chapter plan. This example skips optional rules and items and confirms an empty volume location list.

![Follow writing progress through volume preparation, an arc, a scene, and the first chapter plan](.github/assets/readme/demo-03-planning.gif)

</details>

<details>
<summary><strong>04 · Write the first chapter: generate → review → save</strong> (expand to play)</summary>

Generate prose from the saved chapter plan, review the candidate, and save the first chapter. The full novel is still in progress.

![Generate the first chapter, review the candidate, and confirm the save](.github/assets/readme/demo-04-writing.gif)

</details>

## Install and run

The main route below uses **Windows, PowerShell, and MongoDB in Docker**. Installation downloads dependencies; AI generation also requires a model service you configure yourself.

### 1. Prepare the environment and code

Install [Python 3.13](https://www.python.org/downloads/), [Node.js 24](https://nodejs.org/en/download), [Git](https://git-scm.com/downloads), and [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/). Start Docker Desktop and wait for its engine to run. Check that `python --version`, `node --version`, and `docker compose version` print their versions. The frontend requires Node.js 20.9 or later.

```powershell
git clone https://github.com/YILING0013/AI_NovelGenerator.git
cd AI_NovelGenerator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
cd ..
```

### 2. Start a MongoDB replica set

Saving arcs, chapters, and related records requires MongoDB multi-document transactions, so **a replica set is required**. The bundled [compose.mongodb.yaml](compose.mongodb.yaml) runs MongoDB 8.0 as a single-node replica set named `rs0`, available at `127.0.0.1:27017`.

First check that another service is not using `27017` (on Windows: `netstat -ano | findstr :27017`). **An existing standalone Windows MongoDB service cannot simply be mixed with this Docker instance or started on the same port.** If you already have a writable replica set, use its connection address directly. Back up an existing standalone database before planning its conversion or a separate port. Do not delete volumes or recreate existing databases to resolve a port conflict.

From the project root:

```powershell
docker compose -f compose.mongodb.yaml up -d
docker compose -f compose.mongodb.yaml exec mongodb mongosh
```

**Only when using a new, empty data volume for the first time**, run this once inside the MongoDB shell:

```javascript
rs.initiate({ _id: "rs0", members: [{ _id: 0, host: "localhost:27017" }] })
exit()
```

Back in PowerShell:

```powershell
docker compose -f compose.mongodb.yaml ps
```

Wait until `mongodb` is **healthy**, meaning it is a writable primary. An uninitialized instance may show unhealthy; that is not a reason to erase its data. Subsequent starts need only `up -d`; do not initialize an existing replica set again.

Data persists in the named volumes `novel-generator-mongodb-data` and `novel-generator-mongodb-config`. `docker compose -f compose.mongodb.yaml stop` only stops the service. **Do not use `down -v` to remove these data volumes.**

### 3. Start the application and connect the database

Double-click **`start.bat`** in the project root and start both services in the desktop launcher. It uses the installed `.venv`; production mode builds the frontend on first use and after relevant code or configuration changes. `start.bat` does not install dependencies or MongoDB.

Open **http://127.0.0.1:3300** and go to **Settings → Database Configuration**. Choose “Replace connection,” enter and confirm the URI, then fill in the database name and save the settings:

| Field | Value for the local Docker setup |
| --- | --- |
| MongoDB URI | `mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true` |
| Database name | `novel_generator` |

The configuration file defaults `mongo_transaction_mode` to `required`. Keep this value; no manual edit is needed for a fresh installation.

Once the connection checks pass, you can create a novel. The backend defaults to `http://127.0.0.1:8200`. For a port conflict, identify the existing service before changing ports in the launcher. Closing the launcher stops the services it started; Docker manages MongoDB separately.

### 4. Configure a model and start writing

Under **Settings → LLM Provider Management**, add and enable your service type, endpoint, API key, and model, then save. Choose and save a global default Provider under **Novel Generation Workflow Configuration**. Built-in workflows provide a starting point; individual nodes can also select their own model. The endpoint must support the selected adapter, parameters depend on the provider, and the provider charges for model usage.

After creating a novel, follow **Writing Progress** to prepare core material, plan volumes and their participants, then detail arcs, scenes, and chapter plans. Review generated results before saving, or write the manuscript directly. Chapter records help review changes to characters, relationships, items, and world rules.

<details>
<summary><strong>Command-line startup (including macOS / Linux)</strong></summary>

Install the same dependencies and prepare a replica set. On macOS / Linux, create the environment with `python3 -m venv .venv`, then use `.venv/bin/python` instead of the Windows interpreter path. You do not need `start.bat`.

Start the backend from the project root:

```powershell
.\.venv\Scripts\python.exe main.py
```

Open a second PowerShell terminal for the frontend:

```powershell
cd frontend
$env:NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8200"
npm run build
npm run start -- --hostname 127.0.0.1 --port 3300
```

On macOS / Linux, the equivalent environment command is `export NEXT_PUBLIC_API_BASE="http://127.0.0.1:8200"`. Set the address before building and rebuild after changing it. For development, use `npm run dev -- --hostname 127.0.0.1 --port 3300`.

`NOVEL_GENERATOR_BACKEND_PORT` changes the backend port. `NOVEL_GENERATOR_MONGODB_URL` and `NOVEL_GENERATOR_MONGO_DATABASE_NAME` override the database settings. Restart the backend after editing its configuration file directly.

</details>

## Explore the interface

The **character and faction graph** brings relationships and membership together. Filter the graph, zoom, drag nodes, and inspect their details.

![Three characters, two factions, and their relationships in Tidal Archives](.github/assets/readme/relationships.png)

<details>
<summary><strong>Story information, characters, volume planning, and prose</strong></summary>

Novel information holds the story direction, worldbuilding, style, and target length. Character facts can be viewed at story positions. Planning develops from volumes into finer detail, while the manuscript editor provides word counts, saving, draft export, and revision history.

![Novel information and story premise](.github/assets/readme/story.png)
![Character profile and growth direction](.github/assets/readme/characters.png)
![Volume overview and plan](.github/assets/readme/volumes.png)
![First chapter manuscript with its saved status](.github/assets/readme/writing.png)

</details>

<details>
<summary><strong>Editable AI workflows and prompts</strong></summary>

Built-in workflows cover novel creation, reference material, planning, prose, and chapter checks. Edit nodes and connections on the canvas, or change prompts, inputs, outputs, and model settings. You can start writing with the built-ins before creating any custom workflow.

![Novel creation workflow canvas and connections](.github/assets/readme/workflow.png)
![Prompt configuration for an AI generation node](.github/assets/readme/node.png)

</details>

The interface supports Chinese and English, light and dark themes, and responsive layouts. These captures show the Chinese desktop interface. Built with Next.js 16, React 19, HeroUI, React Flow, FastAPI, PyMongo, and PySide6.

## Backups and upgrades

Current `main` is the rewritten application; the previous version is preserved on [`old`](https://github.com/YILING0013/AI_NovelGenerator/tree/old). Their data structures differ, so use separate databases. Book archives now export v14; older application versions cannot read these archives.

| Data | Location |
| --- | --- |
| Novels, characters, plans, manuscripts, and writing records | Configured MongoDB database |
| Database and model configuration, including API keys | `user_data/config/config.yaml` |
| Custom workflows and uploaded covers | `user_data/task_flows/`, `user_data/static/` |
| Exports, migration backups, and records | `user_data/exports/`, `user_data/backups/`, `user_data/migrations/` |
| Launcher ports | `user_data/config/launcher_settings.json` |
| Unsaved manuscript drafts | Local storage for the current browser and site address |

The default user directory is `user_data/` under the project. Set `NOVEL_GENERATOR_USER_DATA_DIR` to use a separate directory.

- **Before updating:** verify pending saves, export unsaved drafts, stop the application, and back up MongoDB and user files separately. Copying `user_data` or exporting one book is not a complete backup. Update the code, reinstall dependencies, and rebuild the frontend yourself.
- **At startup:** migration handles supported old file locations and data only. Recognized, unchanged built-in workflows using the latest default revision are backed up and upgraded; custom workflows and pinned older revisions are preserved. The application does not install MongoDB, download new code, or convert arbitrary historical databases.
- **If migration fails:** keep the original files, backups, and migration records, and resolve the reported conflict. Do not delete `user_data` or the database to retry. Generation recovery depends on the original backend process and page; refreshing or restarting does not guarantee recovery, and retrying a model call may incur another charge.

This application is intended for local use and has no public-facing user authentication. The bundled MongoDB has no password and binds only to the loopback address. Do not expose either directly to the internet. AI operations send the necessary story context to your configured model service.

## Feedback and contributions

Report problems through [Issues](https://github.com/YILING0013/AI_NovelGenerator/issues/new/choose), including the version, environment, reproduction steps, and redacted screenshots or logs. Read the [contribution guide](.github/CONTRIBUTING.md) before contributing. Licensed under [GNU AGPL v3.0](LICENSE).

## Star History

[![GitHub star history for YILING0013/AI_NovelGenerator](https://api.star-history.com/svg?repos=YILING0013/AI_NovelGenerator&type=Date)](https://www.star-history.com/?repos=YILING0013%2FAI_NovelGenerator&type=date&legend=top-left)
