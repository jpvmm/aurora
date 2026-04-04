# Phase 4: Long-Term Memory Fusion - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning

<domain>
## Phase Boundary

User interactions persist as long-term memory across CLI sessions. Assistant retrieves relevant memories alongside KB evidence and combines them in unified responses. User can manage memories via CLI commands. Memory governance (pinning, decay rules, forgetting) is v2 scope.

</domain>

<decisions>
## Implementation Decisions

### Two-Tier Memory Architecture
- **D-01:** Two-tier approach inspired by Claude Code's CLAUDE.md pattern:
  - **Tier 1 (Preferences):** Free-form markdown file always injected into system prompt. User-editable. Contains rules, conventions, style preferences.
  - **Tier 2 (Episodic):** Session summaries saved as individual markdown files, indexed by QMD in a separate `aurora-memory` collection. Searched at query time alongside KB.
- **D-02:** No Graphiti/Neo4j/Docker. Memories are plain markdown files indexed by QMD. Keeps the local-first, zero-infra philosophy. Graphiti can be a future migration if needed.

### Memory Storage
- **D-03:** Episodic memory files stored in `~/Library/Application Support/aurora/memory/`. Managed by Aurora, not visible in the Obsidian vault.
- **D-04:** Preferences file at `~/Library/Application Support/aurora/preferences.md`. Free-form markdown, no schema. Raw text injected into every system prompt.
- **D-05:** Episodic memories stored as separate markdown files (one per session). QMD indexes them as collection `aurora-memory`.

### Memory File Format
- **D-06:** Episodic files named with timestamp: `2026-04-04T19-30.md`. ISO date-time, auto-sorted chronologically, no collisions.
- **D-07:** Episodic files have YAML frontmatter: `date`, `topic`, `turn_count`, `source` (chat). Body is the LLM-generated summary.

### Memory Capture Strategy
- **D-08:** Automatic memory creation after every `aurora chat` session. When user exits, Aurora summarizes the session using the LLM and saves as a markdown file.
- **D-09:** Only `aurora chat` creates memories. `aurora ask` stays stateless (fire-and-forget).
- **D-10:** LLM-generated summary of the session (not full transcript, not raw Q&A pairs). Compact, searchable, useful for future retrieval.
- **D-11:** Minimum 2 turns required to create a memory. Single-turn sessions are skipped.
- **D-12:** Summary generated as background async save on chat exit. User exits immediately without waiting.

### Memory + KB Fusion
- **D-13:** Unified answer that naturally weaves vault evidence and memories together. No separate sections. System prompt instructs model to cite both sources.
- **D-14:** Vault always wins when content contradicts an old memory. Model is instructed to prefer current vault evidence over historical memories.
- **D-15:** Always retrieve both KB and memory on every vault turn. Two parallel QMD queries (one per collection). No LLM gate for whether to search memories.
- **D-16:** Memory citations use inline format with prefix: `[memoria: titulo]`. Vault citations stay as `[notas/projeto.md]`. Visual distinction between sources.

### Memory Staleness
- **D-17:** Accumulate forever. QMD's relevance scoring naturally pushes old irrelevant memories down. No TTL, no auto-consolidation, no recency weighting. User can manually clear via CLI.

### Memory Management UX
- **D-18:** `aurora memory list` — show all episodic memories with dates and topics (from frontmatter).
- **D-19:** `aurora memory search <query>` — semantic search over memories via QMD.
- **D-20:** `aurora memory edit` — open preferences.md (Tier 1) in `$EDITOR`.
- **D-21:** `aurora memory clear` — delete all episodic memory files + remove from `aurora-memory` QMD collection. Preferences file stays. KB stays. Confirmation prompt required (MEM-04).

### Chat Exit + Summary Flow
- **D-22:** Background async save: user types 'sair' -> exit immediately -> summary generated in background.
- **D-23:** If background save fails, log warning to file silently. Optionally notify on next `aurora chat` start.

### Claude's Discretion
- Summary generation prompt design (what instructions to give the model for summarization)
- Preferences file injection strategy (how to combine with existing system prompts)
- Memory retrieval top-K and min-score thresholds for the aurora-memory collection
- Background process implementation (fork, thread, subprocess)
- Exact frontmatter fields beyond date/topic/turn_count/source

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing Chat/Memory Code
- `src/aurora/chat/history.py` — Existing JSONL chat history (ChatHistory class). Phase 4 extends this with summary generation on exit.
- `src/aurora/chat/session.py` — ChatSession with intent routing. Phase 4 adds memory retrieval to vault turns and summary on exit.
- `src/aurora/cli/chat.py` — Chat CLI command. Phase 4 adds background save on exit.

### Retrieval Pipeline
- `src/aurora/retrieval/service.py` — RetrievalService. Phase 4 extends to query both KB and memory collections.
- `src/aurora/retrieval/qmd_search.py` — QMDSearchBackend. May need collection parameter support.
- `src/aurora/retrieval/contracts.py` — RetrievalResult, QMDSearchHit. May need memory source distinction.

### LLM Layer
- `src/aurora/llm/prompts.py` — System prompts. Phase 4 adds preferences injection and memory citation instructions.
- `src/aurora/llm/service.py` — LLMService. Phase 4 adds summarize_session method.

### Runtime
- `src/aurora/runtime/settings.py` — RuntimeSettings. May need memory-related settings.
- `src/aurora/runtime/paths.py` — Path helpers. Phase 4 adds memory dir and preferences path.
- `src/aurora/cli/app.py` — Root CLI. Phase 4 adds `memory` command group.

### Requirements
- `.planning/REQUIREMENTS.md` — MEM-01 through MEM-04

### Research Reference
- Claude Code CLAUDE.md pattern: flat markdown file, always loaded, user-editable, transparent
- Mem0 patterns: automatic extraction, semantic search, entity-based retrieval

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ChatHistory` (`src/aurora/chat/history.py`): JSONL persistence with append_turn, load, get_recent, clear. The raw chat history that will be summarized into episodic memory on exit.
- `QMDSearchBackend` (`src/aurora/retrieval/qmd_search.py`): Shell-out to QMD CLI. Already supports `--index` flag. Needs `-c collection` flag for multi-collection queries.
- `RetrievalService` (`src/aurora/retrieval/service.py`): search -> fetch -> dedup -> truncate. Can be extended to merge results from KB and memory collections.
- `LLMService` (`src/aurora/llm/service.py`): ask_grounded, chat_turn, classify_intent. Needs new summarize_session method for memory creation.
- `get_config_dir()` (`src/aurora/runtime/paths.py`): Returns platform-specific config directory. Memory dir will be a sibling of the existing KB corpus dir.

### Established Patterns
- QMD CLI shell-out via subprocess (QMDCliBackend pattern)
- Typer CLI command groups (kb_app, model_app, ask_app, chat_app pattern)
- Settings with Pydantic validators (RuntimeSettings)
- Frozen dataclasses for contracts (QMDSearchHit, RetrievalResult)

### Integration Points
- `aurora chat` exit flow — trigger background summary generation
- `RetrievalService.retrieve()` — extend to query both collections and merge results
- System prompt assembly — inject preferences.md content before grounding instructions
- `app.py` — register new `memory_app` command group

</code_context>

<specifics>
## Specific Ideas

- Inspired by Claude Code's CLAUDE.md: preferences file is free-form markdown, injected raw into system prompt. User treats it like a configuration file they write naturally.
- Memory citations use `[memoria: titulo]` prefix to visually distinguish from vault citations `[notas/path.md]`.
- Background async save on chat exit avoids blocking the user. If summary fails, it's silently logged — not worth interrupting the exit flow for.
- QMD's built-in relevance scoring handles staleness naturally. No need for custom recency decay logic.

</specifics>

<deferred>
## Deferred Ideas

- Graphiti graph memory backend — future migration path if relationship modeling is needed
- Memory pinning (MEM-G01) — v2 scope per REQUIREMENTS.md
- Explicit memory forgetting (MEM-G02) — v2 scope
- Memory decay rules (MEM-G03) — v2 scope
- Recency-weighted scoring — not needed with QMD relevance scoring
- TTL/auto-consolidation — deferred, accumulate forever for now
- `aurora ask` reading memories — keep ask stateless for now, revisit if users want it

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-long-term-memory-fusion*
*Context gathered: 2026-04-04*
