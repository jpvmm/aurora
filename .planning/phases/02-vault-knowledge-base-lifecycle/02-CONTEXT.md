# Phase 2: Vault Knowledge Base Lifecycle - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the local CLI lifecycle for the vault knowledge base: ingest markdown notes from an Obsidian vault, enforce include/exclude scope rules, run incremental updates, handle delete/rebuild operations, and provide readable progress/final stats.

This phase defines how the KB lifecycle works operationally. Retrieval/assistant answering stays out of scope for this phase.

</domain>

<decisions>
## Implementation Decisions

### CLI Surface
- Use `aurora kb ...` namespace for KB lifecycle commands.
- Ingestion entrypoint must require explicit vault path (`aurora kb ingest <vault_path>`).
- Default output is human-readable text, with structured output available via `--json`.
- Long-running operations should fail fast on critical errors and print explicit recovery guidance.

### Scope Rules and Privacy Boundary
- Scope rules support both path-based rules and glob patterns.
- When include/exclude conflicts occur, `exclude` wins.
- Default first-run scope is whole vault with safe default exclusions for hidden/system/junk paths.
- Scope rules are persisted in Aurora global config (same global settings model).
- Scope matching is relative to vault root, not absolute filesystem paths.
- Includes pointing outside vault are blocked with explicit error.
- Symlinks are ignored by default.
- Matching should be case-sensitive.
- If include rules match zero notes, command fails with clear guidance (not silent success).
- Provide scope preview via `--dry-run` before indexing.
- Only `.md` files are eligible for indexing in this phase.

### Markdown Pre-processing (Templater)
- Add pre-processing to ignore/remove common Templater snippets before indexing (e.g., `<% ... %>` patterns and known variants).
- Index the cleaned content while preserving origin traceability in metadata.
- Apply the same pre-processing behavior to ingest, update, and rebuild.
- Log snippet-cleaning counts per file without exposing note content.

### Incremental Update / Delete / Rebuild Semantics
- `kb update` detects changes via `mtime + size`, with hash checks on demand for precision.
- Files removed from vault should be removed from index automatically and included in final report.
- `kb update` must respect configured scope rules (no implicit full-vault override).
- If runtime/index state is too divergent/corrupted, fail with guidance and recommend explicit rebuild.

### Progress and Final Stats (KB-05)
- Live progress should show stage + counters (read/indexed/updated/removed/skipped/errors).
- Default verbosity should be progressive summary; advanced detail can be added via flags.
- Final summary must include totals for read/indexed/updated/removed/skipped/errors, duration, and effective scope.
- Error reporting must include path + error category + recovery hint, without leaking note content.

### Claude's Discretion
- Exact command/flag naming beyond locked decisions above (short flags, aliases, optional flags).
- Exact default exclusion list content (while preserving intent: hidden/system/junk by default).
- Internal metadata schema details for storing cleaned-vs-original traceability.
- Presentation format details for progress rendering (spinner/progress bar/step table), as long as required stats are present.

</decisions>

<specifics>
## Specific Ideas

- Explicit user requirement: include pre-processing to avoid indexing Templater code snippets.
- Explicit user requirement: ingest only markdown files (`.md`) in this phase.
- Explicit user intent: phase should stay CLI-friendly, scriptable, and with actionable diagnostics.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/aurora/cli/app.py`: established Typer group registration pattern (`setup`, `config`, `model`, `doctor`) suitable for adding a `kb` group.
- `src/aurora/cli/model.py`: mature command UX patterns (`--json`, pt-BR actionable messages, fail-fast command exits).
- `src/aurora/runtime/settings.py` + `src/aurora/runtime/paths.py`: global per-user settings persistence and canonical paths.
- `src/aurora/runtime/errors.py`: structured diagnostic categories + recovery command style to mirror in KB flows.

### Established Patterns
- CLI behavior is local-first, explicit, and operationally actionable in pt-BR.
- JSON output contracts are deterministic and used for automation.
- Non-interactive-safe command behavior is preferred over implicit prompts.
- Privacy defaults avoid exposing sensitive data in terminal output.

### Integration Points
- Add KB command group module under `src/aurora/cli/` and register it in `src/aurora/cli/app.py`.
- Extend global settings/config model to persist vault path and scope rules.
- Reuse existing diagnostics style from runtime/doctor for KB operation failures.
- Add CLI and runtime tests under `tests/cli/` and `tests/runtime/` following current test style.

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 02-vault-knowledge-base-lifecycle*
*Context gathered: 2026-03-03*
