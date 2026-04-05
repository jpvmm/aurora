# Phase 5: Operational Command Surface - Context

**Gathered:** 2026-04-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Consolidate Aurora's CLI into a clean, minimal command surface with unified status, comprehensive diagnostics, and consistent output patterns. This phase restructures existing commands — it does not add new retrieval, memory, or model capabilities.

</domain>

<decisions>
## Implementation Decisions

### Command Consolidation
- **D-01:** Reduce top-level commands to 4 core entry points: `aurora ask`, `aurora chat`, `aurora status`, `aurora doctor`.
- **D-02:** Move `kb`, `model`, `memory` subcommands under `aurora config` namespace: `aurora config kb ...`, `aurora config model ...`, `aurora config memory ...`.
- **D-03:** `setup` merges into `aurora config` (e.g., `aurora config setup` or absorbed into first-run wizard).
- **D-04:** Old top-level commands (`aurora kb`, `aurora model`, `aurora memory`) remain as aliases with pt-BR deprecation warning: "Aviso: use `aurora config kb ...`" — one release cycle, then remove.

### Unified Status Command
- **D-05:** New `aurora status` command shows full dashboard: model state (running/stopped, model name, endpoint), KB state (collection, note count, last update), memory state (memory count, last session), config summary (vault path, language).
- **D-06:** `aurora status` is report-only — does not auto-start model or trigger any side effects.
- **D-07:** `aurora status --json` supported for scripting/automation, returning structured JSON with all sections.

### Doctor Completeness
- **D-08:** `aurora doctor` must check: model/endpoint connectivity, QMD binary availability and version, KB collection health (exists, has documents, embeddings generated), memory index health (aurora-memory collection exists, has embeddings), disk space for models, Python version, required packages.
- **D-09:** Doctor output pattern: each check shows pass/fail + what failed + why + exact recovery command. E.g., "KB sem embeddings. Execute: `aurora config kb rebuild`".
- **D-10:** Doctor does not auto-fix — only reports and suggests commands.

### Output Consistency
- **D-11:** Every command that produces output supports `--json` for structured output. Universal contract for scripting.
- **D-12:** Structured error pattern across all commands: what failed + why + recovery command. Exit code 1 for user errors, exit code 2 for system errors. With `--json`, errors return `{"error": "...", "recovery": "..."}`.

### Missing Operations
- **D-13:** Move KB operations under `aurora config kb` (ingest, update, delete, rebuild, config) as part of consolidation. Same functionality, cleaner namespace.
- **D-14:** Audit and improve all command `--help` text for clarity, consistency, pt-BR, and usage examples.
- **D-15:** Add shell completions via Typer's built-in support (bash/zsh/fish).
- **D-16:** No `aurora version` command — version info included in `aurora status` output instead.

### Claude's Discretion
- Exact layout and formatting of status dashboard sections
- Ordering and grouping of doctor checks
- Deprecation warning exact wording and styling
- Shell completion installation instructions

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### CLI structure
- `src/aurora/cli/app.py` — Root Typer app with all current command registrations
- `src/aurora/cli/doctor.py` — Current doctor implementation to extend
- `src/aurora/cli/config.py` — Current config commands to absorb model/kb/memory subcommands
- `src/aurora/cli/kb.py` — KB commands to move under config namespace
- `src/aurora/cli/model.py` — Model commands to move under config namespace
- `src/aurora/cli/memory.py` — Memory commands to move under config namespace

### Patterns to follow
- `src/aurora/cli/ask.py` — Example of `--json` flag pattern and streaming output
- `src/aurora/cli/chat.py` — Example of interactive session pattern

### Requirements
- `.planning/REQUIREMENTS.md` — CLI-02 (dedicated commands) and CLI-04 (doctor diagnostics)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/aurora/cli/doctor.py` — Has model/endpoint checks, extend with QMD/KB/memory checks
- `src/aurora/cli/config.py` — Already has `config show`, natural home for consolidated subcommands
- `src/aurora/cli/model.py` — `model status` and `model health` contain reusable status-checking logic
- `src/aurora/runtime/settings.py` — Central settings with all config paths, endpoints, collection names

### Established Patterns
- Typer app with `typer.Typer()` per command group, added via `app.add_typer()`
- `--json` flag with `json.dumps(ensure_ascii=False, indent=2)` for structured output
- Status messages via `typer.echo(..., err=True)` to keep stdout clean for data
- `QMDSearchBackend` for checking collection/index state

### Integration Points
- `app.py` — Will need restructured `add_typer()` registrations for new namespace
- `aurora.memory.store` — MEMORY_COLLECTION and MEMORY_INDEX constants for doctor checks
- `aurora.kb.service` — KBService for KB health checks
- `aurora.kb.qmd_backend` — QMDBackend for collection state queries

</code_context>

<specifics>
## Specific Ideas

- User wants to reduce the number of commands to "a few that the user can use the most" — consolidation is the primary driver
- Core user flow should be: `aurora ask` / `aurora chat` for daily use, `aurora status` for quick health check, `aurora doctor` for troubleshooting
- Everything else is "configuration" and lives under `aurora config`

</specifics>

<deferred>
## Deferred Ideas

- `aurora version` as standalone command — version info will be in `aurora status` instead
- Auto-fix mode for doctor (prompting to fix issues inline) — deferred to future iteration

</deferred>

---

*Phase: 05-operational-command-surface*
*Context gathered: 2026-04-05*
