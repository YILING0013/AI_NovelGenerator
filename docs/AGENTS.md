# AGENTS.md - docs

**Generated:** 2026-02-17
**Module:** Product, developer, and archival documentation

## OVERVIEW
`docs/` mixes active manuals/guides with a large archive of historical root-cause and fix reports. Prioritize current manuals first, then consult archive artifacts for incident context.

## STRUCTURE
```
docs/
├── USER_MANUAL.md / API_REFERENCE.md / DEPLOYMENT.md  # Active user/dev docs
├── DEVELOPMENT.md / DOCUMENTATION_INDEX.md            # Contributor navigation
├── complete_workflow_v3.md / MIGRATION_GUIDE.md       # Process and migration notes
└── archive/root_reports/                               # Historical investigations
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| User operation questions | `USER_MANUAL.md` | GUI and workflow usage |
| Interface details | `API_REFERENCE.md` | Module/API behavior |
| Setup and release workflow | `DEVELOPMENT.md`, `DEPLOYMENT.md` | Dev + deployment guidance |
| Document navigation | `DOCUMENTATION_INDEX.md` | Fast entrypoint by role |
| Past bug investigations | `archive/root_reports/*.md` | Incident history and fixes |

## CONVENTIONS
- Keep user-facing guidance in top-level docs, not in `archive/`.
- Place postmortems and one-off fix reports under `archive/root_reports/`.
- Update docs when behavior changes in `main.py`, `ui/`, or `novel_generator/`.

## ANTI-PATTERNS
- Do not treat archived reports as authoritative current behavior.
- Do not duplicate the same procedure across multiple active docs.
- Do not leave command examples unverified after dependency/runtime changes.

## NOTES
- `docs/archive/` is high-volume and useful for historical debugging patterns.
- Current source of truth for architecture boundaries remains root `AGENTS.md` plus module AGENTS files.
