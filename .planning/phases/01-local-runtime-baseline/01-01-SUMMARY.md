---
phase: 01-local-runtime-baseline
plan: 01
subsystem: cli
tags: [python, typer, uv, pipx, packaging, pytest]
requires: []
provides:
  - Global `aurora` CLI entrypoint via `project.scripts`
  - Root Typer app with Phase 1 command-group placeholders
  - Smoke tests for entrypoint resolution and command-surface discovery
affects: [phase-01-plan-02, model-setup, cli-surface]
tech-stack:
  added: [typer, pytest, hatchling]
  patterns: [Typer root-app with subapp placeholders, CLI smoke testing through CliRunner]
key-files:
  created:
    - pyproject.toml
    - src/aurora/__init__.py
    - src/aurora/cli/__init__.py
    - src/aurora/cli/app.py
    - tests/cli/test_entrypoint.py
    - README.md
  modified:
    - src/aurora/cli/app.py
    - tests/cli/test_entrypoint.py
key-decisions:
  - "Expose `setup`, `config`, `model`, and `doctor` as Typer subapps immediately to lock command naming early."
  - "Use explicit pt-BR placeholder errors with non-zero exit codes to avoid silent no-op behavior."
patterns-established:
  - "CLI contract first: lock `project.scripts` entrypoint and test it before feature work."
  - "Phase placeholders are visible and explicit, allowing future plans to fill behavior without renaming churn."
requirements-completed: [CLI-01]
duration: 3 min
completed: 2026-03-02
---

# Phase 1 Plan 1: Local Runtime Baseline Summary

**Python CLI scaffold with `aurora` global entrypoint, Phase 1 command-group placeholders, and smoke coverage for root command discovery.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-02T00:17:31Z
- **Completed:** 2026-03-02T00:21:01Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Bootstrapped package metadata with `[project.scripts]` mapping `aurora = "aurora.cli.app:app"`.
- Implemented an importable Typer root app and registered `setup`, `config`, `model`, and `doctor` placeholders.
- Added deterministic CLI smoke tests that verify entrypoint mapping, root help output, command-group discoverability, and explicit pt-BR placeholder errors.
- Documented global install and PATH recovery for both `uv tool` and `pipx`.

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Bootstrap package metadata, root CLI app, and entrypoint smoke tests** - `2e7abc4` (test)
2. **Task 1 (GREEN): Bootstrap package metadata, root CLI app, and entrypoint smoke tests** - `30bc755` (feat)
3. **Task 2 (RED): Register Phase 1 command groups and docs flow** - `cad5f65` (test)
4. **Task 2 (GREEN): Register Phase 1 command groups and docs flow** - `6319a28` (feat)

## Files Created/Modified

- `pyproject.toml` - package metadata, Python build config, and `aurora` script entrypoint.
- `src/aurora/__init__.py` - package initialization and version export.
- `src/aurora/cli/__init__.py` - CLI package export surface.
- `src/aurora/cli/app.py` - Typer root app and Phase 1 placeholder command groups.
- `tests/cli/test_entrypoint.py` - entrypoint and command-surface smoke tests.
- `README.md` - global installation and PATH troubleshooting instructions.

## Decisions Made

- Locked Phase 1 command-group names (`setup`, `config`, `model`, `doctor`) at root level now to preserve future command stability.
- Placeholder group invocation returns explicit pt-BR errors with `exit_code=1` to make unfinished behavior obvious.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Typer root app raised runtime error without callback**
- **Found during:** Task 1
- **Issue:** A Typer app with no callback/commands raised `RuntimeError: Could not get a command for this Typer instance` in test execution.
- **Fix:** Added a root callback and deterministic test invocation (`prog_name="aurora"`) so help rendering is stable.
- **Files modified:** `src/aurora/cli/app.py`, `tests/cli/test_entrypoint.py`
- **Verification:** `uv run pytest tests/cli/test_entrypoint.py -q`
- **Committed in:** `30bc755`

---

**Total deviations:** 1 auto-fixed (Rule 1: 1)
**Impact on plan:** No scope creep; fix was required for command correctness and test stability.

## Issues Encountered

- `~/.claude/get-shit-done/bin/gsd-tools.cjs` was unavailable in this workspace. Execution proceeded with the available `~/.codex/get-shit-done/bin/gsd-tools.cjs` path.

## Authentication Gates

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 1 Plan 01 baseline is complete. The repository now exposes a stable CLI contract and placeholder groups required for `01-02-PLAN.md`.

---
*Phase: 01-local-runtime-baseline*
*Completed: 2026-03-02*

## Self-Check: PASSED
