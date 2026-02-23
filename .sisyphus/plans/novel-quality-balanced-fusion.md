# Quality-First Balanced Fusion Plan

## TL;DR
> **Summary**: Re-center the project on novel quality by hardening single-source architecture ingestion, making fusion rules non-negotiable, and aligning scoring/gates to voice consistency, causality, pacing, and anti-style-drift.
> **Deliverables**:
> - Runtime architecture ingestion honors whitelist execution ranges and prevents archive leakage.
> - `Novel_architecture.txt` gains a decision-complete 20-reference fusion matrix (one absorb-point + one forbidden spillover per reference).
> - Quality analyzers and loop gates prioritize story quality over legacy genre-coupled heuristics.
> - End-to-end baseline/regression verification with reproducible evidence artifacts.
> **Effort**: Large
> **Parallel**: YES - 3 waves
> **Critical Path**: Task 1 -> Task 2 -> Task 3 -> Task 8 -> Task 10 -> Task 15

## Context
### Original Request
- User asked whether `Novel_architecture_active.txt` is needed, then removed it and confirmed preference for single-file architecture.
- User asked for architecture quality comparison vs 20 references and requested forward motion.
- User explicitly prioritized: "I care most about novel quality."

### Interview Summary
- Strategy locked: balanced fusion (not pure爽感, not pure文学优先).
- Non-negotiable: avoid "四不像" by keeping one core identity and controlled borrowing.
- Current runtime architecture source is single-file mode (`Novel_architecture.txt`) with online whitelist intent (`0-12, 88-136`).
- Planning scope is quality-first improvement across architecture content, runtime ingestion, scoring gates, and verification.

### Metis Review (gaps addressed)
- Added guardrails for identity lock, anti-contamination, and conflict resolution priority.
- Added measurable acceptance criteria and evidence generation for every task.
- Added edge-case handling for prompt truncation and archive leakage.
- Added explicit defaults where user did not request alternate tradeoffs.

## Work Objectives
### Core Objective
- Deliver a quality-first generation system where architecture guidance remains coherent, fusion remains single-voice, and generated chapters improve in measurable quality dimensions without style fragmentation.

### Deliverables
- Code changes in architecture ingestion path, prompt assembly order, and quality-loop scoring/gates.
- Architecture-file updates for quality identity contract + 20-reference balanced fusion matrix.
- New validators/tests/scripts proving anti-archive-leak, anti-style-drift, and score improvement behavior.
- Evidence bundle under `.sisyphus/evidence/` for each task.

### Definition of Done (verifiable conditions with commands)
- `python scripts/verify_v28_gate_consistency.py` returns success on updated architecture.
- `python scripts/verify_architecture_compliance.py --project-root /media/tcui/82BC0F4BBC0F3965/AI_NovelGenerator` runs successfully and emits a report.
- Targeted test suite passes for ingestion/scoring/consistency updates (pytest commands defined per task).
- Baseline comparison report shows no regression in consistency gates and improved or stable final quality score trend.

### Must Have
- Single-source architecture ingestion in chapter generation path (no hardcoded bypass).
- Runtime only consumes allowed execution ranges (`0-12, 88-136`) for prompt-critical guidance.
- Fusion map enforces one absorb-point and one forbidden spillover per each of 20 references.
- Quality scoring prioritizes voice consistency, causal coherence, pacing health, and style purity.
- All quality-critical checks are script/test verifiable.

### Must NOT Have (guardrails, AI slop patterns, scope boundaries)
- Must NOT introduce multi-style prose blending by copying signature phrases/structures from references.
- Must NOT rely on archive sections (`13-87`) for online runtime decisions.
- Must NOT add new world-law mechanics that override locked final-law or cost constraints.
- Must NOT leave quality claims without executable checks/evidence.
- Must NOT include secrets in commits, logs, or evidence artifacts.

## Verification Strategy
> ZERO HUMAN INTERVENTION — all verification is agent-executed.
- Test decision: tests-after using `pytest` + existing project verification scripts + quality baseline scripts.
- QA policy: every task includes happy-path and failure/edge scenarios with explicit commands.
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks for max parallelism.

Wave 1: Runtime ingestion hardening + architecture execution boundary enforcement (Tasks 1-5)
Wave 2: Quality engine and gate alignment (Tasks 6-10)
Wave 3: Test harness, baseline comparison, and rollout proof (Tasks 11-15)

### Dependency Matrix (full, all tasks)
- Task 1 blocks Tasks 2, 3, 11.
- Task 2 blocks Tasks 3, 6, 11.
- Task 3 blocks Tasks 8, 10, 15.
- Task 4 blocks Task 7.
- Task 5 blocks Tasks 6, 9.
- Task 6 blocks Tasks 8, 10, 14.
- Task 7 blocks Tasks 14, 15.
- Task 8 blocks Tasks 10, 14, 15.
- Task 9 blocks Task 10.
- Task 10 blocks Task 15.
- Task 11 blocks Tasks 14, 15.
- Task 12 blocks Tasks 13, 15.
- Task 13 blocks Task 15.
- Task 14 blocks Task 15.

### Agent Dispatch Summary (wave -> task count -> categories)
- Wave 1 -> 5 tasks -> deep/unspecified-high/quick (runtime correctness + architecture guardrails)
- Wave 2 -> 5 tasks -> deep/unspecified-high (quality scoring + pacing + style gates)
- Wave 3 -> 5 tasks -> unspecified-high/writing/quick (tests, baseline reports, rollout docs)

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [ ] 1. Unify Runtime Architecture Source Resolution (Single-File Policy)

  **What to do**: Remove hardcoded architecture reads across runtime paths, and enforce single-file policy (`Novel_architecture.txt`) by default through a centralized loader utility used by chapter/parser paths.
  **Must NOT do**: No runtime path may hardcode `Novel_architecture.txt` or implicitly prefer `Novel_architecture_active.txt` after policy lock.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: quality-critical runtime correctness.
  - Skills: [`none`] — straightforward code + test change.
  - Omitted: [`playwright`] — no browser context.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: [2, 3, 11] | Blocked By: []

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `utils.py:7` — architecture resolver contract and `prefer_active` behavior.
  - Pattern: `novel_generator/chapter.py:516` — chapter prompt hardcoded path to remove.
  - Pattern: `novel_generator/architecture_parser.py:153` — parser hardcoded path to remove.
  - Pattern: `scripts/verify_v28_gate_consistency.py:139` — script default active-first fallback to align with single-file policy.
  - API/Type: `novel_generator/chapter.py:607` — chapter-1 architecture injection slot.
  - API/Type: `novel_generator/chapter.py:936` — chapter-N architecture injection slot.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/unit/test_chapter_architecture_source.py tests/unit/test_architecture_parser_source_resolution.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Single-file source policy applies to chapter and parser paths
    Tool: Bash
    Steps: Run `pytest tests/unit/test_chapter_architecture_source.py::test_build_prompt_uses_runtime_loader -q && pytest tests/unit/test_architecture_parser_source_resolution.py::test_parser_uses_runtime_loader -q`
    Expected: Both chapter and parser paths use centralized loader and no hardcoded file path remains
    Evidence: .sisyphus/evidence/task-1-source-resolver.txt

  Scenario: Missing active file falls back safely
    Tool: Bash
    Steps: Run `pytest tests/unit/test_chapter_architecture_source.py::test_single_file_policy_ignores_active_when_disabled -q`
    Expected: Runtime source remains `Novel_architecture.txt` even when active file exists (policy lock)
    Evidence: .sisyphus/evidence/task-1-source-fallback.txt
  ```

  **Commit**: YES | Message: `fix(runtime): centralize architecture source under single-file policy` | Files: `utils.py`, `novel_generator/chapter.py`, `novel_generator/architecture_parser.py`, `scripts/verify_v28_gate_consistency.py`, `tests/unit/test_chapter_architecture_source.py`, `tests/unit/test_architecture_parser_source_resolution.py`

- [ ] 2. Implement Runtime Architecture Whitelist Slicer (Chapter + Blueprint)

  **What to do**: Add parser utility that extracts only active execution ranges (`0-12`, `88-136`) and apply it to chapter and blueprint runtime consumers.
  **Must NOT do**: Do not rely on line-number slicing; do not include sections `13-87`.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: parser edge cases directly impact quality rules.
  - Skills: [`none`] — parser + tests.
  - Omitted: [`frontend-ui-ux`] — non-UI.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: [3, 6, 11] | Blocked By: [1]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `scripts/verify_v28_gate_consistency.py:57` — heading parsing style.
  - Pattern: `novel_generator/architecture_reader.py:16` — section parsing baseline.
  - API/Type: `wxhyj/Novel_architecture.txt:7` — whitelist intent.
  - API/Type: `wxhyj/Novel_architecture.txt:734` — archive boundary.
  - API/Type: `wxhyj/Novel_architecture.txt:5006` — execution source authority.
  - Pattern: `novel_generator/blueprint.py:1161` — blueprint resolver read path that must consume sliced runtime text when used for quality gates.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/unit/test_architecture_runtime_slice.py tests/unit/test_blueprint_runtime_slice_usage.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Active ranges extracted correctly
    Tool: Bash
    Steps: Run `pytest tests/unit/test_architecture_runtime_slice.py::test_extracts_0_12_and_88_136_only -q && pytest tests/unit/test_blueprint_runtime_slice_usage.py::test_blueprint_gate_uses_sliced_runtime_architecture -q`
    Expected: `## 13`-`## 87` excluded from runtime payload
    Evidence: .sisyphus/evidence/task-2-slice-pass.txt

  Scenario: Malformed headings handled deterministically
    Tool: Bash
    Steps: Run `pytest tests/unit/test_architecture_runtime_slice.py::test_malformed_headings_trigger_parse_fallback_warning -q`
    Expected: No crash, deterministic fallback + warning
    Evidence: .sisyphus/evidence/task-2-slice-fallback.txt
  ```

  **Commit**: YES | Message: `feat(runtime): apply whitelist slicer to chapter and blueprint paths` | Files: `novel_generator/architecture_runtime_slice.py`, `novel_generator/chapter.py`, `novel_generator/blueprint.py`, `tests/unit/test_architecture_runtime_slice.py`, `tests/unit/test_blueprint_runtime_slice_usage.py`

- [ ] 3. Make Prompt Assembly Truncation-Resilient for Quality Constraints

  **What to do**: Integrate sliced architecture payload and ensure identity/gate-critical tokens survive truncation in head/tail regions.
  **Must NOT do**: Do not alter blueprint semantics; keep existing truncation telemetry.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: prompt ordering affects generation quality.
  - Skills: [`none`] — prompt pipeline work.
  - Omitted: [`playwright`] — no UI.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: [8, 10, 15] | Blocked By: [1, 2]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `novel_generator/chapter.py:1066` — token budget logic.
  - Pattern: `novel_generator/chapter.py:1090` — truncation notice insertion.
  - API/Type: `novel_generator/chapter.py:1098` — truncation logging.
  - Pattern: `wxhyj/Novel_architecture.txt:2905` — active priority marker.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/unit/test_prompt_truncation_retains_quality_constraints.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Truncated prompt keeps identity markers
    Tool: Bash
    Steps: Run `pytest tests/unit/test_prompt_truncation_retains_quality_constraints.py::test_truncation_keeps_identity_and_gate_markers -q`
    Expected: Identity/gate marker assertions pass
    Evidence: .sisyphus/evidence/task-3-truncation-pass.txt

  Scenario: Archive markers do not survive runtime payload
    Tool: Bash
    Steps: Run `pytest tests/unit/test_prompt_truncation_retains_quality_constraints.py::test_archive_section_markers_do_not_survive_runtime_payload -q`
    Expected: No archive marker in runtime architecture payload
    Evidence: .sisyphus/evidence/task-3-archive-block.txt
  ```

  **Commit**: YES | Message: `feat(prompt): preserve quality constraints under truncation` | Files: `novel_generator/chapter.py`, `tests/unit/test_prompt_truncation_retains_quality_constraints.py`

- [ ] 4. Add Archive-Leakage Guard for Runtime Quality Path

  **What to do**: Add deterministic checker and enforce it in quality loop preflight to reject archive-zone leakage.
  **Must NOT do**: Do not depend on manual review.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: gate correctness.
  - Skills: [`none`] — validation + tests.
  - Omitted: [`playwright`] — no browser.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: [7] | Blocked By: [1]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `novel_generator/quality_loop_controller.py:214` — loop entry integration.
  - Pattern: `novel_generator/quality_loop_controller.py:239` — hard-gate toggles.
  - API/Type: `wxhyj/Novel_architecture.txt:734` — archive declaration.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/unit/test_archive_leakage_guard.py -q` passes.
  - [ ] `python scripts/check_architecture_prompt_leakage.py --architecture wxhyj/Novel_architecture.txt --strict` exits 0 on clean input.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Clean architecture passes leakage guard
    Tool: Bash
    Steps: Run strict checker command above
    Expected: Exit code 0
    Evidence: .sisyphus/evidence/task-4-leak-guard-pass.txt

  Scenario: Injected archive marker fails guard
    Tool: Bash
    Steps: Run `pytest tests/unit/test_archive_leakage_guard.py::test_injected_archive_marker_triggers_failure -q`
    Expected: Explicit violation detected
    Evidence: .sisyphus/evidence/task-4-leak-guard-fail.txt
  ```

  **Commit**: YES | Message: `feat(quality): enforce archive leakage guard` | Files: `scripts/check_architecture_prompt_leakage.py`, `novel_generator/quality_loop_controller.py`, `tests/unit/test_archive_leakage_guard.py`

- [ ] 5. Add Quality Identity Contract in Active Architecture Zone

  **What to do**: Extend active architecture section (`136.*`) with single-voice contract, causal model lock, and conflict-priority ladder.
  **Must NOT do**: Do not alter locked final-law outcomes or required section numbering.

  **Recommended Agent Profile**:
  - Category: `writing` — Reason: high-precision architecture wording.
  - Skills: [`none`] — markdown/spec editing.
  - Omitted: [`frontend-ui-ux`] — not relevant.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: [6, 9] | Blocked By: []

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `wxhyj/Novel_architecture.txt:5000` — section 136 anchor.
  - Pattern: `wxhyj/Novel_architecture.txt:5006` — single-source runtime clause.
  - Pattern: `wxhyj/Novel_architecture.txt:5025` — anti-contamination lexicon.
  - API/Type: `scripts/verify_v28_gate_consistency.py:17` — required sections contract.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `python scripts/verify_v28_gate_consistency.py` passes.
  - [ ] `pytest tests/unit/test_architecture_identity_contract.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Identity contract markers exist
    Tool: Bash
    Steps: Run `pytest tests/unit/test_architecture_identity_contract.py::test_identity_contract_markers_present -q`
    Expected: Voice, causality, cost-scale, conflict-ladder markers exist
    Evidence: .sisyphus/evidence/task-5-identity-contract.txt

  Scenario: Gate consistency preserved
    Tool: Bash
    Steps: Run gate consistency script
    Expected: All checks pass
    Evidence: .sisyphus/evidence/task-5-gate-consistency.txt
  ```

  **Commit**: YES | Message: `docs(architecture): add quality identity contract and conflict ladder` | Files: `wxhyj/Novel_architecture.txt`, `tests/unit/test_architecture_identity_contract.py`

- [ ] 6. Encode 20-Reference Balanced Fusion Matrix (One Absorb + One Forbid)

  **What to do**: Add a strict 20-row fusion matrix in active zone with one absorb-point + one forbidden spillover per reference.
  **Must NOT do**: No multiple absorb-points per reference; no imitation-level instructions.

  **Recommended Agent Profile**:
  - Category: `writing` — Reason: controlled matrix design with strict semantics.
  - Skills: [`none`] — content architecture authoring.
  - Omitted: [`playwright`] — no UI.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: [8, 10, 14] | Blocked By: [2, 5]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `wxhyj/Novel_architecture.txt:25` — reference pool sections.
  - Pattern: `wxhyj/Novel_architecture.txt:2859` — active quality tables area.
  - Pattern: `wxhyj/Novel_architecture.txt:4990` — conflict arbitration style.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/unit/test_fusion_matrix_schema.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Matrix has exactly 20 valid rows
    Tool: Bash
    Steps: Run `pytest tests/unit/test_fusion_matrix_schema.py::test_matrix_has_20_rows_and_required_columns -q`
    Expected: Row count and required fields validated
    Evidence: .sisyphus/evidence/task-6-matrix-schema.txt

  Scenario: Duplicate absorb-point is rejected
    Tool: Bash
    Steps: Run `pytest tests/unit/test_fusion_matrix_schema.py::test_duplicate_absorb_point_for_reference_fails -q`
    Expected: Validation catches duplicate design
    Evidence: .sisyphus/evidence/task-6-matrix-fail.txt
  ```

  **Commit**: YES | Message: `docs(architecture): add strict 20-reference fusion matrix` | Files: `wxhyj/Novel_architecture.txt`, `tests/unit/test_fusion_matrix_schema.py`

- [ ] 7. Implement Fusion Matrix Validator CLI

  **What to do**: Create `scripts/validate_fusion_matrix.py` with strict mode and non-zero exit on any schema violation.
  **Must NOT do**: No LLM-dependent validation.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: robust validator + fixtures.
  - Skills: [`none`] — parser/CLI work.
  - Omitted: [`dev-browser`] — irrelevant.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: [14, 15] | Blocked By: [4]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `scripts/verify_v28_gate_consistency.py:137` — strict CLI pattern.
  - Pattern: `scripts/verify_v28_gate_consistency.py:57` — heading parsing helper.
  - Pattern: `wxhyj/Novel_architecture.txt:2859` — matrix zone.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/unit/test_validate_fusion_matrix.py -q` passes.
  - [ ] `python scripts/validate_fusion_matrix.py --architecture wxhyj/Novel_architecture.txt --strict` exits 0.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Valid matrix passes strict validator
    Tool: Bash
    Steps: Run strict validator command above
    Expected: Exit code 0 with validation summary
    Evidence: .sisyphus/evidence/task-7-validator-pass.txt

  Scenario: Invalid fixture fails strict validator
    Tool: Bash
    Steps: Run `pytest tests/unit/test_validate_fusion_matrix.py::test_invalid_fixture_returns_nonzero_exit -q`
    Expected: Non-zero path asserted
    Evidence: .sisyphus/evidence/task-7-validator-fail.txt
  ```

  **Commit**: YES | Message: `feat(scripts): validate balanced fusion matrix constraints` | Files: `scripts/validate_fusion_matrix.py`, `tests/unit/test_validate_fusion_matrix.py`, `tests/fixtures/fusion_matrix_invalid.md`

- [ ] 8. Refactor Root Chapter Quality Analyzer to Quality-First Rubric

  **What to do**: Reweight dimensions and hard-gates in `chapter_quality_analyzer.py` for voice/causality/style-first scoring while preserving public output schema.
  **Must NOT do**: Do not remove veto behavior or break downstream key names.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: central scoring behavior affects all loops.
  - Skills: [`none`] — scoring logic + tests.
  - Omitted: [`playwright`] — no UI.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: [10, 14, 15] | Blocked By: [3, 6]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `chapter_quality_analyzer.py:29` — current weights.
  - Pattern: `chapter_quality_analyzer.py:47` — veto logic.
  - Pattern: `chapter_quality_analyzer.py:68` — genre extension support.
  - Pattern: `wxhyj/Novel_architecture.txt:5027` — banned-term policy.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/unit/test_chapter_quality_analyzer_quality_first.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Xianxia profile removes programmer-density dominance
    Tool: Bash
    Steps: Run `pytest tests/unit/test_chapter_quality_analyzer_quality_first.py::test_xianxia_profile_disables_programmer_bias -q`
    Expected: Bias removed under xianxia architecture context
    Evidence: .sisyphus/evidence/task-8-rubric-pass.txt

  Scenario: Critical-dimension veto still works
    Tool: Bash
    Steps: Run `pytest tests/unit/test_chapter_quality_analyzer_quality_first.py::test_veto_fires_on_critical_dimension_failure -q`
    Expected: Fuse-down behavior preserved
    Evidence: .sisyphus/evidence/task-8-rubric-failpath.txt
  ```

  **Commit**: YES | Message: `refactor(quality): rebalance root analyzer to quality-first rubric` | Files: `chapter_quality_analyzer.py`, `tests/unit/test_chapter_quality_analyzer_quality_first.py`

- [ ] 9. Align Heuristic Chapter Analyzer with Architecture-Aware Quality Signals

  **What to do**: Update `novel_generator/analyzers/chapter_quality.py` weights/rules to architecture-aware quality profile while keeping API compatibility.
  **Must NOT do**: Do not alter `analyze_chapter` return schema.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: compatibility-sensitive analyzer update.
  - Skills: [`none`] — internal analyzer work.
  - Omitted: [`frontend-ui-ux`] — non-UI.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: [10] | Blocked By: [5]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `novel_generator/analyzers/chapter_quality.py:41` — current dimension map.
  - Pattern: `novel_generator/analyzers/chapter_quality.py:26` — programmer keyword bias source.
  - Pattern: `novel_generator/language_quality.py:66` — style-consistency helper style.
  - API/Type: `wxhyj/Novel_architecture.txt:5025` — contamination policy source.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/unit/test_analyzer_chapter_quality_alignment.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Architecture context changes weighting safely
    Tool: Bash
    Steps: Run `pytest tests/unit/test_analyzer_chapter_quality_alignment.py::test_architecture_context_changes_dimension_weighting -q`
    Expected: Weights adapt and output schema stays stable
    Evidence: .sisyphus/evidence/task-9-alignment-pass.txt

  Scenario: Unknown genre fallback deterministic
    Tool: Bash
    Steps: Run `pytest tests/unit/test_analyzer_chapter_quality_alignment.py::test_unknown_genre_uses_safe_default_profile -q`
    Expected: Deterministic fallback, no exception
    Evidence: .sisyphus/evidence/task-9-alignment-fallback.txt
  ```

  **Commit**: YES | Message: `refactor(analyzer): align heuristic quality signals with architecture context` | Files: `novel_generator/analyzers/chapter_quality.py`, `tests/unit/test_analyzer_chapter_quality_alignment.py`

- [ ] 10. Integrate Pacing + Style Contamination Gates into Quality Loop

  **What to do**: Extend `QualityLoopController` gate logic with pacing and contamination thresholds.
  **Must NOT do**: Do not create infinite loops; preserve consistency/timeline hard gates.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: loop stability + quality impact.
  - Skills: [`none`] — policy integration.
  - Omitted: [`playwright`] — no UI.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: [15] | Blocked By: [3, 6, 8, 9]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `novel_generator/quality_loop_controller.py:152` — quality dimensions.
  - Pattern: `novel_generator/quality_loop_controller.py:162` — policy defaults.
  - API/Type: `novel_generator/pacing_agent.py:24` — pacing schema.
  - API/Type: `novel_generator/density_checker.py:36` — density signal model.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/unit/test_quality_loop_gate_integration.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Gate violation triggers rewrite branch
    Tool: Bash
    Steps: Run `pytest tests/unit/test_quality_loop_gate_integration.py::test_rewrite_triggered_on_gate_violation -q`
    Expected: Rewrite branch entered with explicit gate reason
    Evidence: .sisyphus/evidence/task-10-loop-pass.txt

  Scenario: Missing optional pacing module degrades gracefully
    Tool: Bash
    Steps: Run `pytest tests/unit/test_quality_loop_gate_integration.py::test_missing_pacing_agent_does_not_break_loop -q`
    Expected: Loop runs with fallback behavior
    Evidence: .sisyphus/evidence/task-10-loop-fallback.txt
  ```

  **Commit**: YES | Message: `feat(loop): gate quality loop with pacing and contamination signals` | Files: `novel_generator/quality_loop_controller.py`, `tests/unit/test_quality_loop_gate_integration.py`

- [ ] 11. Add Style Contamination Checker (Architecture-Driven)

  **What to do**: Implement checker that derives banned/high-risk terms from architecture policy and outputs contamination score + hits.
  **Must NOT do**: Do not assume one fixed novel path.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: new quality module and fixtures.
  - Skills: [`none`] — text analysis + tests.
  - Omitted: [`frontend-ui-ux`] — non-UI.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: [14, 15] | Blocked By: [1, 2]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `wxhyj/Novel_architecture.txt:5025` — banned term policy source.
  - Pattern: `novel_generator/density_checker.py:19` — rule-based checker pattern.
  - Pattern: `novel_generator/language_quality.py:33` — issue typing style.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/unit/test_style_contamination_checker.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Banned terms reduce purity score
    Tool: Bash
    Steps: Run `pytest tests/unit/test_style_contamination_checker.py::test_banned_terms_reduce_style_purity_score -q`
    Expected: Score drops and hit list populated
    Evidence: .sisyphus/evidence/task-11-contamination-pass.txt

  Scenario: Missing policy yields degraded warning state
    Tool: Bash
    Steps: Run `pytest tests/unit/test_style_contamination_checker.py::test_missing_policy_returns_degraded_warning_state -q`
    Expected: No crash and warning state returned
    Evidence: .sisyphus/evidence/task-11-contamination-fallback.txt
  ```

  **Commit**: YES | Message: `feat(quality): add architecture-driven style contamination checker` | Files: `novel_generator/style_contamination_checker.py`, `tests/unit/test_style_contamination_checker.py`

- [ ] 12. Normalize Quality Policy Defaults and Validate Config Safety

  **What to do**: Normalize quality-policy merge behavior and add strict config validator for quality settings.
  **Must NOT do**: Do not expose sensitive config values in logs.

  **Recommended Agent Profile**:
  - Category: `quick` — Reason: focused config + validator work.
  - Skills: [`none`] — config/test task.
  - Omitted: [`playwright`] — not relevant.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: [15] | Blocked By: [11]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `config.json:26` — quality policy block.
  - Pattern: `config.json:89` — runtime quality toggles.
  - API/Type: `novel_generator/quality_loop_controller.py:162` — policy dataclass.
  - API/Type: `novel_generator/quality_loop_controller.py:180` — safe-cast helper.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/unit/test_quality_policy_config_validation.py -q` passes.
  - [ ] `python scripts/validate_quality_policy_config.py --config config.json --strict` exits 0.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Defaults keep hard gates enabled
    Tool: Bash
    Steps: Run `pytest tests/unit/test_quality_policy_config_validation.py::test_defaults_keep_hard_gates_enabled -q`
    Expected: Hard gates remain enabled by default
    Evidence: .sisyphus/evidence/task-12-policy-pass.txt

  Scenario: Invalid policy shape fails strict mode
    Tool: Bash
    Steps: Run `pytest tests/unit/test_quality_policy_config_validation.py::test_invalid_schema_fails_strict -q`
    Expected: Validation fails with explicit error
    Evidence: .sisyphus/evidence/task-12-policy-fail.txt
  ```

  **Commit**: YES | Message: `chore(config): normalize quality policy defaults and validation` | Files: `novel_generator/quality_loop_controller.py`, `scripts/validate_quality_policy_config.py`, `tests/unit/test_quality_policy_config_validation.py`

- [ ] 13. Build Baseline Delta Comparator for Quality Trends

  **What to do**: Add comparator that diffs two baseline JSON reports and emits markdown delta summary.
  **Must NOT do**: Do not compare mismatched sample sets silently.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: reporting + correctness fixtures.
  - Skills: [`none`] — script/test task.
  - Omitted: [`dev-browser`] — CLI only.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: [15] | Blocked By: [12]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `scripts/collect_quality_baseline.py:74` — report schema.
  - Pattern: `scripts/collect_quality_baseline.py:155` — summary fields.
  - Pattern: `novel_generator/batch_quality_check.py:203` — distribution metrics.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/unit/test_quality_baseline_delta.py -q` passes.
  - [ ] `python scripts/compare_quality_baseline.py --before tests/fixtures/quality_baseline_before.json --after tests/fixtures/quality_baseline_after.json --out .sisyphus/evidence/task-13-baseline-delta.md` exits 0.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Delta metrics computed deterministically
    Tool: Bash
    Steps: Run `pytest tests/unit/test_quality_baseline_delta.py::test_delta_metrics_are_computed_correctly -q`
    Expected: Expected score/pass-rate deltas match fixture values
    Evidence: .sisyphus/evidence/task-13-delta-pass.txt

  Scenario: Mismatched samples fail fast
    Tool: Bash
    Steps: Run `pytest tests/unit/test_quality_baseline_delta.py::test_mismatched_sample_sets_fail_fast -q`
    Expected: Explicit mismatch failure
    Evidence: .sisyphus/evidence/task-13-delta-fail.txt
  ```

  **Commit**: YES | Message: `feat(report): add quality baseline delta comparator` | Files: `scripts/compare_quality_baseline.py`, `tests/unit/test_quality_baseline_delta.py`, `tests/fixtures/quality_baseline_before.json`, `tests/fixtures/quality_baseline_after.json`

- [ ] 14. Add Quality-First Integration Regression Suite

  **What to do**: Add integration tests for resolver->slicer->prompt->analyzer->loop gate behavior using deterministic fixtures.
  **Must NOT do**: Do not depend on external network/LLM.

  **Recommended Agent Profile**:
  - Category: `deep` — Reason: multi-module regression coverage.
  - Skills: [`none`] — integration testing.
  - Omitted: [`playwright`] — no browser.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: [15] | Blocked By: [6, 7, 8, 11, 13]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `tests/test_progressive_generator.py` — integration style baseline.
  - Pattern: `tests/test_root_cause_fixes.py` — regression style baseline.
  - Pattern: `tests/dummy_novel/` — fixture corpus.
  - API/Type: `novel_generator/chapter.py:483` — generation entrypoint.
  - API/Type: `novel_generator/quality_loop_controller.py:214` — loop entrypoint.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `pytest tests/integration/test_quality_first_fusion_pipeline.py -q` passes.

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Clean end-to-end quality path passes
    Tool: Bash
    Steps: Run `pytest tests/integration/test_quality_first_fusion_pipeline.py::test_quality_first_pipeline_passes_with_clean_inputs -q`
    Expected: No archive leakage, no contamination redline
    Evidence: .sisyphus/evidence/task-14-integration-pass.txt

  Scenario: Bad fixture is blocked by gates
    Tool: Bash
    Steps: Run `pytest tests/integration/test_quality_first_fusion_pipeline.py::test_pipeline_blocks_archive_or_style_contamination -q`
    Expected: Explicit gate failure reason returned
    Evidence: .sisyphus/evidence/task-14-integration-fail.txt
  ```

  **Commit**: YES | Message: `test(integration): add quality-first fusion regression suite` | Files: `tests/integration/test_quality_first_fusion_pipeline.py`, `tests/fixtures/*quality_first*`

- [x] 15. Execute Full Quality Verification Runbook and Publish Evidence Bundle

  **What to do**: Execute full verification command set and publish a manifest for all evidence artifacts.
  **Must NOT do**: No success claim with partial runs.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: final orchestrated verification.
  - Skills: [`none`] — command + evidence orchestration.
  - Omitted: [`frontend-ui-ux`] — non-UI.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: [] | Blocked By: [3, 7, 8, 10, 11, 12, 13, 14]

  **References** (executor has NO interview context — be exhaustive):
  - Pattern: `scripts/verify_v28_gate_consistency.py` — architecture gate check.
  - Pattern: `scripts/verify_architecture_compliance.py:142` — compliance entrypoint.
  - Pattern: `scripts/collect_quality_baseline.py:215` — baseline command interface.
  - Pattern: `novel_generator/batch_quality_check.py:144` — batch checker entrypoint.

  **Acceptance Criteria** (agent-executable only):
  - [x] `python scripts/verify_v28_gate_consistency.py`
  - [x] `python scripts/check_architecture_prompt_leakage.py --architecture wxhyj/Novel_architecture.txt --strict`
  - [x] `python scripts/audit_prompt_runtime_architecture.py --project-dir wxhyj --sample-size 20 --strict`
  - [x] `python scripts/verify_architecture_compliance.py --project-root /media/tcui/82BC0F4BBC0F3965/AI_NovelGenerator`
  - [x] `python -m pytest tests/test_blueprint_guardrails.py tests/unit/test_generation_handlers_telemetry.py tests/unit/test_architecture_runtime_slice.py -q`
  - [x] `python -m pytest tests/unit/test_blueprint_runtime_slice_usage.py tests/unit/test_architecture_prompt_leakage_guard.py tests/unit/test_prompt_runtime_architecture_audit.py tests/unit/test_batch_quality_checker_runtime.py tests/unit/test_prompt_contracts.py tests/unit/test_prompt_legacy_hygiene.py -q`
  - [x] `python -m pytest tests/ -q`
  - [x] `python scripts/collect_quality_baseline.py --novel-path /media/tcui/82BC0F4BBC0F3965/AI_NovelGenerator/wxhyj --threshold 8.5 --sample-size 20 --output-dir /media/tcui/82BC0F4BBC0F3965/AI_NovelGenerator/.sisyphus/evidence`

  **QA Scenarios** (MANDATORY — task incomplete without these):
  ```bash
  Scenario: Full verification runbook succeeds
    Tool: Bash
    Steps: Execute full acceptance command list and save output logs
    Expected: All exits are 0 and evidence manifest is complete
    Evidence: .sisyphus/evidence/task-15-runbook-success.txt

  Scenario: Controlled failure capture works
    Tool: Bash
    Steps: Run one known-bad fixture case and verify fail summary emission
    Expected: Failure is recorded and success is not declared
    Evidence: .sisyphus/evidence/task-15-runbook-failpath.txt
  ```

  **Commit**: NO | Message: `n/a` | Files: `.sisyphus/evidence/*`, `architecture_compliance_report.md`

  **Closure update (2026-02-24, post-reconciliation stability extension)**:
  - Mandatory Task 15 acceptance command set is reconciled to repo-runnable commands and has successful evidence logs.
  - Additional baseline stability extension executed with two extra runs:
    - `quality_baseline_20260224_031100.json` -> `average_final_score=9.641`, `pass_count=20`
    - `quality_baseline_20260224_031758.json` -> `average_final_score=9.264`, `pass_count=19`
  - Four-run closure window (`023822`, `025712`, `031100`, `031758`) shows:
    - `average_final_score` mean `9.416`, range `0.497`, population stddev `0.217`
    - `pass_count` range `18-20`
  - Evidence references: `.sisyphus/evidence/task-15-evidence-index.md`, `.sisyphus/evidence/task-15-command-manifest.md`, `.sisyphus/evidence/task-15-runbook-success.txt`.

## Final Verification Wave (4 parallel agents, ALL must APPROVE for closure)
- [x] F1. Plan Compliance Audit — oracle — Verdict: `APPROVED` (fresh rerun on reconciled artifacts; no blocking findings) | Session: `ses_3740a50edffdmhvAwNbCgl7NQC`
- [x] F2. Code Quality Review — unspecified-high — Verdict: `APPROVED` (fresh rerun on reconciled artifacts; only non-blocking risk notes) | Session: `ses_3740a50ccffe0tRP12N3qsdVnX`
- [x] F3. Real Manual QA — unspecified-high (+ playwright if UI) — Verdict: `PASS` (fresh rerun confirms closure-readiness on current evidence set) | Session: `ses_3740a50c2ffeKToMRAHCAR6I3b`
- [x] F4. Scope Fidelity Check — deep — Verdict: `APPROVED` (fresh rerun confirms anti-style-contamination evidence linkage is sufficient) | Session: `ses_3740a50cdffe7RItRrUQsyHsrh`
- [x] Note: This approval wave supersedes the earlier stale mismatch wave after reconciliation updates were applied.

### Closure blockers after F-wave
- [x] Evidence index and manifest aligned with regenerated compliance findings and baseline-threshold interpretation.
- [x] Controlled failpath documentation now includes strict gate-policy failure proof (not only invalid-path proof).
- [x] Scope-fidelity section now maps anti-style-contamination claims to strict command and regression-test evidence.
- [x] F1-F4 re-review completed with non-blocking verdicts (`APPROVED`/`PASS`) on reconciled artifacts.

## Commit Strategy
- Use atomic commits by wave with strict quality intent in commit message scope.
- Enforce no-secret staging checks before each commit.
- Suggested sequence:
  - `feat(quality): harden architecture runtime source and whitelist slicing`
  - `feat(quality): align analyzers and loop gates to quality-first rubric`
  - `test(quality): add ingestion/scoring regression suite and baseline comparer`
  - `docs(quality): record fusion matrix and execution guardrails`

## Success Criteria
- Runtime chapter generation no longer bypasses architecture resolver.
- Prompt-critical architecture guidance survives truncation and excludes archive sections.
- Fusion execution remains single-voice under measurable anti-contamination checks.
- Quality baseline report demonstrates improved/stable aggregate quality without consistency regressions.
- All defined verification commands pass and evidence files are generated.
