---
phase: 05-operational-command-surface
plan: 02
subsystem: cli
tags: [typer, cli, status-dashboard, doctor, diagnostics, json-output, qmd, kb, memory, disk-space, python-version]

# Dependency graph
requires:
  - phase: 05-01
    provides: 4-core root CLI surface (ask, chat, doctor, config) + deprecated aliases. `doctor_app` already registered as a core Typer; `status_app` slotted next to it.
  - phase: 01-local-runtime-baseline
    provides: ServerLifecycleService.get_status() lock-file-only read path used by status and doctor.
  - phase: 02-vault-knowledge-base-lifecycle
    provides: KBManifest + load_kb_manifest() for KB health; kb_qmd_index_name/kb_qmd_collection_name settings for QMD collection probes.
  - phase: 04-long-term-memory-fusion
    provides: EpisodicMemoryStore.list_memories() used by both status and doctor to detect indexed memory presence.
provides:
  - "aurora status — unified dashboard covering version, model lifecycle state, KB manifest/notes, memory count, and config summary in text or --json mode"
  - "aurora doctor extended with QMD binary + version, KB manifest + embeddings, memory index, disk space, Python version, and required package checks"
  - "aurora doctor --json emitting {ok, checks, issues[]} payload with pt-BR recovery commands per issue"
  - "Report-only status contract (D-06): no network requests, no lifecycle mutation, no check_health call"
affects: [06-observability-hardening, future CLI plans that extend the status or doctor surface]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "status dashboard: each of 4 domain reads (version, model, KB, memory) wrapped in independent try/except so one broken subsystem produces a partial dashboard instead of a crash"
    - "doctor check = pure function returning DoctorIssue|None: no side effects, no auto-fix (D-10), aggregated by run_doctor_checks via _append_if_issue"
    - "dual-mode output via json_output flag: same run_doctor_checks/ _run_status logic collects state once and branches on json_output at the render step"
    - "test helper _install_all_passing_monkeypatches: seeds every new check to the green-path shape so individual tests only need to flip the single check under test"

key-files:
  created:
    - "src/aurora/cli/status.py — status_app Typer with text + --json dashboard, mask_sensitive on endpoint, report-only contract (162 lines)"
    - "tests/cli/test_status_command.py — 4 tests covering text, JSON, graceful degradation, and an explicit assertion that check_health is never called (D-06)"
  modified:
    - "src/aurora/cli/app.py — import status_app and register it between chat and doctor in the core command block"
    - "src/aurora/cli/doctor.py — 8 new check helpers + --json flag + _print_json_report + extended _print_issues headings (333 lines, up from 113)"
    - "tests/cli/test_doctor.py — 7 new tests + _install_all_passing_monkeypatches helper; existing 2 tests extended to consume the helper so they survive the new check surface"
    - "tests/cli/test_entrypoint.py — test_doctor_group_runs_runtime_checks_without_placeholder_message updated to monkeypatch the new checks (cascading blocking fix)"

key-decisions:
  - "Lazy imports inside _run_status for ServerLifecycleService / load_kb_manifest / EpisodicMemoryStore so import cycles and environment-dependent modules never break the status entrypoint, and so test monkeypatching can operate on the source module without touching aurora.cli.status attribute namespace."
  - "Patch source modules (aurora.runtime.server_lifecycle / aurora.kb.manifest / aurora.memory.store) rather than aurora.cli.status symbols, because status.py uses lazy imports and the symbols only exist inside the function call stack."
  - "Doctor preserves the original two-section output ordering: Phase1PolicyError short-circuits with its own JSON/text branch, then the main run_doctor_checks path layers the new checks after existing runtime validation so the diagnostic header (endpoint/model/local-only/telemetria) is unchanged."
  - "_check_memory_index returns None when no memories exist because no-memory is a valid state for a fresh install; only when memories exist but the QMD collection is absent does it become an actionable issue."
  - "_check_disk_space tolerates FileNotFoundError on the config dir (first run before save_settings) by silently skipping; threshold fixed at 500 MB per the plan."
  - "_check_required_packages lists the core runtime dependencies (typer, pydantic, pydantic-settings, pyyaml, httpx) — the exact list from the plan. Intentionally shallow: deeper transitive checks are out of scope."
  - "doctor --json on Phase1PolicyError emits a minimal checks snapshot with empty endpoint/model fields because load_settings failed; this keeps the JSON schema stable for scripting consumers even on the early-exit path."

patterns-established:
  - "Status dashboard pattern: collect state in a try/except-per-domain block, then render once (text or JSON) based on a --json flag. Reusable for any future unified-view CLI commands."
  - "Doctor check expansion pattern: define `_check_X(settings?) -> DoctorIssue | None`, append via `_append_if_issue`, add category to `_print_issues` headings, and add a green-path monkeypatch to `_install_all_passing_monkeypatches`. Every new doctor check follows this 4-step recipe."
  - "Test helper that installs an all-passing doctor monkeypatch suite: individual tests then only flip one check to failure mode, keeping tests focused and resistant to future check additions."

requirements-completed: [CLI-02, CLI-04]

# Metrics
duration: 15min
completed: 2026-04-11
---

# Phase 05 Plan 02: Status Command and Extended Doctor Summary

**aurora status unified dashboard (version, model lifecycle, KB notes, memory count, config) and aurora doctor extended with QMD, KB, memory-index, disk, Python, and package checks — both commands gain --json output, status is report-only with no network calls, doctor never auto-fixes.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-11T15:02:00Z
- **Completed:** 2026-04-11T15:17:00Z
- **Tasks:** 2
- **Files modified:** 5 (2 new production + test files, 3 modified production + test files)

## Accomplishments

- `aurora status` renders a 4-section dashboard (Modelo, Base de Conhecimento, Memoria, Configuracao) in human-readable text and structured JSON; each section degrades gracefully when its data source fails.
- `aurora status` is strictly report-only (D-06): validated via unit test that asserts `ServerLifecycleService.check_health` is never invoked during the status render.
- `aurora doctor` now runs the original runtime validation plus eight new check helpers: Python version, QMD binary, QMD version, KB manifest + notes, KB QMD embeddings, memory index, disk space, and required Python packages.
- `aurora doctor --json` emits the `{ok, checks, issues[]}` schema with pt-BR `recovery_commands` per issue — suitable for scripting.
- Doctor still refuses to auto-fix anything (D-10); every check returns `DoctorIssue | None` and the command only reports.
- Full CLI test suite is green: 141 passed (up from 130 baseline), 1 pre-existing qmd-dependent failure deselected.
- Full project test suite green: 459 passed, 2 pre-existing qmd-dependent failures deselected (both tracked in deferred-items.md from plan 05-01).

## Task Commits

Each task was committed atomically (parallel worktree — committed with `--no-verify` per orchestrator policy):

1. **Task 1: Create aurora status command with text and JSON dashboard** — `777435b` (feat)
2. **Task 2: Extend aurora doctor with full-stack checks and --json output** — `03780f7` (feat)

## Files Created/Modified

- **`src/aurora/cli/status.py` (new)** — `status_app` Typer with `invoke_without_command=True` + `@status_app.callback()`. `_run_status(*, json_output)` collects version via `importlib.metadata.version("aurora")`, model state via `ServerLifecycleService().get_status()` (lock-file only, no network), KB state via `load_kb_manifest()` + `os.path.getmtime(get_kb_manifest_path())`, memory state via `EpisodicMemoryStore().list_memories()`, and config from `load_settings()`. Each domain is wrapped in its own `try/except` and falls back to default/empty values on failure. Text mode masks the endpoint via `mask_sensitive`; JSON mode leaves it verbatim (scripting needs the real URL). `__all__ = ["status_app", "status_command"]`.

- **`src/aurora/cli/app.py` (modified)** — Added `from aurora.cli.status import status_app` and `app.add_typer(status_app, name="status")` in the core command block between `chat_app` and `doctor_app`. Core registration order is now: ask, chat, status, doctor, config — then deprecated aliases. `aurora --help` verified manually.

- **`tests/cli/test_status_command.py` (new)** — 4 tests using `RUNNER = CliRunner()` and `AURORA_CONFIG_DIR`-scoped `tmp_path`:
  1. `test_status_renders_text_dashboard` — asserts all four section headers + version header render with a happy-path monkeypatch.
  2. `test_status_json_returns_structured_output` — parses stdout as JSON and asserts `version`, `model`, `kb`, `memory`, `config` keys plus the right types for `model.state`, `kb.note_count`, `memory.memory_count`, `config.local_only`.
  3. `test_status_gracefully_handles_missing_services` — all three lazy-imported services (`ServerLifecycleService`, `load_kb_manifest`, `EpisodicMemoryStore`) raise `RuntimeError`; the command still exits 0 with a partial dashboard.
  4. `test_status_does_not_call_check_health` — installs a tracking `_TrackingService` whose `check_health` sets a sentinel and raises. After `aurora status` runs, the sentinel must still be False. This is the hard guarantee for D-06.

- **`src/aurora/cli/doctor.py` (modified, 113 → 333 lines)** — Added:
  - Top-level imports: `importlib.metadata`, `json`, `shutil`, `subprocess`, `sys`; `load_kb_manifest`, `get_settings_path`, `RuntimeSettings`.
  - `doctor_command` callback gained `json_output: bool = typer.Option(False, "--json", ...)`.
  - `run_doctor_checks(*, json_output: bool = False)` — now also handles the Phase1PolicyError early-exit in JSON mode.
  - Eight new check helpers:
    - `_check_python_version` — fails when `sys.version_info < (3, 13)`.
    - `_check_qmd_binary` — `shutil.which("qmd")` None → issue.
    - `_check_qmd_version` — runs `qmd --version` via subprocess; skipped if binary missing.
    - `_check_kb_collection` — reads manifest; `None` → `kb_no_manifest`, empty notes → `kb_collection_empty`, raise → `kb_manifest_error`.
    - `_check_kb_embeddings` — runs `qmd --index <name> collection list` and checks for the managed collection name in stdout.
    - `_check_memory_index` — lists memories; if non-empty but QMD `aurora-memory` collection absent, reports `memory_index_missing`.
    - `_check_disk_space` — `shutil.disk_usage` < 500 MB → low-disk issue; FileNotFoundError on config dir is silent.
    - `_check_required_packages` — five packages (typer, pydantic, pydantic-settings, pyyaml, httpx) via `importlib.metadata.version`.
  - `_append_if_issue` helper for `DoctorIssue | None` aggregation.
  - `_print_json_report(*, settings, issues)` — emits `{ok, checks, issues[]}` with `mask_sensitive` on endpoint.
  - `_print_issues` `headings` map extended with the nine new categories (qmd_missing, qmd_version, kb_no_manifest, kb_collection_empty, kb_embeddings_missing, kb_manifest_error, memory_index_missing, disk_space_low, python_version, package_missing).
  - `__all__` now exports `DoctorIssue` in addition to the existing symbols.

- **`tests/cli/test_doctor.py` (modified, 2 → 9 tests)** — Added `_install_all_passing_monkeypatches(monkeypatch, doctor_module)` helper that patches `validate_runtime`, `shutil.which`, `subprocess.run`, `load_kb_manifest`, `shutil.disk_usage`, and `EpisodicMemoryStore` to the green-path shape. Rewired the existing 2 tests to use the helper (happy path) or to start from the helper and flip a single check (model_missing failure test). Added 7 new tests: `test_doctor_reports_qmd_missing`, `test_doctor_reports_kb_no_manifest`, `test_doctor_reports_python_version_ok`, `test_doctor_json_output`, `test_doctor_json_all_pass`, `test_doctor_checks_disk_space`, `test_doctor_reports_kb_embeddings_missing`.

- **`tests/cli/test_entrypoint.py` (modified)** — `test_doctor_group_runs_runtime_checks_without_placeholder_message` now takes `tmp_path` and `monkeypatch`, sets `AURORA_CONFIG_DIR`, seeds fresh settings, and monkeypatches `shutil.which`, `subprocess.run`, `load_kb_manifest`, `shutil.disk_usage`, and `EpisodicMemoryStore` to the all-green shape (mirroring the test_doctor.py helper, inlined here to avoid a cross-test-file import). See "Deviations from Plan" for the rationale.

## Decisions Made

1. **Lazy imports inside `_run_status`** — The three heavy domain services (`ServerLifecycleService`, `load_kb_manifest`, `EpisodicMemoryStore`) are imported inside the function body, not at module top. This means (a) any import-time error in those modules cannot break `aurora status` itself, and (b) test monkeypatching targets the source modules (`aurora.runtime.server_lifecycle`, `aurora.kb.manifest`, `aurora.memory.store`) rather than `aurora.cli.status` attribute names. Documented in `test_status_command.py` comments via the monkeypatch setup pattern.

2. **Patch source modules, not cli.status symbols** — Consequence of decision 1. Tests use e.g. `monkeypatch.setattr(lifecycle_mod, "ServerLifecycleService", _FakeLifecycleService)` because `_run_status` reimports on every call.

3. **Phase1PolicyError JSON branch** — When `load_settings()` raises Phase1PolicyError before we have a settings object, the JSON output still emits the `{ok, checks, issues[]}` schema with empty endpoint/model strings and `local_only=True` as a neutral default. This keeps the JSON contract stable for scripting consumers regardless of which code path triggered the failure.

4. **`_check_memory_index` returns None on empty memories** — No memory is a valid state for a fresh install; only when memories exist but the QMD collection is absent does the check report a problem. Prevents false-positive diagnostics on day-1 use.

5. **`_check_disk_space` silent on missing config dir** — First-run users may run `aurora doctor` before `aurora config setup`; the config dir doesn't exist yet. `shutil.disk_usage` raising `FileNotFoundError` in that window should not be classified as a disk-space problem. Caught explicitly.

6. **Threshold = 500 MB** — Fixed per the plan. If a future doctor config surface wants to make this user-tunable, a settings field can be added without changing the check signature.

7. **Green-path test helper seeds all new checks** — `_install_all_passing_monkeypatches` puts every new check into the passing shape. Individual tests then only need to flip one check to failure mode. This keeps tests focused and makes adding future checks a 4-step recipe without breaking existing tests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Cascading test update in `tests/cli/test_entrypoint.py`**

- **Found during:** Task 2 verification (`uv run pytest tests/cli/ -x -q`)
- **Issue:** `test_doctor_group_runs_runtime_checks_without_placeholder_message` in `test_entrypoint.py` only monkeypatched `validate_runtime` to succeed. With the expanded doctor surface, the unmocked `_check_kb_collection`, `_check_qmd_binary`, `_check_disk_space`, etc., would run against the real environment during the test and find real issues, flipping `result.exit_code` from 0 to 1. This caused a regression failure in an unrelated test file.
- **Fix:** Migrated the test to accept `tmp_path` + `monkeypatch`, set `AURORA_CONFIG_DIR` to an isolated directory, save fresh `RuntimeSettings()`, and inline-monkeypatch the new checks (`shutil.which`, `subprocess.run`, `load_kb_manifest`, `shutil.disk_usage`, `EpisodicMemoryStore`) to the green-path shape — mirroring the `_install_all_passing_monkeypatches` helper from `test_doctor.py`. I intentionally did not import the helper across test files to keep test file coupling low.
- **Files modified:** `tests/cli/test_entrypoint.py`
- **Verification:** `uv run pytest tests/cli/ -q --deselect tests/cli/test_kb_command.py::test_update_reports_privacy_safe_read_errors_without_forcing_delete` → 141 passed. Broader sweep: `uv run pytest tests/ -q --deselect <pre-existing>` → 459 passed.
- **Committed in:** `03780f7` (part of Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking: cascading test update)
**Impact on plan:** Necessary correctness fix. The plan's test enumeration for Task 2 covered `tests/cli/test_doctor.py` but (like plan 05-01's similar situation with `test_kb_command.py` / `test_memory_command.py` / `test_model_command.py`) did not enumerate the entrypoint-level test that also exercises `aurora doctor`. Fix is a direct mechanical consequence of the check-surface expansion. No scope creep.

## Issues Encountered

- **Pre-existing qmd-dependent failure still deferred:** `tests/cli/test_kb_command.py::test_update_reports_privacy_safe_read_errors_without_forcing_delete` and `tests/integration/test_kb_qmd_integration.py::test_real_qmd_lifecycle_ingest_update_delete_rebuild` remain pre-existing environmental failures from phase 05-01 (tracked in `.planning/phases/05-operational-command-surface/deferred-items.md`). Deselected from the verification run. Not caused by plan 05-02.

- **Baseline was at an older commit:** Worktree base was `6291b60` instead of the required `72de288`. Reset via `git reset --hard 72de2886380e49c9d8e54deb25a0f6d3ea7d226d` before starting execution — the worktree had no uncommitted changes so the reset was clean.

- **Real llama-server running on 127.0.0.1:8080 during doctor smoke test:** During manual `aurora doctor --json` verification, the developer's local llama-server was actively serving a different model (`Qwen3.5-9B.Q8_0.gguf`) than the default `Qwen3-8B-Q8_0`. Doctor correctly reported this as a `model_missing` issue with the right recovery commands, which confirms the validate_runtime path still works end-to-end. Expected behavior, not a bug.

## User Setup Required

None. Both new commands are report-only and do not require user configuration beyond the existing `aurora config setup` / `aurora config model set` flows. Users on environments without `qmd` installed will see doctor issues advising them to `pip install qmd`, which is the intended UX.

## Next Phase Readiness

- **Plan 05-02 unblocks phase 06 (observability hardening):** `aurora status` is the canonical read-only view of runtime state and `aurora doctor --json` is the canonical health check. Phase 06 can consume the JSON outputs from both commands for log aggregation, health metrics, or watchdog tooling without touching their internals.
- **Deferred: manual UAT of `aurora status` against a real running llama-server + indexed vault.** The unit tests cover the command logic and the report-only contract; end-to-end UX validation with real data is an orchestrator/verifier concern.
- **No blockers.**
- **Known stubs:** None.

## Threat Flags

None — this plan does not introduce new network endpoints, filesystem write paths outside the existing QMD/KB/memory surfaces, or new trust boundaries. `aurora status` is strictly read-only: it reads the lock file, the KB manifest file, and memory markdown files already owned by the process user. `aurora doctor` only invokes `qmd` as a read-only `collection list` subprocess call, bounded by `subprocess.run(..., timeout=15)`. No shell=True, no user-controlled command construction.

## Self-Check: PASSED

- FOUND: src/aurora/cli/status.py (new)
- FOUND: src/aurora/cli/app.py (modified — registers status_app)
- FOUND: tests/cli/test_status_command.py (new)
- FOUND: src/aurora/cli/doctor.py (modified — extended checks + --json)
- FOUND: tests/cli/test_doctor.py (modified — 9 tests)
- FOUND: tests/cli/test_entrypoint.py (modified — cascading test fix)
- FOUND commit: 777435b (Task 1)
- FOUND commit: 03780f7 (Task 2)

---
*Phase: 05-operational-command-surface*
*Completed: 2026-04-11*
