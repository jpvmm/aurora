---
phase: 01-local-runtime-baseline
verified: 2026-03-02T01:08:53Z
status: human_needed
score: 11/12 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 10/12
  gaps_closed:
    - "Entrypoint smoke tests no longer assert legacy placeholder behavior for setup/config/doctor and now pass."
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Global install and invocation from arbitrary directory"
    expected: "`aurora --help` resolves after `uv tool install .` or `pipx install .`, including a fresh shell session."
    why_human: "Depends on host PATH/shell environment and installer behavior outside isolated test runner."
  - test: "Live setup + doctor flow against real local llama.cpp endpoint"
    expected: "Wizard blocks until endpoint/model are ready; doctor reports ready state when runtime is healthy."
    why_human: "Requires external runtime process and interactive operator validation."
---

# Phase 1: Local Runtime Baseline Verification Report

**Phase Goal:** User can run Aurora locally with safe defaults and validated local model connectivity.  
**Verified:** 2026-03-02T01:08:53Z  
**Status:** human_needed  
**Re-verification:** Yes - after gap closure

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | User can install Aurora as a global CLI tool and invoke `aurora` from any directory. | ? UNCERTAIN | `pyproject.toml` defines `aurora = "aurora.cli.app:app"` and README documents `uv tool install .`/`pipx install .`; real shell PATH verification still requires host-level run. |
| 2 | Root command exposes setup/config/model/doctor and no longer depends on placeholder behavior. | ✓ VERIFIED | `src/aurora/cli/app.py` registers all groups; `tests/cli/test_entrypoint.py` asserts help/discovery and absence of legacy placeholder assertions. |
| 3 | Entrypoint smoke contract is aligned with implemented setup/config/doctor/model behavior. | ✓ VERIFIED | `uv run pytest tests/cli/test_entrypoint.py -q` passes within the Phase 1 suite (`46 passed`). |
| 4 | User can configure local llama.cpp endpoint/model via `aurora model set`. | ✓ VERIFIED | `src/aurora/cli/model.py` persists endpoint/model/source via `save_settings`; covered by `tests/cli/test_model_command.py`. |
| 5 | HF source input accepts `repo/model:arquivo.gguf` and prefers local cache. | ✓ VERIFIED | `parse_hf_target` and `resolve_cached_model` enforce format and cache-first resolution; covered by `tests/runtime/test_model_source.py`. |
| 6 | Large downloads require explicit confirmation and support private-token prompt flow. | ✓ VERIFIED | `src/aurora/runtime/model_download.py` enforces confirmation threshold and token prompt; covered by `tests/runtime/test_model_download.py`. |
| 7 | First run opens guided setup wizard when required runtime config is missing. | ✓ VERIFIED | `src/aurora/cli/app.py` gates root callback via `should_run_first_run_wizard()`/`run_first_run_wizard()`; covered by `tests/cli/test_setup_wizard.py`. |
| 8 | Wizard blocks completion until endpoint connectivity and active model validation pass. | ✓ VERIFIED | `src/aurora/cli/setup.py` loops until `validate_runtime` succeeds or user aborts; covered by retry/abort tests. |
| 9 | Runtime failures return categorized pt-BR errors with exact recovery commands. | ✓ VERIFIED | `src/aurora/runtime/errors.py` + `src/aurora/runtime/llama_client.py`; covered by `tests/runtime/test_llama_client.py` and doctor/setup tests. |
| 10 | Config/status output shows local-only and telemetry-off defaults. | ✓ VERIFIED | `src/aurora/cli/config.py` and `src/aurora/cli/doctor.py` print explicit privacy state; covered by `tests/cli/test_config_show.py` and `tests/cli/test_doctor.py`. |
| 11 | Aurora persists runtime settings in per-user global location independent of CWD with privacy defaults. | ✓ VERIFIED | `src/aurora/runtime/paths.py` + `src/aurora/runtime/settings.py`; covered by `tests/runtime/test_settings_defaults.py`. |
| 12 | Cloud endpoint values are rejected by policy checks before runtime calls. | ✓ VERIFIED | `validate_local_endpoint` is enforced in settings load/save boundaries; covered by `tests/privacy/test_policy.py` and model command tests. |

**Score:** 11/12 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `pyproject.toml` | Global CLI entrypoint via `project.scripts` | ✓ VERIFIED | Contains `aurora = "aurora.cli.app:app"`. |
| `src/aurora/cli/app.py` | Root Typer app with command groups | ✓ VERIFIED | Exports `app`, registers `setup/config/model/doctor`, and shows help on no-args when wizard is not required. |
| `tests/cli/test_entrypoint.py` | Smoke checks for entrypoint + command discovery | ✓ VERIFIED | Updated contract covers implemented behavior (no placeholder coupling) and passes. |
| `src/aurora/cli/model.py` | `aurora model set` with persistence | ✓ VERIFIED | Exports `model_set_command`; wired to source parsing, download flow, and settings save. |
| `src/aurora/runtime/model_source.py` | HF parser/validation helpers | ✓ VERIFIED | Implements `parse_hf_target` and actionable pt-BR validation errors. |
| `src/aurora/runtime/model_download.py` | Download orchestration | ✓ VERIFIED | Implements confirmation, token flow, cache short-circuit, and guidance errors. |
| `src/aurora/cli/setup.py` | Guided setup flow | ✓ VERIFIED | Exports `setup_command` + `run_first_run_wizard`; includes blocking validation loop. |
| `src/aurora/runtime/llama_client.py` | Runtime connectivity/model probes | ✓ VERIFIED | Probes `/health` and `/v1/models`; classifies connectivity failures. |
| `src/aurora/runtime/errors.py` | Typed error taxonomy | ✓ VERIFIED | Includes `endpoint_offline`, `timeout`, `model_missing`, `invalid_token`. |
| `src/aurora/cli/config.py` | `aurora config show` privacy visibility | ✓ VERIFIED | Exports `config_show_command`; loads settings and prints privacy defaults. |
| `src/aurora/runtime/settings.py` | Typed settings + privacy defaults | ✓ VERIFIED | Defaults local-only true / telemetry false; save/load with policy validation. |
| `src/aurora/privacy/policy.py` | Local-only endpoint guards | ✓ VERIFIED | Enforces localhost/127.0.0.1 policy in Phase 1. |
| `tests/runtime/test_settings_defaults.py` | Defaults/path/persistence checks | ✓ VERIFIED | Includes deterministic path and round-trip assertions. |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `pyproject.toml` | `src/aurora/cli/app.py` | project script entrypoint | ✓ WIRED | Script maps to `aurora.cli.app:app`. |
| `src/aurora/cli/app.py` | `tests/cli/test_entrypoint.py` | help/assertions for command groups | ✓ WIRED | Entry-point smoke tests now assert real setup/config/model/doctor behavior and pass. |
| `src/aurora/cli/model.py` | `src/aurora/runtime/model_source.py` | source parsing before save/download | ✓ WIRED | Imports and invokes `parse_hf_target`. |
| `src/aurora/cli/model.py` | `src/aurora/runtime/model_download.py` | download pipeline | ✓ WIRED | Imports and invokes `download_model`. |
| `src/aurora/cli/model.py` | `src/aurora/runtime/settings.py` | persist endpoint/model/source | ✓ WIRED | Imports and invokes `save_settings`. |
| `src/aurora/cli/setup.py` | `src/aurora/runtime/llama_client.py` | wizard completion gate | ✓ WIRED | Imports and invokes `validate_runtime`. |
| `src/aurora/runtime/llama_client.py` | `src/aurora/runtime/errors.py` | exception classification | ✓ WIRED | Imports and invokes `classify_runtime_error`. |
| `src/aurora/cli/config.py` | `src/aurora/runtime/settings.py` | display persisted privacy defaults | ✓ WIRED | Imports and invokes `load_settings`. |
| `src/aurora/runtime/settings.py` | `src/aurora/runtime/paths.py` | global config path resolution | ✓ WIRED | Imports and uses `ensure_config_dir` + `get_settings_path`; `paths.py` uses `platformdirs`. |
| `src/aurora/runtime/settings.py` | `src/aurora/privacy/policy.py` | endpoint validation on save/load | ✓ WIRED | Imports and invokes `validate_local_endpoint`. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| CLI-01 | 01-01, 01-05 | User can invoke Aurora globally from any terminal directory after installation. | ? NEEDS HUMAN | Entry-point mapping and smoke tests are green; still requires host PATH validation after real `uv tool`/`pipx` install. |
| MOD-01 | 01-02, 01-03 | User can configure local llama.cpp endpoint/model through CLI configuration. | ✓ SATISFIED | `aurora model set`, setup wizard integration, and passing command/runtime tests. |
| MOD-03 | 01-03 | User receives actionable configuration errors when model endpoint is unavailable. | ✓ SATISFIED | Categorized runtime errors with recovery commands in `errors.py`/`llama_client.py`, plus doctor/setup coverage. |
| PRIV-01 | 01-02, 01-04 | User can run Aurora in local-only default mode without cloud API dependency. | ✓ SATISFIED | Policy enforcement rejects non-loopback endpoints at settings boundary and in CLI flow. |
| PRIV-04 | 01-03, 01-04 | User has telemetry disabled by default. | ✓ SATISFIED | Defaults in `RuntimeSettings` and explicit output in `config show`/`doctor`. |

Orphaned requirements for Phase 1: **none** (all roadmap phase IDs are represented in plan requirements).

### Anti-Patterns Found

No blocker/warning anti-patterns detected in phase implementation files (`src/aurora/**`, `tests/**`) for `TODO/FIXME` placeholders, empty stubs, or console-only behavior.

### Human Verification Required

### 1. Global Install Invocation

**Test:** Install with `uv tool install .` (or `pipx install .`) and run `aurora --help` from a different directory and fresh shell session.  
**Expected:** `aurora` resolves on PATH and renders command surface without project-local context.  
**Why human:** Requires shell PATH/session behavior and installer integration beyond unit tests.

### 2. Live Endpoint Validation Flow

**Test:** Run `aurora setup` against an actual local `llama-server` endpoint, including one failing attempt then successful retry.  
**Expected:** Wizard blocks until connectivity/model checks pass and shows summary with privacy defaults.  
**Why human:** Depends on real runtime process behavior and interactive UX quality.

### Gaps Summary

Previous verification gap is closed: entrypoint smoke tests are aligned with implemented Phase 1 behavior and the full Phase 1 suite now passes (`46 passed`). No code-level blocker gaps remain. Final phase sign-off still depends on two environment-level human checks (global install/PATH behavior and live llama.cpp runtime interaction).

---

_Verified: 2026-03-02T01:08:53Z_  
_Verifier: Codex (gsd-verifier)_
