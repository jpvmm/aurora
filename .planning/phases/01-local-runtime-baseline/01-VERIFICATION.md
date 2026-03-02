---
phase: 01-local-runtime-baseline
verified: 2026-03-02T00:51:22Z
status: gaps_found
score: 10/12 must-haves verified
gaps:
  - truth: "Root command exposes the Phase 1 command groups (`setup`, `config`, `model`, `doctor`) with explicit placeholder behavior."
    status: failed
    reason: "Setup/config/doctor now execute real behavior, but entrypoint smoke tests still assert legacy placeholder text."
    artifacts:
      - path: "tests/cli/test_entrypoint.py"
        issue: "3 failing tests still require 'ainda não implementado' for setup/config/doctor."
    missing:
      - "Align entrypoint smoke tests and/or must-have wording with the implemented non-placeholder command behavior."
      - "Restore green status for `uv run pytest tests/cli/test_entrypoint.py -q`."
---

# Phase 1: Local Runtime Baseline Verification Report

**Phase Goal:** User can run Aurora locally with safe defaults and validated local model connectivity.  
**Verified:** 2026-03-02T00:51:22Z  
**Status:** gaps_found  
**Re-verification:** No - initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | User can install Aurora as a global CLI tool and invoke `aurora` from any directory. | ? UNCERTAIN | `pyproject.toml` defines `project.scripts` entrypoint and README has `uv tool`/`pipx` install guidance, but cross-shell global invocation was not executed in this verification. |
| 2 | Root command exposes Phase 1 groups with explicit placeholder behavior. | ✗ FAILED | `setup`, `config`, `doctor` are implemented command flows; `tests/cli/test_entrypoint.py` still expects placeholder text and fails (3 failures). |
| 3 | User can configure local llama.cpp endpoint/model via `aurora model set`. | ✓ VERIFIED | `src/aurora/cli/model.py` implements `model set` and persists via `save_settings`; covered by `tests/cli/test_model_command.py`. |
| 4 | HF source input accepts `repo/model:arquivo.gguf` and prefers local cache. | ✓ VERIFIED | `parse_hf_target` in `src/aurora/runtime/model_source.py`; cache resolution in `src/aurora/runtime/model_registry.py`; covered by `tests/runtime/test_model_source.py`. |
| 5 | Large downloads require explicit confirmation and support private-token prompt flow. | ✓ VERIFIED | `src/aurora/runtime/model_download.py` enforces confirmation threshold + token prompt; covered by `tests/runtime/test_model_download.py`. |
| 6 | First run opens guided setup wizard when required runtime config is missing. | ✓ VERIFIED | `src/aurora/cli/app.py` calls `should_run_first_run_wizard()` and `run_first_run_wizard()`; covered by `tests/cli/test_setup_wizard.py`. |
| 7 | Wizard blocks completion until endpoint connectivity and active model validation pass. | ✓ VERIFIED | `src/aurora/cli/setup.py` loops until `validate_runtime()` succeeds or user aborts; covered by setup wizard retry/abort tests. |
| 8 | Runtime failures return categorized pt-BR errors with exact recovery commands. | ✓ VERIFIED | `src/aurora/runtime/errors.py` + `src/aurora/runtime/llama_client.py`; covered by `tests/runtime/test_llama_client.py` and doctor/setup tests. |
| 9 | Config/status output shows local-only and telemetry-off defaults. | ✓ VERIFIED | `aurora config show` and `aurora doctor` print privacy state; confirmed in CLI tests and direct command output. |
| 10 | Aurora persists runtime settings in per-user global location independent of CWD. | ✓ VERIFIED | `src/aurora/runtime/paths.py` + `src/aurora/runtime/settings.py`; covered by `tests/runtime/test_settings_defaults.py`. |
| 11 | Defaults enforce local-only mode and telemetry disabled in Phase 1. | ✓ VERIFIED | `RuntimeSettings` defaults in `src/aurora/runtime/settings.py`; verified by defaults tests and `config show` output. |
| 12 | Cloud endpoint values are rejected by policy checks before runtime calls. | ✓ VERIFIED | `validate_local_endpoint` enforced during `save_settings`; covered by `tests/privacy/test_policy.py` and model command tests. |

**Score:** 10/12 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `pyproject.toml` | Global CLI entrypoint via `project.scripts` | ✓ VERIFIED | Contains `aurora = "aurora.cli.app:app"`. |
| `src/aurora/cli/app.py` | Root Typer app with command groups | ✓ VERIFIED | Exports `app`, registers `setup/config/model/doctor`, runs first-run wizard gate. |
| `tests/cli/test_entrypoint.py` | Smoke checks for entrypoint + command discovery | ⚠️ REGRESSION | Exists and substantive, but 3 tests fail due outdated placeholder expectations. |
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
| `src/aurora/cli/app.py` | `tests/cli/test_entrypoint.py` | help assertions for command groups | ⚠️ PARTIAL | Coverage exists but placeholder assertions are stale and failing. |
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
| CLI-01 | 01-01 | User can invoke Aurora globally from any terminal directory after installation. | ? NEEDS HUMAN | Entrypoint mapping and docs are present; global invocation after real `uv tool`/`pipx` install across directories not executed here. |
| MOD-01 | 01-02, 01-03 | User can configure local llama.cpp endpoint/model through CLI configuration. | ✓ SATISFIED | `aurora model set`, setup wizard integration, and passing command/runtime tests. |
| MOD-03 | 01-03 | User receives actionable configuration errors when model endpoint is unavailable. | ✓ SATISFIED | Categorized runtime errors with recovery commands in `errors.py`/`llama_client.py`, plus doctor/setup coverage. |
| PRIV-01 | 01-02, 01-04 | User can run Aurora in local-only default mode without cloud API dependency. | ✓ SATISFIED | Policy enforcement rejects non-loopback endpoints at settings boundary and in CLI flow. |
| PRIV-04 | 01-03, 01-04 | User has telemetry disabled by default. | ✓ SATISFIED | Defaults in `RuntimeSettings` and explicit output in `config show`/`doctor`. |

Orphaned requirements for Phase 1: **none** (all roadmap phase IDs are represented in plan requirements).

### Anti-Patterns Found

No blocker/warning anti-patterns detected in phase files (`TODO/FIXME` placeholders, empty impl stubs, console-only handlers).

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

Phase goal is largely implemented and wired (safe defaults, local-only policy, runtime validation, model configuration), but verification found one contract regression: entrypoint smoke tests still encode obsolete placeholder behavior for commands now implemented in later plans. This leaves a red test artifact tied to must-have coverage and prevents full pass.

---

_Verified: 2026-03-02T00:51:22Z_  
_Verifier: Codex (gsd-verifier)_
