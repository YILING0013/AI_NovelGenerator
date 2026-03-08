# AGENTS.md - scripts

**Generated:** 2026-02-17
**Module:** Operational one-off scripts for repair, verification, and analysis

## OVERVIEW
`scripts/` contains ad-hoc maintenance utilities for directory repair, blueprint fixes, chapter checks, and diagnostics. Treat scripts as operator tools, not core runtime API.

## STRUCTURE
```
scripts/
├── cleanup_*.py / fix_*.py / repair_*.py   # Directory and content repair
├── analyze_*.py / diagnose_*.py            # Investigation and quality analysis
├── verify_*.py / check_*.py / test_*.py    # Validation and smoke checks
├── generate_*.py                            # Targeted generation helpers
└── llm_logs/                                # Script-produced logs
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Directory cleanup | `cleanup_directory.py`, `clean_novel_directory.py` | File-system-level cleanup helpers |
| Blueprint repair | `auto_repair_blueprints.py`, `fix_blueprint_issues.py` | Repair low-quality or malformed blueprints |
| Parser/format checks | `verify_parser.py`, `finalize_directory_format.py` | Validate/normalize directory structure |
| Chapter quality diagnostics | `chapter_completeness_analyzer.py`, `diagnose_low_score.py` | Root-cause analysis for weak chapters |
| Prompt debugging | `debug_prompt.py`, `verify_prompts.py` | Prompt-level troubleshooting |

## CONVENTIONS
- Prefer reading `config.json` over embedding runtime constants.
- Use project-relative paths; avoid hardcoded machine-specific absolute paths.
- Keep scripts idempotent where possible (safe to rerun).
- Log explicit before/after counts when mutating files.

## ANTI-PATTERNS
- Do not run destructive cleanup scripts without backup files.
- Do not treat scripts here as canonical production pipeline behavior.
- Do not commit scripts with real API keys or local absolute user paths.

## NOTES
- Many scripts are historical incident tooling; check `docs/archive/` for corresponding reports.
- Prefer `main.py` + UI workflow for standard usage; use `scripts/` for targeted ops only.
