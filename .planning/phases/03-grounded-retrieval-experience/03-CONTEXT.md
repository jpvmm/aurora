# Phase 3: Grounded Retrieval Experience - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

User can ask questions via CLI and receive trustworthy, evidence-grounded responses from vault content. Covers single-shot Q&A (`aurora ask`) and multi-turn chat (`aurora chat`) with intent-based routing. Long-term memory persistence across sessions is Phase 4 scope.

</domain>

<decisions>
## Implementation Decisions

### Retrieval Strategy
- **D-01:** Use QMD's built-in `qmd query` command for hybrid search (BM25 + vector + LLM rerank). No custom RAG pipeline needed — QMD already satisfies RET-03 natively.
- **D-02:** Fixed top-K retrieval (5-10 results). Predictable token usage per query.
- **D-03:** Send full notes to the model (not just chunks). Use `qmd get` to fetch complete documents after search identifies relevant ones.
- **D-04:** Truncate to fit when retrieved notes exceed model context window. Prioritize top-ranked notes, drop the rest.
- **D-05:** Pass user query directly to QMD without preprocessing. QMD has its own query expansion built in.
- **D-06:** Hardcoded system prompt that enforces grounding rules, citation format, and pt-BR default. Not user-editable.
- **D-07:** Log retrieved note paths and relevance scores for debugging/transparency. Respects PRIV-03 by not logging content.

### Citation Format
- **D-08:** Inline references in the answer text, format: `[notas/projeto.md]`. Path only, no section or line numbers.
- **D-09:** Deduplicate citations — one reference per note even if multiple chunks from the same note were used.

### Conversation UX
- **D-10:** Two commands: `aurora ask "question"` for single-shot grounded Q&A, and `aurora chat` for interactive multi-turn sessions.
- **D-11:** Stream tokens to terminal as they're generated. llama.cpp supports SSE streaming.
- **D-12:** `aurora chat` persists conversation history to disk so sessions can be resumed later.
- **D-13:** `aurora chat` re-retrieves from KB on each turn (fresh QMD search per question).
- **D-14:** `aurora chat` uses LLM-based intent routing — classifies each message as "vault question" (triggers KB retrieval) or "general chat" (responds directly without retrieval).
- **D-15:** `aurora ask` always retrieves from KB — no intent routing, always grounded.

### Insufficient Evidence
- **D-16:** QMD min-score threshold gates insufficient evidence. If no results pass the threshold, Aurora refuses to answer.
- **D-17:** Refusal message is clear and actionable in pt-BR: "Nao encontrei evidencia suficiente no vault para responder. Tente reformular ou verifique se o topico esta indexado."
- **D-18:** In `aurora chat` general chat mode (no KB retrieval), the model chats freely without grounding constraints.

### Claude's Discretion
- Exact system prompt wording and grounding instructions
- Top-K default value (within 5-10 range)
- Min-score threshold value for insufficient evidence gate
- Chat history persistence format and storage location
- Intent classification prompt design
- Streaming implementation details

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### QMD Integration
- QMD CLI docs: `qmd query --json`, `qmd get`, `qmd multi-get` — search and retrieval commands
- `src/aurora/kb/qmd_backend.py` — existing QMD CLI transport, established shell-out patterns
- `src/aurora/kb/qmd_adapter.py` — adapter boundary between Aurora and QMD

### Runtime
- `src/aurora/runtime/llama_client.py` — existing llama.cpp client with health probes and model validation
- `src/aurora/runtime/settings.py` — RuntimeSettings with endpoint/model config
- `src/aurora/runtime/server_lifecycle.py` — server start/stop/status management

### CLI Patterns
- `src/aurora/cli/app.py` — root CLI app, typer registration pattern
- `src/aurora/cli/model.py` — established CLI command patterns (--json flag, error handling, lifecycle integration)
- `src/aurora/cli/kb.py` — KB command patterns

### Requirements
- `.planning/REQUIREMENTS.md` — RET-01 through RET-04 and CLI-03

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `QMDCliBackend` (`src/aurora/kb/qmd_backend.py`): Shell-out pattern for QMD CLI commands. Can be extended or mirrored for `qmd query`/`qmd get` search commands.
- `LlamaRuntimeClient` (`src/aurora/runtime/llama_client.py`): HTTP client for llama.cpp `/health` and `/v1/models`. Needs extension for `/v1/chat/completions` with streaming.
- `RuntimeSettings` (`src/aurora/runtime/settings.py`): Already stores endpoint_url and model_id. Chat history path and retrieval settings can be added here.
- `ServerLifecycleService`: Auto-start server before queries if not running.

### Established Patterns
- CLI commands use typer with `--json` flag for structured output
- Backend operations go through adapter/protocol boundaries (QMDBackend protocol)
- Error handling uses diagnostic dataclasses with category + recovery_hint
- Privacy policy validates local-only endpoints

### Integration Points
- New `aurora ask` and `aurora chat` commands register in `src/aurora/cli/app.py`
- Retrieval service calls QMD CLI via subprocess (same pattern as `QMDCliBackend`)
- LLM inference calls llama.cpp `/v1/chat/completions` endpoint
- Server lifecycle auto-start before first query

</code_context>

<specifics>
## Specific Ideas

- Intent routing in `aurora chat`: the agent structure must decide if the user is trying to get information about a note or just chatting with the model. LLM classifies intent before deciding retrieval path.
- QMD `--json` output provides docid, file, title, score, snippet, line — use score for insufficient evidence gating and file path for citations.
- `qmd query` already does hybrid search (BM25 + vector + LLM rerank) — no need to build custom retrieval pipeline.

</specifics>

<deferred>
## Deferred Ideas

- User-customizable system prompt — keep hardcoded for now, revisit in future phase
- LLM-rewritten queries for better search recall — QMD's built-in query expansion handles this
- Partial answers with caveats when evidence is weak — strict refusal for now per RET-04

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-grounded-retrieval-experience*
*Context gathered: 2026-04-03*
