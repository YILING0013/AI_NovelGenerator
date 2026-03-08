# AGENTS.md - novel_generator

**Generated:** 2026-01-27
**Module:** Core business logic for novel generation

## OVERVIEW
Core module implementing novel generation pipeline: architecture → blueprint → chapter → finalization.

## STRUCTURE
```
novel_generator/
├── __init__.py              # Public API exports
├── architecture.py          # Novel architecture generation
├── blueprint.py             # Chapter blueprint generation
├── chapter.py               # Chapter content generation
├── finalization.py           # Chapter polishing/enrichment
├── knowledge.py             # Knowledge base import
├── vectorstore_utils.py      # ChromaDB vector storage
├── schemas.py               # Pydantic schemas
├── schema_validator.py      # Schema validation
├── error_handler.py         # Centralized error handling
├── pipeline.py              # Generation pipeline orchestration
├── state_manager.py         # Generation state management
├── analyzers/               # Analysis modules
├── core/                    # Core blueprint generation
└── validators/              # Blueprint validation
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Architecture | architecture.py | Novel structure, character list |
| Blueprint | blueprint.py, core/blueprint.py | Chapter-level planning |
| Chapter generation | chapter.py | Draft generation |
| Finalization | finalization.py | Text enrichment |
| Validation | validators/ | Multiple validation rules |
| Consistency | consistency_checker.py | Cross-chapter coherence |
| State | state_manager.py | Track generation progress |

## CORE EXPORTS (__init__.py)
- Novel_architecture_generate
- Chapter_blueprint_generate (Strict)
- generate_chapter_draft
- finalize_chapter
- import_knowledge_file
- schemas, schema_validator
- error_handler
- pipeline_interfaces, pipeline

## CONVENTIONS
- **Pipeline order**: architecture → blueprint → chapter → finalization
- **Validation**: Multiple validators run in sequence
- **Error handling**: Use error_handler for consistent error reporting
- **State management**: state_manager tracks progress for progressive generation

## ANTI-PATTERNS
- Do NOT skip blueprint validation
- Do NOT generate chapters without architecture
- Do NOT ignore consistency warnings
- Do NOT modify schemas directly - use schema_validator
- Do NOT bypass error_handler exceptions

## UNIQUE STYLES
- Progressive generation: supports incremental chapter generation
- Blueprint repair: automatic fixing of invalid blueprint structures
- Multiple validation layers: structure, consistency, duplicate detection
- Vector store integration: ChromaDB for knowledge base queries
- Quality loop: text_optimizer with multiple critique agents

## NOTES
- `blueprint.py` has multiple versions: main file + core/blueprint.py
- Validators are modular - each handles specific validation rules
