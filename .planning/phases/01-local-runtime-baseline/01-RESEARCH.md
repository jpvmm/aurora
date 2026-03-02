# Phase 1: Local Runtime Baseline - Research

**Researched:** 2026-03-01  
**Domain:** Python CLI bootstrap, local `llama.cpp` runtime connectivity, privacy-safe defaults  
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Setup Flow
- Primary onboarding path is global install via `uv tool` / `pipx`.
- First run should open a guided wizard when required runtime config is missing.
- Wizard must validate endpoint connectivity and active model before completion.
- Setup completion should show a clear summary and immediate next command (`aurora ask` example).
- If setup validation fails, setup should block and guide user through correction.
- Onboarding language defaults to pt-BR with explicit guidance on changing language.
- User expects model setup to support Hugging Face model path input and local serving flow.

### Config UX
- Configuration UX should support both command-based config and wizard flow.
- Model source input should accept explicit Hugging Face target in `repo/model:arquivo.gguf` form.
- Initial default model should be `Qwen3-8B-Q8_0` (GGUF).
- Config scope is global per user, so Aurora works consistently from any directory.
- Download UX should show detailed progress (percent, size, ETA).
- Model switching should activate new default and keep previously downloaded models.
- Downloaded models should live in a global Aurora directory by default.
- QMD alignment should be inspiration-level (familiar behavior), not strict one-to-one cloning.
- If download fails, CLI should provide guided retry.
- Private Hugging Face models should be supported with secure token prompt in-flow.
- If offline and HF download is requested, CLI should show actionable offline guidance.
- Preferred command naming: `aurora model set`.
- Large downloads should always require explicit confirmation.
- CLI should provide dedicated config inspection command (for example, `aurora config show`).
- If a requested model already exists locally, local cache should be prioritized.

### Model Errors
- Error messages should be direct and actionable, not generic.
- Failure reasons should be grouped by type (endpoint offline, model missing, invalid token, timeout).
- Each error should include exact recovery command(s), with `aurora doctor` available when relevant.
- Error communication remains in clear pt-BR by default.

### Privacy UX
- Startup/status should explicitly show local-only runtime state.
- Telemetry-off default should be visible in configuration/status output.
- Attempting cloud endpoint setup in Phase 1 should be blocked with clear explanation.
- Sensitive paths/content in logs should be masked by default.

### Claude's Discretion
- Exact copywriting and visual formatting of wizard screens and status outputs.
- Exact command output layout for progress blocks and confirmation prompts.
- Precise wording strategy for privacy and error banners while keeping tone practical.

### Specific Ideas

- "the cli must be able to spin up a model from huggingface for llama.cpp based on a hugginface model path name setup by the user."
- "as default lets use Qwen3-8B-Q8_0.gguf for the assistant."
- "check how the QMD lib does it and follow."

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within Phase 1 scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CLI-01 | User can invoke Aurora globally from any terminal directory after installation. | Packaging via `pyproject.toml` `[project.scripts]` + install flows with `uv tool install` / `pipx install`, plus PATH checks (`uv tool update-shell` / `pipx ensurepath`). |
| MOD-01 | User can configure local llama.cpp endpoint/model through CLI configuration. | Global config model + wizard + `aurora model set` with endpoint URL + model id + HF source parsing (`repo/model:file.gguf`). |
| MOD-03 | User receives actionable configuration errors when model endpoint is unavailable. | Deterministic connectivity probe (`/health`, `/v1/models`) and typed error mapping from `httpx` exception hierarchy to recovery commands. |
| PRIV-01 | User can run Aurora in local-only default mode without cloud API dependency. | Startup policy guardrails: local endpoint only (`127.0.0.1`/`localhost` default), reject cloud endpoint setup in Phase 1, no cloud provider fallback paths. |
| PRIV-04 | User has telemetry disabled by default. | Explicit default flags for `AGNO_TELEMETRY=false` and `GRAPHITI_TELEMETRY_ENABLED=false`; surface status in `aurora config show` and startup banner. |
</phase_requirements>

## Summary

Phase 1 should be planned as a strict runtime contract phase, not as assistant feature development. The goal is to guarantee that any user can install `aurora`, run it from any directory, complete setup once, and immediately know whether their local model runtime is healthy. This requires clear separation between packaging/install concerns, persistent global configuration, and runtime verification/error classification.

For global invocation, standard Python packaging and tool installers are sufficient and should not be reinvented: expose `aurora` through `[project.scripts]`, support `uv tool install` and `pipx install`, and include explicit PATH diagnostics for first-run failures. For model setup, use a guided wizard plus command-mode config (`aurora model set`) backed by a typed config schema, and validate via `llama-server` endpoints before setup completion.

Privacy defaults are enforceable in this phase: local endpoint defaults, cloud endpoint block in setup, and telemetry-off defaults visible to the user. The plan should include explicit error taxonomy for endpoint offline, timeout, model-missing, invalid HF token, and offline download mode, each with exact pt-BR recovery commands.

**Primary recommendation:** Plan Phase 1 around one vertical slice: `install -> setup wizard -> endpoint/model validation -> status output`, with hard local-only and telemetry-off guardrails enabled by default.

## Standard Stack

### Core

| Library / Tool | Version | Purpose | Why Standard |
|---|---|---|---|
| Python | 3.13.x | Runtime and packaging target | Matches project baseline and strong ecosystem support for CLI + local AI tooling. |
| `uv` | current stable (`0.10.x` line) | Primary install path for global CLI tool install | Officially supports persistent tool install with executables on PATH. |
| `pipx` | current stable | Secondary install path for global CLI tool install | Isolated venv per app; purpose-built for globally invokable Python CLIs. |
| `llama.cpp` (`llama-server`) | current stable release line | Local model serving and OpenAI-compatible endpoints | Native local-first serving, `--hf-repo` support, `/health` and `/v1/models` for readiness/model introspection. |
| `typer` + `rich` | current stable | CLI command surface and setup UX | Fast path to subcommands, prompts, and readable terminal output. |
| `pydantic-settings` | current stable | Typed config and env override handling | Strong schema validation for setup/config defaults and overrides. |
| `platformdirs` | current stable | Global per-user config/cache/data paths | Avoids OS-specific path hand-rolling. |
| `httpx` | current stable | Endpoint health/model probes + typed networking errors | Exception hierarchy maps cleanly to actionable CLI diagnostics. |
| `huggingface_hub` | current stable (`1.x`) | HF model file/repo download with auth and cache semantics | Handles private/public repos, token flow, and download filtering. |

### Supporting

| Library / Tool | Purpose | When to Use |
|---|---|---|
| `tomli-w` (if needed) | Safe TOML write support | If config is persisted in TOML and you need stable serialization. |
| `packaging` | Version/constraint checks | If model/runtime compatibility validation is added in this phase. |
| `prompt-toolkit` (optional) | Advanced wizard interactions | Only if Typer/Rich prompts become limiting. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| `huggingface_hub` downloads | `llama-server --hf-repo` only | Simpler integration, but less control over progress UX and explicit file targeting/reporting in wizard. |
| Typer command surface | Click directly | More manual boilerplate for typed options/help and reduced readability for rapid CLI expansion. |
| TOML config | JSON/YAML | TOML fits Python packaging ecosystem and human editability better for CLI users. |

**Installation (baseline for planning):**
```bash
uv init
uv add typer rich pydantic-settings platformdirs httpx huggingface_hub
```

## Architecture Patterns

### Recommended Project Structure
```text
src/
└── aurora/
    ├── cli/
    │   ├── app.py              # root command + groups
    │   ├── setup.py            # first-run wizard
    │   ├── config.py           # config show/set commands
    │   └── model.py            # aurora model set
    ├── runtime/
    │   ├── settings.py         # typed config model + load/save
    │   ├── llama_client.py     # /health + /v1/models probes
    │   ├── model_source.py     # parse repo/model:file.gguf
    │   └── errors.py           # classified user-facing errors
    └── privacy/
        └── policy.py           # local-only + telemetry defaults/guards
```

### Pattern 1: Installer + Entrypoint Contract
**What:** Define global executable via `[project.scripts]` and validate after `uv tool install` / `pipx install`.  
**When to use:** Immediately in Wave 0; this is required for CLI-01.  
**Example:**
```toml
[project.scripts]
aurora = "aurora.cli.app:app"
```
Source: https://packaging.python.org/specifications/entry-points/

### Pattern 2: Global Config with Strict Schema
**What:** Persist a single global user config (endpoint, model id, model source, telemetry/local-only flags), with env overrides optional.  
**When to use:** Required for MOD-01 and PRIV defaults.  
**Example:**
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class AuroraSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AURORA_")
    endpoint_base_url: str = "http://127.0.0.1:8080"
    model_id: str = "Qwen3-8B-Q8_0"
    telemetry_enabled: bool = False
    local_only: bool = True
```
Source: https://docs.pydantic.dev/usage/settings/

### Pattern 3: Two-Step Runtime Validation
**What:** Validate server readiness (`GET /health`) and selected model presence (`GET /v1/models`) before finishing setup.  
**When to use:** Wizard completion gate and `aurora config validate`/`aurora status`.  
**Example:**
```python
import httpx

def validate_runtime(base_url: str, expected_model: str) -> None:
    with httpx.Client(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
        health = client.get(f"{base_url}/health")
        health.raise_for_status()
        models = client.get(f"{base_url}/v1/models")
        models.raise_for_status()
        ids = {m["id"] for m in models.json().get("data", [])}
        if expected_model not in ids:
            raise RuntimeError("model_missing")
```
Sources: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md, https://www.python-httpx.org/exceptions/

### Pattern 4: Explicit HF Source Parsing
**What:** Accept input as `repo/model:arquivo.gguf`, split into `repo_id` + `filename`, then download with auth/caching semantics.  
**When to use:** `aurora model set --source` and setup wizard model step.  
**Example:**
```python
def parse_hf_target(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise ValueError("use repo/model:arquivo.gguf")
    repo_id, filename = value.split(":", 1)
    return repo_id.strip(), filename.strip()
```
Source: https://huggingface.co/docs/huggingface_hub/guides/download

### Anti-Patterns to Avoid
- **Generic `except Exception` for connectivity:** lose actionable error categories; map `httpx` exception types explicitly.
- **Local-only claim without endpoint restrictions:** Phase 1 must block cloud endpoint setup paths.
- **Config in current working directory:** violates global consistency requirement from context.
- **Logging raw token/absolute sensitive paths:** violates privacy UX goals.

## Don't Hand-Roll

| Problem | Don’t Build | Use Instead | Why |
|---|---|---|---|
| Cross-platform config/cache path logic | Custom `~/.aurora` path branching per OS | `platformdirs` (`user_config_dir`, `user_cache_dir`) | Avoid platform-specific bugs and migration issues. |
| HF auth/cache/download/retry mechanics | Manual HTTP downloader | `huggingface_hub` (`hf_hub_download` / `snapshot_download` / `hf download`) | Built-in token + cache semantics and filtering support. |
| Python CLI global installation plumbing | Custom shell scripts/symlink installer | `uv tool install` and `pipx install` flows | Standardized, isolated install behavior with PATH guidance. |
| Model endpoint error taxonomy | Ad-hoc string matching on error text | `httpx` typed exceptions + endpoint status checks | Predictable actionable diagnostics for MOD-03. |
| Model fetch from HF repos | Custom HF repo file discovery logic | `llama.cpp --hf-repo` / `--hf-file` support where applicable | Native runtime support already exists, including token/env integration. |

**Key insight:** Phase 1 is integration-and-guardrails work; leverage mature tooling and invest effort in UX/error policy, not reinvention.

## Common Pitfalls

### Pitfall 1: CLI installs but command is not found
**What goes wrong:** `aurora` cannot be invoked globally after install.  
**Why it happens:** User PATH missing the tool bin dir.  
**How to avoid:** Detect and print exact remediation (`uv tool update-shell` or `pipx ensurepath`) during install docs and setup failures.  
**Warning signs:** `command not found: aurora` right after successful install logs.

### Pitfall 2: Endpoint check reports “down” while model is still loading
**What goes wrong:** False-negative setup failures.  
**Why it happens:** Only checking one endpoint or misreading `503 Loading model` from `/health`.  
**How to avoid:** Treat `/health` `503` as transitional with retry/backoff and clear “carregando modelo” messaging.  
**Warning signs:** Frequent fail/retry loops immediately after server startup.

### Pitfall 3: Selected model id does not match loaded alias
**What goes wrong:** Setup passes endpoint but runtime later fails “model not found”.  
**Why it happens:** `llama-server` model id defaults to path unless alias is set.  
**How to avoid:** Validate against `/v1/models` returned id(s) and store the exact selected id/alias.  
**Warning signs:** `404`/invalid model errors on first generation call.

### Pitfall 4: Private HF model flow fails silently
**What goes wrong:** Download failure without clear next action.  
**Why it happens:** Missing/invalid token handling not classified.  
**How to avoid:** Explicitly catch auth/permission failure and prompt secure token retry with masked display.  
**Warning signs:** 401/403 without guided retry command.

### Pitfall 5: “Local-only” mode still permits cloud endpoints
**What goes wrong:** Product promise breach.  
**Why it happens:** No setup-time policy check on endpoint host/URL.  
**How to avoid:** Phase 1 hard-block for non-local endpoints and clear explanation that cloud endpoints are out of scope in this phase.  
**Warning signs:** Configs containing non-loopback hosts in Phase 1 profile.

### Pitfall 6: Telemetry-off default not reflected in UX
**What goes wrong:** Unclear privacy state for user.  
**Why it happens:** Default exists in code but not surfaced in status/config output.  
**How to avoid:** Show telemetry status in `aurora config show` and startup/status banner.  
**Warning signs:** User cannot verify privacy state from CLI.

## Code Examples

Verified patterns to reuse in planning:

### Global CLI install commands
```bash
# Preferred
uv tool install .

# Alternative
pipx install .
```
Sources: https://docs.astral.sh/uv/guides/tools/, https://pipx.pypa.io/stable/docs/

### llama.cpp local server baseline
```bash
llama-server --host 127.0.0.1 --port 8080 \
  --hf-repo ggml-org/gemma-3-1b-it-GGUF --hf-token "$HF_TOKEN"
```
Source: https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md

### HF CLI download with dry-run
```bash
hf download Qwen/Qwen3-8B-GGUF Qwen3-8B-Q8_0.gguf --dry-run
hf download Qwen/Qwen3-8B-GGUF Qwen3-8B-Q8_0.gguf --local-dir ~/.cache/aurora/models
```
Source: https://huggingface.co/docs/huggingface_hub/guides/download

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| Ad-hoc Python CLI installs with manual venv/symlink docs | Tool-native app install (`uv tool`, `pipx`) | Matured across 2024-2025 tool ecosystem | More reliable global invocation and cleaner uninstall/upgrade story. |
| Generic “ping endpoint” checks | Explicit readiness + model introspection (`/health` + `/v1/models`) | Current `llama-server` docs/API | Better diagnosis quality for MOD-03 and fewer false setup failures. |
| Manual HF file fetch scripts | `huggingface_hub` API/CLI with cache+auth primitives | Current Hub client docs | Faster implementation of private/public model download UX with fewer edge-case bugs. |

**Deprecated/outdated for this phase:**
- Installing Aurora via `pip install` directly into user/system interpreter as primary recommendation.
- Claiming local-only without enforcing endpoint constraints and visible telemetry state.

## Open Questions

1. **Which download path should be primary in Phase 1 (`huggingface_hub` vs `llama-server --hf-repo`)?**
   - What we know: both are viable; `llama-server` supports HF repo/file/token/offline flags, while `huggingface_hub` gives richer download controls and CLI dry-run.
   - What’s unclear: which path yields the best pt-BR wizard UX for progress/confirmation/caching.
   - Recommendation: choose `huggingface_hub` as primary download mechanism in-app; keep `llama-server --hf-repo` as supported fallback/advanced path.

2. **Should setup auto-start `llama-server` or only validate an already running endpoint?**
   - What we know: success criteria require validated connectivity, not daemon orchestration.
   - What’s unclear: user expectation for “spin up model” in same command versus explicit external runtime management.
   - Recommendation: plan Phase 1 for “validate existing endpoint” + guided start commands; defer robust process management to later phase unless required during planning.

3. **How strict should local-only endpoint validation be?**
   - What we know: Phase 1 requires cloud endpoint blocking.
   - What’s unclear: whether LAN private IPs should be allowed in addition to loopback.
   - Recommendation: default allowlist only `localhost` / `127.0.0.1` in Phase 1; document rationale and revisit in a future phase.

## Sources

### Primary (HIGH confidence)
- https://docs.astral.sh/uv/guides/tools/ - `uv tool install`, PATH/update-shell behavior, persistent tool install model.
- https://docs.astral.sh/uv/ - `uv` overview with tools model and install examples.
- https://pipx.pypa.io/stable/docs/ - `pipx install` global app semantics, PATH expectations, ensurepath command.
- https://packaging.python.org/specifications/entry-points/ - `[project.scripts]` entry-point contract for global CLI commands.
- https://raw.githubusercontent.com/ggml-org/llama.cpp/master/README.md - `llama-server` and `-hf` usage in official project docs.
- https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md - server args (`--host`, `--port`, `--offline`, `--hf-token`), `/health`, `/v1/models`, monitoring endpoints.
- https://huggingface.co/docs/huggingface_hub/guides/download - `hf_hub_download`, `snapshot_download`, `hf download`, dry-run/download patterns.
- https://huggingface.co/docs/huggingface_hub/main/en/package_reference/environment_variables - `HF_TOKEN`, `HF_HOME`, cache/token behavior.
- https://www.python-httpx.org/exceptions/ - typed exception hierarchy for actionable network diagnostics.
- https://www.python-httpx.org/advanced/timeouts/ - timeout model and exception mapping.
- https://docs.pydantic.dev/usage/settings/ - settings-from-env pattern and typed config model.
- https://platformdirs.readthedocs.io/en/latest/api.html - standard user config/cache directory API.
- https://docs.agno.com/features/telemetry - disabling telemetry with `AGNO_TELEMETRY=false`.
- https://help.getzep.com/graphiti/getting-started/quick-start - Graphiti defaults and `GRAPHITI_TELEMETRY_ENABLED=false`.

### Secondary (MEDIUM confidence)
- https://raw.githubusercontent.com/tobi/qmd/main/README.md - QMD model cache/download UX patterns and local-tool behavior for inspiration alignment.
- /Users/joao.marinho/Projects/aurora/.planning/research/STACK.md - project-level prior stack pinning context.
- /Users/joao.marinho/Projects/aurora/.planning/research/ARCHITECTURE.md - project-level architecture baseline.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - grounded in official tool docs for uv/pipx/packaging/llama.cpp/HF/httpx.
- Architecture patterns: HIGH - directly mapped to phase constraints and official API capabilities.
- Pitfalls: MEDIUM-HIGH - partially inferred from integration behavior, but aligned with documented endpoint/error semantics and project context.

**Research date:** 2026-03-01  
**Valid until:** 2026-03-31
