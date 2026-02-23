# Task 15 Evidence Index

Date: 2026-02-24
Scope: quality-first balanced fusion, Task 15 closure

## Run provenance

- Git HEAD: `5c805f01cb380e150d79091d22e8449edf1bff0c`
- Python runtime: `3.14.3`
- Workspace root: `.` (repository root)
- Compliance report linkage policy: `architecture_compliance_report.md` is regenerated in-place; this index binds the current report contents to the latest rerun record in `.sisyphus/evidence/task-15-runbook-success.txt`.

## Evidence inventory

- Runbook success log: `.sisyphus/evidence/task-15-runbook-success.txt`
- Runbook controlled failpath log: `.sisyphus/evidence/task-15-runbook-failpath.txt`
- Command reconciliation manifest: `.sisyphus/evidence/task-15-command-manifest.md`
- Inventory-only pre-reconciliation baseline JSON: `.sisyphus/evidence/quality_baseline_20260224_022127.json`
- Inventory-only pre-reconciliation baseline Markdown: `.sisyphus/evidence/quality_baseline_20260224_022127.md`
- Baseline JSON (initial Task 15 run): `.sisyphus/evidence/quality_baseline_20260224_023822.json`
- Baseline Markdown (initial Task 15 run): `.sisyphus/evidence/quality_baseline_20260224_023822.md`
- Baseline JSON (closure rerun): `.sisyphus/evidence/quality_baseline_20260224_025712.json`
- Baseline Markdown (closure rerun): `.sisyphus/evidence/quality_baseline_20260224_025712.md`
- Baseline JSON (stability extension): `.sisyphus/evidence/quality_baseline_20260224_031100.json`
- Baseline Markdown (stability extension): `.sisyphus/evidence/quality_baseline_20260224_031100.md`
- Latest baseline JSON: `.sisyphus/evidence/quality_baseline_20260224_031758.json`
- Latest baseline Markdown: `.sisyphus/evidence/quality_baseline_20260224_031758.md`
- Compliance report artifact: `architecture_compliance_report.md`

## Compliance report disposition

- Command status: `python scripts/verify_architecture_compliance.py --project-root .` completed and emitted `architecture_compliance_report.md`.
- Interpretation: findings are corpus-state/domain findings, not verifier execution failures.
- Current findings include:
  - section-12 template-field gaps in chapter files 1, 44, and 89
  - key-plot checkpoint chapters 280/305/318 not generated yet

## Task 15 acceptance reconciliation

- Root cause: original Task 15 acceptance block referenced multiple unit/integration files that do not exist in current repository state.
- Resolution: acceptance commands were reconciled to repo-runnable command packs documented in `.sisyphus/evidence/task-15-command-manifest.md`.
- Result: plan, manifest, and evidence logs are aligned for reproducible reruns, with drift explicitly captured instead of hidden.

## Latest baseline summary

- `chapter_count`: 20
- `average_final_score`: 9.264
- `pass_count`: 19
- `below_threshold`: 1

## Baseline stability window (4-run Task 15 closure set)

| Baseline artifact | average_final_score | pass_count | below_threshold |
|---|---:|---:|---:|
| `quality_baseline_20260224_023822.json` | 9.617 | 20 | 0 |
| `quality_baseline_20260224_025712.json` | 9.144 | 18 | 2 |
| `quality_baseline_20260224_031100.json` | 9.641 | 20 | 0 |
| `quality_baseline_20260224_031758.json` | 9.264 | 19 | 1 |

- `average_final_score` mean: `9.416`
- `average_final_score` min/max/range: `9.144` / `9.641` / `0.497`
- `average_final_score` population stddev: `0.217`
- `pass_count` range: `18-20` (mean `19.25`)
- Disposition: all four closure-set runs keep run-level `average_final_score` above threshold (`8.5`), with intermittent chapter-level below-threshold events in two runs (`below_threshold_count`: `2` and `1`).

## Baseline run notes

- Baseline command executed successfully across all four closure-set runs.
- Inventory policy: `quality_baseline_20260224_022127.*` is preserved for provenance only and excluded from the closure-set stability window because it predates command-reconciliation and controlled-failpath capture.
- Variance drivers observed: intermittent provider instability, JSON parsing fallback warnings, and occasional architecture-adherence fuse-down on specific chapter samples.

## Scope-fidelity evidence notes (anti-style-contamination)

- Strict leakage gate command passed: `python scripts/check_architecture_prompt_leakage.py --architecture wxhyj/Novel_architecture.txt --strict`.
- Runtime prompt audit command passed: `python scripts/audit_prompt_runtime_architecture.py --project-dir wxhyj --sample-size 20 --strict` with `violations=0`.
- Targeted regression pack passed with contamination/audit tests included: `tests/unit/test_architecture_prompt_leakage_guard.py` and `tests/unit/test_prompt_runtime_architecture_audit.py`.
- Scope caveat: Task 15 evidence bundle does not include standalone Task 11/14 artifact files in this repository state; anti-style-contamination proof is anchored to strict command outputs plus the targeted unit regression pack.

## Final verifier rerun status (post-reconciliation)

- F1 Plan Compliance Audit (`oracle`) -> `APPROVED` | session `ses_3740a50edffdmhvAwNbCgl7NQC`
- F2 Code Quality Review (`unspecified-high`) -> `APPROVED` | session `ses_3740a50ccffe0tRP12N3qsdVnX`
- F3 Real Manual QA (`unspecified-high`) -> `PASS` | session `ses_3740a50c2ffeKToMRAHCAR6I3b`
- F4 Scope Fidelity Check (`deep`) -> `APPROVED` | session `ses_3740a50cdffe7RItRrUQsyHsrh`
- Disposition: fresh rerun verdicts supersede the earlier stale mismatch wave and clear the Task 15 closure approval gate.
