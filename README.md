<div align="center">

# AI Novel Generator

### Turn an idea into a story, one chapter at a time.

Story planning · Characters & worlds · Chapter writing · Editable AI workflows

**English** · [简体中文](README.zh-CN.md)

[Take a look](#a-tour-of-the-workspace) · [Workflows & custom nodes](#make-the-ai-workflow-your-own) · [Run locally](#run-locally) · [Report an issue](https://github.com/YILING0013/AI_NovelGenerator/issues/new/choose)

</div>

![Chapter workspace with a scene and chapter directory beside the manuscript editor](.github/assets/readme/writing.png)

Starting a novel is one thing. Keeping its plot, characters, and world consistent as it grows is another.

AI Novel Generator brings that work into a local writing application. Develop the story, break it into volumes, arcs, scenes, and chapters, and keep your characters, locations, factions, items, and world rules nearby. AI can help with ideas, planning, and drafts. You can edit its candidates before deciding what to save.

**Built for writers who want to shape a story as they go, with control over how AI takes part.**

> Current `main` contains the rewritten application. The previous version is preserved on [`old`](https://github.com/YILING0013/AI_NovelGenerator/tree/old) for reference. Their data structures differ: back up legacy data and use a separate database for this version.

All screenshots show the running application with a fictional demo novel, *Letters from the Fog Harbor*, captured at a desktop **16:10** ratio. They illustrate the interface, not model output quality. The interface also adapts to mobile screens. Screenshots use Chinese; the application supports English too.

## A tour of the workspace

Start with the built-in workflows, then change the parts that matter to your writing.

| What you want to do | Where to start |
| --- | --- |
| Develop a loose idea | Create a novel and work out its core, plot, tone, and world |
| Expand an existing outline | Volumes → arcs → scenes → chapter plans |
| Keep a growing cast straight | Character cards, factions, relationship graphs, and chapter records |
| Control how AI writes | Task workflows, node prompts, source material, and model settings |
| Get straight to writing | Use a built-in workflow and edit in the chapter workspace |

### 01 / Give the story a clear direction

The bookshelf keeps your projects together. Inside a novel, the information page holds its core idea, main plot, introduction, worldbuilding, style, point of view, and intended length.

Write these yourself or ask AI to create or revise them. Establishing what the protagonist wants, what stands in the way, and where the story is heading gives later planning a shared direction.

![Novel information, including the story premise, plot, world, and writing style](.github/assets/readme/story.png)

### 02 / Expand the story with a Snowflake-inspired approach

The project borrows the Snowflake Method's idea of expanding a story from a clear core. The built-in novel creation workflow first expands an idea into a compressed story, then extracts the premise and core seed and develops the novel information. Its core-seed prompt explicitly uses the first step of the Snowflake Method.

From there, move through **volumes → arcs → scenes → chapter plans → prose**, stopping to revise at any level.

| Level | The question it answers | Example from the demo novel |
| --- | --- | --- |
| Story core | Who faces what problem, and what must they do? | A restorer receives a letter from her missing mother and investigates a ship that carries memories |
| Volume | What major change should this part achieve? | Find the ship's route and evidence that her mother may still be alive |
| Arc | Which conflicts move that change forward? | Investigate disappearances and connect the letters to the harbor bells |
| Scene | Where does something happen, and what do people do? | A letter slips under the workshop door on a rainy night |
| Chapter plan | Where should this chapter end, and what must it contain? | Recognize the handwriting, notice the old postmark, end with a distant bell |
| Prose | How will the reader experience those events? | Begin with a stopped clock, rain, and paper that is strangely warm |

![Volume planning with goals, conflicts, turning points, and starting and ending states](.github/assets/readme/volumes.png)

Volume planning also organizes the characters, factions, and locations that will be used in that part of the book. Arcs and scenes carry the higher-level goals forward, giving each generation step something concrete to build on.

### 03 / Write, revise, and keep earlier drafts

The chapter workspace keeps the directory, plan, manuscript, and chapter records together. Select a chapter, review its goals and beats, then write it yourself or request an AI draft.

- **Chapter plans** hold goals, starting and ending states, key beats, and things to include or avoid.
- **The manuscript editor** lets you edit, save, check the word count, and export the current draft.
- **Revision history** lets you inspect earlier drafts, compare changes, and restore a saved version.
- **Chapter records** help check character psychology, relationships, item ownership, and world rules before you confirm relevant changes.

Review and edit generated candidates before saving them. As the manuscript grows, confirmed records help track what has actually happened at a particular point in the story.

### 04 / Keep your cast and world within reach

Character cards go beyond names and appearances. They hold desires, fears, conflicts with the main plot, growth directions, and story roles. Character information can be confirmed and read at the beginning of the story, the start of a volume, or before and after a chapter.

![Character management with a cast list, character design, and information tied to story positions](.github/assets/readme/characters.png)

| Area | What it helps you organize |
| --- | --- |
| Characters | Profiles, growth plans, information at different story positions, and relationships |
| Factions | Goals, public stances, hidden motives, resources, and character membership |
| Locations | Places and the locations used in a particular volume |
| Items | Important objects, their owners, and transfers during the story |
| World rules | What is possible, what is restricted, and what it costs |
| Foreshadowing | Clues, related story records, and their later payoff |
| Relationship graph | Visual connections among characters and factions |
| Novel assistant | Finding material in the current book, discussing questions, and reviewing proposed edits |

## Make the AI workflow your own

Writing a chapter can involve several steps: collect the current plan and related material, prepare the context, then generate a candidate manuscript. These steps are available on an editable workflow canvas.

Open the workflow for an AI action to see what it reads, which step runs next, and which results pass between nodes. Built-in workflows cover novel creation, characters and factions, volume planning, arcs, scenes, chapters, and post-chapter checks.

![Workflow canvas with a node library, generation steps, and data connections](.github/assets/readme/workflow.png)

### What can you customize?

Add nodes, change connections, edit prompts, define input and output fields, and choose model settings. Different AI nodes in the same workflow can use different models.

| Node | What it does |
| --- | --- |
| Input / Page context | Accept the current request or read material from the novel and writing position |
| Constant / Text template | Supply reusable instructions or insert earlier results into a prompt |
| Compose fields | Assemble several inputs into the fields needed by the next step |
| AI generation | Call a selected model for text or structured output |
| AI context preparation | Look up and select material from the current novel for later steps |
| Condition / Merge | Choose a path based on an input, then collect branch results |
| Subflow / For each | Reuse a group of steps or run them for each item in a collection |
| Output | Return the final candidate to the original page for review and saving |

Customization means combining these node types into your own generation process. More involved workflows still require understanding fields and JSON structures.

### An example: change how the story core is written

The built-in core-seed node reads the plot, genre, tone, audience, and intended length, then condenses them into a clear story premise. You could ask it to make the conflict come from a character's choice, preserve a gentler tone, or use a different model just for this step.

![Node prompt editor with input-field tokens and the Snowflake core-seed prompt](.github/assets/readme/node.png)

A practical starting point:

1. Copy an existing workflow in the scheme panel and give it a name.
2. Add a node from the library or select an existing one.
3. Use **data connections** to pass values and **execution connections** to set order and branches.
4. Adjust prompts, fields, models, and generation parameters.
5. Validate and save the workflow, then use it from the original AI action.

The editor also supports undo, redo, scheme revisions, and context previews that do not call a model. Previews help check inputs and connections; actual generation quality still depends on the model and context.

## Run locally

The application has a browser interface, a Python backend, and MongoDB storage. Windows users can manage the services with the desktop launcher, or start them in separate terminals.

### Requirements

| Dependency | Requirement |
| --- | --- |
| Python | 3.13 or 3.14, with a recent patch release |
| Node.js and npm | Node.js 20.9 or later, using a maintained release |
| MongoDB | A **replica set**; a single-node setup is provided below |
| Docker | Needed for the bundled MongoDB setup; optional with an existing replica set |
| Model service | Your own API key, endpoint, and model name |

Some writing operations update multiple records in a transaction. A standalone MongoDB instance does not meet the requirements of the complete writing workflow.

### 1. Download and install

Run these commands in PowerShell:

```powershell
git clone https://github.com/YILING0013/AI_NovelGenerator.git
cd AI_NovelGenerator
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
cd ..
```

On macOS and Linux, the virtual environment interpreter is `.venv/bin/python`. See [manual startup](#manual-startup) below.

### 2. Prepare MongoDB

If you already have a MongoDB replica set, configure its connection address directly. For the bundled Docker setup, first make sure local port `27017` is available:

```powershell
docker compose -f compose.mongodb.yaml up -d
docker compose -f compose.mongodb.yaml exec mongodb mongosh
```

Inside the MongoDB shell, run:

```javascript
rs.initiate({
  _id: "rs0",
  members: [{ _id: 0, host: "localhost:27017" }]
})
exit()
```

Run `rs.initiate` **only once for a new data volume**. Back in PowerShell, run `docker compose -f compose.mongodb.yaml ps` and check that the service is `healthy`.

On first setup, copy `backend/config/config_default.yaml` to `backend/config/config.yaml`. If your local configuration already exists, edit it instead of replacing your saved model settings.

Set these values:

```yaml
mongodb_url: "mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true"
mongo_database_name: "novel_generator"
mongo_transaction_mode: "required"
```

The bundled configuration uses named volumes, publishes its port only on `127.0.0.1`, and has no database password. Restart the backend after changing its database connection.

### 3. Start the application

On Windows, double-click **`start.bat`**, then start the services in the desktop launcher. The launcher manages ports, logs, and service shutdown. Production mode builds the frontend on first use and after relevant source or configuration changes.

| Service | Default address |
| --- | --- |
| Writing interface | <http://127.0.0.1:3300> |
| Backend | <http://127.0.0.1:8200> |
| API documentation | <http://127.0.0.1:8200/docs> |

Closing the launcher stops the services it started. Stop services before changing ports. If a port is occupied, identify the existing process before starting another instance.

### 4. Configure a model and write a first chapter

Open **Settings**, enter your provider's API key, endpoint, and model name, and enable that configuration. The project includes adapters for OpenAI, DeepSeek, Gemini, Claude, and corresponding compatible endpoints. Supported parameters depend on the adapter and provider.

For a first try, use a small demo project:

1. Create a novel, enter the idea and intended length, and confirm its information.
2. Prepare core factions, characters, relationships, and world rules, following the progress panel.
3. Plan the volumes, develop the current volume, and confirm its characters, factions, and locations.
4. Break it into arcs, scenes, and chapter plans, then generate or write the first chapter.
5. Edit and save the manuscript, then review relevant post-chapter changes.

The default workflows provide a starting point; you do not need to configure every node before writing. No API keys are included, and model usage is billed by your configured provider.

### Manual startup

From the project root, start the backend:

```powershell
.\.venv\Scripts\python.exe main.py
```

In another terminal, start the frontend:

```powershell
cd frontend
npm run build
npm run start -- --hostname 127.0.0.1 --port 3300
```

For a custom backend address, set `NEXT_PUBLIC_API_BASE` before building. In PowerShell, for example: `$env:NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8200"`. The desktop launcher sets this address for the ports it manages.

`NOVEL_GENERATOR_MONGODB_URL` and `NOVEL_GENERATOR_MONGO_DATABASE_NAME` can override the corresponding database settings.

## Data, backups, and upgrades

Novel data lives in your configured MongoDB database and local files. AI actions send relevant context to the model provider you choose. Running the application locally does not mean model inference also happens on your computer.

| What to back up | Location |
| --- | --- |
| Novels, characters, plans, and writing records | MongoDB |
| Model settings and API keys | `backend/config/config.yaml` |
| Custom workflows and other runtime state | `data/` |
| Uploaded assets, including covers | `static/` |

Back up and stop services before updating code, reinstalling dependencies, and rebuilding the frontend. Keep the legacy and rewritten versions on different databases; direct migration of legacy data is not promised.

The application is intended for local use and has no public-facing user authentication. Do not directly expose it or an unauthenticated MongoDB deployment to the internet. Remove credentials, personal paths, and private manuscripts from public reports.

<details>
<summary><strong>Common questions</strong></summary>

**The page opens, but saving an arc or chapter fails.** Check that MongoDB is initialized as a writable replica set, then verify `mongodb_url` and `mongo_transaction_mode`. Restart the backend after configuration changes.

**Why is an AI action unavailable?** Follow the prerequisites shown on the page. Changes to higher-level plans, plot, or related material may need to be reviewed and confirmed first.

**Can I use a custom API endpoint?** Yes, but it must support the request format required by the selected adapter. Models differ in supported output formats and parameters.

**Does it support mobile, dark mode, or English?** Yes: responsive layouts, light and dark themes, and Chinese and English are included. This guide focuses on the desktop workspace.

**Where is the previous version?** On [`old`](https://github.com/YILING0013/AI_NovelGenerator/tree/old). Earlier issues and PRs were closed for the version transition; this does not mean every historical report was individually fixed.

</details>

## Project structure

```text
backend/               API, data access, generation logic, and built-in prompts
frontend/              Next.js writing interface
desktop_launcher/      Desktop launcher and local service management
.github/               Collaboration templates and README screenshots
main.py                Backend entry point
launcher.py            Launcher entry point
start.bat              Windows startup script
compose.mongodb.yaml   Local single-node MongoDB replica set
requirements.txt       Python dependencies
```

Built with **Next.js 16, React 19, HeroUI, React Flow, FastAPI, PyMongo, MongoDB, and PySide6**.

## Contributing

Use the [Issue forms](https://github.com/YILING0013/AI_NovelGenerator/issues/new/choose) for reproducible problems and ideas. Include your version, environment, reproduction steps, expected and actual results, and redacted screenshots or logs.

Read the [contribution guide](.github/CONTRIBUTING.md) before opening a PR. Work from current `main`, explain the problem you are solving, and describe your validation. If a legacy issue still applies, open a current-version report and link the earlier discussion.

Licensed under the **GNU Affero General Public License v3.0**. See [LICENSE](LICENSE) for the full text.
