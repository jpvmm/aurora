# Phase 2: Vault Knowledge Base Lifecycle - Research

**Researched:** 2026-03-03
**Domain:** Scoped Obsidian Markdown KB lifecycle in Aurora CLI (ingest/update/delete/rebuild)
**Confidence:** MEDIUM-HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

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

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| KB-01 | User can ingest an Obsidian vault path containing `.md` files via CLI command. | Add `aurora kb ingest <vault_path>` with explicit path validation, scoped file discovery (`.md` only), templater preprocessing, and persisted KB state. |
| KB-02 | User can update index incrementally for changed notes without full reingestion. | Implement manifest-driven delta detection (`mtime + size`, optional hash verification) and process only changed/in-scope files. |
| KB-03 | User can delete notes from the knowledge base via CLI command. | Provide explicit `kb delete` semantics (remove from KB state/index without mutating vault file) plus automatic removal of missing files during `kb update`. |
| KB-04 | User can trigger full rebuild of the knowledge base via CLI command. | Add `kb rebuild` that clears KB runtime state/index artifacts and re-ingests from current scope with same preprocessing rules. |
| KB-05 | User can view ingestion progress and final stats in readable CLI logs. | Standardize staged progress counters and deterministic final summary in text and `--json` forms. |
| PRIV-02 | User can define include/exclude scopes for which vault paths are indexed. | Persist scope rules globally, evaluate rules relative to vault root, enforce `exclude` precedence, support dry-run preview, and block out-of-vault paths. |
</phase_requirements>

## Summary

Phase 2 should be planned as an Aurora-owned KB lifecycle contract with QMD as an adapter boundary, not as direct delegation of lifecycle semantics to QMD commands. Locked decisions (case-sensitive scope rules, exclude precedence, explicit dry-run, mtime+size deltas, templater cleaning, privacy-safe logs) are stricter than current off-the-shelf CLI behavior and must be enforced in Aurora runtime code first.

The highest-risk area is state authority: if Aurora does not own a canonical manifest/scope state, update/delete/rebuild behavior will drift and become non-deterministic across terminals. The plan should introduce one global KB state model (same persistence style as Phase 1 runtime state), one scanner/preprocessor pipeline, and one command service used by all `aurora kb` commands.

QMD remains a strong retrieval/index backend, but current upstream docs/source show command surface drift and collection-centric update flows; treat QMD integration as an internal adapter and protect Phase 2 contracts behind Aurora tests. This avoids lock-in to QMD CLI quirks while preserving roadmap alignment with "QMD as KB base".

**Primary recommendation:** Build a deterministic `KBService` (scan -> filter -> preprocess -> delta classify -> apply -> report) with Aurora manifest as source of truth, then sync to QMD through a thin adapter.

## Standard Stack

### Core

| Library / Tool | Version | Purpose | Why Standard |
|---|---|---|---|
| Python | 3.13+ | KB lifecycle runtime and CLI integration | Matches current Aurora baseline and existing test/runtime setup. |
| Typer | existing in repo (`>=0.16.0`) | `aurora kb` command group and `--json` parity | Already established in Aurora command patterns and tests. |
| `pathlib` + `fnmatch` (stdlib) | Python 3.13 stdlib | Relative path enforcement, scoped traversal, case-sensitive matching | Official APIs support `Path.is_relative_to`, `Path.rglob(..., recurse_symlinks=False)` and `fnmatchcase` behavior needed by locked decisions. |
| Pydantic settings model | existing (`pydantic-settings`) | Persist global KB config (vault path + scope rules) | Reuses established deterministic global config pattern from Phase 1. |
| QMD CLI (adapter) | upstream `tobi/qmd` mainline behavior verified 2026-03-03 | Underlying local index/search substrate for downstream retrieval phases | Project direction already commits to QMD as KB base; adapter boundary avoids hard coupling. |

### Supporting

| Library / Tool | Purpose | When to Use |
|---|---|---|
| `json` + dataclasses / pydantic models | Deterministic manifest and state serialization | For KB manifest, operation summaries, and machine-readable outputs. |
| `hashlib` | Optional hash verification of candidate changed files | Use only when `mtime+size` changed or when user requests strict hash verification. |
| `sqlite3` (stdlib) or JSON file state | Persist per-note fingerprints and tombstones | Use SQLite if expecting medium/large vaults; JSON acceptable only for very small initial scope. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| Aurora-owned scope/delta engine | Delegate updates fully to `qmd update` | Simpler short-term, but does not guarantee locked semantics (`mtime+size` policy, dry-run scope preview, explicit delete command semantics). |
| Case-sensitive matcher | OS-default/pathlib default matching | Cross-platform mismatch risk; locked decision requires explicit case-sensitive behavior. |
| Lightweight manifest JSON | SQLite manifest | JSON is faster to bootstrap but harder to query/update safely at scale; SQLite gives safer incremental operations and rebuild diagnostics. |

## Architecture Patterns

### Recommended Project Structure

```text
src/aurora/
|-- cli/
|   |-- app.py                 # register kb_app
|   `-- kb.py                  # aurora kb ingest|update|delete|rebuild
|-- kb/
|   |-- service.py             # orchestration entrypoint (one service)
|   |-- scope.py               # include/exclude rules + dry-run preview
|   |-- scanner.py             # discover .md files relative to vault root
|   |-- preprocess.py          # templater stripping + counters
|   |-- manifest.py            # fingerprint + indexed state persistence
|   `-- qmd_adapter.py         # optional sync boundary with QMD CLI
`-- runtime/
    `-- settings.py            # extend global config with KB settings
```

### Pattern 1: Canonical Relative-Path Pipeline
**What:** Normalize every candidate file to a vault-relative path before rule matching/index operations.
**When to use:** All commands, especially ingest/dry-run/update/delete.
**Example:**
```python
vault_root = vault_path.resolve(strict=True)
abs_path = file_path.resolve(strict=True)
if not abs_path.is_relative_to(vault_root):
    raise ScopeError("include fora do vault")
rel_path = abs_path.relative_to(vault_root).as_posix()
```
Source: Python `pathlib` docs (`Path.resolve`, `Path.is_relative_to`).

### Pattern 2: Two-Stage Delta Detection
**What:** Use manifest fingerprint tuple (`size`, `mtime_ns`) for fast change detection; compute hash only for candidates needing precision.
**When to use:** `kb update` default and strict mode.
**Example:**
```python
if (stored.size, stored.mtime_ns) != (stat.st_size, stat.st_mtime_ns):
    changed = True
    if strict_hash:
        changed = sha256(content) != stored.sha256
```

### Pattern 3: Preprocess-Then-Index with Traceability
**What:** Strip templater commands from indexing payload but preserve metadata (`cleaned_spans`, `cleaned_count`, `source_relpath`).
**When to use:** ingest, update, rebuild.
**Example:**
```python
cleaned_text, cleaned_count = strip_templater(raw_text)
record = {
  "path": rel_path,
  "cleaned_count": cleaned_count,
  "content_for_index": cleaned_text,
}
```
Source: Templater command syntax (`<% ... %>`, `<%* ... %>`) docs.

### Pattern 4: Fail-Fast Operation Envelope
**What:** Critical failures stop the operation with category + recovery command; non-critical per-file failures increment `errors` and continue when safe.
**When to use:** long-running KB commands.
**Example:**
```python
try:
    service.run_update(...)
except KBCriticalError as err:
    render_error(err.category, err.message, err.recovery_commands)
    raise typer.Exit(1)
```

### Anti-Patterns to Avoid
- Driving scope matching with absolute filesystem paths (breaks portability and PRIV-02).
- Logging raw note content on preprocessing/index errors.
- Reusing OS-default case behavior for glob/path checks.
- Coupling CLI command functions directly to subprocess/QMD calls without a service layer.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Path containment and traversal guard | Manual string prefix checks | `Path.resolve()` + `Path.is_relative_to()` | Prevents `..`/symlink/path-normalization bypasses. |
| Recursive file walking with filter edge cases | Custom `os.walk` complexity first | `Path.rglob("*.md", recurse_symlinks=False)` + explicit hidden path filtering | Built-in recursion semantics and explicit symlink control. |
| Case-sensitive glob semantics | Mixed `fnmatch`/OS defaults | `fnmatch.fnmatchcase` in rule evaluator | Guarantees locked case-sensitive behavior across platforms. |
| End-to-end index backend behavior in CLI layer | Inline subprocess logic | `qmd_adapter.py` boundary | Shields planner/implementation from upstream CLI behavior drift. |

**Key insight:** Phase 2 success depends on deterministic Aurora lifecycle contracts; external index tooling should be replaceable behind adapters.

## Common Pitfalls

### Pitfall 1: Scope Rules Escape Vault Boundary
**What goes wrong:** includes/excludes reference paths outside vault and index unintended files.
**Why it happens:** evaluating user rules before canonical path normalization.
**How to avoid:** resolve all paths first and enforce `is_relative_to(vault_root)`.
**Warning signs:** relative paths containing `..` accepted without error.

### Pitfall 2: Missed Updates on Coarse mtime Filesystems
**What goes wrong:** content changes not detected if relying only on low-resolution mtime.
**Why it happens:** rapid edits can keep same second-level timestamps.
**How to avoid:** include file size and optional hash verification path.
**Warning signs:** user edits file but `kb update` reports unchanged.

### Pitfall 3: Over-aggressive Templater Stripping
**What goes wrong:** legitimate note content removed.
**Why it happens:** broad regex without syntax-aware bounds.
**How to avoid:** start with strict templater token patterns and test corpus before widening.
**Warning signs:** cleaned output much shorter than expected for non-template notes.

### Pitfall 4: Delete Semantics Ambiguity
**What goes wrong:** `kb delete` mutates user vault files or appears to do nothing.
**Why it happens:** command contract not explicit about deleting from index vs filesystem.
**How to avoid:** lock command behavior to KB-index deletion only and report exact removed paths.
**Warning signs:** users ask whether files were physically deleted.

### Pitfall 5: Non-deterministic Progress/Stats
**What goes wrong:** counters differ between text and JSON outputs.
**Why it happens:** separate code paths for rendering and counting.
**How to avoid:** single immutable operation summary object rendered into both formats.
**Warning signs:** mismatched totals between logs and `--json` output.

## Code Examples

Verified patterns to reuse in Phase 2:

### Case-sensitive rule matching
```python
from fnmatch import fnmatchcase

def matches_glob(rel_path: str, pattern: str) -> bool:
    return fnmatchcase(rel_path, pattern)
```
Source: Python `fnmatch` docs (`fnmatchcase`).

### Safe recursive markdown discovery
```python
for path in vault_root.rglob("*.md", recurse_symlinks=False):
    rel = path.relative_to(vault_root).as_posix()
    if any(part.startswith(".") for part in rel.split("/")):
        continue
    yield rel, path
```
Source: Python `pathlib` docs (`Path.rglob`, symlink recursion behavior).

### Templater preprocessing baseline
```python
TEMPLATER_PATTERN = re.compile(r"<%[-_+*~]?([\s\S]*?)%>")
cleaned = TEMPLATER_PATTERN.sub("", markdown_text)
```
Source: Templater docs command syntax (supports `<% ... %>` and `<%* ... %>` forms).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| Full reindex for every vault change | Manifest-driven incremental update + selective rebuild | Mature local-first assistant tooling patterns (2024-2026) | Better latency and trust for frequent vault edits. |
| Index-scope implicit from one glob mask | Explicit include/exclude rule engine with preview | Needed for privacy-scoped vault assistants | Reduces accidental indexing and improves auditability. |
| Raw markdown indexing including template code | Preprocess templater constructs before indexing | Obsidian automation-heavy workflows became common | Improves retrieval quality and reduces noise. |

**Deprecated/outdated for this phase:**
- Treating "could not find capability in docs" as proof that capability does not exist.
- Making scope behavior platform-dependent (case sensitivity or symlink traversal differences).

## Open Questions

1. **QMD adapter strategy for file-level delete/update precision**
- What we know: QMD is collection-centric and indexes via collection patterns; Aurora needs explicit `kb delete` and strict scoped semantics.
- What's unclear: whether Aurora should perform fine-grained operations by adapter API/shadow corpus or trigger collection-level updates after manifest deltas.
- Recommendation: plan a short technical spike in Wave 0 to lock adapter contract before implementation tasks split.

2. **Manifest storage format (JSON vs SQLite) for v1**
- What we know: requirements demand deterministic updates, delete handling, and corruption recovery guidance.
- What's unclear: projected vault size/perf envelope for early users.
- Recommendation: default to SQLite-backed manifest now to avoid migration churn in Phase 3 retrieval.

3. **Default scope exclusion list baseline**
- What we know: hidden/system/junk defaults are required, exact list is discretionary.
- What's unclear: whether to include Obsidian config folders (for example `.obsidian`) by default in first release.
- Recommendation: exclude hidden paths by default; make `.obsidian` exclusion explicit and visible in dry-run summary.

## Sources

### Primary (HIGH confidence)
- https://docs.python.org/3/library/pathlib.html#pathlib.Path.is_relative_to - relative containment checks for vault-boundary enforcement.
- https://docs.python.org/3/library/pathlib.html#pathlib.Path.rglob - recursive globbing and `recurse_symlinks` behavior.
- https://docs.python.org/3/library/pathlib.html#pathlib.Path.glob - glob case-sensitivity controls.
- https://docs.python.org/3/library/fnmatch.html#fnmatch.fnmatchcase - explicit case-sensitive glob matching behavior.
- https://raw.githubusercontent.com/SilentVoid13/Templater/master/docs/src/commands/overview.md - templater command delimiters (`<% ... %>`, `<%* ... %>` etc.).
- https://help.obsidian.md/data-storage - vault as local files/Markdown storage model.

### Secondary (MEDIUM confidence)
- https://github.com/tobi/qmd/blob/main/README.md - QMD collection and maintenance command surface.
- https://github.com/tobi/qmd/blob/main/src/qmd.ts - current indexing/update internals (collection update flow, hidden/symlink handling in scanner, progress patterns).
- https://github.com/tobi/qmd/blob/main/src/collections.ts - collection config model (`path`, `pattern`, include defaults).
- /Users/joao.marinho/Projects/aurora/src/aurora/cli/app.py - command-group registration pattern for adding `kb` namespace.
- /Users/joao.marinho/Projects/aurora/src/aurora/runtime/settings.py - global settings persistence model to extend with KB scope config.
- /Users/joao.marinho/Projects/aurora/src/aurora/runtime/errors.py - actionable error category + recovery command UX pattern.
- /Users/joao.marinho/Projects/aurora/tests/cli/test_model_command.py - deterministic text/JSON CLI behavior and testing conventions.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM-HIGH - strong on Python/Aurora patterns; QMD CLI behavior shows some upstream surface drift and should be adapter-isolated.
- Architecture: HIGH - directly derived from locked decisions and existing Aurora runtime patterns.
- Pitfalls: MEDIUM-HIGH - grounded in official Python docs + current QMD implementation review, but adapter details need Wave 0 validation spike.

**Research date:** 2026-03-03
**Valid until:** 2026-03-17
