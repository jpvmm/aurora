---
phase: 05-operational-command-surface
fixed_at: 2026-04-11T14:30:00Z
review_path: .planning/phases/05-operational-command-surface/05-REVIEW.md
iteration: 2
findings_in_scope: 11
fixed: 5
skipped: 6
status: partial
---

# Phase 05: Code Review Fix Report

**Fixed at:** 2026-04-11T14:30:00Z
**Source review:** .planning/phases/05-operational-command-surface/05-REVIEW.md
**Iteration:** 2

**Summary:**
- Findings in scope: 11 (5 Warning + 6 Info; `fix_scope=all`)
- Fixed this iteration: 5 (IN-01..IN-05)
- Skipped this iteration: 6 (WR-01..WR-05 already fixed in iteration 1 commits
  `38947b0`, `f99ad01`, `43a78a8`, `a56f9bc`, `ab5319a`; IN-06 addressed
  incidentally by iteration-1 WR-04 fix). Skipping here means "no new source
  change was needed this iteration" — all six were verified resolved in
  current `HEAD` before being marked skipped.

**Test results:**
- CLI unit suite (`tests/cli/`): 142 passed, 0 failed.
- Full suite (`.venv/bin/pytest -q`): 460 passed, 1 failed. The single failure
  is in `tests/integration/test_kb_qmd_integration.py::test_real_qmd_lifecycle_ingest_update_delete_rebuild`
  at the `aurora kb delete` step (exit code 1). This failure is pre-existing
  and **not** caused by iteration-2 fixes: verified by re-running just that
  test — it fails identically on commits made by this iteration, and the only
  files touched in iteration 2 (`src/aurora/cli/config.py`,
  `src/aurora/cli/deprecated.py`, `src/aurora/cli/status.py`,
  `tests/cli/test_status_command.py`) have no code path into the
  `aurora kb delete` integration harness. Flagging for the developer as a
  separate environmental issue to triage.

## Fixed Issues

### IN-01: Stale comment about circular imports in `config.py`

**Files modified:** `src/aurora/cli/config.py`
**Commit:** `9ef07f1`
**Applied fix:** Rewrote the justification at `config.py:85-89` to describe
the real reason the sub-typer imports are deferred — keeping `mask_sensitive`
and the top-level `config_app` importable from `aurora.cli.doctor` and
`aurora.cli.status` before the sub-typers (which themselves import from
`aurora.cli.config` via shared command helpers) are wired up. The previous
claim that "setup.py imports from config via model_set_command chain" was
factually wrong: grep confirms `aurora.cli.setup`, `aurora.cli.model`,
`aurora.cli.kb`, and `aurora.cli.memory` never import from `aurora.cli.config`.

### IN-02: Imprecise Pitfall 1 header comment in `deprecated.py`

**Files modified:** `src/aurora/cli/deprecated.py`
**Commit:** `59c88b9`
**Applied fix:** Rephrased the header docstring at `deprecated.py:8-13` so it
now attributes bare-group help behavior to `no_args_is_help=True` (not
`invoke_without_command=False`), states that the deprecation callback is
intentionally invoked on real subcommand invocations like
`aurora kb ingest ...`, and explicitly notes — as a parenthetical — that
`--help` is an eager Click option that short-circuits the group callback
regardless of `invoke_without_command`, so the two settings are orthogonal.
The rewording matches the reviewer's suggested phrasing in IN-02.

### IN-03: Dead monkeypatch in `test_status_command.py`

**Files modified:** `tests/cli/test_status_command.py`
**Commit:** `21466ee`
**Applied fix:** Deleted the no-op line
`monkeypatch.setattr(status_module, "_run_status", status_module._run_status)`
at line 53 inside `_install_happy_path_monkeypatches`. Kept the `status_module`
parameter in the helper signature to avoid churning the two test call sites
(`test_status_renders_text_dashboard`, `test_status_json_returns_structured_output`)
which still pass `status_module` in. All four `test_status_command.py` tests
continue to pass.

### IN-04: `last_session` vs `date` naming mismatch in `status.py`

**Files modified:** `src/aurora/cli/status.py`
**Commit:** `24c9629`
**Applied fix:** Renamed the variable and JSON key `last_session` ->
`last_session_date` at all three references in `status.py`:
- Variable declaration and type annotation at line 130 (with an inline comment
  noting that the source key `date` is a human-readable date string, not a
  session identifier — references REVIEW IN-04).
- JSON payload key at line 164 (`"last_session_date": last_session_date`).
- Text output interpolation at line 196 (`ultima sessao: {last_session_date or 'nenhuma'}`).

Grep confirmed no test file, nor any downstream code, references the old
`last_session` key name — so the rename is safe and does not require updating
test fixtures. Chose renaming over the "change source key lookup" alternative
because no session-identity field actually exists in `EpisodicMemoryStore`
records today.

### IN-05: `mask_sensitive` does not re-encode query values

**Files modified:** `src/aurora/cli/config.py`
**Commit:** `783a441`
**Applied fix:** Added `urlencode` to the `urllib.parse` import at line 4 and
replaced the manual `"&".join(f"{key}={query_value}" ...)` reconstruction
inside `mask_sensitive` with `urlencode(query_parts, doseq=True)` (lines
80-82, with an inline comment explaining the round-trip concern). Percent-
encoded values like `%20` and `%3D` are now re-encoded on output instead of
being rewritten verbatim. Exercised the round-trip in a throwaway Python
snippet to confirm `http://h/p?x=a%20b&y=c%3Dd` yields the expected
`x=a+b&y=c%3Dd` (both forms decode to the same `a b` / `c=d` pair). No test
regressions in `tests/cli/test_app.py` which exercises `mask_sensitive` via
`aurora config show`.

## Skipped Issues

All six entries below were already resolved before iteration 2 began. Verified
each is still present in the current source before marking as skipped.

### WR-01: `run_doctor_checks` does not catch `RuntimeSettingsLoadError`

**File:** `src/aurora/cli/doctor.py:59-96`
**Reason:** Already fixed in iteration 1 (commit `38947b0`). Verified the
`except RuntimeSettingsLoadError as error` branch is present at
`doctor.py:72-82` and delegates to the shared `_emit_load_failure` helper.
The helper (lines 151-189) emits a single `DoctorIssue` with category
`settings_load_error` in the same text/JSON shape as the `Phase1PolicyError`
path, so a corrupted settings file no longer crashes `aurora doctor`.
**Original issue:** `load_settings()` raises `RuntimeSettingsLoadError`
(wrapping `ValidationError` / `JSONDecodeError` / `OSError`) in addition to
`Phase1PolicyError`, but `run_doctor_checks` only caught the latter — causing
`aurora doctor` to blow up with a traceback on exactly the failure mode a user
would run it to diagnose.

### WR-02: `_check_required_packages` reports `httpx` as missing

**File:** `src/aurora/cli/doctor.py:333-347`
**Reason:** Already fixed in iteration 1 (commit `f99ad01`). Verified the
`required` tuple in `_check_required_packages` at `doctor.py:391-398` now
mirrors `pyproject.toml [project.dependencies]` exactly — `typer`,
`pydantic-settings`, `pyyaml`, `huggingface-hub`, `platformdirs`, `qmd` — and
no longer references `httpx` or `pydantic`. A comment at line 388 warns
maintainers not to add transitive deps.
**Original issue:** `aurora doctor` reported `httpx` as a missing required
package even though Aurora never imports it, adding a false-positive that
hid real diagnostics.

### WR-03: `_check_memory_index` suggests a destructive recovery command

**File:** `src/aurora/cli/doctor.py:302-310`
**Reason:** Already fixed in iteration 1 (commit `43a78a8`). Verified
`_check_memory_index` at `doctor.py:349-364` now lists `aurora chat` as the
primary (non-destructive) recovery command — it re-registers the QMD
collection and re-embeds memories on disk via
`EpisodicMemoryStore._ensure_qmd_collection` / `_qmd_update`. The destructive
`aurora config memory clear --yes` is retained as a fallback with a pt-BR
`ATENCAO` comment warning that it deletes memories on disk in addition to
the index.
**Original issue:** The doctor's primary recovery command for a missing memory
index was `aurora config memory clear --yes`, which destructively deletes
both the episodic files and the QMD collection — exactly the data the user
was trying to re-index.

### WR-04: Substring matching against `qmd collection list` output

**File:** `src/aurora/cli/doctor.py:259, 302`
**Reason:** Already fixed in iteration 1 (commit `a56f9bc`). Verified the new
module-level helper `_collection_present(stdout, name)` at `doctor.py:273-280`
which splits output on newlines, strips each line, and tests exact set
membership (`name in {line.strip() for line in stdout.splitlines() if line.strip()}`).
Both `_check_kb_embeddings` (line 306) and `_check_memory_index` (line 349)
call the helper. A quick regression scenario — a user with
`aurora-kb-managed-v2` but no `aurora-kb-managed` — is now correctly flagged.
**Original issue:** `X not in result.stdout` substring checks gave false
positives and false negatives when collection names were substrings of other
names in `qmd collection list` output.

### WR-05: `doctor` duplicates QMD diagnostics when `qmd` is broken

**File:** `src/aurora/cli/doctor.py:184-207, 236-269, 272-311`
**Reason:** Already fixed in iteration 1 (commit `ab5319a`). Verified the
short-circuit pattern in `run_doctor_checks` at `doctor.py:118-127`:
`qmd_missing = _check_qmd_binary()`,
`qmd_broken = None if qmd_missing is not None else _check_qmd_version()`,
`qmd_ok = qmd_missing is None and qmd_broken is None`. Both
`_check_kb_embeddings(settings)` and `_check_memory_index(settings)` are
wrapped in `if qmd_ok:` so a single broken `qmd` install now surfaces as one
root-cause diagnostic instead of three cascading issues.
**Original issue:** When `qmd --version` exited non-zero, the two downstream
checks still probed `qmd --index ... collection list`, producing duplicated
and misleading diagnostics for a single root cause.

### IN-06: Hardcoded `"aurora-memory"` literal in `_check_memory_index`

**File:** `src/aurora/cli/doctor.py:302, 306`
**Reason:** Addressed incidentally by the iteration-1 WR-04 fix (commit
`a56f9bc`). Verified via grep that the literal `"aurora-memory"` no longer
appears anywhere in `src/aurora/cli/doctor.py`. The check now imports
`MEMORY_COLLECTION` alongside `EpisodicMemoryStore` at `doctor.py:321`,
passes it to `_collection_present` at line 349, and interpolates it into the
issue message at line 354.
**Original issue:** `_check_memory_index` hardcoded the string
`"aurora-memory"` twice instead of importing the already-exported
`MEMORY_COLLECTION` constant from `aurora.memory.store`, creating a drift
risk if the collection name is ever changed.

---

_Fixed: 2026-04-11T14:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 2_
