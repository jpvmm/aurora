# Phase 05: Operational Command Surface - Research

**Researched:** 2026-04-05
**Domain:** Typer CLI restructuring, command namespace consolidation, status/doctor patterns
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Command Consolidation**
- D-01: Reduce top-level commands to 4 core entry points: `aurora ask`, `aurora chat`, `aurora status`, `aurora doctor`.
- D-02: Move `kb`, `model`, `memory` subcommands under `aurora config` namespace: `aurora config kb ...`, `aurora config model ...`, `aurora config memory ...`.
- D-03: `setup` merges into `aurora config` (e.g., `aurora config setup` or absorbed into first-run wizard).
- D-04: Old top-level commands (`aurora kb`, `aurora model`, `aurora memory`) remain as aliases with pt-BR deprecation warning: "Aviso: use `aurora config kb ...`" — one release cycle, then remove.

**Unified Status Command**
- D-05: New `aurora status` command shows full dashboard: model state (running/stopped, model name, endpoint), KB state (collection, note count, last update), memory state (memory count, last session), config summary (vault path, language).
- D-06: `aurora status` is report-only — does not auto-start model or trigger any side effects.
- D-07: `aurora status --json` supported for scripting/automation, returning structured JSON with all sections.

**Doctor Completeness**
- D-08: `aurora doctor` must check: model/endpoint connectivity, QMD binary availability and version, KB collection health (exists, has documents, embeddings generated), memory index health (aurora-memory collection exists, has embeddings), disk space for models, Python version, required packages.
- D-09: Doctor output pattern: each check shows pass/fail + what failed + why + exact recovery command. E.g., "KB sem embeddings. Execute: `aurora config kb rebuild`".
- D-10: Doctor does not auto-fix — only reports and suggests commands.

**Output Consistency**
- D-11: Every command that produces output supports `--json` for structured output. Universal contract for scripting.
- D-12: Structured error pattern across all commands: what failed + why + recovery command. Exit code 1 for user errors, exit code 2 for system errors. With `--json`, errors return `{"error": "...", "recovery": "..."}`.

**Missing Operations**
- D-13: Move KB operations under `aurora config kb` (ingest, update, delete, rebuild, config) as part of consolidation. Same functionality, cleaner namespace.
- D-14: Audit and improve all command `--help` text for clarity, consistency, pt-BR, and usage examples.
- D-15: Add shell completions via Typer's built-in support (bash/zsh/fish).
- D-16: No `aurora version` command — version info included in `aurora status` output instead.

### Claude's Discretion
- Exact layout and formatting of status dashboard sections
- Ordering and grouping of doctor checks
- Deprecation warning exact wording and styling
- Shell completion installation instructions

### Deferred Ideas (OUT OF SCOPE)
- `aurora version` as standalone command — version info will be in `aurora status` instead
- Auto-fix mode for doctor (prompting to fix issues inline) — deferred to future iteration
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CLI-02 | User can use dedicated CLI commands for ingest, update, delete, ask, and status operations. | Existing kb_app commands (ingest/update/delete/rebuild) are feature-complete; need to be re-registered under `aurora config kb`. `aurora status` must be created. `aurora ask` already exists. |
| CLI-04 | User can run a `doctor` command to validate local runtime dependencies and model readiness. | Existing doctor_app checks model/endpoint/policy. Needs extension for QMD binary check, KB collection health, memory index health, disk space, Python version, required packages. |
</phase_requirements>

---

## Summary

Phase 5 is a refactoring and surface-consolidation phase. All underlying functionality (KB ingest/update/delete, model lifecycle, memory management, ask, chat) is fully implemented across prior phases. The work here is surgical restructuring: reorganize command registrations in `app.py`, add a new `aurora status` command, extend the existing `aurora doctor`, add deprecation aliases for old top-level commands, and enable Typer shell completions.

The current `app.py` registers 7 top-level typers: `setup`, `config`, `model`, `doctor`, `kb`, `ask`, `chat`, `memory`. After Phase 5, the surface reduces to 4 core: `ask`, `chat`, `status`, `doctor`. Everything else routes through `aurora config` sub-namespace (config kb, config model, config memory, config setup). Old `aurora kb`, `aurora model`, `aurora memory` remain as aliased Typers emitting a deprecation warning before delegating.

The largest new code surface is the `aurora status` command: it needs to aggregate live state from 3 domains (model lifecycle via `ServerLifecycleService`, KB via `QMDSearchBackend`/`KBService`, memory via `EpisodicMemoryStore`) and render a unified dashboard. None of the data retrieval is new — all the required service methods already exist. The challenge is composition and side-effect-free aggregation.

**Primary recommendation:** Build Phase 5 as three sequential work units — (1) restructure app registrations + deprecation aliases, (2) add `aurora status`, (3) extend `aurora doctor`. Each unit has independent test coverage and can be committed separately.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| typer | 0.24.1 (installed) | CLI framework, subcommand registration, shell completion | Already the project standard; all existing commands use it |
| pydantic-settings | >=2.10.1 | Runtime settings access for status dashboard | Already used by all settings I/O |
| typer.testing.CliRunner | bundled with typer | Test harness for command invocation | All 124 existing CLI tests use it |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| importlib (stdlib) | stdlib | Re-import modules in tests after monkeypatching | Used in every existing CLI test to isolate module state |
| shutil.which (stdlib) | stdlib | Check QMD binary availability for doctor | Preferred over `subprocess` for existence checks |
| shutil.disk_usage (stdlib) | stdlib | Check disk space for models directory in doctor | Pure stdlib, no external dependency |
| importlib.metadata (stdlib) | stdlib | Read installed package versions for doctor | Preferred over `pip show` subprocess calls |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `shutil.which` for QMD check | `subprocess.run(["qmd", "--version"])` | `which` is cheaper; but `--version` also gives version string for doctor output — see pitfall section |
| `importlib.metadata` for package versions | `subprocess.run(["pip", "show", ...])` | `importlib.metadata` is stdlib and works in venvs without relying on pip being on PATH |
| Extending `doctor.py` in-place | Creating new `doctor_checks.py` module | In-place is fine given current file size; split if checks grow past ~200 lines |

---

## Architecture Patterns

### Recommended Project Structure After Phase 5

```
src/aurora/cli/
├── app.py          # Root Typer app — RESTRUCTURED (4 core + config + deprecated aliases)
├── ask.py          # Unchanged
├── chat.py         # Unchanged
├── config.py       # EXTENDED to absorb model/kb/memory/setup sub-typers
├── doctor.py       # EXTENDED with new check categories
├── status.py       # NEW — aurora status command
├── kb.py           # Unchanged (moves to aurora config kb registration)
├── memory.py       # Unchanged (moves to aurora config memory registration)
├── model.py        # Unchanged (moves to aurora config model registration)
└── setup.py        # Unchanged (moves to aurora config setup registration)
```

### Pattern 1: Typer Sub-Typer Registration

**What:** Each command group is a `typer.Typer()` instance added to a parent with `app.add_typer(child, name="name")`. Nesting is achieved by adding a sub-typer to another typer, not to the root app.

**When to use:** All namespace restructuring (moving kb/model/memory under config).

**Example:**
```python
# src/aurora/cli/config.py — add to existing config_app
from aurora.cli.kb import kb_app
from aurora.cli.model import model_app
from aurora.cli.memory import memory_app
from aurora.cli.setup import setup_app

config_app.add_typer(kb_app, name="kb")
config_app.add_typer(model_app, name="model")
config_app.add_typer(memory_app, name="memory")
config_app.add_typer(setup_app, name="setup")
```

```python
# src/aurora/cli/app.py — remove old registrations, keep 4 cores
app.add_typer(ask_app, name="ask")
app.add_typer(chat_app, name="chat")
app.add_typer(status_app, name="status")   # NEW
app.add_typer(doctor_app, name="doctor")
app.add_typer(config_app, name="config")
# Deprecated aliases (emit warning then delegate)
app.add_typer(deprecated_kb_app, name="kb")
app.add_typer(deprecated_model_app, name="model")
app.add_typer(deprecated_memory_app, name="memory")
```

### Pattern 2: Deprecation Alias via Typer Callback

**What:** Register the old name as a Typer callback that prints the deprecation warning to stderr, then delegate to the real implementation by re-invoking it.

**When to use:** D-04 — old top-level `aurora kb`, `aurora model`, `aurora memory` aliases.

**Recommended approach:** Create thin wrapper typers in `app.py` (or a dedicated `deprecated.py`) that use `invoke_without_command=False`, intercept the callback to emit warning, and call through to the real sub-typer's commands. The simplest approach that avoids code duplication: the deprecated wrapper typer imports and re-exposes the same command functions from the real module.

```python
# Deprecation alias example
_deprecated_kb_app = typer.Typer(
    no_args_is_help=True,
    help="[DEPRECADO] Use `aurora config kb`.",
)

@_deprecated_kb_app.callback()
def _deprecated_kb_callback(ctx: typer.Context) -> None:
    typer.echo(
        "Aviso: `aurora kb` foi movido. Use `aurora config kb ...`.",
        err=True,
    )

# Re-export same commands from real kb_app
from aurora.cli.kb import kb_ingest_command, kb_update_command, kb_delete_command, kb_rebuild_command
_deprecated_kb_app.command("ingest")(kb_ingest_command)
_deprecated_kb_app.command("update")(kb_update_command)
_deprecated_kb_app.command("delete")(kb_delete_command)
_deprecated_kb_app.command("rebuild")(kb_rebuild_command)
```

**Pitfall:** Typer callbacks on sub-typers with `invoke_without_command=True` fire even when a sub-command is invoked. Use default (`invoke_without_command=False`) with a `@_deprecated_kb_app.callback()` that always fires — this fires before any subcommand, which is what we want for the warning.

### Pattern 3: Status Command Aggregation

**What:** `aurora status` collects read-only state from multiple domain services and renders a dashboard. All service calls must be guarded with try/except so partial failures still render healthy sections.

**When to use:** Building `status.py`.

**Service integrations available:**
- `ServerLifecycleService().get_status()` — returns `LifecycleStatus` with `lifecycle_state`, `model_id`, `endpoint_url`, `pid`, `uptime_seconds`, `ready`
- `ServerLifecycleService().check_health()` — returns `LifecycleHealth` with `ok`, connectivity check
- `EpisodicMemoryStore().list_memories()` — returns list of memory dicts with `date`, `topic`, `turn_count`
- `load_settings()` — `kb_vault_path`, `kb_qmd_collection_name`, `kb_qmd_index_name`
- `QMDSearchBackend(collection_name=...).search("*")` or direct `qmd` invocation — for KB doc count (LOW confidence — need to verify qmd collection stats API)

**Recommended structure for JSON output:**
```python
# --json output shape
{
  "model": {
    "state": "running|stopped|crashed",
    "model_id": "...",
    "endpoint": "...",
    "pid": 1234,
    "uptime_seconds": 3600
  },
  "kb": {
    "collection": "aurora-kb-managed",
    "vault": "/path/to/vault",
    "note_count": 142,
    "last_update": "2026-04-05T09:00:00Z"
  },
  "memory": {
    "memory_count": 18,
    "last_session": "2026-04-05"
  },
  "config": {
    "vault_path": "/path/to/vault",
    "local_only": true,
    "telemetry_enabled": false
  }
}
```

### Pattern 4: Doctor Check Structure

**What:** Each check follows: probe → classify result → append `DoctorIssue` if failing. All checks run (no short-circuit), results aggregated and printed at end. Existing `DoctorIssue` dataclass and `_print_issues()` function are reusable.

**New checks to add for D-08:**

| Check | Probe Method | Category Name |
|-------|-------------|---------------|
| QMD binary availability | `shutil.which("qmd")` | `qmd_missing` |
| QMD version | `subprocess.run(["qmd", "--version"], capture_output=True)` | `qmd_version` |
| KB collection exists + has docs | `qmd collection list` or manifest inspection | `kb_collection_empty` |
| KB embeddings generated | QMD collection doc count vs manifest count | `kb_embeddings_missing` |
| Memory index health | `QMDSearchBackend(MEMORY_COLLECTION).search("test")` response | `memory_index_missing` |
| Disk space for models | `shutil.disk_usage(model_cache_dir)` | `disk_space_low` |
| Python version | `sys.version_info` vs `requires-python` (>=3.13) | `python_version` |
| Required packages | `importlib.metadata.version("typer")` etc. | `package_missing` |

**Recovery command patterns (from D-09):**
```
KB sem embeddings. Execute: `aurora config kb rebuild`
QMD nao encontrado. Execute: `pip install qmd`
Espaco em disco insuficiente. Libere espaco em {path}
```

### Pattern 5: Shell Completion (Typer Built-In)

**What:** Change root app from `add_completion=False` to `add_completion=True`. Typer 0.24.1 (installed) adds `--install-completion` and `--show-completion` flags to the root command automatically.

**Current state:** `app.py` line 18 sets `add_completion=False`.

**Change required:**
```python
app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    add_completion=True,   # Changed from False
    help="Aurora CLI local.",
)
```

**What this provides:** `aurora --install-completion` installs completion for the user's current shell (bash/zsh/fish). `aurora --show-completion` prints the completion script. No additional code needed — Typer generates completion from registered commands automatically.

**Caveat:** Typer shell completion uses Click's underlying completion engine. Tested on zsh and bash. Fish support exists but is less tested in the ecosystem. Since this is a single-developer tool, the built-in behavior is sufficient.

### Anti-Patterns to Avoid

- **Calling `check_health()` inside `aurora status`:** `check_health()` makes a live HTTP request to the llama.cpp endpoint. For a status command, `get_status()` (which reads the lock file) is sufficient and has no network side effects. Use `check_health()` in `doctor` (explicit diagnostic) but NOT in `status` (D-06: report-only, no side effects).
- **Short-circuiting doctor on first failure:** Doctor must run ALL checks and report ALL issues. Stopping at the first failure defeats the diagnostic purpose. The existing pattern in `doctor.py` already appends to `issues` list — follow it for new checks.
- **Registering deprecated aliases before real commands in app.py:** Typer picks the first matching name. Register real commands first, aliases second — or give aliases different names (they already have the same names, so order matters for disambiguation if needed).
- **Using `typer.echo()` for structured JSON:** All JSON output uses `typer.echo(json.dumps(..., ensure_ascii=False, indent=2))` — not `print()`. The one exception in `ask.py` (uses `print()` for streaming) is acceptable for that use case but `status` and `doctor` should use `typer.echo`.
- **Checking KB doc count via QMD search:** A QMD `search("*")` would hit the model endpoint. Use `qmd collection stats <index> <collection>` subprocess call instead, or read the KB manifest file directly (manifest path available via `get_settings_path().parent / "kb_manifest.json"` — verify actual path in `aurora.kb.manifest`).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Shell tab completion | Custom readline/argparse completion | `typer` `add_completion=True` | Typer generates complete bash/zsh/fish scripts from registered commands automatically |
| Package version introspection | Subprocess `pip show` | `importlib.metadata.version()` | stdlib, works in any venv, no subprocess overhead |
| Binary availability check | Custom PATH scanning | `shutil.which()` | stdlib, cross-platform, handles PATH correctly |
| Disk space check | Custom `os.statvfs` | `shutil.disk_usage()` | stdlib wrapper, simpler API |
| Sub-command delegation for aliases | Custom argument forwarding | Typer `app.add_typer()` with same command functions | Re-register same function objects under new names; no forwarding code needed |

**Key insight:** Every infrastructure-level check needed for doctor (`which`, `disk_usage`, `metadata.version`) is in Python stdlib. The only external tool check is QMD, which uses `subprocess.run` — the same pattern already used in `memory.py` for `_remove_qmd_collection`.

---

## Common Pitfalls

### Pitfall 1: Typer Sub-Typer Callback Firing Order
**What goes wrong:** A callback on a sub-typer with `invoke_without_command=True` fires even when the parent app is invoked directly, not just when that sub-command is chosen. This can cause deprecation warnings to fire incorrectly.
**Why it happens:** Typer propagates invocations down the chain. If the deprecated alias callback has `invoke_without_command=True`, it may fire on `aurora --help`.
**How to avoid:** Use `invoke_without_command=False` (default) for deprecated alias typers. The callback fires only when that specific sub-command group is invoked. The warning will print before the subcommand runs, which is the correct behavior.
**Warning signs:** Deprecation warning appears in `aurora --help` output.

### Pitfall 2: Test Isolation After app.py Restructuring
**What goes wrong:** Existing tests that check `"kb" in result.output` for root help will break because `kb` is no longer a top-level command (it's under `config`).
**Why it happens:** Tests in `test_entrypoint.py` use parametrize over `["setup", "config", "model", "doctor", "kb"]` — the `"kb"` and `"model"` entries will fail after restructuring.
**How to avoid:** Update `test_entrypoint.py` to check new top-level surface (`ask`, `chat`, `status`, `doctor`, `config`) and add separate tests for `aurora config --help` showing `kb`, `model`, `memory`.
**Warning signs:** `test_phase_one_command_groups_are_listed_in_root_help` parametrized test failures.

### Pitfall 3: `aurora status` Triggering Network Side Effects
**What goes wrong:** If `aurora status` calls `ServerLifecycleService().check_health()` (which makes HTTP probe), it violates D-06 (report-only, no side effects).
**Why it happens:** `check_health()` and `get_status()` look similar but behave differently — `get_status()` reads the lock file, `check_health()` makes a live HTTP request.
**How to avoid:** Use `get_status()` for status dashboard. Reserve `check_health()` for `aurora doctor`.
**Warning signs:** `aurora status` hangs when model server is offline due to HTTP timeout.

### Pitfall 4: KB Note Count in Status Without QMD Dependency
**What goes wrong:** Getting the KB note count for `aurora status` may require either a live QMD query (network) or reading internal state. QMD search queries are overkill for a count.
**Why it happens:** There is no direct "collection size" API that's side-effect-free.
**How to avoid:** Read the KB manifest file directly via the `load_kb_manifest()` function from `aurora.kb.manifest`. The manifest records each indexed note — `len(manifest.notes)` gives an accurate count without touching QMD. For last-update time, use the manifest file's mtime.
**Warning signs:** `aurora status` making subprocess calls to `qmd`.

### Pitfall 5: Deprecation Alias Double-Registration of Subcommands
**What goes wrong:** If the deprecated alias typer `kb_app_alias` is populated by re-calling `@app.command()` on the original functions, Typer may complain about functions already registered.
**Why it happens:** Typer tracks command registration by function identity.
**How to avoid:** Create thin wrapper functions that call through, or use `app.registered_commands` introspection. The safest approach: re-import the original functions and register them fresh on the alias typer (tested pattern — Python function objects can be registered on multiple Typer apps).
**Warning signs:** `ValueError: Command already registered` at import time.

### Pitfall 6: `aurora config` Callback Must Not Break Existing Behavior
**What goes wrong:** The existing `config_app` callback (in `config.py` line 22-26) shows guidance and exits with code 1 when invoked without a subcommand. Adding sub-typers under `config_app` changes what counts as "a subcommand" but the callback logic should still work.
**Why it happens:** After adding `kb`, `model`, `memory`, `setup` as sub-typers of `config_app`, the existing `config_callback` fires before routing to sub-typers. This is correct behavior — the existing test `test_config_group_shows_guidance_without_placeholder_message` expects exit code 1 when no subcommand given.
**How to avoid:** Keep the existing callback as-is. The `ctx.invoked_subcommand is not None` check handles the routing correctly — when `aurora config kb ingest` is invoked, `invoked_subcommand` will be `"kb"` and the callback returns early.
**Warning signs:** `aurora config kb ingest` exits with code 1 and shows guidance instead of running.

---

## Code Examples

### Loading KB Manifest for Note Count (Side-Effect-Free)

```python
# Source: aurora.kb.manifest (verified by reading src/aurora/kb/manifest.py)
from aurora.kb.manifest import load_kb_manifest
from aurora.runtime.settings import load_settings

settings = load_settings()
try:
    manifest = load_kb_manifest()
    note_count = len(manifest.notes)
    # last_update: use manifest file mtime or a field if available
except Exception:
    note_count = None  # Graceful degradation for status
```

### Doctor Check Pattern (Extending Existing)

```python
# Source: aurora/cli/doctor.py — existing DoctorIssue + _print_issues pattern
import shutil
import sys

def _check_qmd_binary() -> DoctorIssue | None:
    if shutil.which("qmd") is None:
        return DoctorIssue(
            category="qmd_missing",
            message="QMD nao encontrado no PATH.",
            commands=("pip install qmd",),
        )
    return None

def _check_python_version() -> DoctorIssue | None:
    required = (3, 13)
    if sys.version_info < required:
        return DoctorIssue(
            category="python_version",
            message=f"Python {sys.version_info.major}.{sys.version_info.minor} detectado. Requer >= 3.13.",
            commands=("Instale Python 3.13+",),
        )
    return None
```

### Package Version Check

```python
# Using importlib.metadata (stdlib, Python 3.8+)
import importlib.metadata

def _check_package(name: str) -> DoctorIssue | None:
    try:
        importlib.metadata.version(name)
        return None
    except importlib.metadata.PackageNotFoundError:
        return DoctorIssue(
            category="package_missing",
            message=f"Pacote '{name}' nao instalado.",
            commands=(f"pip install {name}",),
        )
```

### Typer Shell Completion Activation

```python
# Source: Typer docs + verified locally (typer 0.24.1)
# Change in src/aurora/cli/app.py:
app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    add_completion=True,   # was False — enables --install-completion / --show-completion
    help="Aurora CLI local.",
)
```

### Deprecation Alias Wrapper

```python
# Thin alias that warns and delegates
from aurora.cli.kb import kb_ingest_command, kb_update_command, kb_delete_command, kb_rebuild_command

_kb_alias_app = typer.Typer(no_args_is_help=True, help="[DEPRECADO] Use `aurora config kb`.")

@_kb_alias_app.callback()
def _kb_alias_cb(ctx: typer.Context) -> None:
    typer.echo("Aviso: `aurora kb` foi movido. Use `aurora config kb ...`.", err=True)

_kb_alias_app.command("ingest")(kb_ingest_command)
_kb_alias_app.command("update")(kb_update_command)
_kb_alias_app.command("delete")(kb_delete_command)
_kb_alias_app.command("rebuild")(kb_rebuild_command)
```

---

## Runtime State Inventory

> Not applicable: Phase 5 is a CLI restructuring phase, not a rename/rebrand/migration. No stored data, collection names, or persisted keys are being renamed. Existing settings keys (`kb_qmd_index_name`, `kb_qmd_collection_name`, etc.) are unchanged.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13+ | Project requirement (pyproject.toml) | via uv | 3.13.x (uv managed) | — |
| typer | CLI framework | ✓ | 0.24.1 | — |
| qmd | Doctor check target | ✓ | 2.0.1 | Doctor reports `qmd_missing` issue |
| shutil (stdlib) | Doctor disk/which checks | ✓ | stdlib | — |
| importlib.metadata (stdlib) | Doctor package checks | ✓ | stdlib | — |
| typer.testing.CliRunner | Test harness | ✓ | bundled | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None — all required tools are present.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 (in pyproject.toml dependencies) |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/cli/ -x -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CLI-02 | `aurora ask` works as top-level command | unit | `uv run pytest tests/cli/test_ask_command.py -x` | ✅ |
| CLI-02 | `aurora config kb ingest/update/delete/rebuild` works | unit | `uv run pytest tests/cli/test_kb_command.py -x` | ✅ (needs new namespace test) |
| CLI-02 | `aurora status` renders dashboard with model/KB/memory/config sections | unit | `uv run pytest tests/cli/test_status_command.py -x` | ❌ Wave 0 |
| CLI-02 | `aurora status --json` returns structured JSON | unit | `uv run pytest tests/cli/test_status_command.py::test_status_json -x` | ❌ Wave 0 |
| CLI-02 | Deprecated `aurora kb` emits pt-BR warning and delegates | unit | `uv run pytest tests/cli/test_entrypoint.py::test_deprecated_aliases -x` | ❌ Wave 0 |
| CLI-04 | `aurora doctor` checks QMD binary availability | unit | `uv run pytest tests/cli/test_doctor.py -x` | ✅ (needs new check tests) |
| CLI-04 | `aurora doctor` checks KB collection health | unit | `uv run pytest tests/cli/test_doctor.py::test_doctor_kb_checks -x` | ❌ Wave 0 |
| CLI-04 | `aurora doctor` checks memory index health | unit | `uv run pytest tests/cli/test_doctor.py::test_doctor_memory_checks -x` | ❌ Wave 0 |
| CLI-04 | `aurora doctor` shows pass/fail + recovery per check | unit | `uv run pytest tests/cli/test_doctor.py -x` | ✅ (existing pattern, extend) |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/cli/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/cli/test_status_command.py` — covers CLI-02 status dashboard and `--json` contract
- [ ] `tests/cli/test_entrypoint.py` — update parametrized test for new top-level surface, add deprecated alias tests
- [ ] Doctor check expansions in `tests/cli/test_doctor.py` — new check categories (qmd_missing, kb_collection_empty, memory_index_missing, python_version, package_missing, disk_space_low)

*(Existing test infrastructure is in place — pytest, CliRunner, monkeypatch patterns. Only missing test files need creation.)*

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flat top-level commands | 4-core + config namespace | Phase 5 (this phase) | Reduces user surface area; kb/model/memory become "power user" config commands |
| Doctor checks only model/endpoint/policy | Doctor checks full stack (QMD, KB, memory, disk, Python) | Phase 5 (this phase) | Actionable diagnostics for all failure modes |
| No shell completion | Typer built-in completion | Phase 5 (this phase) | `aurora --install-completion` works for bash/zsh/fish |

**Deprecated/outdated after this phase:**
- `aurora kb` as top-level: will emit deprecation warning, use `aurora config kb`
- `aurora model` as top-level: will emit deprecation warning, use `aurora config model`
- `aurora memory` as top-level: will emit deprecation warning, use `aurora config memory`

---

## Open Questions

1. **KB collection health check method**
   - What we know: `QMDSearchBackend.search()` makes network calls. The manifest (`load_kb_manifest()`) has indexed notes. QMD has a `collection list` and potentially `collection stats` subcommand.
   - What's unclear: Whether `qmd collection stats <index> <collection>` gives document count without hitting the embedding model, and what happens when the collection exists in QMD but embeddings are missing vs. collection does not exist at all.
   - Recommendation: Use `qmd collection list --index <index>` via subprocess to check collection existence. Use manifest `len(notes)` for count. Treat absence of collection while manifest has notes as "embeddings missing" condition.

2. **Memory index health probe**
   - What we know: `MEMORY_COLLECTION = "aurora-memory"` and `MEMORY_INDEX = "aurora-kb"`. Memory files are `.md` files in `get_memory_dir()`. QMD collection for memory may or may not be generated.
   - What's unclear: Whether checking "memory index health" means (a) memory files exist, (b) QMD collection exists, or (c) QMD collection has same count as files.
   - Recommendation: For doctor, check: (a) memory files count via `EpisodicMemoryStore().list_memories()`, (b) QMD collection existence via `qmd collection list`. Report mismatch as `memory_index_missing`.

3. **`aurora status` version info format**
   - What we know: D-16 says version info goes in `aurora status` instead of a standalone command.
   - What's unclear: Where to read the project version from (pyproject.toml vs `importlib.metadata.version("aurora")`).
   - Recommendation: Use `importlib.metadata.version("aurora")` — works after `pip install -e .` (the standard dev install). Read `pyproject.toml` version as fallback if package is not installed.

---

## Sources

### Primary (HIGH confidence)

- Source code: `src/aurora/cli/app.py` — current command registrations, `add_completion=False` confirmed
- Source code: `src/aurora/cli/doctor.py` — existing check pattern, `DoctorIssue` dataclass, `_print_issues()`
- Source code: `src/aurora/cli/config.py` — existing `config_app`, `config_show`, `config_callback` pattern
- Source code: `src/aurora/cli/kb.py` — full kb_app command set, kb_config_app, kb_scheduler_app
- Source code: `src/aurora/cli/model.py` — model commands, `_render_status`, `_render_health` patterns
- Source code: `src/aurora/cli/memory.py` — memory commands, `EpisodicMemoryStore` usage
- Source code: `src/aurora/cli/ask.py` — `--json` flag pattern, `allow_interspersed_args`
- Source code: `src/aurora/runtime/settings.py` — `RuntimeSettings` fields available for status dashboard
- Source code: `tests/cli/` — 124 existing tests, patterns for CliRunner + monkeypatch + importlib
- Verified locally: `typer.__version__ == "0.24.1"`, `add_completion=True` adds `--install-completion` and `--show-completion`

### Secondary (MEDIUM confidence)

- Typer documentation: shell completion via `add_completion=True` on root `Typer()` instance; `--install-completion` / `--show-completion` generated automatically
- Python stdlib docs: `shutil.which()`, `shutil.disk_usage()`, `importlib.metadata.version()` — all standard and available in Python 3.9+

### Tertiary (LOW confidence)

- `qmd collection list` / `qmd collection stats` subcommand behavior — not verified by reading qmd source; assumed based on qmd 2.0.1 installed version and existing usage pattern in `memory.py`

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already installed and in use in the project
- Architecture patterns: HIGH — derived from direct source code reading of existing CLI modules
- Pitfalls: HIGH — derived from reading existing tests and understanding the Typer sub-typer mechanics
- Doctor check extensions: MEDIUM — probe methods are standard stdlib; specific qmd subcommands for collection health need verification during implementation

**Research date:** 2026-04-05
**Valid until:** 2026-05-05 (stable domain — CLI patterns and stdlib don't change rapidly)
