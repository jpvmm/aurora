---
phase: 02-vault-knowledge-base-lifecycle
plan: 01
subsystem: cli
tags: [typer, pydantic, runtime-settings, knowledge-base]
requires:
  - phase: 01-local-runtime-baseline
    provides: global runtime settings persistence and root CLI command-group pattern
provides:
  - aurora kb command namespace with stable lifecycle command signatures
  - canonical KB scope/counter/summary contracts for text and JSON outputs
  - global KB scope persistence defaults in runtime settings and paths
affects: [02-02, 02-03, 02-04, kb-service, scanner, manifest]
tech-stack:
  added: []
  patterns:
    - deterministic sorted serialization for KB contracts and settings
    - fail-fast CLI diagnostics with shared summary contract backing text/json
key-files:
  created:
    - src/aurora/cli/kb.py
    - src/aurora/kb/__init__.py
    - src/aurora/kb/contracts.py
    - tests/kb/test_contracts.py
  modified:
    - src/aurora/cli/app.py
    - src/aurora/runtime/paths.py
    - src/aurora/runtime/settings.py
    - tests/cli/test_entrypoint.py
    - tests/runtime/test_settings_defaults.py
key-decisions:
  - "KB contracts use frozen Pydantic models with normalized tuple fields to keep deterministic dumps."
  - "Unwired KB commands fail fast with pt-BR actionable diagnostics while still emitting the shared summary payload for --json."
patterns-established:
  - "Contract-first lifecycle: tests lock scope/counter/summary schema before scanner/service integration."
  - "Runtime settings validation raises actionable load errors instead of fallback behavior for malformed KB fields."
requirements-completed: [KB-01, KB-05, PRIV-02]
duration: 6 min
completed: 2026-03-03
---

# Phase 02 Plan 01: KB Lifecycle Contract Foundation Summary

**Aurora now exposes a stable `aurora kb` namespace, deterministic KB lifecycle contracts, and persisted global KB scope defaults for downstream ingestion/update service wiring.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-03T22:37:29Z
- **Completed:** 2026-03-03T22:43:38Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- Added KB contract models (`KBScopeConfig`, counters, diagnostics, summary) with deterministic normalization/serialization.
- Extended runtime settings and paths with global KB vault/scope persistence plus actionable malformed-config load errors.
- Registered `aurora kb` commands (`ingest/update/delete/rebuild`) with `--json`/`--dry-run` signatures and consistent fail-fast pt-BR diagnostics.

## Task Commits

Each task was committed atomically:

1. **Task 1: Define KB contracts used by all lifecycle commands**
2. RED `test`: `2b21639`
3. GREEN `feat`: `a6b1dee`
4. **Task 2: Extend global runtime settings and paths for KB scope persistence**
5. RED `test`: `f2a010d`
6. GREEN `feat`: `60bac89`
7. **Task 3: Add `aurora kb` CLI namespace with command signatures and shared output contract**
8. RED `test`: `638ff9e`
9. GREEN `feat`: `c69d1c8`

## Files Created/Modified

- `src/aurora/kb/contracts.py` - Canonical KB scope/counter/diagnostic/summary models.
- `src/aurora/kb/__init__.py` - Contract exports for stable imports.
- `src/aurora/runtime/settings.py` - KB scope fields, normalization validators, actionable load-error handling.
- `src/aurora/runtime/paths.py` - KB manifest/state path helpers.
- `src/aurora/cli/kb.py` - KB command group and fail-fast diagnostics.
- `src/aurora/cli/app.py` - Root CLI registration for `kb`.
- `tests/kb/test_contracts.py` - Contract normalization and deterministic serialization assertions.
- `tests/runtime/test_settings_defaults.py` - KB settings/persistence/path/error behavior coverage.
- `tests/cli/test_entrypoint.py` - KB namespace visibility, signatures, and diagnostics coverage.

## Decisions Made

- Used frozen Pydantic contract models plus sorted tuple normalization to avoid drift between text and JSON renderers.
- Required `kb_include`/`kb_exclude` to be list-like values; malformed persisted settings now fail with explicit recovery guidance instead of implicit fallback.
- Implemented temporary CLI fail-fast behavior with explicit category/recovery fields so Wave 2 service wiring can swap internals without changing command contracts.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Execution tooling path mismatch**
- **Found during:** Plan bootstrap
- **Issue:** Workflow instructions referenced `~/.claude/get-shit-done`, but this environment exposes tooling at `~/.codex/get-shit-done`.
- **Fix:** Switched all GSD tool invocations to the available `.codex` path while preserving the same workflow steps.
- **Files modified:** None (execution environment only)
- **Verification:** `node ~/.codex/get-shit-done/bin/gsd-tools.cjs init execute-phase 02` succeeded.
- **Committed in:** N/A

**2. [Rule 3 - Blocking] Transient git index lock during Task 1 RED commit**
- **Found during:** Task 1 commit protocol
- **Issue:** `git commit` returned `.git/index.lock` blocking staged commit.
- **Fix:** Verified no active git process and retried commit serially.
- **Files modified:** None (execution flow only)
- **Verification:** RED commit completed successfully on retry.
- **Committed in:** `2b21639`

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** No scope changes. Both fixes were operational and required to complete planned tasks.

## Authentication Gates

None.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- CLI/settings/contracts are now locked for parallel Wave 2 implementation work.
- Ready for `02-02-PLAN.md` (scanner/preprocessing/service wiring on top of this contract layer).

---
*Phase: 02-vault-knowledge-base-lifecycle*
*Completed: 2026-03-03*

## Self-Check: PASSED

- Found SUMMARY artifact at `.planning/phases/02-vault-knowledge-base-lifecycle/02-01-SUMMARY.md`.
- Verified task commits exist: `2b21639`, `a6b1dee`, `f2a010d`, `60bac89`, `638ff9e`, `c69d1c8`.
