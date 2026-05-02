# Phase 7: Iterative Retrieval Loop - Context

**Gathered:** 2026-05-02
**Status:** Ready for planning
**Source:** Conversation discussion in lieu of /gsd-discuss-phase (decisions captured live)

<domain>
## Phase Boundary

Wrap the existing single-shot retrieval pipeline (`RetrievalService.retrieve`, `retrieve_with_memory`, `retrieve_memory_first`) in an iterative loop that:
1. Runs the first retrieval as today.
2. Evaluates whether the returned evidence is sufficient to answer the user's question.
3. If thin, reformulates the query and retrieves once more (bounded).
4. Stops when sufficient OR when the iteration cap is reached, then hands off to the existing answer path (which preserves the RET-04 "insufficient evidence" contract).

The phase changes the *retrieval orchestration*. It does not change:
- Backend search APIs (`QMDSearchBackend.search`, `keyword_search`).
- The grounded answer prompts or citation contract.
- Memory persistence, intent classification, or carry-forward.
- The user-facing answer format (only the optional `--trace` flag adds new output).

</domain>

<decisions>
## Implementation Decisions

### Sufficiency signal (the "is evidence thin?" check)
- **D-01:** Sufficiency is computed from a **deterministic signal first**, with an optional LLM judge gated behind a flag. Pure LLM judgment is too slow and too vibes-driven for the default path.
- **D-02:** Default deterministic signal combines three indicators (any one trips "thin"):
  - Top hit score below a configurable threshold (`retrieval_min_top_score`, default ~0.35 — tune during planning by sampling current logs).
  - Fewer than `retrieval_min_hits` results above the floor (default 2).
  - Total assembled context character count below `retrieval_min_context_chars` (default 800) — i.e. matches existed but were tiny snippets.
- **D-03:** LLM sufficiency judge is opt-in via `iterative_retrieval_judge: true` in settings. When enabled, after the deterministic check passes, a tiny structured-output call ("yes/no, is this enough to answer X?") gates the loop. Off by default to keep latency predictable.
- **D-04:** Sufficiency check runs only on **vault** and **memory** intents, never on **chat** intent. Chat turns don't retrieve.

### Query reformulation
- **D-05:** Reformulation is an LLM call. Heuristic rewrites (synonym expansion, etc.) were considered and rejected as too brittle for free-form Portuguese queries.
- **D-06:** Reformulation prompt receives: original query, prior turn carry-forward context (if any), the *paths and titles* (NOT full snippets) of the notes already retrieved, and the sufficiency reason ("only 1 hit", "top score 0.18", etc.). It returns a single new query string in pt-BR.
- **D-07:** Reformulation runs the same retrieval strategy as the first attempt (vault, memory-first, or with-memory). Don't switch strategies mid-loop — too many moving parts to debug.
- **D-08:** Reformulated query is logged to the chat history as an internal note, NOT shown in the assistant message. `--trace` is the way to see it.

### Loop bounding
- **D-09:** Hard cap of **2 retrievals total** by default (1 reformulation). Configurable via `retrieval_max_attempts` (range 1–4). One reformulation is enough to capture the most common rescue case (vague first query → refined second) without ballooning latency.
- **D-10:** If the second retrieval is still insufficient, the loop exits and the existing insufficient-evidence path runs (preserves RET-04). The user is not told the system tried twice — that detail is in `--trace`.
- **D-11:** Dedup across attempts: results from earlier attempts are merged with the new attempt before the next sufficiency check, so a follow-up retrieval that adds even one new strong hit can flip "thin" → "sufficient".
- **D-12:** Total per-question time budget: soft target ≤ 1× the original ask latency on the happy path (first attempt sufficient), ≤ 2.5× on the worst case (both attempts run + LLM reformulate). Plan must measure this.

### Observability — `--trace`
- **D-13:** New `--trace` flag on `aurora ask` and `aurora chat`. When set, after the answer the CLI prints a structured trace block: each attempt's query, hit count, top score, sufficiency verdict, and reformulation reason if any.
- **D-14:** Trace is **stderr** (or a separate "diagnostic" channel for chat) so `--json` output stays parseable.
- **D-15:** Trace must be privacy-safe per PRIV-03 — log note paths, scores, hit counts, and the reformulated query, but NOT note content snippets. Snippets only appear in the answer body where the user expects them.

### Configuration surface
- **D-16:** New settings (all in `RuntimeSettings`):
  - `iterative_retrieval_enabled: bool = True` — master switch (default on).
  - `retrieval_max_attempts: int = 2` — hard cap (range 1–4).
  - `retrieval_min_top_score: float = 0.35` — sufficiency threshold.
  - `retrieval_min_hits: int = 2` — minimum hit count above threshold.
  - `retrieval_min_context_chars: int = 800` — minimum assembled context size.
  - `iterative_retrieval_judge: bool = False` — opt-in LLM sufficiency judge.
- **D-17:** All settings exposed via `aurora config` (consistent with Phase 5 consolidation). Defaults chosen so the loop is on for everyone but tunable.

### Disable path
- **D-18:** Setting `iterative_retrieval_enabled = false` falls back to today's single-shot behavior exactly. No code path divergence beyond the orchestrator branch.

### Claude's Discretion
- Exact default values for `retrieval_min_top_score` and `retrieval_min_context_chars` — planner should sample existing failure cases (UAT logs, prior fix-phase artifacts) before locking these.
- Whether the iterative orchestrator lives as a new `IterativeRetrieval` class or as a wrapper method on `RetrievalService`.
- Format of the `--trace` output (TUI-friendly table vs structured JSON when paired with `--json`).
- Whether reformulation uses a dedicated small prompt template or extends an existing one.
- Test-fixture strategy — likely needs a deterministic fake LLM that returns scripted reformulations + a fake `QMDSearchBackend` that can return tiered "thin then thick" result sets.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Retrieval pipeline (the surface this phase wraps)
- `src/aurora/retrieval/service.py` — `RetrievalService.retrieve`, `retrieve_with_memory`, `retrieve_memory_first`, `_keyword_fallback`, `_search_with_strategy`, `_dedup_hits`, `_assemble_context`. The iterative loop wraps these — it does not modify their signatures.
- `src/aurora/retrieval/qmd_search.py` — `QMDSearchBackend.search`, `keyword_search`, `fetch`. No backend changes expected.
- `src/aurora/retrieval/contracts.py` — `RetrievalResult`, `RetrievedNote`, `QMDSearchHit`, `QMDSearchDiagnostic`. May need a new `RetrievalAttempt` or `RetrievalTrace` dataclass for the trace surface.

### Chat / ask wiring (call sites that adopt the loop)
- `src/aurora/chat/session.py` — `ChatSession.process_turn`, `_handle_vault_turn`, `_handle_memory_turn`, `_apply_carry_forward`. The loop must compose with carry-forward (carry-forward applies BEFORE the first sufficiency check, per the 04.2-02 decision).
- `src/aurora/cli/ask.py` — single-shot ask command. Adopts `--trace`.
- `src/aurora/cli/chat.py` — interactive chat. Adopts `--trace`.

### LLM service (reformulation + optional judge)
- `src/aurora/llm/service.py` — `LLMService.classify_intent`, streaming/non-streaming entry points. The reformulation call is a non-streaming LLM call returning a short string. The optional judge is a structured y/n.
- `src/aurora/llm/prompts.py` (or wherever pt-BR prompts live) — add `REFORMULATION_PROMPT` and optional `SUFFICIENCY_JUDGE_PROMPT`.

### Settings
- `src/aurora/runtime/settings.py` — `RuntimeSettings`. Add the six new fields per D-16. Validators required per existing pattern (range checks, pt-BR error messages).

### Observability + privacy contract
- `.planning/REQUIREMENTS.md` — RET-01, RET-03, RET-04 (enhanced), PRIV-03 (trace must not leak content).
- `.planning/phases/04.2-fix-retrieval-quality-increase-top-k-add-keyword-fallback-search-carry-forward-prior-turn-context/04.2-CONTEXT.md` — established that carry-forward applies BEFORE insufficient-evidence check, retrieval_top_k=15, MAX_CONTEXT_CHARS=24000.
- `.planning/phases/05-operational-command-surface/05-CONTEXT.md` — established `--json` contract and `aurora config` namespace.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets
- `RetrievalService._dedup_hits` — already merges/dedups hits by path. Reuse for cross-attempt merging.
- `RetrievalService._assemble_context` — produces the final context string the LLM sees. Sufficiency check on `len(assembled_context)` is one line of code.
- `RetrievalService._keyword_fallback` — proves the pattern of "try one path, then enrich with another". The iterative loop is the same shape but with LLM reformulation between attempts.
- `ChatSession._apply_carry_forward` — runs BEFORE the existing single-shot retrieval per Phase 04.2. Iterative loop must apply carry-forward only on attempt 1 (otherwise it leaks across reformulations).
- `LLMService.classify_intent` — single-message LLM call returning a short structured string. Reformulation can mirror this pattern (no streaming, no history).

### Established patterns
- Frozen dataclasses with `@dataclass(frozen=True)` for all retrieval contracts.
- pt-BR error messages with actionable recovery commands for any user-facing failure.
- Settings validated at load/save boundary, not inline at use sites.
- Chat history strips internal-only metadata before passing to LLM (precedent for "log reformulation but don't expose").

### Integration points
- `RetrievalService.retrieve*` callers in `ChatSession._handle_vault_turn` and `_handle_memory_turn` are the only two places that need to adopt the loop. CLI `ask` goes through ChatSession → simpler than weaving it into ask.py directly.
- Settings validators follow the `retrieval_top_k` pattern (range with pt-BR errors). Mirror it for the six new fields.
- The trace surface is new — no precedent in the codebase. Planner will need to decide where the dataclass lives (`retrieval/contracts.py` is the obvious home).

### Failure modes to design against
- **Latency blowout** if reformulation prompt is too long or the model is slow. Plan must include a measurement task.
- **Prompt loops** where reformulation produces a near-identical query. Mitigation: pass prior queries into the reformulation prompt and instruct "produce a substantively different query".
- **Trace leakage** of note content into stderr — would violate PRIV-03. Test must assert that trace output contains no snippet text.
- **Carry-forward double-dipping** if carry-forward paths get re-counted as "new evidence" on attempt 2. The dedup pass must run before the second sufficiency check.
- **Disabled-path drift** — if the disable flag silently changes behavior over time. A regression test pins single-shot semantics.

</code_context>

<specifics>
## Specific Ideas

- The user explicitly accepted the latency tradeoff: "Cost: latency, less predictable behavior" was in the original idea framing. Planner should not over-engineer to avoid the second LLM call — that call IS the feature.
- The 04.x phases established a pattern of "deterministic signal first, LLM as the rescue path". This phase mirrors that pattern at a different layer.
- `aurora ask --trace` overlaps conceptually with the "retrieval tracing" idea I floated earlier in the conversation — the trace surface built here is the foundation that future eval-harness work would consume.

</specifics>

<deferred>
## Deferred Ideas

- **Cross-encoder reranker** — discussed but kept separate; would compose with iterative retrieval but adds another model dependency.
- **HyDE / query expansion at attempt 1** — would change the first attempt, not the iterative wrap. Worth its own phase if iterative loop alone doesn't close the quality gap.
- **Multi-step reasoning beyond retrieval** (plan → tool use → answer) — this phase is scoped strictly to retrieval orchestration, not generic agent loops.
- **Eval harness consuming `--trace`** — explicitly future. This phase ships the trace; an eval phase consumes it.
- **Adaptive thresholds** that tune `retrieval_min_top_score` per-user from observed answers — premature, wait for data.

</deferred>

---

*Phase: 07-iterative-retrieval-loop*
*Context gathered: 2026-05-02 via in-conversation discussion*
