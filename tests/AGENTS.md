# AGENTS.md - tests

**Generated:** 2026-01-27
**Module:** Test suite for novel_generator

## OVERVIEW
Unit and integration tests covering core novel generation logic, blueprint validation, and pipeline orchestration.

## STRUCTURE
```
tests/
├── __init__.py
├── conftest.py                     # Pytest fixtures
├── test_blueprint_indexer.py       # Blueprint indexing tests
├── test_chapter_utils.py           # Chapter utility tests
├── test_progressive_generator.py  # Progressive generation tests
├── test_root_cause_fixes.py        # Regression tests
├── core_modules/                   # Core module tests
├── data/                           # Test data fixtures
├── dummy_novel/                    # Sample novel for testing
├── fixtures/                       # Shared test fixtures
├── gui/                            # GUI tests
├── integration/                   # Integration tests
└── unit/                           # Unit tests
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Test fixtures | conftest.py | Shared pytest fixtures |
| Blueprint tests | test_blueprint_indexer.py | Blueprint parsing/indexing |
| Chapter tests | test_chapter_utils.py | Chapter utilities |
| Progressive gen | test_progressive_generator.py | Incremental generation |
| Regression | test_root_cause_fixes.py | Bug regression tests |
| Integration | integration/ | End-to-end flows |
| Unit | unit/ | Isolated component tests |

## CONVENTIONS
- **Framework**: pytest
- **Fixtures**: Define in conftest.py for reuse
- **Test naming**: test_<function_name>
- **Data**: Use data/ for test fixtures
- **Isolation**: Unit tests isolated, integration tests may depend on fixtures

## ANTI-PATTERNS
- Do NOT use production data in tests
- Do NOT hardcode paths - use fixtures
- Do NOT skip tests without comment
- Do NOT mock LLM calls in integration tests

## UNIQUE STYLES
- Dummy novel: complete test novel in dummy_novel/
- Root cause tests: regression suite for specific bugs
- Modular structure: core_modules, integration, unit separation

## NOTES
- Pytest configuration in pytest.ini
- Tests cover: blueprint validation, chapter generation, consistency
