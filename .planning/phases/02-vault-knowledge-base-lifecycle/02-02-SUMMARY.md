---
phase: 02-vault-knowledge-base-lifecycle
plan: 02
subsystem: kb
tags: [scope, scanner, templater, privacy]
requires:
  - phase: 02-01
    provides: KB contracts, `aurora kb` namespace, and persisted KB scope settings
provides:
  - Case-sensitive scope evaluation with vault-boundary enforcement and dry-run previews
  - Deterministic markdown scanner with scope-aware skip diagnostics
  - Templater preprocessing output with cleaned snippet/span metadata
affects: [02-03, 02-04, kb lifecycle operations]
tech-stack:
  added: []
  patterns: [vault-relative normalization, fnmatchcase scope rules, privacy-safe preprocessing metadata]
key-files:
  created:
    - src/aurora/kb/scope.py
    - src/aurora/kb/scanner.py
    - src/aurora/kb/preprocess.py
    - tests/kb/test_scope.py
    - tests/kb/test_scanner.py
    - tests/kb/test_preprocess.py
  modified: []
key-decisions:
  - "Scope rules validate include/exclude patterns against vault boundaries using `Path.resolve` and `is_relative_to`."
  - "Scanner classifies hidden/system skips from default excludes while keeping deterministic sorted output."
  - "Templater preprocessing strips `<%...%>` variants and reports cleanup metadata without logging raw note content."
patterns-established:
  - "Scope Pattern: evaluate excludes before includes so exclude precedence is explicit and stable."
  - "Pipeline Pattern: keep scanner content-blind and push cleanup logic into dedicated preprocessing module."
requirements-completed: [KB-01, KB-05, PRIV-02]
duration: 3 min
completed: 2026-03-03
---

# Phase 2 Plan 2: Scoped Discovery and Preprocessing Summary

**Vault-scoped markdown discovery with case-sensitive include/exclude enforcement and templater cleanup metadata for KB lifecycle commands**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-03T22:48:07Z
- **Completed:** 2026-03-03T22:51:55Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- Added `ScopeRules` engine with case-sensitive matching, exclude precedence, vault-boundary checks, and dry-run preview payloads.
- Implemented deterministic scanner that indexes only lowercase `.md` files, ignores symlinks, and reports privacy-safe skip reasons.
- Implemented templater preprocessing that removes common `<% ... %>` variants while emitting cleaned snippet/span metadata.

## Task Commits

Each task was committed atomically:

1. **Task 1: Build scope rule engine with vault-boundary enforcement and dry-run preview** - `9668158` (test), `09c1f44` (feat)
2. **Task 2: Implement markdown scanner constrained to scope and privacy defaults** - `2281eca` (test), `e0b6675` (feat)
3. **Task 3: Add templater pre-processing with traceability metadata** - `894b529` (test), `6b9983c` (feat)

## Files Created/Modified
- `src/aurora/kb/scope.py` - Scope evaluator, dry-run preview types, and vault-boundary validations.
- `src/aurora/kb/scanner.py` - Deterministic scanner with extension/symlink/scope skip classification.
- `src/aurora/kb/preprocess.py` - Templater cleanup pipeline with per-file metadata contract.
- `tests/kb/test_scope.py` - Scope behavior coverage for case sensitivity, precedence, and zero-match handling.
- `tests/kb/test_scanner.py` - Scanner behavior coverage for scoped indexing and skip reasons.
- `tests/kb/test_preprocess.py` - Preprocessor coverage for no-template, multi-template, and variant cleanup.

## Decisions Made
- Kept scope validation strict: include/exclude rules must remain relative to vault context and fail fast when escaping via `..` or absolute patterns.
- Classified default-exclude hits as `hidden_system_exclusion` in scanner output to keep privacy defaults explicit in diagnostics.
- Preserved preprocessing traceability via explicit `cleaned_spans` and count fields so downstream summaries can report cleanup without leaking note text.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Hidden-folder normalization accidentally removed leading dots**
- **Found during:** Task 1 (scope engine implementation)
- **Issue:** Relative-path normalization used broad stripping that converted `.obsidian/...` into `obsidian/...`, breaking default-exclude matches.
- **Fix:** Replaced broad prefix stripping with explicit `./` prefix handling.
- **Files modified:** `src/aurora/kb/scope.py`
- **Verification:** `uv run pytest tests/kb/test_scope.py -q`
- **Committed in:** `09c1f44` (part of Task 1 feat commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Auto-fix was required for correct hidden/system exclusion behavior; no scope expansion.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Scope, scanner, and preprocessing contracts are stable for manifest/delta integration in `02-03`.
- Ready for `02-03-PLAN.md`.

## Self-Check: PASSED
- Verified all key files for this plan exist on disk.
- Verified all task commit hashes are present in git history.

---
*Phase: 02-vault-knowledge-base-lifecycle*
*Completed: 2026-03-03*
