---
phase: 02-vault-knowledge-base-lifecycle
plan: 06
subsystem: testing
tags: [pytest, typer, qmd, integration, cli]
requires:
  - phase: 02-05
    provides: Concrete QMDCliBackend transport and prepared-note adapter flow
provides:
  - Deterministic CLI readability contract tests for KB lifecycle output
  - Real-QMD integration verification for ingest/update/delete/rebuild lifecycle effects
  - Backend remove/rebuild flow that refreshes collection state to drop stale documents
affects: [03-retrieval-workflow, kb-cli-contracts, qmd-backend-lifecycle]
tech-stack:
  added: []
  patterns:
    - ANSI-normalized terminal contract assertions for CLI readability
    - Isolated per-test QMD index/collection fixtures with deterministic teardown
    - Collection refresh (remove/add/update) for delete/rebuild consistency in QMD
key-files:
  created:
    - tests/integration/conftest.py
    - tests/integration/test_kb_qmd_integration.py
  modified:
    - pyproject.toml
    - tests/cli/test_kb_command.py
    - src/aurora/kb/qmd_backend.py
key-decisions:
  - "Lock KB CLI readability via ordered stage and summary token assertions after ANSI normalization."
  - "Use real QMD integration tests with unique index/collection names and cleanup per test run."
  - "Refresh QMD collections on remove/rebuild to ensure backend-visible stale document removal."
patterns-established:
  - "CLI Contract Pattern: text-mode stage order + stable summary fields + JSON-no-progress invariant."
  - "QMD Integration Pattern: assert lifecycle effects via qmd collection state, not manifest-only checks."
requirements-completed: [KB-01, KB-02, KB-03, KB-04, KB-05, PRIV-02]
duration: 7 min
completed: 2026-03-04
---

# Phase 02 Plan 06: Verification Automation Summary

**Automated KB lifecycle verification now covers terminal readability contracts and real QMD ingest/update/delete/rebuild state transitions end-to-end.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-04T18:00:02Z
- **Completed:** 2026-03-04T18:07:32Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Added deterministic CLI output contract tests for readable stage flow and stable final summary fields across `ingest|update|delete|rebuild`.
- Added real-QMD integration fixtures and lifecycle tests using isolated index/collection names with teardown cleanup.
- Closed backend lifecycle gap by forcing QMD collection refresh during remove/rebuild so stale docs are dropped in backend-visible state.

## Verification
- `uv run pytest tests/cli/test_kb_command.py -q -k "kb and (progress or summary or json or readability)"` passed (`10 passed, 3 deselected`).
- `uv run pytest tests/integration/test_kb_qmd_integration.py -q` passed (`1 passed`).

## Task Commits

Each task was committed atomically through RED/GREEN TDD cycles:

1. `998386b` - Task 1 RED (CLI readability contract tests)
2. `30665a9` - `feat(02-06): implement deterministic KB CLI readability coverage` (Task 1 GREEN)
3. `86644dc` - Task 2 RED (real QMD lifecycle integration tests)
4. `c0bb303` - `feat(02-06): enforce real qmd lifecycle state transitions` (Task 2 GREEN)

## Files Created/Modified
- `tests/cli/test_kb_command.py` - Added readability and JSON contract assertions with deterministic progress-stage expectations.
- `pyproject.toml` - Registered `integration` pytest marker.
- `tests/integration/conftest.py` - Added isolated real-QMD fixture setup/teardown and collection-state helpers.
- `tests/integration/test_kb_qmd_integration.py` - Added end-to-end ingest/update/delete/rebuild lifecycle assertions against QMD collection state.
- `src/aurora/kb/qmd_backend.py` - Added collection refresh flow for remove/rebuild to drop stale backend documents.

## Decisions Made
- Normalized ANSI escape sequences before readability assertions to keep terminal contract tests deterministic.
- Asserted backend effects via `qmd ls`/`qmd get` collection visibility instead of manifest-only checks.
- Treated stale delete behavior in real QMD state as a correctness bug and fixed it inline during task execution.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Delete/rebuild did not remove stale docs from real QMD collection state**
- **Found during:** Task 2 (real QMD lifecycle integration suite)
- **Issue:** Integration RED run showed `kb delete` left previously indexed documents visible in QMD collection state.
- **Fix:** Added collection refresh flow (`collection remove` -> `collection add` -> `update`) in `QMDCliBackend.remove` and `QMDCliBackend.rebuild`.
- **Files modified:** `src/aurora/kb/qmd_backend.py`
- **Verification:** `uv run pytest tests/integration/test_kb_qmd_integration.py -q`
- **Committed in:** `c0bb303`

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Fix was required for plan objective (real backend-visible lifecycle effects) and kept scope bounded to lifecycle correctness.

## Authentication Gates
None.

## Issues Encountered
- Real-QMD behavior differed from manifest expectations: stale docs persisted after delete until collection refresh was introduced.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 2 now has reproducible automated coverage for both prior human-needed gaps (CLI readability baseline and real backend lifecycle verification).
- Ready for phase transition and retrieval workflow planning/execution.

---
*Phase: 02-vault-knowledge-base-lifecycle*
*Completed: 2026-03-04*

## Self-Check: PASSED
