---
phase: 05-operational-command-surface
fixed_at: 2026-04-11T12:45:00Z
review_path: .planning/phases/05-operational-command-surface/05-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 05: Code Review Fix Report

**Fixed at:** 2026-04-11T12:45:00Z
**Source review:** .planning/phases/05-operational-command-surface/05-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (all Warning severity; Critical=0, Info=6 out of scope)
- Fixed: 5
- Skipped: 0

All 9 `tests/cli/test_doctor.py` tests and the full 142-test `tests/cli/` suite
pass after each fix.

## Fixed Issues

### WR-01: `run_doctor_checks` does not catch `RuntimeSettingsLoadError`

**Files modified:** `src/aurora/cli/doctor.py`
**Commit:** 38947b0
**Applied fix:**
- Added `RuntimeSettingsLoadError` to the imports from `aurora.runtime.settings`.
- Extracted the duplicated text/JSON load-failure rendering into a new
  `_emit_load_failure(*, category, message, commands, json_output)` helper
  that builds a single `DoctorIssue` and emits it in the same shape the
  `Phase1PolicyError` handler was producing inline.
- Added an `except RuntimeSettingsLoadError as error` branch next to the
  existing `Phase1PolicyError` branch. Both branches now call
  `_emit_load_failure` and then `raise typer.Exit(code=1)`, so a corrupted or
  schema-invalid settings file produces a structured diagnostic
  (category `settings_load_error`, recovery: `aurora config setup`,
  `aurora config show`) instead of an uncaught Python traceback.
- Registered `"settings_load_error": "Configuracao"` in the `_print_issues`
  headings table so the new category prints under a readable group name.

### WR-02: `_check_required_packages` reports `httpx` as missing even though Aurora does not depend on it

**Files modified:** `src/aurora/cli/doctor.py`
**Commit:** f99ad01
**Applied fix:**
- Replaced the required-package tuple with the direct dependencies declared
  in `pyproject.toml` `[project.dependencies]`: `typer`, `pydantic-settings`,
  `pyyaml`, `huggingface-hub`, `platformdirs`, `qmd`.
- Removed `httpx` (not imported anywhere in `src/aurora`, only a transitive
  dep) and `pydantic` (transitive via `pydantic-settings`).
- Added a comment warning maintainers not to add transitive deps here, so the
  drift is unlikely to recur.

### WR-03: `_check_memory_index` suggests a destructive recovery command

**Files modified:** `src/aurora/cli/doctor.py`
**Commit:** a56f9bc
**Applied fix:**
- Changed the recovery `commands` tuple for `memory_index_missing` to list a
  non-destructive option first (`aurora chat`), then the destructive fallback
  (`aurora config memory clear --yes`).
- `aurora chat` / `aurora ask` call `EpisodicMemoryStore` which runs
  `_ensure_qmd_collection` + `_qmd_update` in `src/aurora/memory/store.py`,
  re-registering the `aurora-memory` collection and re-embedding existing
  memory files without deleting them. Confirmed this is the actual
  re-indexing path because no dedicated `aurora config memory reindex`
  command exists in `src/aurora/cli/memory.py`.
- Added inline comments explaining which command is safe vs. destructive
  (with the pt-BR `ATENCAO` warning on the destructive one) so future readers
  cannot swap the order back.

### WR-04: Substring matching against `qmd collection list` is unreliable

**Files modified:** `src/aurora/cli/doctor.py`
**Commit:** 43a78a8
**Applied fix:**
- Added a new module-level helper `_collection_present(stdout, name)` that
  splits `qmd collection list` output on newlines, strips each line, filters
  empty lines, and tests exact set membership. The docstring documents the
  substring-collision failure mode this fixes.
- Replaced `settings.kb_qmd_collection_name not in (result.stdout or "")` in
  `_check_kb_embeddings` with
  `not _collection_present(result.stdout or "", settings.kb_qmd_collection_name)`.
- Replaced `"aurora-memory" not in (result.stdout or "")` in
  `_check_memory_index` with
  `not _collection_present(result.stdout or "", MEMORY_COLLECTION)`, and
  extended the lazy import inside the function to pull
  `MEMORY_COLLECTION` from `aurora.memory.store` (incidentally also
  addressing Info finding IN-06 — hardcoded literal `"aurora-memory"` — as
  the review explicitly recommends). Also used `{MEMORY_COLLECTION}` inside
  the issue message f-string.

### WR-05: `doctor` duplicates QMD-related diagnostics when `qmd` is broken

**Files modified:** `src/aurora/cli/doctor.py`
**Commit:** ab5319a
**Applied fix:**
- Restructured the check sequence inside `run_doctor_checks` so downstream
  QMD-dependent checks short-circuit when the upstream QMD checks fail.
- Captured `_check_qmd_binary()` result into a local `qmd_missing`. If it is
  already an issue, `_check_qmd_version()` is skipped (`qmd_broken = None`)
  to avoid calling a binary we already know is missing. Otherwise
  `qmd_broken = _check_qmd_version()`.
- Derived `qmd_ok = qmd_missing is None and qmd_broken is None`.
- Wrapped `_check_kb_embeddings(settings)` and `_check_memory_index(settings)`
  inside `if qmd_ok:` so a single broken `qmd` install now surfaces as one
  diagnostic instead of three cascading issues.
- `_check_kb_collection(settings)` is kept outside the gate because it reads
  the KB manifest on disk, which does not depend on the `qmd` binary.
- Added explanatory comments describing why the ordering matters so future
  edits do not accidentally remove the short-circuit.

## Verification

- **Tier 1 (re-read):** Applied after every edit; confirmed each fix text was
  present and surrounding code intact.
- **Tier 2 (syntax check):** `python3 -c "import ast; ast.parse(open(...))"`
  run after each edit to `src/aurora/cli/doctor.py`. All passed.
- **Tier 3 (test suite):** After all five fixes, ran
  `uv run pytest tests/cli/test_doctor.py` (9 passed) and
  `uv run pytest tests/cli/` (142 passed). Both suites were green without any
  test changes — the existing happy-path monkeypatches already produce
  `stdout="aurora-kb-managed\naurora-memory"`, which splits into exact lines
  and still satisfies the new `_collection_present` helper.

## Skipped Issues

None.

---

_Fixed: 2026-04-11T12:45:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
