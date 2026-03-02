---
phase: 01-local-runtime-baseline
plan: 03
subsystem: runtime
tags: [wizard, diagnostics, llama-cpp, typer, privacy]
requires:
  - phase: 01-local-runtime-baseline
    provides: model set flow, global settings persistence, and local-only policy guards from plans 01, 02, and 04
provides:
  - runtime probe client with deterministic error taxonomy and recovery commands
  - first-run setup wizard that blocks until endpoint and model validation succeed
  - config show and doctor commands with explicit privacy-state visibility
affects: [setup, config, doctor, runtime-validation, privacy-ux]
tech-stack:
  added: []
  patterns:
    - TDD task execution with test and feature commits per task
    - categorized pt-BR runtime diagnostics with explicit CLI remediation
    - privacy-state UX surfaced in setup summary and diagnostics commands
key-files:
  created:
    - src/aurora/runtime/errors.py
    - src/aurora/runtime/llama_client.py
    - src/aurora/cli/setup.py
    - src/aurora/cli/config.py
    - src/aurora/cli/doctor.py
    - tests/runtime/test_llama_client.py
    - tests/cli/test_setup_wizard.py
    - tests/cli/test_config_show.py
    - tests/cli/test_doctor.py
  modified:
    - src/aurora/cli/app.py
key-decisions:
  - "Runtime failures are normalized into endpoint_offline, timeout, model_missing, and invalid_token categories with concrete command recovery."
  - "First-run configuration is keyed off missing settings file and blocks completion until runtime endpoint/model probes succeed."
  - "Diagnostics commands always expose local-only and telemetry state while masking sensitive endpoint credentials."
patterns-established:
  - "Root CLI callback now gates first-run onboarding before user attempts ask flows."
  - "Doctor output groups issues by category and prints actionable remediation commands."
requirements-completed: [MOD-01, MOD-03, PRIV-04]
duration: 6m
completed: 2026-03-02
---

# Phase 1 Plan 03: Runtime Readiness UX Summary

**Aurora now validates local runtime readiness through a blocking first-run wizard, categorized runtime probes, and privacy-transparent config/doctor diagnostics.**

## Performance

- **Duration:** 6m
- **Started:** 2026-03-02T00:39:05Z
- **Completed:** 2026-03-02T00:45:33Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments

- Added runtime probe infrastructure for `/health` and `/v1/models` with retry-aware loading behavior and typed error categories.
- Implemented first-run setup wizard in pt-BR that loops on runtime validation failures and prints onboarding summary plus language-change guidance.
- Replaced config/doctor placeholders with production commands that expose privacy defaults and grouped troubleshooting commands.
- Verified end-to-end via targeted plan tests and command-level checks for root wizard trigger and config visibility.

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement runtime probe client and deterministic error classification** - `ce98967` (test), `1ba31d9` (feat)
2. **Task 2: Build first-run setup wizard with blocking validation and summary output** - `5801f93` (test), `4342996` (feat)
3. **Task 3: Expose diagnostics via config show and doctor with privacy-state visibility** - `6145d7a` (test), `fbb4d3f` (feat)

**Plan metadata:** Pending docs/state commit.

## Files Created/Modified

- `src/aurora/runtime/errors.py` - Defines runtime error taxonomy and command-first pt-BR remediation guidance.
- `src/aurora/runtime/llama_client.py` - Implements health/model probes with timeout/loading differentiation and model presence checks.
- `src/aurora/cli/setup.py` - Adds guided first-run wizard and blocking validation loop.
- `src/aurora/cli/config.py` - Adds `aurora config show` with masked output and explicit privacy defaults.
- `src/aurora/cli/doctor.py` - Adds grouped runtime diagnostics and actionable recovery output.
- `src/aurora/cli/app.py` - Wires setup/config/doctor command groups and root first-run trigger.
- `tests/runtime/test_llama_client.py` - Covers runtime category mapping and retry behavior.
- `tests/cli/test_setup_wizard.py` - Covers setup retry/abort flow and root-triggered onboarding.
- `tests/cli/test_config_show.py` - Covers config visibility and credential masking.
- `tests/cli/test_doctor.py` - Covers doctor success/failure grouped diagnostics output.

## Decisions Made

- Standardized runtime validation around two probes (`/health` then `/v1/models`) to separate endpoint reachability from model availability.
- Reused `aurora model set` inside wizard attempts to keep persistence/download behavior consistent across command and onboarding paths.
- Kept doctor failure output command-driven to make CLI recovery immediate without tracebacks.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Switched execution tooling path to available gsd-tools installation**
- **Found during:** Plan initialization
- **Issue:** `~/.claude/get-shit-done/bin/gsd-tools.cjs` was not present in this environment.
- **Fix:** Executed all init/state/roadmap commands via `~/.codex/get-shit-done/bin/gsd-tools.cjs`.
- **Files modified:** None
- **Verification:** `init execute-phase` and subsequent state tooling commands executed successfully.
- **Committed in:** N/A (execution environment fix)

**2. [Rule 3 - Blocking] Created planned modules that were absent in current branch**
- **Found during:** Task 1 and Task 3 startup
- **Issue:** Plan-targeted files (`runtime/errors.py`, `runtime/llama_client.py`, `cli/setup.py`, `cli/config.py`, `cli/doctor.py`) did not exist.
- **Fix:** Implemented modules from plan contracts and wired them into root CLI.
- **Files modified:** `src/aurora/runtime/errors.py`, `src/aurora/runtime/llama_client.py`, `src/aurora/cli/setup.py`, `src/aurora/cli/config.py`, `src/aurora/cli/doctor.py`, `src/aurora/cli/app.py`
- **Verification:** Targeted pytest suite and command smoke checks passed.
- **Committed in:** `1ba31d9`, `4342996`, `fbb4d3f`

**3. [Rule 1 - Bug] Corrected root CLI no-args behavior to allow first-run wizard trigger**
- **Found during:** Task 2 GREEN verification
- **Issue:** Root app still used `no_args_is_help=True`, exiting before onboarding callback.
- **Fix:** Set root Typer app to `no_args_is_help=False`.
- **Files modified:** `src/aurora/cli/app.py`
- **Verification:** `tests/cli/test_setup_wizard.py` root trigger test passed.
- **Committed in:** `4342996`

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 bug)
**Impact on plan:** All deviations were required for correctness and execution continuity; no scope creep beyond planned runtime readiness UX.

## Issues Encountered

- Hit transient `.git/index.lock` during Task 1 RED commit attempt; lock cleared automatically and commit succeeded on retry.

## Authentication Gates

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 1 is now fully executable from CLI onboarding through diagnostics. Remaining work is phase-level closure (state/roadmap/requirements updates and final docs commit).

---
*Phase: 01-local-runtime-baseline*
*Completed: 2026-03-02*

## Self-Check: PASSED
- Verified all claimed created/modified files exist on disk.
- Verified all task commit hashes are present in git history.
