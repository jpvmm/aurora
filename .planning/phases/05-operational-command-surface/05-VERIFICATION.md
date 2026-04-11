---
phase: 05-operational-command-surface
verified: 2026-04-11T16:00:00Z
status: human_needed
score: 10/10 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Triage REVIEW.md WR-01: doctor crash on corrupted settings file"
    expected: "Decide whether to fix WR-01 (catch RuntimeSettingsLoadError in run_doctor_checks) before shipping or defer to a follow-up plan. Current behavior: any malformed settings file produces an unhandled traceback from `aurora doctor` instead of a structured diagnostic."
    why_human: "Acceptance criteria says 'actionable guidance' but the SC does not explicitly require crash-resilience on corrupted settings. Whether this is a ship-blocker depends on operator risk tolerance — needs developer decision."
  - test: "Triage REVIEW.md WR-03: destructive recovery for memory_index_missing"
    expected: "Decide whether `_check_memory_index` should keep recommending `aurora config memory clear --yes` (destructive — deletes both files and index) as the recovery, or be changed to a non-destructive reindex path or an explicit warning. Current behavior: doctor tells users to delete their own memory files when only the QMD index is missing."
    why_human: "This is a UX/safety footgun. The SC says 'actionable guidance' — the guidance is technically present but could cause data loss. Developer must decide whether 'actionable' implies 'safe' for verification purposes."
  - test: "Triage REVIEW.md WR-02: false-positive `httpx` package missing"
    expected: "Decide whether `_check_required_packages` should drop `httpx` (and possibly `pydantic`) from the required-package list since neither is a direct dep in pyproject.toml. Current behavior: a user without httpx in their environment sees a bogus 'pacote httpx nao instalado' diagnostic."
    why_human: "False-positive diagnostics undermine trust in doctor. SC achievement is technically met but quality is degraded."
  - test: "Triage REVIEW.md WR-04: substring matching against `qmd collection list`"
    expected: "Decide whether to fix `_check_kb_embeddings` and `_check_memory_index` to use exact line-match instead of `name in stdout`. Current behavior: works correctly for the default long collection names but produces false positives/negatives if a user configures a shorter collection name that is a substring of another."
    why_human: "Latent bug — defaults work today, but the check is unreliable under user-configurable collection names."
  - test: "Triage REVIEW.md WR-05: duplicated qmd diagnostics when qmd is broken"
    expected: "Decide whether to thread a 'qmd is functional' sentinel so kb_embeddings/memory_index checks short-circuit when qmd_version already failed. Current behavior: a single broken qmd install can produce 3 near-identical issues, hiding the root cause."
    why_human: "UX quality — diagnostic noise makes the actual root cause harder to see. Goal still met but quality degraded."
  - test: "Manual UAT of `aurora status` against a real running llama-server + indexed vault"
    expected: "Verifier already smoke-tested `aurora status` and `aurora status --json` against the developer's live environment (llama-server running on 127.0.0.1:8080, 337 indexed notes, 4 memories). Output rendered all four sections with real data. Marked as human-confirmed sanity check."
    why_human: "Originally deferred per 05-02-SUMMARY.md 'Next Phase Readiness'. Verifier completed the smoke test and observed correct output, but a human should still confirm the dashboard format meets UX expectations."
  - test: "Manual UAT of `aurora doctor` happy path on real environment"
    expected: "Verifier already smoke-tested `aurora doctor` and `aurora doctor --json` against the live environment. Both exited 0 with no issues, confirming the validate_runtime + 8 new checks all pass on a healthy install."
    why_human: "End-to-end UX validation with real data was deferred per 05-02-SUMMARY.md. Verifier completed the smoke test; human should confirm the diagnostic header and pt-BR text feel right."
---

# Phase 05: Operational Command Surface Verification Report

**Phase Goal:** User can operate Aurora end-to-end through explicit commands and built-in diagnostics.
**Verified:** 2026-04-11T16:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                       | Status     | Evidence                                                                                                                                                                |
| --- | ------------------------------------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | User sees 4 core commands (ask, chat, status, doctor) plus config in root help              | VERIFIED   | `aurora --help` shows ask, chat, status, doctor, config + 3 deprecated aliases (kb, model, memory) tagged `[DEPRECADO]`. Smoke-tested live.                              |
| 2   | User can reach kb/model/memory/setup via `aurora config` namespace                          | VERIFIED   | `aurora config --help` lists kb, model, memory, setup, show. `aurora config kb --help` exposes ingest/update/delete/rebuild + config + scheduler subgroups.              |
| 3   | Deprecated `aurora kb`/`model`/`memory` emit pt-BR warning to stderr then delegate          | VERIFIED   | `aurora kb ingest --help` produces "Aviso: `aurora kb` foi movido. Use `aurora config kb ...`." then renders the ingest help. Confirmed via live invocation.             |
| 4   | User can use `--install-completion` and `--show-completion` on root aurora command           | VERIFIED   | `aurora --help` shows both options. `add_completion=True` set in app.py:20.                                                                                              |
| 5   | User can run `aurora status` to see model/KB/memory/config in a single dashboard            | VERIFIED   | `aurora status` smoke-tested against live env: rendered all 4 sections with real data (model running, 337 KB notes, 4 memories, config flags). _Spot-check passed._     |
| 6   | User can run `aurora status --json` to get structured JSON output                           | VERIFIED   | `aurora status --json` returned valid JSON with version/model/kb/memory/config keys, all populated with real data. _Spot-check passed._                                  |
| 7   | `aurora status` does NOT trigger network requests or model auto-start (report-only per D-06) | VERIFIED   | `tests/cli/test_status_command.py::test_status_does_not_call_check_health` asserts `check_health` is never called. status.py only calls `get_status()` (lock-file read). |
| 8   | User can run `aurora doctor` to validate QMD/KB/memory/disk/Python/packages stack            | VERIFIED   | doctor.py implements 8 check functions (`_check_python_version`, `_check_qmd_binary`, `_check_qmd_version`, `_check_kb_collection`, `_check_kb_embeddings`, `_check_memory_index`, `_check_disk_space`, `_check_required_packages`). All importable and wired into `run_doctor_checks`. |
| 9   | `aurora doctor` shows pass/fail per check with pt-BR recovery commands                       | VERIFIED   | Each `DoctorIssue` has `category` + pt-BR `message` + `commands`. `_print_issues` groups by heading. Live `aurora doctor` produced "Runtime local pronto. Nenhum problema encontrado." on healthy env. |
| 10  | `aurora doctor --json` supports structured JSON output and never auto-fixes                  | VERIFIED   | `aurora doctor --json` smoke-tested live: returned `{ok, checks, issues[]}` payload. No auto-fix code paths anywhere in doctor.py — every check returns `DoctorIssue \| None` and `run_doctor_checks` only reports. |

**Score:** 10/10 truths verified

### Required Artifacts

| Artifact                              | Expected                                                            | Status     | Details                                                                                                  |
| ------------------------------------- | ------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------- |
| `src/aurora/cli/app.py`               | Restructured root Typer with 4 core + config + deprecated aliases   | VERIFIED   | 47 lines. Registers ask/chat/status/doctor/config + deprecated kb/model/memory. `add_completion=True` set. |
| `src/aurora/cli/config.py`            | Config app extended with kb/model/memory/setup sub-typers           | VERIFIED   | `config_app.add_typer(kb_app, name="kb")` etc. on lines 92-95. Bottom-of-module imports per circular-import workaround. |
| `src/aurora/cli/deprecated.py`        | Deprecation alias typers for kb, model, memory                      | VERIFIED   | 116 lines. Three Typer apps with `@callback()` warnings to stderr (`Aviso:` text), `.command(name)(func)` re-registration of canonical commands. |
| `src/aurora/cli/status.py`            | aurora status command with text and JSON dashboard                  | VERIFIED   | 207 lines. Lazy imports for ServerLifecycleService/load_kb_manifest/EpisodicMemoryStore. Try/except per domain. JSON branch + text dashboard. |
| `src/aurora/cli/doctor.py`            | Extended doctor with full-stack checks                              | VERIFIED   | 421 lines (up from baseline 113). 8 new check helpers + JSON report + extended headings + DoctorIssue dataclass. |
| `tests/cli/test_entrypoint.py`        | Updated tests for new command surface                               | VERIFIED   | Contains `test_deprecated_kb_alias_emits_warning_and_delegates`, `test_deprecated_model_alias_emits_warning`, `test_deprecated_memory_alias_emits_warning`, `test_config_shows_kb_model_memory_setup_subgroups`, `test_shell_completion_flags_available`. |
| `tests/cli/test_status_command.py`    | Status command tests for text and JSON modes                        | VERIFIED   | 4 tests including `test_status_does_not_call_check_health` which guards D-06.                            |
| `tests/cli/test_doctor.py`            | Extended doctor tests for new check categories                      | VERIFIED   | 9 tests including `test_doctor_reports_qmd_missing`, `test_doctor_reports_kb_no_manifest`, `test_doctor_json_output`, `test_doctor_checks_disk_space`, `test_doctor_reports_kb_embeddings_missing`. |

### Key Link Verification

| From                          | To                                  | Via                                          | Status     | Details                                                                                                                  |
| ----------------------------- | ----------------------------------- | -------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------ |
| `cli/config.py`               | `cli/kb.py`                         | `config_app.add_typer(kb_app, name="kb")`    | WIRED      | Confirmed at config.py:92. (Tool regex returned false; manual grep confirmed.)                                            |
| `cli/app.py`                  | `cli/deprecated.py`                 | `app.add_typer(deprecated_*)`                | WIRED      | Lines 8-12 import the three apps; lines 44-46 register them.                                                              |
| `cli/status.py`               | `runtime/server_lifecycle.py`       | `ServerLifecycleService().get_status()`      | WIRED      | status.py:75-77 lazy-imports and calls `get_status()`. Live invocation returned real model state.                         |
| `cli/status.py`               | `kb/manifest.py`                    | `load_kb_manifest()`                         | WIRED      | status.py:97-100 lazy-imports and calls. Live invocation returned 337 notes from real manifest.                            |
| `cli/status.py`               | `memory/store.py`                   | `EpisodicMemoryStore().list_memories()`      | WIRED      | status.py:130-132 lazy-imports and calls. Live invocation returned 4 memories.                                            |
| `cli/app.py`                  | `cli/status.py`                     | `app.add_typer(status_app, name="status")`   | WIRED      | app.py:39. `aurora status` resolves and runs.                                                                              |
| `cli/doctor.py`               | `shutil`                            | `shutil.which`, `shutil.disk_usage`          | WIRED      | doctor.py uses `shutil.which("qmd")` (4 sites) and `shutil.disk_usage(config_dir)` (1 site). Confirmed via grep.         |

### Data-Flow Trace (Level 4)

| Artifact                | Data Variable               | Source                                              | Produces Real Data | Status |
| ----------------------- | --------------------------- | --------------------------------------------------- | ------------------ | ------ |
| `cli/status.py` model section   | `lifecycle_status.lifecycle_state`, `model_id`, `endpoint_url`, `pid`, `uptime_seconds` | `ServerLifecycleService.get_status()` reads lock file | YES — live env returned `running`, real `model_id`, real pid, real uptime | FLOWING |
| `cli/status.py` KB section      | `note_count`, `vault_root`, `last_update` | `load_kb_manifest()` reads `~/.config/.../kb_manifest.json` + mtime | YES — live env returned 337 notes from real manifest | FLOWING |
| `cli/status.py` memory section  | `memory_count`, `last_session` | `EpisodicMemoryStore().list_memories()` reads memory dir | YES — live env returned 4 memories with real session date | FLOWING |
| `cli/status.py` config section  | `vault_path`, `local_only`, `telemetry_enabled` | `load_settings()` reads global config | YES — live env returned real config flags | FLOWING |
| `cli/doctor.py` JSON checks     | `endpoint`, `model`, `local_only`, `telemetry_enabled` | `load_settings()` | YES — live env returned real values | FLOWING |
| `cli/doctor.py` issue list      | `issues` from 8 check functions | Each check function inspects real OS state (PATH, manifest, disk) | YES — live env all checks passed against real state | FLOWING |

### Behavioral Spot-Checks

| Behavior                                                | Command                      | Result                                                                       | Status |
| ------------------------------------------------------- | ---------------------------- | ---------------------------------------------------------------------------- | ------ |
| `aurora --help` shows 4 core commands + config + deprecated | `uv run aurora --help`       | Shows ask, chat, status, doctor, config + kb/model/memory (`[DEPRECADO]`)    | PASS   |
| `aurora status` renders full dashboard with real data   | `uv run aurora status`       | All 4 sections rendered. Model: running. KB: 337 notas. Memoria: 4. Config: ativado/desativado. | PASS   |
| `aurora status --json` returns valid parseable JSON     | `uv run aurora status --json` | Valid JSON, all expected keys present, all values populated from live state.  | PASS   |
| `aurora doctor` runs all checks on healthy environment  | `uv run aurora doctor`        | Exited 0. "Runtime local pronto. Nenhum problema encontrado."                | PASS   |
| `aurora doctor --json` returns valid parseable JSON     | `uv run aurora doctor --json` | Valid JSON: `{"ok": true, "checks": {...}, "issues": []}`                    | PASS   |
| `aurora kb ingest --help` shows pt-BR deprecation warning | `uv run aurora kb ingest --help` | "Aviso: `aurora kb` foi movido. Use `aurora config kb ...`." then help.  | PASS   |
| `aurora config --help` exposes kb/model/memory/setup    | `uv run aurora config --help` | Lists show + kb + model + memory + setup subgroups                            | PASS   |
| `aurora config kb --help` exposes ingest/update/delete/rebuild | `uv run aurora config kb --help` | Lists ingest, update, delete, rebuild, config, scheduler                | PASS   |
| Phase 5 test suite green                                | `uv run pytest tests/cli/test_entrypoint.py tests/cli/test_status_command.py tests/cli/test_doctor.py -q` | 39 passed in 0.30s                | PASS   |
| Full CLI test suite green                                | `uv run pytest tests/cli/ -q` | 142 passed in 1.18s                                                          | PASS   |

### Requirements Coverage

| Requirement | Source Plan      | Description                                                                                                | Status   | Evidence                                                                                                                                                                                  |
| ----------- | ---------------- | ---------------------------------------------------------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CLI-02      | 05-01, 05-02     | User can use dedicated CLI commands for ingest, update, delete, ask, and status operations                 | SATISFIED | All 5 commands reachable: `aurora config kb ingest/update/delete` (also `aurora kb ingest/update/delete` via deprecated alias), `aurora ask`, `aurora status`. All five smoke-tested.       |
| CLI-04      | 05-02            | User can run a `doctor` command to validate local runtime dependencies and model readiness                  | SATISFIED | `aurora doctor` runs validate_runtime (existing) plus 8 new checks: Python version, QMD binary, QMD version, KB manifest, KB embeddings, memory index, disk space, required packages. Live test passed. Each issue carries pt-BR `commands` for recovery. |

No orphaned requirements. REQUIREMENTS.md maps only CLI-02 and CLI-04 to Phase 5; both are claimed by phase plans.

### Anti-Patterns Found

| File                       | Line     | Pattern                                 | Severity | Impact                                                                                                                                                                                               |
| -------------------------- | -------- | --------------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/aurora/cli/doctor.py` | 309      | `commands=("aurora config memory clear --yes",)` recommends DESTRUCTIVE recovery for `memory_index_missing` | Warning  | REVIEW WR-03. Doctor tells users to delete their own memory files when only the QMD index is missing. Goal "actionable guidance" technically met but advice is harmful. Surfaced for human triage.     |
| `src/aurora/cli/doctor.py` | 334      | `required = ("typer", "pydantic", "pydantic-settings", "pyyaml", "httpx")` includes `httpx` which is NOT a direct Aurora dependency | Warning  | REVIEW WR-02. False-positive diagnostic when httpx is absent. Goal still met but doctor produces noise. Surfaced for triage.                                                                          |
| `src/aurora/cli/doctor.py` | 259, 302 | `settings.kb_qmd_collection_name not in (result.stdout or "")` substring match against `qmd collection list` | Warning  | REVIEW WR-04. Latent false-positive/negative under user-configured short collection names. Defaults work. Surfaced for triage.                                                                       |
| `src/aurora/cli/doctor.py` | 59-96    | `run_doctor_checks` only catches `Phase1PolicyError` from `load_settings()`; sibling `RuntimeSettingsLoadError` propagates as unhandled traceback | Warning  | REVIEW WR-01. Corrupted settings file crashes doctor with a stack trace. Goal "actionable guidance" not met for this failure mode. Happy path works. Surfaced for triage.                              |
| `src/aurora/cli/doctor.py` | 184-207, 236-269, 272-311 | `_check_kb_embeddings` and `_check_memory_index` re-probe qmd after `_check_qmd_version` already failed | Warning  | REVIEW WR-05. Single broken qmd install produces 3 near-identical issues, hiding root cause. Goal still met but UX degraded. Surfaced for triage.                                                    |
| `src/aurora/cli/doctor.py` | 302, 306 | Hardcoded `"aurora-memory"` literal instead of importing `MEMORY_COLLECTION` from `aurora.memory.store` | Info     | REVIEW IN-06. Drift risk. Constant exists. Quality nit, not goal-blocking.                                                                                                                            |
| `src/aurora/cli/config.py` | 86       | Stale comment claims circular-import justification that grep cannot verify | Info     | REVIEW IN-01. Misleading comment. Quality nit.                                                                                                                                                        |
| `src/aurora/cli/deprecated.py` | 8-11 | Header comment conflates `invoke_without_command` and `--help` short-circuit semantics | Info     | REVIEW IN-02. Documentation imprecision. Quality nit.                                                                                                                                                 |
| `tests/cli/test_status_command.py` | 53 | `monkeypatch.setattr(status_module, "_run_status", status_module._run_status)` is a no-op left over from refactor | Info     | REVIEW IN-03. Dead test code. Cosmetic.                                                                                                                                                              |
| `src/aurora/cli/status.py` | 128-139  | Variable named `last_session` but populated from dict key `date` | Info     | REVIEW IN-04. Naming inconsistency. Cosmetic.                                                                                                                                                         |
| `src/aurora/cli/config.py` | 74-82    | `mask_sensitive` reconstructs query string manually without re-encoding | Info     | REVIEW IN-05. Round-trip breakage on percent-encoded values. Output is human-facing only.                                                                                                            |

No blockers. No TODO/FIXME/PLACEHOLDER markers found in phase 05 source files.

### Human Verification Required

See YAML frontmatter for the structured list. Summary:

1. **REVIEW WR-01: doctor crash on corrupted settings file** — Decide whether to fix before shipping or defer.
2. **REVIEW WR-03: destructive recovery for memory_index_missing** — Decide whether `memory clear --yes` is acceptable guidance for an indexing problem (it deletes user data).
3. **REVIEW WR-02: false-positive httpx diagnostic** — Decide whether to drop httpx (and pydantic) from required-packages list.
4. **REVIEW WR-04: substring matching against qmd collection list** — Decide whether to fix the latent collection-name aliasing bug.
5. **REVIEW WR-05: duplicated qmd diagnostics** — Decide whether to short-circuit downstream qmd checks when version probe fails.
6. **Manual UAT of `aurora status` against real env** — Verifier completed; human should confirm dashboard format.
7. **Manual UAT of `aurora doctor` happy path** — Verifier completed; human should confirm pt-BR text and diagnostic header.

### Gaps Summary

**No gaps blocking goal achievement.** All 10 must-haves verify against the codebase, all 7 artifacts pass three-level verification, all 7 key links are wired (one tool false-negative manually verified), all 6 data-flow traces produce real data on the live environment, all 10 behavioral spot-checks pass, and both requirement IDs (CLI-02, CLI-04) are satisfied with concrete evidence.

The phase implements the full scope in the plans: command surface restructure (Plan 01) and status + extended doctor (Plan 02). The full CLI test suite is green (142 passed). Live smoke tests against the developer's running environment confirm `aurora status` and `aurora doctor` operate end-to-end with real data.

The five Warning-level findings from `05-REVIEW.md` are quality concerns that the goal-level verification does not classify as gaps:

- The happy path of every must-have works.
- Every Warning is documented in REVIEW.md with a recommended fix.
- None are scheduled for a later phase.
- WR-03 (destructive recovery) and WR-01 (uncaught error) have the highest user-impact risk and warrant explicit triage before shipping.

Status is `human_needed` rather than `passed` because:

1. The five REVIEW warnings need a developer triage decision (fix-now vs. defer-to-future-plan).
2. Two manual UAT items were originally deferred per `05-02-SUMMARY.md`; the verifier completed the smoke tests but a human should confirm UX expectations on the dashboard format and diagnostic output.

If the developer accepts the REVIEW warnings as "ship as-is, fix in follow-up" they can mark this phase passed. If any of WR-01/WR-03 are deemed ship-blockers, those become gaps for a 05-03 closure plan.

---

_Verified: 2026-04-11T16:00:00Z_
_Verifier: Claude (gsd-verifier)_
