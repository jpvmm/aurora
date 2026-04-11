---
phase: 05-operational-command-surface
plan: 01
subsystem: cli
tags: [typer, cli, command-surface, namespace, deprecation-aliases, shell-completion]

# Dependency graph
requires:
  - phase: 01-local-runtime-baseline
    provides: Typer root app (aurora.cli.app) with setup/config/model/doctor/kb sub-typers
  - phase: 02-vault-knowledge-base-lifecycle
    provides: kb_app with ingest/update/delete/rebuild + kb_config_app + kb_scheduler_app
  - phase: 04-long-term-memory-fusion
    provides: memory_app with list/search/edit/clear
provides:
  - 4-core root command surface (ask, chat, doctor, config) plus 3 deprecated aliases (kb, model, memory)
  - config namespace absorbs kb/model/memory/setup sub-typers via `config_app.add_typer`
  - src/aurora/cli/deprecated.py module with three pt-BR alias Typers that warn on stderr and delegate
  - typer shell completion enabled at root (--install-completion, --show-completion)
  - Updated entrypoint/kb/memory/model tests rerouted through the new `config` namespace
affects: [05-02-status-and-doctor, future CLI plans that add root commands]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "deprecated-alias Typer: @callback() emits pt-BR warning to stderr, then re-exposes same command functions via .command(name)(function)"
    - "namespace sub-typer: config_app.add_typer(<app>, name=...) mounts existing feature Typers without duplication"
    - "bottom-of-module lateral imports in config.py to avoid circular imports when referencing setup/kb/model/memory"

key-files:
  created:
    - "src/aurora/cli/deprecated.py — three deprecation alias Typers (kb, model, memory) with pt-BR stderr warnings"
    - ".planning/phases/05-operational-command-surface/deferred-items.md — tracks pre-existing qmd-dependent failures"
  modified:
    - "src/aurora/cli/app.py — rewrite root typer registrations: 4-core + config + 3 deprecated aliases, add_completion=True"
    - "src/aurora/cli/config.py — mount kb/model/memory/setup under config namespace, update guidance message"
    - "tests/cli/test_entrypoint.py — rewrite parametrize list, add 5 new tests for deprecation aliases / config subgroups / shell completion"
    - "tests/cli/test_kb_command.py — reroute all RUNNER.invoke calls through `config kb ...`"
    - "tests/cli/test_memory_command.py — reroute all runner.invoke calls through `config memory ...`"
    - "tests/cli/test_model_command.py — reroute all RUNNER.invoke calls through `config model ...`"

key-decisions:
  - "Deprecated aliases re-register the SAME command functions via .command('name')(func) to avoid code duplication and keep options/flags in sync with canonical commands."
  - "Deprecated Typers set no_args_is_help=True (not invoke_without_command=True) so Typer's help machinery fires for parent-level `aurora kb --help` without triggering the callback warning twice."
  - "Lateral imports at the bottom of config.py (with `# noqa: E402`) avoid circular imports between config.py ↔ setup.py ↔ model.py."
  - "Test files that parse JSON from result.output had to be rerouted through the new canonical `config` namespace because the deprecated alias writes its pt-BR warning to stderr which Click's CliRunner mixes into result.output by default, corrupting JSON parsing."
  - "Pre-existing qmd-dependent test failures (test_update_reports_privacy_safe_read_errors_without_forcing_delete, test_real_qmd_lifecycle_ingest_update_delete_rebuild) were verified against baseline and deferred via deferred-items.md — they are environmental (missing qmd binary), not regressed by this plan."

patterns-established:
  - "Deprecation alias pattern: new module `aurora.cli.deprecated` wraps each legacy top-level typer with a fresh Typer() + @callback stderr warning + .command() delegation. Extensible for future namespace moves."
  - "Namespace move test migration: when moving a Typer from root to a namespace, update test RUNNER.invoke routes to the new canonical path to prevent stderr warnings from contaminating stdout-based assertions (JSON parsing, text matching)."

requirements-completed: [CLI-02]

# Metrics
duration: 7min
completed: 2026-04-11
---

# Phase 05 Plan 01: CLI Namespace Restructure Summary

**Root CLI surface reduced from 7+ top-level commands to 4 core (ask, chat, doctor, config) plus 3 deprecated-alias wrappers for kb/model/memory that delegate to `aurora config <name>` with pt-BR stderr warnings, plus Typer shell completion enabled at the root.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-11T14:36:38Z
- **Completed:** 2026-04-11T14:43:36Z
- **Tasks:** 2
- **Files modified:** 6 (3 new-or-modified production files, 4 test files, 1 deferred-items tracking file)

## Accomplishments

- `aurora --help` now shows exactly ask, chat, doctor, config as core entry points plus kb/model/memory tagged `[DEPRECADO]`.
- `aurora config --help` shows all legacy namespaces as sub-groups: kb, model, memory, setup (and the existing `show` command).
- Every old path (`aurora kb ingest`, `aurora model start`, `aurora memory list`, etc.) continues to work unchanged from the user's point of view — they just see a pt-BR warning on stderr before the real command runs.
- Shell completion via `--install-completion` / `--show-completion` is now available on the root `aurora` command.
- Full CLI test suite reroutes through the canonical namespace, with new tests explicitly covering deprecation aliases, config sub-groups, and the shell completion flag.

## Task Commits

Each task was committed atomically (parallel worktree — committed with `--no-verify` per orchestrator policy):

1. **Task 1: Restructure config.py and create deprecated.py** — `887c8f1` (feat)
2. **Task 2: Restructure app.py and update entrypoint tests** — `5b345bf` (feat)

## Files Created/Modified

- `src/aurora/cli/app.py` — Root typer rewritten: 4-core commands + config + 3 deprecated aliases; add_completion flipped from False → True.
- `src/aurora/cli/config.py` — Added imports and `config_app.add_typer(...)` for kb/model/memory/setup. Updated guidance message to mention `aurora config --help`. Imports placed at bottom with `# noqa: E402` to sidestep circular imports.
- `src/aurora/cli/deprecated.py` — New module. Exports `deprecated_kb_app`, `deprecated_model_app`, `deprecated_memory_app`. Each is a fresh `typer.Typer(no_args_is_help=True, help="[DEPRECADO] Use aurora config ...")`, with a `@callback()` that emits a pt-BR `Aviso:` warning to `stderr`, and re-registers the same command functions via `.command("<name>")(<func>)`. `deprecated_kb_app` also re-mounts `kb_config_app` and `kb_scheduler_app` so that `aurora kb config show` and `aurora kb scheduler status` still resolve.
- `tests/cli/test_entrypoint.py` — Updated `test_root_no_args_shows_help_when_wizard_is_not_required` and `test_phase_one_command_groups_are_listed_in_root_help` to expect the new surface. Migrated `test_setup_group_invokes_setup_wizard_entrypoint` to drive setup via `["config", "setup"]`. Migrated `test_model_group_exposes_set_command_in_help`, `test_kb_group_exposes_lifecycle_commands`, `test_kb_ingest_requires_explicit_vault_path`, `test_kb_commands_expose_json_and_optional_dry_run`, `test_kb_update_help_mentions_hash_precision_behavior` to invoke via `["config", "kb", ...]` or `["config", "model", ...]`. Added 5 new tests: `test_deprecated_kb_alias_emits_warning_and_delegates`, `test_deprecated_model_alias_emits_warning`, `test_deprecated_memory_alias_emits_warning`, `test_config_shows_kb_model_memory_setup_subgroups`, `test_shell_completion_flags_available`. Total 26 entrypoint tests, all passing.
- `tests/cli/test_kb_command.py` — Rerouted all `RUNNER.invoke(app_module.app, ["kb", ...])` calls to `["config", "kb", ...]` (about 15 occurrences including parametrized lists). User-facing recovery text assertions (e.g. `"aurora kb delete --yes"`) were left unchanged since that text is still user-facing output from the command.
- `tests/cli/test_memory_command.py` — Rerouted all 17 `runner.invoke` calls to `["config", "memory", ...]`. This fixed 4 JSON-parsing failures where the deprecated-alias stderr warning was being mixed into stdout by `CliRunner`.
- `tests/cli/test_model_command.py` — Rerouted 11 `RUNNER.invoke` call sites to `["config", "model", ...]`.
- `.planning/phases/05-operational-command-surface/deferred-items.md` — New file. Tracks two pre-existing qmd-dependent test failures (`test_update_reports_privacy_safe_read_errors_without_forcing_delete`, `test_real_qmd_lifecycle_ingest_update_delete_rebuild`) that are environmental (missing `qmd` binary on the worktree), verified as baseline failures, and out of scope for this plan.

## Decisions Made

1. **Delegate-by-reference, not copy:** Deprecated aliases use `.command("<name>")(<func>)` to reuse the same callable objects from kb/model/memory. This guarantees no drift between the deprecated path and the canonical path for flags, help text, type coercion, and return semantics.

2. **`no_args_is_help=True` on deprecated Typers, not `invoke_without_command=True`:** Per Pitfall 1 in the research doc. This keeps `aurora kb --help` (and `aurora kb`, `aurora model`, `aurora memory`) working correctly — Typer renders help and the `@callback()` does not fire on bare help invocation.

3. **Bottom-of-module imports in config.py:** Setup → Model → Config chain risks a circular import during module load. Placing `from aurora.cli.kb import kb_app` etc. at the bottom of `config.py` (with `# noqa: E402`) means they run only after config.py's own definitions are complete. Verified via `uv run python -c "from aurora.cli.config import config_app"` in Task 1 verification.

4. **Test migration is in-scope:** The plan explicitly required `uv run pytest tests/cli/ -x -q` to exit 0. Because the deprecated alias emits stderr warnings that `CliRunner` mixes into `result.output`, JSON-parsing tests break unless we route them through the canonical namespace. This is a direct consequence of the namespace move, so updating the three test files was in-scope per the plan's acceptance criteria.

5. **Leave recovery text untouched:** Command output still says things like `"Use aurora kb delete --yes"`. The plan didn't ask to rename this user-facing text, and users will still be able to run both old (deprecated) and new paths. Updating all recovery strings is a larger documentation/UX task.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Cascading test updates in test_kb_command.py, test_memory_command.py, test_model_command.py**

- **Found during:** Task 2 verification (`uv run pytest tests/cli/ -x -q`)
- **Issue:** The plan's action instructions enumerated test updates for `test_entrypoint.py` but did not enumerate the necessary updates to `test_kb_command.py`, `test_memory_command.py`, and `test_model_command.py`. After Task 2, those test files still routed invocations through `["kb", ...]`, `["model", ...]`, `["memory", ...]` at the root app. Because the deprecated alias writes a pt-BR warning to stderr and Click's `CliRunner` mixes stderr into `result.output` by default, any test that called `json.loads(result.output)` broke (warning prefix corrupts the JSON). 4 failures in `test_memory_command.py` and 1 in `test_kb_command.py` were directly caused by the namespace move.
- **Fix:** Global-rerouted all affected `RUNNER.invoke`/`runner.invoke` calls in these three files through the canonical `["config", <name>, ...]` path. Used a regex sed-style script to catch both single-line and multi-line list literals (including parametrize values). Verified by rerunning the CLI test suite and the broader `tests/` suite.
- **Files modified:** tests/cli/test_kb_command.py, tests/cli/test_memory_command.py, tests/cli/test_model_command.py
- **Verification:** `uv run pytest tests/cli/ -q --deselect <pre-existing>` → 130 passed. `uv run pytest tests/ -q --deselect <pre-existing>` → 448 passed.
- **Committed in:** `5b345bf` (part of Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking: cascading test updates)
**Impact on plan:** Necessary correctness fix. The plan's test update list covered the behavioral contract change in `test_entrypoint.py` but missed the mechanical stdout/stderr contamination problem in other test files. No scope creep — all fixes are direct consequences of the namespace move.

## Issues Encountered

- **Pre-existing qmd-dependent failures deferred:** Two tests (`test_update_reports_privacy_safe_read_errors_without_forcing_delete` and `test_real_qmd_lifecycle_ingest_update_delete_rebuild`) fail on baseline `e54cea8` because the worktree environment does not have the `qmd` binary available. Verified by stashing my changes and running both tests on the unmodified baseline. Logged in `.planning/phases/05-operational-command-surface/deferred-items.md` with suggested future-plan fixes. Out of scope per deviation-rules scope boundary.

- **Worktree branch base was incorrect at start:** The worktree was created from `6291b60` (main before phase-05 planning commits) instead of `e54cea8` (phase-05 base). Reset via `git reset --soft e54cea8` plus `git checkout e54cea8 -- .planning/phases/05-operational-command-surface/ .planning/ROADMAP.md` to restore phase 05 files to the working tree before starting execution.

## User Setup Required

None — this is a pure CLI restructuring. Users upgrading from prior versions will see pt-BR deprecation warnings on `aurora kb|model|memory` and should migrate to `aurora config <name>`, but no configuration changes are required.

## Next Phase Readiness

- **Plan 05-02 (status command + extended doctor) unblocked:** The root app structure, `add_typer` positioning, and test patterns are locked in. Plan 02 can now add `status` as a new core command next to ask/chat/doctor/config without touching any of the deprecated-alias infrastructure.
- **No blockers.**
- **Known stubs:** None.

## Threat Flags

None — this plan does not introduce or modify any network endpoint, auth surface, filesystem access pattern, or schema at a trust boundary. It restructures command registration inside the CLI process only.

## Self-Check: PASSED

- FOUND: src/aurora/cli/app.py (modified)
- FOUND: src/aurora/cli/config.py (modified)
- FOUND: src/aurora/cli/deprecated.py (new)
- FOUND: tests/cli/test_entrypoint.py (modified)
- FOUND: tests/cli/test_kb_command.py (modified)
- FOUND: tests/cli/test_memory_command.py (modified)
- FOUND: tests/cli/test_model_command.py (modified)
- FOUND: .planning/phases/05-operational-command-surface/deferred-items.md (new)
- FOUND commit: 887c8f1 (Task 1)
- FOUND commit: 5b345bf (Task 2)

---
*Phase: 05-operational-command-surface*
*Completed: 2026-04-11*
