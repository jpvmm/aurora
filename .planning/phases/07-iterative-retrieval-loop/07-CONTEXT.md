# Phase 7: Iterative Retrieval Loop - Context

**Gathered:** 2026-05-02
**Status:** Ready for planning
**Source:** /gsd-discuss-phase-equivalent — three rounds of interactive AskUserQuestion (loop shape, reformulation mechanics, observability/persistence/escape-hatches)

<domain>
## Phase Boundary

Wrap the existing single-shot retrieval pipeline (`RetrievalService.retrieve`, `retrieve_with_memory`, `retrieve_memory_first`) in a bounded iterative loop:

1. Run the first retrieval as today (with carry-forward applied per Phase 04.2).
2. Check whether the returned evidence is sufficient using a deterministic signal (optional LLM judge gated behind a setting).
3. If thin, reformulate the query via an LLM rewrite and run **one** more retrieval.
4. Stop. Hand off to the existing answer path (which preserves the RET-04 "insufficient evidence" contract when both attempts fail).

The phase changes the *retrieval orchestration*. It does NOT change:
- Backend search APIs (`QMDSearchBackend.search`, `keyword_search`, `fetch`).
- The grounded-answer prompts or citation contract.
- Memory persistence, intent classification, or carry-forward semantics.
- The user-facing answer format. The only new user-visible surfaces are: a brief `revisando busca…` status line while reformulation runs, and an opt-in `--trace` flag.

</domain>

<decisions>
## Implementation Decisions

All twelve below were locked through interactive discussion. Each cites the round it came from.

### Loop shape (Round 1)

- **D-01 (Sufficiency signal):** Deterministic by default. The check combines top-1 score, hit count above floor, and assembled-context character length. An optional LLM judge runs AFTER the deterministic check passes — gated behind `iterative_retrieval_judge: bool = False`. Pure-LLM-always was rejected (latency on every query); deterministic-only was rejected (misses nuanced thin cases the user may want the LLM to catch).

- **D-02 (Visibility):** When the loop fires, Aurora prints a brief `revisando busca…` (pt-BR) to stderr while the reformulation + second retrieval run. The user sees that latency comes from a second attempt, not a stuck process. This is OVERT behavior, not silent. The explicit reformulated query is NOT shown in the status line — that's `--trace` territory (D-09).

- **D-03 (Cap):** Hard cap of **one reformulation** → **maximum two retrievals per question**. NOT configurable. Rejected the configurable-range design (1–4) because: (a) one reformulation captures the most common rescue case (vague → refined), (b) every additional attempt halves the marginal value, (c) a fixed cap removes a tunable knob that doesn't change real outcomes.

- **D-04 (Scope):** Loop applies to BOTH `aurora ask` and `aurora chat`. Inside chat, applies on vault-intent and memory-intent turns (D-08), never on chat-intent turns (no retrieval to wrap).

### Reformulation (Round 2)

- **D-05 (Strategy):** LLM rewrite — a single non-streaming LLM call returning a new pt-BR query string. Rejected: HyDE (changes attempt 1 shape, not the loop), step-back (over-broadens for a vault that's mostly personal notes), heuristic-first (already covered by Phase 04.2's BM25 fallback at the backend layer).

- **D-06 (Reformulation prompt input):** The LLM sees the original query AND the sufficiency reason ("1 hit, top score 0.18", "context only 220 chars", etc.). It does NOT see note titles, paths, or content. Rationale: privacy-safe by construction (no note text near LLM call), and the sufficiency reason is enough signal for the LLM to know *which way* to push the rewrite.

- **D-07 (Carry-forward composition):** Carry-forward (Phase 04.2's `_apply_carry_forward`) applies **once, before attempt 1 only**. The reformulated attempt 2 is a fresh search of the new query — NO carry-forward re-application. This avoids double-counting carry-forward notes as "new evidence" in the second sufficiency check, which would let the loop falsely pass on cases where the new query alone is still thin.

- **D-08 (Memory-turn scope):** Loop applies to memory-intent turns as well as vault-intent turns. Memory queries ("o que pensei sobre X recentemente?") benefit from the same rescue path. Reformulation prompt is identical; the orchestrator just calls the matching `retrieve_memory_first` (memory-intent) or `retrieve_with_memory` (vault-intent) inside the loop.

### Observability, persistence, escape hatches (Round 3)

- **D-09 (Trace surface):** New `--trace` flag on `aurora ask` and `aurora chat`. When set, the CLI emits a per-attempt structured trace AFTER the answer: query, intent, hit count, top score, sufficiency verdict, reformulation reason (if attempt 2 ran). Trace channel is **stderr** for text mode and a `trace` key inside the stdout JSON envelope for `--json` mode. NO persistent log file — `--trace` is opt-in per command, no on-disk artifact.

- **D-10 (Reformulation persistence to chat history):** Reformulated queries ARE persisted to the chat history JSONL as system-role entries with the literal `[reformulation] ` prefix (open-bracket, lowercase, close-bracket, single space). They are filtered out before `ChatHistory.get_recent` returns the LLM's context window — so they are inspectable when the user exports/reads history but never pollute the LLM's prompt. Two operations are pinned by tests: (a) reformulation appears in the JSONL file after a thin→thick turn, (b) `get_recent` excludes them.

- **D-11 (Disable kill-switch):** Settings field `iterative_retrieval_enabled: bool = True` in `RuntimeSettings`, exposed via `aurora config`. Default ON. NO per-command CLI flag (kept simple). When set to False, the entire loop is bypassed and behavior matches today's single-shot retrieval byte-for-byte (or output-equivalent — pinned by a regression test).

- **D-12 (Diversity guard):** Token-Jaccard similarity between original query and reformulated query, computed locally (no extra LLM call). If similarity ≥ 0.7, exit the loop early — skip the second retrieval entirely and fall through to the same insufficient-evidence path as if the second attempt had run and failed. Rationale: prevents wasting one retrieval on a near-identical rewrite (e.g., LLM swaps "find" for "search" but keeps the rest). Exact threshold (0.7) is a starting value the planner can tune.

### Privacy floor (implied by D-09 + D-10 + project-wide PRIV-03)

- **D-13 (Privacy):** The trace surface contains paths, scores, hit counts, and queries (original + reformulated) only. NEVER note content, snippets, or any portion of `RetrievedNote.content`. This is structural — the dataclass holding trace data must not have a `snippet` / `content` / `text` field, so leaks become impossible by design rather than by discipline. Both stderr (text trace) and stdout (`--json`'s `trace` key) are tested for absence of injected secret strings.

### Claude's Discretion

The planner decides these — they were intentionally left open so the planner can sample real failure cases first:

- **Sufficiency thresholds:** numeric defaults for `retrieval_min_top_score`, `retrieval_min_hits`, `retrieval_min_context_chars`. Recommended starting values from RESEARCH (top-score ≥ 0.35, hits ≥ 2, context ≥ 800 chars) but planner should sample any available bad-query logs (UAT artifacts, prior 04.x phase notes) before locking.
- **LLM judge ambiguity policy:** when the opt-in judge returns text containing both "sim" and "não" (e.g., "sim porque nao falta nada"), what's the verdict? Recommend "negative wins on tie" (conservative — extra reformulation is cheap, missing a thin case is expensive), but the planner can argue for an alternative.
- **Exact pt-BR phrasing** of the reformulation prompt and the `revisando busca…` status line.
- **Where the orchestrator class lives:** new module `retrieval/iterative.py` is the obvious home (composition over inheritance), but planner can co-locate inside `retrieval/service.py` if the diff is cleaner.
- **Trace dataclass shape:** the planner decides exact field names and where dataclasses live (`retrieval/contracts.py` is the obvious home).
- **Test fixture strategy:** likely a deterministic fake LLM (scripted reformulation responses) and a tiered fake `QMDSearchBackend` (returns thin then thick on demand) — but the planner picks the exact shape.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Retrieval pipeline (the surface this phase wraps)
- `src/aurora/retrieval/service.py` — `RetrievalService.retrieve`, `retrieve_with_memory`, `retrieve_memory_first`, `_keyword_fallback`, `_search_with_strategy`, `_dedup_hits`, `_assemble_context`. The iterative loop wraps these — it does NOT modify their signatures.
- `src/aurora/retrieval/qmd_search.py` — `QMDSearchBackend.search`, `keyword_search`, `fetch`. No backend changes expected in this phase.
- `src/aurora/retrieval/contracts.py` — `RetrievalResult`, `RetrievedNote`, `QMDSearchHit`, `QMDSearchDiagnostic`. Add new dataclasses for trace surface (per D-13, structurally no snippet field).

### Chat / ask wiring (call sites that adopt the loop)
- `src/aurora/chat/session.py` — `ChatSession.process_turn`, `_handle_vault_turn`, `_handle_memory_turn`, `_apply_carry_forward`. The loop must compose with carry-forward per D-07.
- `src/aurora/chat/history.py` — `ChatHistory.__init__(*, path: Path | None = None)`, `append_turn`, `get_recent`. D-10 requires modifying `get_recent` to filter `[reformulation] ` system entries before max-turns slicing.
- `src/aurora/cli/ask.py` — single-shot ask command. Adopts `--trace` and `revisando busca…` status output.
- `src/aurora/cli/chat.py` — interactive chat. Adopts `--trace` and `revisando busca…` status output.

### LLM service (reformulation + optional judge)
- `src/aurora/llm/service.py` — `LLMService.classify_intent` is the pattern for non-streaming structured-output calls. Add `reformulate_query` (single new query string) and `judge_sufficiency` (yes/no) following the same shape.
- LLM prompts module (`src/aurora/llm/prompts.py` or wherever existing prompts live) — add `REFORMULATION_PROMPT` (pt-BR, see D-06) and optional `SUFFICIENCY_JUDGE_PROMPT`.

### Settings
- `src/aurora/runtime/settings.py` — add five new fields per D-01 / D-11:
  - `iterative_retrieval_enabled: bool = True` (D-11)
  - `iterative_retrieval_judge: bool = False` (D-01)
  - `retrieval_min_top_score: float` (default — planner discretion)
  - `retrieval_min_hits: int = 2`
  - `retrieval_min_context_chars: int` (default — planner discretion)
  - All with pt-BR validators, mirroring the existing `retrieval_top_k` validator pattern.

### Requirements + lineage
- `.planning/REQUIREMENTS.md` — RET-01, RET-03, RET-04 (enhanced); PRIV-03 (trace must not leak content).
- `.planning/phases/04.2-fix-retrieval-quality-increase-top-k-add-keyword-fallback-search-carry-forward-prior-turn-context/04.2-CONTEXT.md` — established that carry-forward applies BEFORE insufficient-evidence check, retrieval_top_k=15, MAX_CONTEXT_CHARS=24000. Phase 7 builds on this.
- `.planning/phases/05-operational-command-surface/05-CONTEXT.md` — established `--json` contract and `aurora config` namespace. Phase 7's settings live under `aurora config`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets
- `RetrievalService._dedup_hits` — already merges/dedups hits by path. Reuse for cross-attempt merging.
- `RetrievalService._assemble_context` — produces the final context string. The "context length" sufficiency signal (D-01) is `len(assembled_context)`.
- `RetrievalService._keyword_fallback` — proves the pattern of "try one path, then enrich with another". The iterative loop is the same shape but with LLM reformulation between attempts.
- `ChatSession._apply_carry_forward` — runs BEFORE single-shot retrieval per Phase 04.2. The orchestrator must apply this once before attempt 1 only (D-07).
- `LLMService.classify_intent` — single-message non-streaming LLM call returning a short structured string. Reformulation and judge follow this pattern.

### Established patterns
- Frozen dataclasses with `@dataclass(frozen=True)` for all retrieval contracts.
- pt-BR error messages with actionable recovery commands for any user-facing failure.
- Settings validated at load/save boundary, not inline at use sites.
- Chat history strips internal-only metadata before passing to LLM (precedent for D-10's [reformulation] filter).

### Integration points
- Two ChatSession adoption sites: `_handle_vault_turn` and `_handle_memory_turn`. `_handle_chat_turn` does NOT adopt (chat-intent never retrieves).
- `aurora ask` is single-shot vault-with-memory retrieval — adopts the loop directly.
- Settings validators follow the `retrieval_top_k` pattern (range with pt-BR errors).
- Status line output goes to stderr — same channel as existing pt-BR diagnostic messages (e.g., progress logs, error recovery hints).

### Failure modes to design against
- **Carry-forward double-dipping** if carry-forward paths get re-counted as "new evidence" on attempt 2 (D-07 prevents this).
- **Insufficient_evidence preservation** when both attempts return empty: the cross-attempt merge MUST keep `insufficient_evidence=True` so ChatSession routes to the existing INSUFFICIENT_EVIDENCE_MSG path (RET-04 preservation, success criterion 5).
- **Trace leakage** of note content into stderr or `--json` envelope — would violate PRIV-03 and D-13. Test must inject a known secret string into a `RetrievedNote` and assert absence in both output channels.
- **Disabled-path drift** — if the disable flag silently changes behavior over time. A regression test pins single-shot semantics when `iterative_retrieval_enabled=False` (D-11).
- **Near-identical reformulation** wasting a retrieval on essentially the same query. Token Jaccard ≥ 0.7 guard (D-12) catches this cheaply.
- **Latency surprises** if the reformulation prompt grows over time. The prompt seeing only the original query + sufficiency reason (D-06) keeps it bounded.

</code_context>

<specifics>
## Specific Ideas

- The user explicitly accepted the latency tradeoff in the original menu framing: extra LLM call per thin query is the COST of the feature, not a bug to engineer around.
- The 04.x phases established a "deterministic signal first, LLM as the rescue path" pattern. Phase 7 mirrors it at the orchestrator layer (deterministic sufficiency, LLM reformulation).
- `revisando busca…` is the user's first signal that Aurora is "thinking harder" — this is the principled UX choice the user prefers over silent retries (Round 1, D-02).
- The `--trace` surface built here is the foundation a future eval-harness phase would consume (intentional — keep trace dataclass shape stable).

</specifics>

<deferred>
## Deferred Ideas

- **Cross-encoder reranker** — discussed in pre-discuss menu, deferred. Composes with iterative retrieval but adds another model dependency.
- **HyDE / query expansion at attempt 1** — would change the first-attempt shape, not the iterative wrap. Worth its own phase if iterative loop alone doesn't close the quality gap.
- **Multi-step reasoning beyond retrieval** (plan → tool use → answer) — Phase 7 is scoped strictly to retrieval orchestration, not generic agent loops.
- **Eval harness consuming `--trace`** — explicit follow-up phase. Phase 7 ships the trace; an eval phase consumes it.
- **Adaptive thresholds** (auto-tune `retrieval_min_top_score` per-user from observed answers) — premature. Wait for data from the trace surface before considering this.
- **Persistent trace log file** (`~/.aurora/traces.jsonl`) — explicitly rejected in Round 3. `--trace` is opt-in per command.
- **Per-command `--no-iterative` flag** — explicitly rejected in Round 3. Settings-only kill-switch, no CLI flag.
- **Configurable cap > 1 reformulation** — explicitly rejected in Round 1. Fixed at 1, reduces tunables.

</deferred>

---

*Phase: 07-iterative-retrieval-loop*
*Context gathered: 2026-05-02 via three-round discuss-equivalent (loop shape → reformulation mechanics → observability)*
