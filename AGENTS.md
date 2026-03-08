# AGENTS.md - AI Novel Generator

**Generated:** 2026-02-17
**Project:** AI小说生成工具 (CustomTkinter + multi-LLM novel pipeline)

## OVERVIEW
Desktop novel-generation app with a clear split between UI (`ui/`) and generation engine (`novel_generator/`). Runtime flow is GUI-first: `main.py` -> `ui/main_window.py` -> `ui/generation_handlers.py` -> `novel_generator/*`.

## STRUCTURE
```
./
├── main.py                  # GUI entrypoint
├── config_manager.py        # JSON config load/save + defaults
├── llm_adapters.py          # Provider adapters/factory
├── novel_generator/         # Core pipeline and generation logic
├── ui/                      # Tabbed CustomTkinter interface
├── tests/                   # pytest + unittest-style coverage
├── scripts/                 # One-off ops/repair/analysis scripts
├── docs/                    # Manuals + archival investigation reports
├── config/                  # JSON rule packs
├── knowledge/               # KB helper modules
├── security/                # Security utilities
└── templates/               # Template logic files
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| App startup | `main.py` | Creates CTk app and launches GUI |
| Main window wiring | `ui/main_window.py` | Tab creation + callback registration |
| UI -> backend bridge | `ui/generation_handlers.py` | Invokes generation APIs |
| Core API surface | `novel_generator/__init__.py` | Lazy-exported public functions |
| Pipeline orchestration | `novel_generator/pipeline.py` | Stage-based generation flow |
| Config persistence | `config_manager.py` | Reads/writes `config.json` |
| LLM provider abstraction | `llm_adapters.py` | OpenAI/Gemini/Azure/etc adapters |
| Operational scripts | `scripts/` | Cleanup, repair, diagnostics, batch helpers |
| Tests | `tests/` | Core + regression + fixture-driven tests |

## CODE MAP
- Core flow: `Novel_architecture_generate` -> `Chapter_blueprint_generate` -> `generate_chapter_draft` -> `finalize_chapter`
- Core subdomains: `architecture.py`, `blueprint.py`, `chapter.py`, `finalization.py`, `knowledge.py`, `vectorstore_utils.py`
- Pipeline abstractions: `pipeline_interfaces.py`, `pipeline.py`
- Supporting modules: `schemas.py`, `schema_validator.py`, `error_handler.py`

## CONVENTIONS
- Naming: PascalCase classes, snake_case functions, UPPER_CASE constants
- Public functions should keep type hints and docstrings
- Keep UI-only logic in `ui/`; keep generation/business logic in `novel_generator/`
- Prefer config-driven behavior (`config.json`) over hardcoded runtime values

## ANTI-PATTERNS
- Never commit secrets/API keys
- Do not bypass validation/consistency stages in generation flow
- Do not block UI thread for long-running generation tasks
- Do not make root-level refactors while shipping targeted bugfixes

## UNIQUE STYLES
- Very large centralized prompt bank (`prompt_definitions.py`)
- Heavy historical/debug artifacts in `docs/archive/` and root report files
- Progressive generation and blueprint-repair workflow is a first-class pattern
- Knowledge retrieval/vectorstore integration is part of chapter generation path

## COMMANDS
```bash
# Install dependencies
pip install -r requirements.txt

# Run app
python main.py

# Run tests
pytest tests/

# Build executable
pyinstaller main.spec
```

## SUBMODULE AGENTS
- `novel_generator/AGENTS.md`
- `ui/AGENTS.md`
- `tests/AGENTS.md`
- `scripts/AGENTS.md`
- `docs/AGENTS.md`

## NOTES
- Large generated output/log trees (notably `wxhyj/`) dominate file count; treat as runtime artifacts, not source architecture.
- Python 3.14 currently triggers dependency warnings in parts of the LLM/vector stack; Python 3.12 environment is safer for reproducible runs.
