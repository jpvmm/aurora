---
phase: 02-vault-knowledge-base-lifecycle
plan: 05
subsystem: kb
tags: [qmd, backend, subprocess, deterministic-index, kb-lifecycle]
requires:
  - phase: 02-vault-knowledge-base-lifecycle
    provides: service/scanner/preprocess/manifest lifecycle orchestration from 02-04
provides:
  - concrete QMDCliBackend transport with deterministic index/collection/corpus state
  - prepared-note payload flow from KBService through adapter into backend commands
  - regression coverage for backend sequencing, failure mapping, and privacy-safe diagnostics
affects: [02-06, integration-qmd, kb-runtime-operations]
tech-stack:
  added: []
  patterns:
    - qmd subprocess execution via explicit argv with no shell interpolation
    - manifest mutation only after backend success with prepared payload integrity checks
key-files:
  created:
    - src/aurora/kb/qmd_backend.py
    - tests/kb/test_qmd_backend.py
  modified:
    - src/aurora/kb/contracts.py
    - src/aurora/kb/qmd_adapter.py
    - src/aurora/kb/service.py
    - src/aurora/runtime/paths.py
    - src/aurora/runtime/settings.py
    - tests/kb/test_qmd_adapter.py
    - tests/runtime/test_kb_service.py
key-decisions:
  - "KBService now defaults to QMDCliBackend to remove no-op backend behavior from production lifecycle commands."
  - "Adapter/backend contracts now accept KBPreparedNote payloads so cleaned markdown content and metadata drive backend mutations deterministically."
  - "QMDCliBackend rejects mismatched cleaned_size metadata before issuing qmd commands to prevent inconsistent backend state."
patterns-established:
  - "Backend operations are always bootstrap-first (collection add) then update, with duplicate bootstrap failures treated as idempotent."
  - "Backend diagnostics remain typed and privacy-safe, never echoing raw note content from stderr."
requirements-completed: [KB-01, KB-02, KB-03, KB-04, KB-05, PRIV-02]
duration: 11 min
completed: 2026-03-04
---

# Phase 02 Plan 05: QMD Backend Integration Summary

**Aurora KB lifecycle now mutates a concrete QMD-backed transport with deterministic managed corpus/index wiring and prepared-content payload flow.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-03-04T17:44:55Z
- **Completed:** 2026-03-04T17:55:59Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- Implemented `QMDCliBackend` with explicit `qmd --index ...` subprocess argv execution, managed corpus bootstrap, and typed privacy-safe diagnostics.
- Rewired `KBService` and `QMDAdapter` to pass prepared markdown payloads (`KBPreparedNote`) into backend apply/rebuild flows while preserving manifest-after-backend commit ordering.
- Added deterministic regression coverage for backend command sequencing, failure mapping, payload integrity validation, and non-leakage of raw note bodies.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement concrete QMD backend transport and deterministic backend settings**
2. RED `test`: `8c1faac`
3. GREEN `feat`: `95e05a8`
4. **Task 2: Wire service and adapter to prepared-content backend flow without breaking manifest guarantees**
5. RED `test`: `114fc3c`
6. GREEN `feat`: `ce1ee15`
7. **Task 3: Add regression coverage for QMD backend command sequencing and failure mapping**
8. RED `test`: `87365a1`
9. GREEN `fix`: `0797c52`

## Files Created/Modified

- `src/aurora/kb/qmd_backend.py` - Concrete QMD CLI backend transport and managed corpus mutation logic.
- `src/aurora/kb/contracts.py` - Prepared backend payload contract (`KBPreparedNote`).
- `src/aurora/kb/qmd_adapter.py` - Prepared payload delegation and manifest commit safeguards.
- `src/aurora/kb/service.py` - Concrete backend factory wiring and prepared payload generation.
- `src/aurora/runtime/paths.py` - Deterministic managed QMD corpus path helpers.
- `src/aurora/runtime/settings.py` - Deterministic QMD index/collection runtime identifiers.
- `tests/kb/test_qmd_backend.py` - Backend sequencing/failure/privacy regression coverage.
- `tests/kb/test_qmd_adapter.py` - Adapter payload propagation and rebuild payload assertions.
- `tests/runtime/test_kb_service.py` - Service payload forwarding and concrete backend default assertion.

## Decisions Made

- Set runtime-managed QMD identifiers (`kb_qmd_index_name`, `kb_qmd_collection_name`) as deterministic settings inputs.
- Kept backend command diagnostics recovery-oriented and content-safe by never reflecting subprocess stderr directly.
- Added payload integrity validation (`cleaned_size` vs cleaned text bytes) as a pre-command guardrail.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] GSD tool path mismatch in executor template**
- **Found during:** Plan bootstrap
- **Issue:** Template commands referenced `~/.claude/get-shit-done/bin/gsd-tools.cjs`, but this environment exposes tooling at `~/.codex/get-shit-done/bin/gsd-tools.cjs`.
- **Fix:** Switched execution/state command invocations to the available `.codex` tool path.
- **Files modified:** None (execution environment only)
- **Verification:** `node ~/.codex/get-shit-done/bin/gsd-tools.cjs init execute-phase 02-vault-knowledge-base-lifecycle` succeeded.
- **Committed in:** N/A

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** No scope change; deviation only affected automation tooling path resolution.

## Authentication Gates

None.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 05 now closes the concrete backend integration gap from Phase 2 verification.
- Phase `02-06` can proceed with real end-to-end integration tests over this transport.

---
*Phase: 02-vault-knowledge-base-lifecycle*
*Completed: 2026-03-04*

## Self-Check: PASSED

- Found summary artifact: `.planning/phases/02-vault-knowledge-base-lifecycle/02-05-SUMMARY.md`.
- Verified task commits exist: `8c1faac`, `95e05a8`, `114fc3c`, `ce1ee15`, `87365a1`, `0797c52`.
