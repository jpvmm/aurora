---
phase: 05-operational-command-surface
reviewed: 2026-04-11T12:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - src/aurora/cli/app.py
  - src/aurora/cli/config.py
  - src/aurora/cli/deprecated.py
  - src/aurora/cli/doctor.py
  - src/aurora/cli/status.py
  - tests/cli/test_doctor.py
  - tests/cli/test_entrypoint.py
  - tests/cli/test_kb_command.py
  - tests/cli/test_memory_command.py
  - tests/cli/test_model_command.py
  - tests/cli/test_status_command.py
findings:
  critical: 0
  warning: 5
  info: 6
  total: 11
status: issues_found
---

# Phase 05: Code Review Report

**Reviewed:** 2026-04-11T12:00:00Z
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Reviewed the new operational command surface (`aurora status`, extended `aurora doctor`,
root `config` namespace with `kb`/`model`/`memory`/`setup` subgroups, and deprecated
top-level aliases) plus their test coverage. The implementation is well-structured,
uses graceful-degradation patterns correctly in `status.py`, and has thorough test
coverage across all new commands.

Overall the code is in good shape. Five Warning-level issues are worth addressing
before shipping:

1. `doctor` crashes on a corrupted settings file because it only catches
   `Phase1PolicyError` — a sibling exception `RuntimeSettingsLoadError` from the
   same module will propagate unhandled and produce a stack trace rather than a
   structured diagnostic.
2. `_check_required_packages` reports spurious "missing package" diagnostics for
   `httpx`, which is not a direct dependency of Aurora (and Aurora code never
   imports it). A user without `httpx` in their environment will see a bogus
   red flag from `aurora doctor`.
3. `_check_memory_index` recommends the destructive command
   `aurora config memory clear --yes` as the recovery when the memory QMD
   collection is missing. Clearing is the wrong escalation — it deletes the
   user's memory files as well as the index.
4. `_check_kb_embeddings` and `_check_memory_index` use substring matching against
   `qmd collection list` output, which yields false positives/negatives when one
   collection name is a substring of another (e.g. `aurora-memory` matches
   `aurora-memory-backup`, and the default collection name `aurora-kb-managed`
   would match `aurora-kb-managed-v2`).
5. `doctor` re-probes `qmd` via `_check_kb_embeddings`/`_check_memory_index`
   after `_check_qmd_version` has already failed, producing duplicated (and
   misleading) issues for a single root cause.

Six Info-level items cover stale comments, dead test code, and minor
maintainability concerns.

## Warnings

### WR-01: `run_doctor_checks` does not catch `RuntimeSettingsLoadError`

**File:** `src/aurora/cli/doctor.py:59-96`
**Issue:** `load_settings()` raises two distinct exception types — `Phase1PolicyError`
(from the privacy policy validator) and `RuntimeSettingsLoadError` (from
`src/aurora/runtime/settings.py:104-105`, wrapping `ValidationError`,
`json.JSONDecodeError`, and `OSError`). `run_doctor_checks` only catches
`Phase1PolicyError`. If the user has a corrupted or schema-invalid settings file
(e.g. manual edit, partial write after crash, downgraded schema), `aurora doctor`
— the command they would naturally run to diagnose the problem — will explode
with an uncaught exception and a Python traceback, defeating the purpose of the
tool.

**Fix:**

```python
from aurora.runtime.settings import RuntimeSettings, RuntimeSettingsLoadError, load_settings

def run_doctor_checks(*, json_output: bool = False) -> None:
    try:
        settings = load_settings()
    except Phase1PolicyError:
        _emit_load_failure(
            category="policy_mismatch",
            message="Endpoint configurado viola a politica local-only.",
            commands=(
                "aurora model set --endpoint http://127.0.0.1:8080",
                "aurora config show",
            ),
            json_output=json_output,
        )
        raise typer.Exit(code=1)
    except RuntimeSettingsLoadError as error:
        _emit_load_failure(
            category="settings_load_error",
            message=f"Nao foi possivel carregar as configuracoes: {error}.",
            commands=(
                "aurora config setup",
                "aurora config show",
            ),
            json_output=json_output,
        )
        raise typer.Exit(code=1)
    ...
```

Factor the JSON-vs-text branch of the existing `Phase1PolicyError` handler into
a small helper so both failure modes share the same shape.

---

### WR-02: `_check_required_packages` reports `httpx` as missing even though Aurora does not depend on it

**File:** `src/aurora/cli/doctor.py:333-347`
**Issue:** The required list is
`("typer", "pydantic", "pydantic-settings", "pyyaml", "httpx")`. Checking
`pyproject.toml`, Aurora's direct dependencies are `huggingface-hub`,
`platformdirs`, `pydantic-settings`, `pytest`, `pyyaml`, `qmd`, `typer`. Neither
`pydantic` nor `httpx` is declared directly, and `grep` confirms that no file in
`src/aurora` imports `httpx` at all. `httpx` is only present as a transitive
dependency of some other package. A user on a minimal install — or an alternate
Python environment where the transitive chain drops `httpx` — will see
`aurora doctor` surface a false-positive "pacote 'httpx' nao instalado" with
the suggestion `pip install httpx`, which does not solve any real problem and
adds noise that hides real diagnostics.

A related, smaller issue: `pydantic` is not a direct dep either, but at least
it is imported by `aurora.runtime.settings` and `aurora.kb.contracts`, so it is
always pulled via `pydantic-settings`. That makes it *reasonable* to check, but
still violates the principle of listing only direct deps.

**Fix:** Align the check with actual `pyproject.toml` direct deps, and either
drop `httpx` entirely or limit `_check_required_packages` to the packages that
Aurora explicitly requires:

```python
def _check_required_packages() -> list[DoctorIssue]:
    # Mirror pyproject.toml [project.dependencies]; do not list transitive deps.
    required = (
        "typer",
        "pydantic-settings",
        "pyyaml",
        "huggingface-hub",
        "platformdirs",
        "qmd",
    )
    ...
```

Long-term, consider parsing `importlib.metadata.requires("aurora")` to avoid
drift between `pyproject.toml` and the doctor list.

---

### WR-03: `_check_memory_index` suggests a destructive recovery command

**File:** `src/aurora/cli/doctor.py:302-310`
**Issue:** When `EpisodicMemoryStore.list_memories()` reports that memories
exist on disk but the `aurora-memory` QMD collection is missing, the check
emits the recovery command `aurora config memory clear --yes`. Per
`tests/cli/test_memory_command.py` (`test_memory_clear_with_yes_deletes_files`),
`memory clear --yes` deletes **both** the episodic files (`mock_store.clear`
returns the count of removed files) and the QMD collection. So the recovery
command the doctor recommends tells the user to delete the very data whose
index is missing — a destructive action that is almost never what the user
wants when they just want to rebuild embeddings.

**Fix:** Either

1. Recommend a non-destructive re-index path (e.g.
   `aurora config memory rebuild` if one exists, or document that re-running
   `chat`/`ask` will re-index), or
2. Explicitly warn that this is destructive and offer both options:

```python
return DoctorIssue(
    category="memory_index_missing",
    message=(
        f"Memorias encontradas ({len(memories)}) mas colecao QMD "
        "aurora-memory ausente."
    ),
    commands=(
        # Non-destructive: rebuild index from existing files
        "aurora config memory reindex",  # add this command if not present
        # Destructive fallback (ATENCAO: apaga as memorias):
        "aurora config memory clear --yes",
    ),
)
```

If no non-destructive reindex command exists, add one in a follow-up before
shipping this check — recommending `clear` as the primary recovery for a
missing index is a footgun.

---

### WR-04: Substring matching against `qmd collection list` is unreliable

**File:** `src/aurora/cli/doctor.py:259, 302`
**Issue:** Both `_check_kb_embeddings` and `_check_memory_index` test collection
presence with `X not in result.stdout`. This fails in two ways:

1. **False positive (check passes when collection is absent):** If
   `kb_qmd_collection_name = "aurora-kb"` and the user has
   `aurora-kb-managed` in their index but not `aurora-kb`, the substring check
   considers the collection present even though the exact name is missing.
2. **False negative (check fails when collection is present):** Any collection
   name that is itself a substring of another collection name — including the
   trivial case where a user renames a collection to a shorter prefix — will
   match incorrectly.

The issue is latent today because the defaults `aurora-kb-managed` /
`aurora-memory` are long-ish strings, but the moment anyone configures a
shorter name via `aurora config kb config set --collection ...` or
`--index ...`, the check becomes unreliable.

**Fix:** Split the output into lines and use exact-match on stripped entries:

```python
def _collection_present(stdout: str, name: str) -> bool:
    # qmd prints one collection per line; match exact name, not substring.
    return name in {line.strip() for line in stdout.splitlines() if line.strip()}

# ...
if not _collection_present(result.stdout or "", settings.kb_qmd_collection_name):
    ...
if not _collection_present(result.stdout or "", MEMORY_COLLECTION):
    ...
```

While you are here, import `MEMORY_COLLECTION` from `aurora.memory.store`
instead of hardcoding `"aurora-memory"` on line 302, so the constant has a
single source of truth.

---

### WR-05: `doctor` duplicates QMD-related diagnostics when `qmd` is broken

**File:** `src/aurora/cli/doctor.py:184-207, 236-269, 272-311`
**Issue:** `_check_qmd_version` reports that `qmd` is installed but failing
(`--version` exits non-zero). `_check_kb_embeddings` and `_check_memory_index`
do not know the version check failed — they only guard on `shutil.which("qmd")`
and therefore still attempt `qmd --index ... collection list`, which will
almost certainly fail in the same way. The user ends up with three
near-identical issues (`qmd_version`, `kb_embeddings_missing`, possibly
`memory_index_missing`), all rooted in a single broken install. This is
confusing and hides the true root cause under noise.

**Fix:** Thread a lightweight "qmd is functional" sentinel through the check
sequence, or restructure so downstream checks short-circuit when the upstream
check fails:

```python
def run_doctor_checks(*, json_output: bool = False) -> None:
    ...
    _append_if_issue(issues, _check_python_version())
    qmd_missing = _check_qmd_binary()
    _append_if_issue(issues, qmd_missing)
    qmd_broken = None if qmd_missing else _check_qmd_version()
    _append_if_issue(issues, qmd_broken)

    qmd_ok = qmd_missing is None and qmd_broken is None
    _append_if_issue(issues, _check_kb_collection(settings))
    if qmd_ok:
        _append_if_issue(issues, _check_kb_embeddings(settings))
        _append_if_issue(issues, _check_memory_index(settings))
    _append_if_issue(issues, _check_disk_space())
    issues.extend(_check_required_packages())
```

This keeps the "full diagnostic sweep" intent but ensures each real problem is
reported once.

## Info

### IN-01: Stale comment about circular imports in `config.py`

**File:** `src/aurora/cli/config.py:85-86`
**Issue:** The comment reads "Imported at module bottom to avoid circular
imports (setup.py imports from config via model_set_command chain)." Grep shows
that `setup.py`, `model.py`, `kb.py`, and `memory.py` do **not** import
anything from `aurora.cli.config`. The import-at-bottom pattern may still be
defensive against a future cycle, but the justification in the comment is
factually wrong and will mislead future maintainers.
**Fix:** Either remove the justification or rewrite it to describe the *real*
reason (e.g. "Deferred to keep `mask_sensitive` importable from `doctor.py`
and `status.py` before the sub-typers are wired up.").

---

### IN-02: Pitfall 1 claim in `deprecated.py` header comment is imprecise

**File:** `src/aurora/cli/deprecated.py:8-11`
**Issue:** The header says the typers do not set `invoke_without_command=True`
so that "Typer's help machinery keeps working at the parent level
(`aurora kb --help`) without firing the callback for help-only invocations."
In practice, `--help` is an eager Click option that short-circuits group
callbacks regardless of `invoke_without_command`. The design choice is fine
(and the tests pass), but the justification conflates two orthogonal settings.
Consider rephrasing to: "`no_args_is_help=True` ensures `aurora kb` with no
subcommand prints help without running the deprecation callback; the callback
is intentionally called on real subcommand invocations
(`aurora kb ingest ...`) so the deprecation warning appears on the output
paths users actually exercise."

---

### IN-03: Dead monkeypatch in `test_status_command.py`

**File:** `tests/cli/test_status_command.py:53`
**Issue:** `monkeypatch.setattr(status_module, "_run_status", status_module._run_status)`
sets the attribute to the same object it already holds — a no-op. It looks
like scaffolding from an earlier refactor.
**Fix:** Delete the line.

---

### IN-04: `_run_status` names a field `last_session` but populates it from the dict key `date`

**File:** `src/aurora/cli/status.py:128-139`
**Issue:** The variable / JSON key is `last_session`, but it pulls
`tail.get("date")`. This is not a bug (the value is a date string, which is
fine for display), but the naming inconsistency will confuse future readers
who look for a `session_id` or similar semantic meaning.
**Fix:** Rename to `last_session_date` in both text and JSON output, or change
the source key lookup to a field that genuinely represents a session identity.

---

### IN-05: `mask_sensitive` does not re-encode query values

**File:** `src/aurora/cli/config.py:74-82`
**Issue:** The function uses `parse_qsl` to parse the query, then
reconstructs it with manual `f"{key}={value}"` joining. Values that contained
percent-encoded characters (`%20`, `%3D`, etc.) lose their encoding and are
rewritten verbatim. This is only cosmetic — the output is meant for humans,
not re-parsed — but a future caller that feeds `mask_sensitive(url)` back into
a URL library will get surprising round-trip behavior.
**Fix:** Use `urllib.parse.urlencode(query_parts, doseq=True)` for the
reconstruction.

---

### IN-06: Hardcoded `"aurora-memory"` literal in `_check_memory_index`

**File:** `src/aurora/cli/doctor.py:302, 306`
**Issue:** `aurora.memory.store` already exports `MEMORY_COLLECTION = "aurora-memory"`
(confirmed by `tests/cli/test_memory_command.py:300` which imports it). The
doctor hardcodes the literal string twice, creating a drift risk if the
collection is ever renamed.
**Fix:**

```python
from aurora.memory.store import MEMORY_COLLECTION
...
if not _collection_present(result.stdout or "", MEMORY_COLLECTION):
    return DoctorIssue(
        category="memory_index_missing",
        message=(
            f"Memorias encontradas ({len(memories)}) mas colecao QMD "
            f"{MEMORY_COLLECTION} ausente."
        ),
        ...
    )
```

This pairs naturally with the fix in WR-04.

---

_Reviewed: 2026-04-11T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
