# Phase 7: Iterative Retrieval Loop — Research

**Researched:** 2026-05-02
**Domain:** Iterative / agentic retrieval orchestration over a hybrid (BM25 + vector) backend, local llama.cpp 4–8B model, pt-BR queries
**Confidence:** HIGH on prior art and llama.cpp grammar mechanics; MEDIUM on threshold defaults (need on-device tuning); HIGH on integration shape (codebase patterns are clear)

## Summary

Phase 7 wraps Aurora's existing single-shot retrieval (`RetrievalService.retrieve*`) in a bounded loop that detects "evidence is thin" before answering and reformulates the query for a second attempt. The literature converges on a clear pattern that matches Aurora's locked decisions almost exactly: **deterministic signal first (CRAG-style retrieval evaluator), reformulate only when thin (FLARE/CRAG-style), bound iterations hard (DSPy-style assertions), preserve the original answer contract on final failure (CRAG "incorrect" branch → existing RET-04 path)**.

The two non-obvious findings the planner needs to internalize:

1. **Hybrid scores are not directly comparable across QMD modes.** `qmd query` (hybrid+rerank) and `qmd search` (BM25) produce scores on different scales — `_keyword_fallback` already uses `min_score=0.10` for keyword vs the default `retrieval_min_score=0.30` for hybrid. The sufficiency check must look at scores **per source mode** or accept that the threshold is calibrated against hybrid only and treat keyword hits as a separate "presence" signal (count contributes to `min_hits`, score does not contribute to top-score check).
2. **Reformulation prompts on small local models drift toward synonym substitution.** The literature (DSPy Assertions, FLARE) explicitly addresses this with two mitigations: (a) inject prior queries into the prompt with an explicit "produce a substantively different query" instruction, and (b) reject reformulations whose token overlap with the prior query exceeds a threshold (Jaccard on tokenized query).

**Primary recommendation:** Build `IterativeRetrieval` as a thin orchestrator class composing `RetrievalService` (no inheritance, no method-on-RetrievalService — keeps RetrievalService single-responsibility and the loop trivially testable). Default sufficiency = the three deterministic checks already in CONTEXT.md (D-02). Default reformulation = single-shot LLM call mirroring `LLMService.classify_intent` shape (sync, no streaming, short prompt). Optional sufficiency judge uses llama.cpp GBNF grammar for a `yes|no` token to keep judging deterministic and cheap. Trace dataclass lives in `retrieval/contracts.py` per the established convention.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| First retrieval attempt | `RetrievalService` (existing) | — | No change to retrieval semantics |
| Sufficiency evaluation (deterministic) | `IterativeRetrieval` orchestrator | — | Pure function over `RetrievalResult`; no LLM, no I/O |
| Sufficiency evaluation (LLM judge, opt-in) | `LLMService` (new method) | `IterativeRetrieval` consumes | Mirrors `classify_intent` pattern: sync call, structured short output |
| Query reformulation | `LLMService` (new method) | `IterativeRetrieval` consumes | LLM-bound; same pattern as `classify_intent` |
| Cross-attempt dedup + merge | `RetrievalService._dedup_hits` (existing) | `IterativeRetrieval` calls into it | D-11 explicitly reuses `_dedup_hits` |
| Carry-forward composition | `ChatSession._apply_carry_forward` (existing) | `IterativeRetrieval` (read-only awareness) | Carry-forward applies on attempt 1 only — see D-09 of 04.2 + Pitfall in this phase's CONTEXT |
| Trace emission | `IterativeRetrieval` builds `RetrievalTrace` | CLI renders it (stderr) | Privacy-safe: no content in trace |
| Trace rendering (`--trace`) | `cli/ask.py`, `cli/chat.py` | `RetrievalTrace.to_text()` / `.to_json()` | UI concern lives in CLI; orchestrator just emits the dataclass |
| Disable path | `IterativeRetrieval.__init__` reads `iterative_retrieval_enabled` | `ChatSession` calls orchestrator unconditionally | Single branch — orchestrator returns first attempt unchanged when disabled |

**Planner takeaway:** New code is concentrated in one new module (`retrieval/iterative.py`), one new dataclass family in `retrieval/contracts.py`, two new methods on `LLMService`, two new prompt templates, and surgical edits to two `ChatSession` methods + two CLI commands. RetrievalService stays untouched.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Sufficiency signal (D-01 to D-04):**
- D-01: Sufficiency = deterministic signal first; LLM judge is opt-in.
- D-02: Default deterministic signal = OR over three checks: top-1 score below `retrieval_min_top_score` (~0.35), hits-above-floor below `retrieval_min_hits` (default 2), assembled context length below `retrieval_min_context_chars` (default 800).
- D-03: LLM judge gated by `iterative_retrieval_judge` (default false).
- D-04: Sufficiency runs only on **vault** and **memory** intents, never on **chat**.

**Query reformulation (D-05 to D-08):**
- D-05: Reformulation is an LLM call (no heuristic synonym expansion).
- D-06: Reformulation prompt receives: original query, carry-forward context (if any), paths+titles of already-retrieved notes (NO snippets), sufficiency reason. Returns single new pt-BR query string.
- D-07: Same retrieval strategy across attempts (vault / memory-first / with-memory). No mid-loop strategy switch.
- D-08: Reformulated query logged as internal note in chat history; not shown in assistant message; surfaced via `--trace`.

**Loop bounding (D-09 to D-12):**
- D-09: Hard cap = 2 retrievals (1 reformulation). Configurable via `retrieval_max_attempts` (range 1–4).
- D-10: If second retrieval still insufficient, existing RET-04 path runs unchanged.
- D-11: Cross-attempt merge + dedup before each subsequent sufficiency check.
- D-12: Latency target: ≤1× original on happy path, ≤2.5× worst case. Plan must measure.

**Observability (D-13 to D-15):**
- D-13: `--trace` flag on `aurora ask` and `aurora chat`.
- D-14: Trace goes to stderr (or separate diagnostic channel) so `--json` stdout stays parseable.
- D-15: Trace must be PRIV-03-safe: paths/scores/counts/queries OK, snippets NEVER.

**Configuration (D-16 to D-17):** Six new `RuntimeSettings` fields, all exposed via `aurora config`.

**Disable path (D-18):** `iterative_retrieval_enabled = false` falls back to today's behavior with no other code-path divergence.

### Claude's Discretion

- Exact defaults for `retrieval_min_top_score` (~0.35) and `retrieval_min_context_chars` (~800) — sample failure cases before locking.
- Whether iterative orchestrator is a new `IterativeRetrieval` class or a method on `RetrievalService`.
- Trace output format (TUI table vs JSON when paired with `--json`).
- Whether reformulation uses dedicated prompt or extends an existing one.
- Test fixture strategy.

### Deferred Ideas (OUT OF SCOPE)

- Cross-encoder reranker
- HyDE / query expansion at attempt 1
- Multi-step reasoning beyond retrieval (plan→tool→answer)
- Eval harness consuming `--trace`
- Adaptive thresholds tuned per-user from observed answers

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RET-01 | User can ask questions and receive grounded answers | Loop preserves the path; second attempt enriches evidence pool |
| RET-03 | Hybrid retrieval used | Loop wraps existing hybrid pipeline; does not change retrieval mode |
| RET-04 | Insufficient-evidence response when vault context not enough | Loop exits to existing INSUFFICIENT_EVIDENCE_MSG path on final failure (D-10) |
| PRIV-03 | Logs do not leak note content | Trace dataclass design excludes snippets by construction (see Trace section) |

## Project Constraints (from CLAUDE.md)

No `CLAUDE.md` exists at project root (verified: `Read` returned File does not exist). Project conventions inferred from existing code:

- pt-BR error/status messages with actionable recovery hints.
- Frozen dataclasses (`@dataclass(frozen=True)`) for all retrieval contracts.
- Settings validators raise `ValueError` with pt-BR message; checked at load/save boundary.
- Tests use `MagicMock` for service injection; constructor takes optional service params for substitution.
- Sync, no-streaming LLM calls go through `chat_completion_sync`; streaming through `stream_chat_completions`.
- `commit_docs: true` in `.planning/config.json` — research artifact gets committed.

## Standard Stack

### Core (already in the codebase, no new deps)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic-settings | (existing) | `RuntimeSettings` field + validator | Established settings pattern |
| `subprocess` (stdlib) | — | Shell out to `qmd` | Existing transport in `QMDSearchBackend` |
| `urllib.request` (stdlib) | — | llama.cpp HTTP calls | Existing in `streaming.py` |
| `dataclasses` (stdlib) | — | Frozen dataclasses for contracts | Established convention |

### Optional (only if D-03 LLM judge is enabled and we want hard guarantees)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| llama.cpp GBNF grammar (server-side) | — | Constrain judge output to `yes|no` | Only if LLM judge enabled; passed via `grammar` field in `/v1/chat/completions` request body [VERIFIED: llama.cpp server README] |

**llama.cpp grammar payload shape** (verified against current llama.cpp server docs):

```json
{
  "model": "...",
  "messages": [...],
  "stream": false,
  "grammar": "root ::= \"yes\" | \"no\""
}
```

The current `chat_completion_sync` in `llm/streaming.py` does not pass `grammar`. Adding it requires extending the JSON body — small, isolated change. `[CITED: github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md]`

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom orchestrator | DSPy `dspy.Suggest` + `dspy.Module` | DSPy is a heavy dep (transitive: torch, etc.) for one phase. Aurora's local-only constraint and stdlib-leaning style argue against it. Patterns are reusable; the framework is not. |
| Custom orchestrator | LangGraph state machine | Same dep weight problem. CRAG reference implementations use LangGraph for the demo, but the actual algorithm is ~50 lines of Python. |
| GBNF grammar for judge | JSON Schema mode (llama.cpp `json_schema` field) | JSON schema is heavier-weight for a single yes/no token. GBNF `root ::= "yes" \| "no"` is one line and forces a single token. |
| GBNF grammar for judge | Plain text + parse | Works fine for a "starts with 'sim' or 'não'" check; small models occasionally emit preambles ("Análise: a resposta é sim..."). Grammar guarantees no preamble. Risk-vs-cost: the parsing approach is fine for v1 since the judge is opt-in; defer grammar to follow-up if needed. |

**No new dependencies required.** Confirmed by reading `pyproject.toml`-adjacent imports — every needed primitive exists.

**Planner takeaway:** Zero new deps. Optional GBNF grammar support is a single JSON-body field addition to `chat_completion_sync` and only used when the opt-in judge is enabled.

## Architecture Patterns

### System Architecture Diagram

```
                        ┌──────────────────────────────────┐
                        │ ChatSession.process_turn         │
                        │  (vault or memory intent)        │
                        └──────────────┬───────────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────────┐
                        │ _apply_carry_forward (attempt 1) │
                        └──────────────┬───────────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────────┐
                        │ IterativeRetrieval.run            │
                        │ (new orchestrator)                │
                        └──────────────┬───────────────────┘
                                       │
        ┌──────────────────────────────┴────────────────────┐
        │ if iterative_retrieval_enabled == false:          │
        │   return RetrievalService.retrieve* (single shot) │
        └──────────────────────────────┬────────────────────┘
                                       │ enabled
                                       ▼
                ┌──────────────────────────────────────────────┐
                │ Attempt 1: RetrievalService.retrieve*(query) │
                └────────────────────┬─────────────────────────┘
                                     │
                                     ▼
                ┌──────────────────────────────────────────────┐
                │ Sufficiency check (deterministic OR LLM)     │
                │  inputs: notes, scores, context_text         │
                │  output: SufficiencyVerdict(ok, reason)      │
                └────────────────────┬─────────────────────────┘
                       sufficient │     │ thin
                                  │     │
                                  │     ▼
                                  │  ┌──────────────────────────────────┐
                                  │  │ if attempt_count >= max_attempts │
                                  │  │   → exit, return last result     │
                                  │  │     (carries insufficient flag)  │
                                  │  └────────────────┬─────────────────┘
                                  │       below cap   │
                                  │                   ▼
                                  │  ┌──────────────────────────────────┐
                                  │  │ LLMService.reformulate_query     │
                                  │  │  inputs: query, paths+titles,    │
                                  │  │          carry-fwd, reason       │
                                  │  │  output: new pt-BR query string  │
                                  │  └────────────────┬─────────────────┘
                                  │                   │
                                  │                   ▼
                                  │  ┌──────────────────────────────────┐
                                  │  │ Reformulation guard: token       │
                                  │  │ overlap with prior queries       │
                                  │  │ → if too similar, exit loop      │
                                  │  └────────────────┬─────────────────┘
                                  │                   │
                                  │                   ▼
                                  │  ┌──────────────────────────────────┐
                                  │  │ Attempt N+1: same strategy       │
                                  │  │  RetrievalService.retrieve*      │
                                  │  └────────────────┬─────────────────┘
                                  │                   │
                                  │                   ▼
                                  │  ┌──────────────────────────────────┐
                                  │  │ Cross-attempt merge + _dedup     │
                                  │  │  (existing helper)               │
                                  │  └────────────────┬─────────────────┘
                                  │                   │
                                  │                   └──→ back to sufficiency
                                  │
                                  ▼
                ┌──────────────────────────────────────────────┐
                │ Return (RetrievalResult, RetrievalTrace)     │
                └────────────────────┬─────────────────────────┘
                                     │
                                     ▼
                ┌──────────────────────────────────────────────┐
                │ ChatSession: existing answer path            │
                │  (insufficient → RET-04, otherwise generate) │
                └────────────────────┬─────────────────────────┘
                                     │
                                     ▼
                          ┌─────────────────────┐
                          │ CLI renders trace   │
                          │  if --trace enabled │
                          └─────────────────────┘
```

### Recommended Project Structure

```
src/aurora/retrieval/
├── contracts.py          # ADD: RetrievalAttempt, SufficiencyVerdict, RetrievalTrace
├── iterative.py          # NEW: IterativeRetrieval orchestrator
├── service.py            # UNCHANGED (orchestrator composes it)
└── qmd_search.py         # UNCHANGED

src/aurora/llm/
├── prompts.py            # ADD: REFORMULATION_PROMPT, SUFFICIENCY_JUDGE_PROMPT
├── service.py            # ADD: reformulate_query(), judge_sufficiency()
└── streaming.py          # MAYBE: add `grammar` kwarg to chat_completion_sync (only if GBNF used)

src/aurora/chat/
└── session.py            # EDIT: _handle_vault_turn, _handle_memory_turn (call orchestrator instead of retrieve directly)

src/aurora/cli/
├── ask.py                # EDIT: add --trace flag, render trace to stderr
└── chat.py               # EDIT: add --trace flag, persist diagnostic per-turn

src/aurora/runtime/
└── settings.py           # EDIT: 6 new fields per D-16, validators

tests/retrieval/
├── test_iterative.py             # NEW: orchestrator unit tests w/ FakeRetrieval, FakeLLM
├── test_sufficiency.py           # NEW: deterministic verdict pure-function tests
└── test_retrieval_service.py     # UNCHANGED

tests/chat/
├── test_session.py                       # ADD: 3-4 cases for orchestrator integration
└── test_session_iterative_loop.py        # NEW: end-to-end loop behavior in chat context

tests/cli/
└── test_ask_trace.py             # NEW: --trace renders, --json + --trace coexist, no snippet leak
```

### Pattern 1: Bounded loop with merge-then-judge (CRAG / DSPy-Assertions hybrid)

**What:** Run retrieve → judge sufficiency → if thin and under cap, reformulate and retrieve → merge with prior attempt's hits → re-judge. Stop when sufficient or cap hit.

**When to use:** This is exactly the Aurora case: small fixed number of attempts, deterministic stop condition, results from earlier attempts are kept (D-11).

**Reference shape (synthesized from CRAG and DSPy multi-hop tutorials):**

```python
# Source pattern: derived from CRAG (arxiv.org/abs/2401.15884) "if incorrect → trigger
# corrective action" and DSPy MultiHop tutorial (dspy.ai/tutorials/multihop_search/)
def run(query: str, *, strategy: str, terms: list[str]) -> tuple[RetrievalResult, RetrievalTrace]:
    attempts: list[RetrievalAttempt] = []
    accumulated_hits: list[QMDSearchHit] = []
    current_query = query
    prior_queries: list[str] = [query]

    for n in range(1, max_attempts + 1):
        result = retrieval_service.retrieve_with_strategy(current_query, strategy, terms)
        # Merge with prior accumulated hits before judging (D-11)
        merged_result = merge_with_accumulated(result, accumulated_hits)
        verdict = judge_sufficiency(merged_result)
        attempts.append(RetrievalAttempt(
            attempt=n, query=current_query,
            hit_count=len(merged_result.notes),
            top_score=top_score(merged_result),
            verdict=verdict,
        ))
        if verdict.ok or n == max_attempts:
            return merged_result, RetrievalTrace(attempts=tuple(attempts))
        # Reformulate
        new_query = llm.reformulate_query(
            original=query, prior_queries=prior_queries,
            paths_titles=[(n.path, _title(n)) for n in merged_result.notes],
            reason=verdict.reason,
        )
        if too_similar(new_query, prior_queries):
            attempts[-1] = replace(attempts[-1], reformulation_skipped=True)
            return merged_result, RetrievalTrace(attempts=tuple(attempts))
        accumulated_hits = collect_hits(merged_result)
        current_query = new_query
        prior_queries.append(new_query)
```

### Pattern 2: Sufficiency as a pure function over `RetrievalResult`

**What:** A pure-Python function (no LLM, no I/O) that maps `RetrievalResult` → `SufficiencyVerdict`. Easy to unit-test exhaustively.

**When to use:** Default deterministic path (D-02). The LLM judge wraps this function — runs only when deterministic check passes, providing a second opinion.

**Reference shape:**

```python
@dataclass(frozen=True)
class SufficiencyVerdict:
    ok: bool
    reason: str  # short pt-BR explanation, surfaced in trace and reformulation prompt
    signals: tuple[str, ...]  # e.g., ("top_score=0.18 < 0.35", "hits=1 < 2")

def judge_sufficiency_deterministic(
    result: RetrievalResult,
    *,
    min_top_score: float,
    min_hits: int,
    min_context_chars: int,
) -> SufficiencyVerdict:
    if result.insufficient_evidence or not result.notes:
        return SufficiencyVerdict(ok=False, reason="sem resultados", signals=("hits=0",))
    top = max(n.score for n in result.notes)
    hits_above = sum(1 for n in result.notes if n.score >= min_top_score)
    ctx_len = len(result.context_text)
    signals = []
    if top < min_top_score:
        signals.append(f"top_score={top:.2f} < {min_top_score:.2f}")
    if hits_above < min_hits:
        signals.append(f"hits_above_floor={hits_above} < {min_hits}")
    if ctx_len < min_context_chars:
        signals.append(f"context_chars={ctx_len} < {min_context_chars}")
    if signals:
        return SufficiencyVerdict(ok=False, reason="evidencia rasa", signals=tuple(signals))
    return SufficiencyVerdict(ok=True, reason="suficiente", signals=())
```

**Note on hybrid score scales:** `qmd query` (hybrid+rerank) scores roughly 0.0–1.0; `qmd search` (BM25) scores are unbounded but `_keyword_fallback` floors them at 0.10. The `min_top_score=0.35` default is calibrated against hybrid. **For mixed-source result sets** (vault hybrid + memory hybrid + keyword fallback), consider:

- **Option A (simple, recommended):** Apply `min_top_score` only to hits whose origin is hybrid (would require tagging `QMDSearchHit` with origin, OR computing top-score from the first call's hits before fallback merge). Counts and `min_context_chars` are mode-agnostic and contribute regardless.
- **Option B:** Track top-score per origin; "thin" if BOTH origins fail their respective thresholds.

The codebase currently does not tag origin on `QMDSearchHit`. Option A would require either (1) a small contract change adding `origin: str = "hybrid"` to `QMDSearchHit`, or (2) the orchestrator keeps origin separately by wrapping the per-call hit lists. Option (2) is less invasive. **Planner decision:** wrap and track separately in `IterativeRetrieval`, do not modify `QMDSearchHit`.

### Pattern 3: Reformulation with prior-query guard

**What:** Reformulation prompt explicitly receives prior queries and is instructed to differ. After generation, a deterministic Jaccard-overlap check rejects near-identical reformulations.

**When to use:** Always, when reformulating. Single biggest reformulation failure mode (FLARE paper, DSPy Assertions paper) is the model emitting a synonym swap that retrieves the same documents.

**Reference prompt sketch (pt-BR, fits existing prompts.py style):**

```python
REFORMULATION_PROMPT = """Voce esta ajudando a reformular uma busca no vault pessoal do usuario.

A busca anterior nao trouxe evidencia suficiente. Reescreva a pergunta para uma nova busca
que provavelmente recupere notas DIFERENTES das que ja foram tentadas.

Diretrizes:
- Responda SOMENTE com a nova consulta, em pt-BR, sem explicacao.
- A nova consulta deve ser SUBSTANCIALMENTE diferente das anteriores. Sinonimos nao bastam.
- Considere termos relacionados, hiponimos/hiperonimos, periodos de tempo, contextos diferentes.
- Mantenha-a curta (1-2 frases ou ate 12 palavras).

Pergunta original: {original_query}
Consultas ja tentadas:
{prior_queries_bulleted}

Notas ja recuperadas (caminhos e titulos, sem conteudo):
{paths_titles_bulleted}

Motivo da nova tentativa: {reason}

Nova consulta:"""
```

**Jaccard guard:**

```python
def _too_similar(new: str, prior: list[str], *, threshold: float = 0.7) -> bool:
    new_tokens = set(new.lower().split())
    return any(
        len(new_tokens & set(q.lower().split())) / max(len(new_tokens | set(q.lower().split())), 1) >= threshold
        for q in prior
    )
```

Threshold of 0.7 is a starting point — DSPy's reference uses "dissimilar" as a soft assertion without a hard number; 0.7 means at least 30% novel tokens. Tune during planning if the prompt model is too conservative.

### Anti-Patterns to Avoid

- **Inheriting from `RetrievalService` to add the loop.** Breaks single-responsibility, makes the disable path tangled. Compose, don't inherit.
- **Streaming the reformulation call.** Reformulation is internal; user sees nothing. Use sync `chat_completion_sync` like `classify_intent` does.
- **Putting the loop inside `RetrievalService.retrieve*`.** RetrievalService is the deterministic transport over QMD. Adding LLM dependencies into it is a layering violation.
- **Re-applying carry-forward on attempt 2.** Carry-forward paths from the prior _turn_ must apply only on attempt 1; otherwise the same supplementary notes get re-counted as "new evidence" on attempt 2 and inflate hit counts. The orchestrator receives the already-carry-forwarded result for attempt 1, but on attempt 2 it must NOT re-call `_apply_carry_forward`. Easiest way: orchestrator never calls `_apply_carry_forward` itself; `ChatSession` calls it once before invoking the orchestrator.
- **Logging snippets to trace.** PRIV-03 violation. Trace dataclass should not have a `snippet` field at all — make leakage structurally impossible.
- **Re-classifying intent on the reformulated query.** Intent already determined; D-07 locks strategy across attempts.

**Planner takeaway:** The orchestrator is ~80–120 lines of Python with one well-defined contract: takes a query + strategy + carry-forwarded first result (or lazily computes attempt 1), returns `(RetrievalResult, RetrievalTrace)`. Everything else is composition.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Result dedup across attempts | New dedup logic | `RetrievalService._dedup_hits` (existing) | Already handles best-score-per-path, already tested |
| Context assembly across merged hits | New assembler | `RetrievalService._assemble_context` (existing) | Already enforces `MAX_CONTEXT_CHARS=24000` truncation |
| Note fetching | New `qmd get` calls | `QMDSearchBackend.fetch` (existing) | Handles missing-file → None case |
| Token counting / similarity | TF-IDF, embedding similarity | Plain Jaccard on tokenized strings | Words-level overlap is fine for "is this a near-identical rewrite" |
| LLM judge structured output | JSON parsing + validation | GBNF grammar `"yes"|"no"` (if needed) | One-token output, no preamble possible |
| Trace formatting | New rendering framework | Plain f-strings to stderr (text) + `dataclasses.asdict` + `json.dumps` (json) | Trace is a 5-line dataclass — overkill to introduce a renderer |

**Key insight:** The phase ships ~1 net new file (`retrieval/iterative.py`) + 3 dataclass additions + 2 LLM methods + 2 prompts + 6 settings fields + edits to 2 chat handlers and 2 CLI commands. Don't build a "retrieval framework" — wire the existing primitives.

**Planner takeaway:** Heavy reliance on existing helpers means the integration tasks are surgical. Reject any plan task that proposes building parallel infrastructure for dedup, assembly, or fetching.

## Sufficiency Signals — Detailed

### Deterministic signals (D-02 default; this is what runs in the hot path)

| Signal | Computation | Reliability | Latency | Hybrid+BM25 interaction |
|--------|------------|-------------|---------|-------------------------|
| **Top-1 score** | `max(n.score for n in result.notes)` against `min_top_score` | HIGH for hybrid; UNCALIBRATED for BM25 (different scale) | ~1µs | Apply only to hybrid-origin hits, OR accept that mixed sets may pass even when hybrid alone would fail (Option A above). |
| **Hits above floor** | `sum(1 for n in result.notes if n.score >= min_top_score)` against `min_hits` | MEDIUM-HIGH; cheap to game with low threshold | ~1µs | Same caveat: BM25 scores below the hybrid threshold may not count. Recommend: count hits-above-floor _per origin_ if origin is tracked, else use `len(result.notes) >= min_hits` as a proxy. |
| **Assembled context length** | `len(result.context_text)` against `min_context_chars` | HIGH for "matches existed but were tiny" case | ~1µs | Mode-agnostic; works regardless of source. Strong signal for "we found stub notes". |
| **Embedding diversity (NOT recommended)** | Pairwise cosine over note embeddings | HIGH but expensive | ~10ms+ | Requires embedding access; QMD doesn't expose this without re-encoding. Skip. |
| **Retrieval count == 0** | `len(result.notes) == 0` (already in `_INSUFFICIENT`) | TRIVIAL | ~0 | Already handled by `RetrievalService` returning `_INSUFFICIENT`. |

**Signal ordering:** Run the count-zero short-circuit first (`result.insufficient_evidence` → thin), then top-score, then hits-above-floor, then context length. Any one trips "thin" (D-02). Collect all tripped signals into `SufficiencyVerdict.signals` for the trace and reformulation prompt — multiple tripped signals tell the reformulator "broaden substantially" vs a single low-context signal saying "find longer notes".

### LLM judge (D-03 opt-in)

**Sequence:** deterministic check first → if it passes, optionally run LLM judge as second-pass. (Asymmetric: if deterministic says thin, that's enough; if deterministic says ok, judge can override to thin.) This ordering keeps latency low: judge only runs when we're already going to answer, so its cost is "free at the level of decisiveness, but not free in tokens."

**Prompt sketch (pt-BR, single-token output via grammar OR plain text + parse):**

```python
SUFFICIENCY_JUDGE_PROMPT = """Decida se o contexto abaixo e SUFICIENTE para responder a pergunta.

Considere suficiente se as notas claramente contem informacao para responder ao menos uma parte significativa da pergunta.

Pergunta: {query}

Notas recuperadas (caminhos):
{paths_bulleted}

Trechos do contexto montado (primeiros {sample_chars} caracteres):
{context_sample}

Responda APENAS com uma palavra: sim ou nao."""
```

Note: the judge prompt _must_ include enough context to make a real decision but cannot include the full `context_text` because that defeats the latency goal. Recommend: pass the first ~1000 characters of `context_text` (or the full text if shorter). This is internal — not user-facing — so it does not violate PRIV-03 (which is about logs, not prompts).

**Latency budget for judge:** On a 4–8B Q8_0 model on CPU/Metal, expect 50–150 tokens prompt + 1 token output ≈ 100–300ms. Acceptable as opt-in; would be too high if mandatory.

**Planner takeaway:** Default deterministic (always-on, ~1µs total). LLM judge is a clean second pass with its own latency budget; users opt in via `iterative_retrieval_judge: true` and accept the cost.

## Query Reformulation Strategies — Survey

| Strategy | When it helps | When it hurts | Fit for Aurora |
|----------|--------------|---------------|----------------|
| **Plain "rewrite this to be more specific"** | Vague queries ("notas sobre saude") that need narrowing | When the user already wrote a specific query — model adds noise | **Recommended default** for Aurora's pt-BR free-form vault queries. Matches D-05/D-06 prompt design. |
| **HyDE** [CITED: arxiv.org/abs/2212.10496] | When the corpus uses very different vocabulary than the query | Low-resource domains; model hallucinates fictional content [CITED: milvus.io/ai-quick-reference HyDE] | Risky for pt-BR personal vault — model may invent diary content that biases retrieval. Deferred per CONTEXT. |
| **Step-back** [CITED: Google DeepMind, arxiv.org/abs/2310.06117] | Multi-hop reasoning needing principles ("what causes X?" → "what category of phenomena is X?") | Single-hop factual queries; adds abstraction that misses concrete matches | Marginal fit — Aurora vault queries are mostly single-hop. Could be a fallback if first reformulation also fails (out of scope for v1). |
| **Sub-query decomposition** | Compound questions ("X and also Y") | Atomic queries; produces fragmentation | Low fit — Aurora intents are short. Compound questions are rare in personal-vault use. |
| **Paraphrase-and-broaden** | When query has rare-word lock-in | When rare word IS the key (e.g., proper noun) | Counterproductive for the proper-noun cases that 04.2's keyword fallback already targets. Avoid. |
| **Synonym expansion (heuristic)** | Domain-specific thesauri with curated mapping | Free-form pt-BR; brittle without a thesaurus | Explicitly rejected per D-05. |

### Recommended default for Aurora

**"Rewrite for substantively different retrieval, given prior queries and seen paths"** — this is closest to the DSPy multi-hop pattern adapted to a single reformulation step. Reasoning:

1. **Local 4–8B model constraint:** HyDE-style hallucinated documents are too risky on a smaller model that may invent vault-style notes. Plain rewrite stays grounded in the user's actual question.
2. **pt-BR constraint:** All listed strategies are documented primarily on English benchmarks. Plain rewrite is the lowest-risk port; the model's own pt-BR understanding is doing the work, not a structured technique.
3. **Already-retrieved paths in prompt:** Telling the model "here's what you already got, find different things" is the most direct way to elicit divergent reformulation without a complex framework.
4. **Single-hop emphasis:** Aurora vault queries are predominantly single-hop. Multi-hop techniques (step-back, decomposition) add overhead for a corner case.
5. **One reformulation only:** D-09 caps at 2 attempts. There's no second chance to course-correct from a HyDE hallucination, which makes the failure mode permanent on this turn.

**Planner takeaway:** Keep the prompt simple (≤200 tokens of instructions + variable inputs). The complexity is in the inputs (prior queries, seen paths, sufficiency reason), not in the technique.

## Loop Bounding and Convergence

### Standard practice for bounding agentic-retrieval loops

- **CRAG:** Single retrieval evaluation pass → corrective action → done. Effectively a hard cap of 1 retry.
- **FLARE:** Per-sentence triggering, but each trigger is a single-shot retrieval. No nested loop.
- **IRCoT:** Loop bounded by reasoning chain length, typically 5–7 steps. Heavyweight.
- **DSPy multi-hop:** Configurable `num_hops`, default 2–3. Uses Suggest assertions to enforce query dissimilarity per hop.
- **Self-RAG:** Reflection-token-driven; not externally bounded — the model itself decides "no more retrievals needed" via the `Retrieve=No` token.

**Convergence:** None of the production systems run unbounded loops. The general principle is **"bound by attempts, not by quality"** — let the bound be the stop condition, accept that some queries won't reach sufficient. This matches D-09 + D-10 exactly.

### "Near-identical reformulation" failure mode

This is the dominant failure mode and is explicitly addressed in:

- **DSPy Assertions paper** [CITED: arxiv.org/abs/2312.13382]: introduces `Suggest("queries should be dissimilar from previous hops")` as a soft constraint with backtracking on violation.
- **FLARE paper** [CITED: arxiv.org/abs/2305.06983]: uses token-level confidence to detect when the regeneration didn't actually shift.

**Practical mitigations (any subset works):**

1. **Pass prior queries into prompt** (D-06 already locks this). HIGH effectiveness, zero compute cost.
2. **Explicit instruction "substantially different"** in pt-BR prompt. HIGH effectiveness, zero cost.
3. **Post-generation Jaccard-overlap check** on tokens. MEDIUM-HIGH effectiveness, ~1µs cost. Hard guarantee.
4. **Reject-and-retry** the reformulation call up to N times if guard fails. ASSUMED MEDIUM effectiveness; doubles latency. Skip for v1.

**Recommended:** All three of #1, #2, #3. If #3 trips, exit the loop early (treat as "model couldn't find a meaningfully different angle, don't waste a second retrieval"). This is more conservative than DSPy's reject-and-retry, which fits Aurora's "predictable latency" priority.

### Cross-attempt dedup strategy (D-11)

Standard pattern is **merge-then-judge:** after attempt 2, combine attempt-1 hits + attempt-2 hits into a single hit list, dedup by ID/path keeping highest score, fetch the union, assemble context, then judge. This is exactly what `_dedup_hits` already does — orchestrator calls it on the combined list.

**Subtle gotcha:** when dedup'ing across hybrid + keyword runs of the same query, score scales differ (already discussed above). Across the same mode (hybrid attempt 1 + hybrid attempt 2), scales are comparable — keep highest. Across modes, the existing `_dedup_hits` keeps "highest score" but a BM25 score of 5.0 can outrank a hybrid score of 0.9 for the same path, which is wrong direction. **Mitigation:** dedup _within_ origin first, then merge across origins as separate sub-pools whose order is determined by the assembly step (which is mode-agnostic). The simplest fix is to constrain dedup to within-attempt for now and let the merge be a list concat (keeping first occurrence by path order).

**Planner takeaway:** Use `_dedup_hits` for within-attempt dedup; for across-attempt merge, use a separate small helper that prefers attempt-2 hits (newer evidence) when paths collide. Don't trust score comparisons across attempts.

## Local-LLM Constraints

### Realistic latency expectations

For one extra non-streaming reformulation call on llama.cpp serving Qwen3-8B-Q8_0 (the codebase default in `RuntimeSettings`):

| Operation | Typical token counts | Est. latency on M-series Mac (Metal) | Est. latency on CPU |
|-----------|---------------------|--------------------------------------|---------------------|
| Reformulation (sync) | ~250 prompt + ~20 output | 200–600 ms `[ASSUMED based on llama.cpp Qwen3-8B Q8 typical throughput; verify on device]` | 1.5–4 s `[ASSUMED]` |
| Sufficiency judge (sync, with 1KB context sample) | ~400 prompt + 1 output | 150–400 ms `[ASSUMED]` | 1–3 s `[ASSUMED]` |
| Existing intent classify (for comparison) | ~150 prompt + ~10 output | 100–300 ms | 0.5–1.5 s |

The user has accepted up to 2.5× original latency on the worst case (D-12). With the original ask path being roughly: classify (~200ms) + retrieve (~50–500ms depending on QMD) + stream answer (~2–8s for typical 200-token answer) ≈ 2.3–8.7s, the worst-case loop adds:

- Reformulation call: +200–600ms
- Second retrieval: +50–500ms
- Optional judge × 2 (if enabled, runs after each attempt): +300–800ms

Worst-case delta: ~0.5–2.4s on top of a 2–8s baseline → 1.06× to 1.30× on the slow end, ~1.3× on the fast end. Well within the 2.5× budget. **This means the latency budget is not the binding constraint** — the binding constraint is user-perceived snappiness on the happy path (no reformulation), which the deterministic-first design already handles (sufficiency check is microseconds; loop exits immediately if sufficient).

### Prompt size / context cache

llama.cpp's prompt cache (`--cache-reuse`, automatic prefix matching) helps when consecutive prompts share a long prefix. The reformulation and judge prompts are short and one-shot; they will not benefit from cache reuse from the main streaming call (different prompts entirely).

**Tactic:** Keep both prompts small. Reformulation ≤200 tokens of instruction + variable. Judge ≤150 tokens + ~1KB context sample. Neither approaches the typical 8K context window, so context budget is not a concern.

### Structured y/n on small models

Three approaches in increasing order of robustness:

1. **Plain text + parse** (current Aurora pattern, used by `classify_intent`). Adequate when the model is reasonably aligned. Risk: occasional preambles like "Análise: a resposta é sim porque...". Parsable with `lower().startswith("sim")` heuristic.
2. **JSON mode** (llama.cpp `json_schema` field). Heavier than needed for one bit.
3. **GBNF grammar** [CITED: github.com/ggml-org/llama.cpp grammars/README.md]. One line: `root ::= "sim" | "nao"`. Forces a single token, eliminates preambles entirely.

**Recommendation:** Start with #1 (plain text + permissive parse: `lower()` includes "sim" → ok, "nao"/"não" → thin, anything else → conservatively treat as ok to avoid unnecessary loop). If the judge proves unreliable on the chosen model, upgrade to #3 by adding a `grammar` kwarg to `chat_completion_sync`. This is a pure-additive change — tests for the non-grammar path stay valid.

**Planner takeaway:** Latency budget is comfortable. Reformulation prompt ≤200 instruction-tokens. Sufficiency judge can start with plain-text parsing; GBNF is a documented upgrade path if needed.

## Trace / Observability

### Industry practice (LangSmith, Phoenix, Langfuse)

All three converge on a hierarchical trace model: **Trace** contains **Spans**; each span has attributes for inputs, outputs, metadata. RAG-specific span types are documented: `retrieval`, `llm`, `tool`. Phoenix uses the OpenInference semantic convention; Langfuse uses its own observation types but maps cleanly to OpenTelemetry. `[CITED: phoenix.arize.com, langfuse.com/docs/observability/data-model]`

For Aurora's local-only constraint, **shipping OpenTelemetry export is overkill** — there's no observability backend to export to, and adding the dep would violate the no-cloud spirit. The internal trace shape can _shape itself_ after these conventions, so a future `--trace --otel` flag is a small extension.

### Minimum viable trace shape for Aurora

```python
@dataclass(frozen=True)
class RetrievalAttempt:
    attempt: int                       # 1-indexed
    query: str                          # original (n=1) or reformulated (n>1)
    strategy: str                       # "hybrid" / "keyword" / "both"
    hit_count: int                      # post-dedup, post-merge
    top_score: float                    # max score in this attempt's contribution
    paths: tuple[str, ...]              # paths only — NEVER snippets
    verdict_ok: bool
    verdict_reason: str                 # short pt-BR
    verdict_signals: tuple[str, ...]    # raw signal trips
    reformulation_skipped: bool = False # True if Jaccard guard tripped
    reformulation_reason: str = ""      # "evidencia rasa: top_score=0.18 < 0.35"
    duration_ms: float = 0.0

@dataclass(frozen=True)
class RetrievalTrace:
    enabled: bool                       # False when iterative_retrieval_enabled=False
    intent: str                         # "vault" / "memory"
    attempts: tuple[RetrievalAttempt, ...]
    final_verdict_ok: bool
    judge_used: bool                    # True if LLM judge ran
    total_duration_ms: float
```

**Privacy verification:** No `snippet`, `content`, or `context_text` field. The dataclass _structurally_ cannot leak content. A single test asserting `assert "snippet" not in dataclasses.asdict(trace_instance).keys()` and that none of the existing fields contain content would pin this.

### Render shapes

**Text (default for `--trace`):**

```
[trace] intent=vault attempts=2 final=ok duration=1840ms
  [1] q="Rosely diario" strategy=hybrid hits=1 top=0.18 verdict=thin
      signals: top_score=0.18 < 0.35; hits_above_floor=0 < 2
  [2] q="anotacoes pessoais sobre Rosely" strategy=hybrid hits=4 top=0.62 verdict=ok
      paths: notas/diario/2024-03-15.md, notas/diario/2024-04-02.md, ...
```

**JSON (when paired with `--json`):** `dataclasses.asdict(trace)` dumped to a `"trace"` key in the existing JSON envelope. Keeps `--json` parseable.

### Trace channel (D-14)

- `aurora ask`: trace goes to **stderr** as text; trace appears in the JSON envelope (under `"trace"` key) when `--json --trace` are combined. This matches the existing pattern of progress messages on stderr.
- `aurora chat`: per-turn trace goes to stderr after each turn. No JSON envelope concern in chat mode (chat never returns JSON).

**Planner takeaway:** Trace is a 3-dataclass file in `contracts.py` and a 2-method renderer (text + dict). Privacy safety is structural — paths-only, no snippet field exists. The JSON path is a `dataclasses.asdict` away.

## Common Pitfalls

### Pitfall 1: Carry-forward double-counting on attempt 2

**What goes wrong:** `ChatSession._apply_carry_forward` adds up to 3 supplementary notes from the prior turn. If the orchestrator re-applies it on attempt 2, those same paths get re-counted as "new evidence", inflating hit counts and possibly tripping false sufficiency.
**Why it happens:** The orchestrator works at the `RetrievalResult` level and may not realize some notes are carry-forward supplements. There's no flag distinguishing them.
**How to avoid:** Apply carry-forward in `ChatSession` ONCE before invoking the orchestrator. Orchestrator never calls `_apply_carry_forward`. Attempt-2 retrieval goes through `RetrievalService.retrieve*` directly, which has no knowledge of carry-forward.
**Warning signs:** Attempt-2 hit_count >= attempt-1 hit_count + 3 with the same paths re-appearing in `paths`.

### Pitfall 2: Reformulation produces a synonym swap

**What goes wrong:** Local 4–8B model returns "encontrar Rosely no diario" → "achar Rosely no diario". Hits identical, second attempt accomplishes nothing but adds latency.
**Why it happens:** Default LLM behavior on rewrite tasks is conservative paraphrase.
**How to avoid:** Three locks in CONTEXT.md and Pattern 3 above: prior-query injection, "substantially different" instruction, post-generation Jaccard guard with early loop exit.
**Warning signs:** Trace shows attempt-2 query with >70% token overlap with attempt-1; attempt-2 hits substantially overlap attempt-1.

### Pitfall 3: Trace leaks snippet content

**What goes wrong:** Someone adds `snippet: str` to `RetrievalAttempt` "for debugging convenience". PRIV-03 violation.
**Why it happens:** Convenience pressure during debugging.
**How to avoid:** Make leakage structurally impossible — define `RetrievalAttempt` without any content-carrying field. Add a unit test that introspects all dataclass fields and rejects names matching `{"snippet", "content", "text", "context"}`.
**Warning signs:** Any reviewer should reject any dataclass change adding such a field.

### Pitfall 4: Disable path drift

**What goes wrong:** Over time, the disable path (`iterative_retrieval_enabled = false`) silently changes behavior because someone refactored the orchestrator's "shortcut return".
**Why it happens:** The disable path is the cold path; nobody notices regressions.
**How to avoid:** A regression test pins the disable-path behavior: `IterativeRetrieval(enabled=False).run(query, ...)` returns a `RetrievalResult` byte-identical (or structurally identical) to `RetrievalService.retrieve(query, ...)`. Test runs in CI on every change.
**Warning signs:** Disable path test fails after orchestrator edits.

### Pitfall 5: Threshold tuning hell

**What goes wrong:** `retrieval_min_top_score` is set without data; later tuning produces oscillation (raise → too aggressive looping → user complains → lower → no rescue → user complains).
**Why it happens:** Defaults chosen by intuition, not by sampling current failure cases.
**How to avoid:** Per CONTEXT "Claude's Discretion", planner samples actual prior failure cases (UAT logs from prior fix-phase artifacts: `.planning/phases/04.2-*` summaries; `~/.aurora/` debug logs if present) before locking defaults. Document the sampling and rationale in the PLAN. Treat the defaults as v1 — expect a follow-up phase to reconsider after some real usage data.
**Warning signs:** Issue reports of "the loop runs every time" (threshold too high) or "the loop never runs" (threshold too low) within first weeks of usage.

### Pitfall 6: Latency surprise on slow models

**What goes wrong:** User runs Aurora with a larger or quantized model on CPU; the +200ms for reformulation becomes +3s; D-12's "≤2.5×" budget blows.
**Why it happens:** Latency estimates are model/hardware-dependent. We don't have a way to dynamically detect "this model is slow".
**How to avoid:** Plan must include a measurement task (run the loop on the chosen default model, record p50/p95 latency). Document the measurement in the SUMMARY. Provide an escape hatch (`iterative_retrieval_enabled = false`) prominently in setup docs for users who notice slowness.
**Warning signs:** Users with non-default models report doubled latency.

### Pitfall 7: Eval gaming

**What goes wrong:** Future eval harness measures "did the loop fire?" or "did we get more hits on attempt 2?" — these are easy to game by lowering thresholds; doesn't measure answer quality.
**Why it happens:** Cheap-to-measure proxies displace expensive-to-measure outcomes.
**How to avoid:** Out of scope for this phase per Deferred Ideas, but the trace shape this phase ships should make it easy to wire human-judged answer quality alongside loop-fired counts. **Planner takeaway:** include in the trace dataclass enough information that an eval harness can reconstruct each attempt's hit set; do _not_ pre-compute "loop usefulness" metrics in this phase.
**Warning signs:** Future eval phase tries to measure success without human grading.

### Pitfall 8: Memory-first vs vault-first asymmetry

**What goes wrong:** Loop wraps `retrieve_memory_first` differently than `retrieve_with_memory`, breaking memory-intent flows in subtle ways.
**Why it happens:** The two methods have similar shape but different ordering; orchestrator may treat them as interchangeable.
**How to avoid:** Orchestrator takes a callable `retrieve_fn: Callable[[str, str, list[str]], RetrievalResult]` rather than knowing which method to call. `ChatSession._handle_*_turn` passes the right method. Orchestrator doesn't care about strategy semantics, only about "call this with these params, get a result back".
**Warning signs:** Tests for memory turns pass but real memory queries miss memory hits in attempt 2.

**Planner takeaway:** Pitfalls 1, 3, and 4 are the load-bearing ones — each becomes a specific test in the PLAN. Pitfalls 5 and 6 are handled by sampling + measurement tasks. Pitfalls 2, 7, 8 are handled by orchestrator design.

## Code Examples

### Orchestrator skeleton (recommended structure)

```python
# src/aurora/retrieval/iterative.py
from __future__ import annotations
import logging
import time
from dataclasses import dataclass, replace
from typing import Callable, Protocol

from aurora.llm.service import LLMService
from aurora.retrieval.contracts import (
    QMDSearchHit, RetrievalAttempt, RetrievalResult, RetrievalTrace, SufficiencyVerdict,
)
from aurora.retrieval.service import RetrievalService
from aurora.runtime.settings import RuntimeSettings, load_settings

logger = logging.getLogger(__name__)

RetrieveFn = Callable[[str, str, list[str]], RetrievalResult]


class IterativeRetrieval:
    """Bounded loop that wraps any RetrievalService.retrieve* method."""

    def __init__(
        self,
        *,
        retrieval: RetrievalService,
        llm: LLMService,
        settings_loader: Callable[[], RuntimeSettings] = load_settings,
    ) -> None:
        s = settings_loader()
        self._retrieval = retrieval
        self._llm = llm
        self._enabled = s.iterative_retrieval_enabled
        self._max_attempts = s.retrieval_max_attempts
        self._min_top_score = s.retrieval_min_top_score
        self._min_hits = s.retrieval_min_hits
        self._min_context_chars = s.retrieval_min_context_chars
        self._judge_enabled = s.iterative_retrieval_judge

    def run(
        self,
        query: str,
        *,
        retrieve_fn: RetrieveFn,
        strategy: str,
        terms: list[str],
        intent: str,                    # "vault" | "memory" — for trace
        first_attempt: RetrievalResult | None = None,  # if ChatSession already ran attempt 1 + carry-fwd
    ) -> tuple[RetrievalResult, RetrievalTrace]:
        if not self._enabled:
            result = first_attempt or retrieve_fn(query, strategy, terms)
            return result, RetrievalTrace(enabled=False, intent=intent, attempts=(), ...)

        attempts: list[RetrievalAttempt] = []
        prior_queries = [query]
        accumulated_hits: list[QMDSearchHit] = []  # for cross-attempt merge

        current_query = query
        current_result = first_attempt
        t_start = time.monotonic()

        for n in range(1, self._max_attempts + 1):
            t_attempt = time.monotonic()
            if current_result is None:
                current_result = retrieve_fn(current_query, strategy, terms)

            # cross-attempt merge (only on n>=2; on n=1 there's nothing to merge)
            merged = self._merge(current_result, accumulated_hits) if n > 1 else current_result

            verdict = self._judge(merged, query=current_query)
            attempts.append(self._build_attempt(n, current_query, strategy, merged, verdict, t_attempt))

            if verdict.ok or n == self._max_attempts:
                return merged, self._build_trace(intent, attempts, verdict.ok, t_start)

            # reformulate
            new_query = self._llm.reformulate_query(
                original=query, prior_queries=prior_queries,
                paths=[note.path for note in merged.notes],
                titles=[note.path.rsplit("/", 1)[-1] for note in merged.notes],
                reason=verdict.reason,
            )
            if self._too_similar(new_query, prior_queries):
                attempts[-1] = replace(attempts[-1], reformulation_skipped=True)
                return merged, self._build_trace(intent, attempts, False, t_start)

            accumulated_hits = self._collect(merged)
            current_query = new_query
            prior_queries.append(new_query)
            current_result = None  # force fresh retrieve

        return merged, self._build_trace(intent, attempts, verdict.ok, t_start)

    # ... helpers: _judge, _merge, _too_similar, _collect, _build_attempt, _build_trace
```

### LLMService method additions

```python
# src/aurora/llm/service.py — additions
from aurora.llm.prompts import REFORMULATION_PROMPT, SUFFICIENCY_JUDGE_PROMPT

def reformulate_query(
    self,
    *,
    original: str,
    prior_queries: list[str],
    paths: list[str],
    titles: list[str],
    reason: str,
) -> str:
    """Generate a substantively different query for a second retrieval attempt."""
    prompt = REFORMULATION_PROMPT.format(
        original_query=original,
        prior_queries_bulleted="\n".join(f"- {q}" for q in prior_queries),
        paths_titles_bulleted="\n".join(f"- {p}: {t}" for p, t in zip(paths, titles)),
        reason=reason,
    )
    raw = self._sync_fn(
        endpoint_url=self._endpoint_url,
        model_id=self._model_id,
        messages=[{"role": "user", "content": prompt}],
    )
    return raw.strip().splitlines()[0].strip()  # first non-empty line, trimmed

def judge_sufficiency(
    self, *, query: str, paths: list[str], context_sample: str,
) -> bool:
    """Optional second-opinion judge. Returns True if sufficient."""
    prompt = SUFFICIENCY_JUDGE_PROMPT.format(
        query=query,
        paths_bulleted="\n".join(f"- {p}" for p in paths),
        sample_chars=len(context_sample),
        context_sample=context_sample,
    )
    raw = self._sync_fn(
        endpoint_url=self._endpoint_url,
        model_id=self._model_id,
        messages=[{"role": "user", "content": prompt}],
    ).strip().lower()
    if "nao" in raw or "não" in raw:
        return False
    if "sim" in raw:
        return True
    return True  # ambiguous → conservatively skip the loop (avoid wasted work)
```

### Settings additions

```python
# src/aurora/runtime/settings.py — additions
class RuntimeSettings(BaseSettings):
    # ... existing fields ...
    iterative_retrieval_enabled: bool = True
    retrieval_max_attempts: int = 2
    retrieval_min_top_score: float = 0.35
    retrieval_min_hits: int = 2
    retrieval_min_context_chars: int = 800
    iterative_retrieval_judge: bool = False

    @field_validator("retrieval_max_attempts")
    @classmethod
    def _validate_retrieval_max_attempts(cls, value: int) -> int:
        if value < 1 or value > 4:
            raise ValueError("retrieval_max_attempts deve estar entre 1 e 4.")
        return value

    @field_validator("retrieval_min_top_score")
    @classmethod
    def _validate_retrieval_min_top_score(cls, value: float) -> float:
        if value < 0.0 or value > 1.0:
            raise ValueError("retrieval_min_top_score deve estar entre 0.0 e 1.0.")
        return value

    @field_validator("retrieval_min_hits")
    @classmethod
    def _validate_retrieval_min_hits(cls, value: int) -> int:
        if value < 1 or value > 20:
            raise ValueError("retrieval_min_hits deve estar entre 1 e 20.")
        return value

    @field_validator("retrieval_min_context_chars")
    @classmethod
    def _validate_retrieval_min_context_chars(cls, value: int) -> int:
        if value < 0 or value > 24_000:
            raise ValueError("retrieval_min_context_chars deve estar entre 0 e 24000.")
        return value
```

### ChatSession integration site

```python
# src/aurora/chat/session.py — _handle_vault_turn skeleton change
def _handle_vault_turn(self, user_message, intent_result=None) -> str:
    self._on_status("Buscando no vault...")
    strategy = getattr(intent_result, "search", "hybrid") if intent_result else "hybrid"
    terms = getattr(intent_result, "terms", []) if intent_result else []

    # Attempt 1: existing path including carry-forward
    if self._retrieval._memory_backend is not None:
        retrieve_fn = self._retrieval.retrieve_with_memory
    else:
        retrieve_fn = self._retrieval.retrieve
    first = retrieve_fn(user_message, search_strategy=strategy, search_terms=terms)
    first = self._apply_carry_forward(first)  # carry-fwd applies ONCE, before loop

    # Bind retrieve_fn for the orchestrator (no carry-fwd on subsequent attempts)
    def _wrapped(q: str, s: str, t: list[str]) -> RetrievalResult:
        return retrieve_fn(q, search_strategy=s, search_terms=t)

    result, trace = self._iterative.run(
        user_message, retrieve_fn=_wrapped, strategy=strategy,
        terms=terms, intent="vault", first_attempt=first,
    )

    # Optionally emit trace via on_trace callback (set by CLI when --trace is on)
    if self._on_trace is not None:
        self._on_trace(trace)

    self._last_retrieved_paths = [n.path for n in result.notes][:3]
    if result.insufficient_evidence:
        # ... existing insufficient path unchanged ...
```

**Planner takeaway:** Each integration site is 5–10 line surgical change. The orchestrator gets `first_attempt` as an optional input so `ChatSession` can keep its carry-forward semantics intact.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-shot retrieval (RAG 1.0) | Adaptive / iterative retrieval (Self-RAG, FLARE, CRAG) | Late 2023 → 2024 | Establishes "judge before answer" as canonical for non-trivial queries |
| LLM-as-judge for everything | Deterministic signals + optional LLM second opinion | 2024 (CRAG showed evaluator can be tiny) | Latency-friendly default; still benefits from LLM when needed |
| Hand-built loop orchestration | Frameworks (LangGraph, DSPy) | 2024 | For Aurora: framework overkill; pattern reusable without dep |
| Heuristic query expansion | LLM-based reformulation | 2023+ | Aurora's locked decision (D-05) matches consensus |

**Deprecated/outdated:**
- "Always run BM25 + vector and rerank, single shot" — still valid as a baseline (and is Aurora's attempt-1), but production teams in 2024–2025 supplement with adaptive layers.
- Pre-FLARE "ask LLM if it knows the answer first" — superseded by retrieval-evaluator approaches.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (existing — confirmed by `tests/` layout) |
| Config file | (none observed at root; pytest auto-discovers from `tests/` directory) |
| Quick run command | `pytest tests/retrieval/test_iterative.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RET-01 | Loop preserves grounded-answer flow on sufficient attempt 1 | unit | `pytest tests/retrieval/test_iterative.py::test_sufficient_attempt_1_returns_immediately -x` | Wave 0 |
| RET-01 | Loop succeeds on attempt 2 when attempt 1 thin | unit | `pytest tests/retrieval/test_iterative.py::test_thin_then_sufficient_succeeds -x` | Wave 0 |
| RET-03 | Strategy is preserved across attempts (D-07) | unit | `pytest tests/retrieval/test_iterative.py::test_strategy_unchanged_across_attempts -x` | Wave 0 |
| RET-04 | Loop exit with insufficient still triggers RET-04 path | integration | `pytest tests/chat/test_session_iterative_loop.py::test_double_thin_falls_back_to_insufficient_msg -x` | Wave 0 |
| PRIV-03 | Trace dataclass has no content/snippet field | unit | `pytest tests/retrieval/test_iterative.py::test_trace_has_no_snippet_fields -x` | Wave 0 |
| PRIV-03 | `--trace` text output contains no note content | integration | `pytest tests/cli/test_ask_trace.py::test_trace_text_does_not_contain_snippets -x` | Wave 0 |
| D-09 | Hard cap respected | unit | `pytest tests/retrieval/test_iterative.py::test_max_attempts_cap -x` | Wave 0 |
| D-11 | Cross-attempt merge dedups by path | unit | `pytest tests/retrieval/test_iterative.py::test_cross_attempt_dedup -x` | Wave 0 |
| D-18 | Disable flag = byte-identical to single-shot | unit | `pytest tests/retrieval/test_iterative.py::test_disabled_path_matches_single_shot -x` | Wave 0 |
| Pitfall 2 | Reformulation Jaccard guard exits loop | unit | `pytest tests/retrieval/test_iterative.py::test_jaccard_guard_skips_second_retrieval -x` | Wave 0 |
| Pitfall 1 | Carry-forward not double-counted on attempt 2 | integration | `pytest tests/chat/test_session_iterative_loop.py::test_carry_forward_applied_once -x` | Wave 0 |
| D-13 | `--trace` flag exists on ask and chat | smoke | `aurora ask --help \| grep -- --trace` AND `aurora chat --help \| grep -- --trace` | manual or click-runner unit |

### Sampling Rate

- **Per task commit:** `pytest tests/retrieval/test_iterative.py tests/chat/test_session_iterative_loop.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`.

### Wave 0 Gaps

- [ ] `tests/retrieval/test_iterative.py` — orchestrator unit tests with FakeLLM + FakeRetrieval
- [ ] `tests/retrieval/test_sufficiency.py` — pure-function sufficiency verdict tests (one fixture per signal trip)
- [ ] `tests/chat/test_session_iterative_loop.py` — integration tests for ChatSession + orchestrator
- [ ] `tests/cli/test_ask_trace.py` — `--trace` rendering, `--json --trace` coexistence, no snippet leak
- [ ] Conftest fixture: `FakeLLMService` with scripted `reformulate_query` and `judge_sufficiency` returns; `FakeRetrievalService` returning a tiered sequence (thin → thick) per attempt

### Test Strategy for Non-Deterministic Loops

The loop has two non-deterministic dependencies (reformulation LLM call, optional judge LLM call). Both are isolated behind `LLMService` methods that take simple inputs and return strings/bools. Substitution pattern from existing tests (see `tests/chat/test_session.py`):

```python
mock_llm = MagicMock(spec=LLMService)
mock_llm.reformulate_query.return_value = "consulta reformulada"
mock_llm.judge_sufficiency.return_value = True
```

For richer scripting, a `FakeLLMService` class with a queue of responses works well:

```python
class FakeLLM:
    def __init__(self, reformulations: list[str], judge_results: list[bool] | None = None):
        self._refs = list(reformulations)
        self._judges = list(judge_results or [])
    def reformulate_query(self, **_): return self._refs.pop(0)
    def judge_sufficiency(self, **_): return self._judges.pop(0)
```

`FakeRetrievalService` mirrors this with per-call result queues. **Result:** every loop test is deterministic — given queue inputs, outputs are exact. No timing, no randomness, no actual LLM/QMD calls.

## Security Domain

> Security enforcement default is "enabled" per orchestrator standard. No explicit `security_enforcement: false` in `.planning/config.json`.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Single-user local CLI; no auth surface |
| V3 Session Management | no | No web sessions |
| V4 Access Control | no | Single-user; no multi-tenant boundaries |
| V5 Input Validation | yes | User query is passed through to LLM and to QMD shell-out; existing `_resolve_identifier` validates QMD identifiers; query content is not executed (only embedded in prompts and shell args via tuple — `subprocess.run` with tuple argv avoids shell injection per existing pattern) |
| V6 Cryptography | no | No new cryptographic primitives |
| V7 Error Handling | yes | Existing pt-BR error pattern with recovery hints; new errors (orchestrator-internal) should follow it |
| V9 Communication | yes | Existing `validate_local_endpoint` enforces local-only; no new network calls beyond existing llama.cpp localhost |
| V12 File / Resources | yes | No new file I/O beyond existing `qmd get`; carry-forward already validates fetch results |

### Known Threat Patterns for Local-CLI Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection in user query attempting to coerce reformulation to leak content | Information Disclosure | Reformulation prompt instructs single-line pt-BR query output; trace logs only the new query; no tool execution wired to reformulation output |
| Path traversal in QMD identifiers | Tampering | `_resolve_identifier` already rejects `/` and `\` |
| Shell injection via query | Tampering | `subprocess.run(tuple_argv, ...)` already used; query passed as argv element, not interpolated |
| Sensitive content in trace logs | Information Disclosure | RetrievalAttempt dataclass structurally excludes content fields; PRIV-03 test pins this |
| Latency DoS via runaway loop | DoS | `retrieval_max_attempts` hard cap (1–4); validator rejects out-of-range |

**Planner takeaway:** No new security surfaces. The privacy-floor risk (PRIV-03 trace leakage) is addressed structurally by dataclass design and pinned by a test.

## Environment Availability

> Phase has no new external dependencies. Skip detailed audit.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `qmd` CLI | All retrieval (existing) | (assumed yes — Aurora is operational) | — | — |
| llama.cpp HTTP server | All LLM calls (existing) | (assumed yes — Aurora is operational) | — | — |
| Python stdlib | Orchestrator | yes | 3.10+ (existing) | — |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Reformulation latency on Qwen3-8B-Q8_0 ranges 200–600ms on Metal, 1.5–4s on CPU | Local-LLM Constraints | If actual is much higher, D-12's 2.5× budget is tight on slow setups. Plan must measure on the target machine. |
| A2 | Sufficiency judge latency ranges 150–400ms on Metal | Local-LLM Constraints | Same — opt-in feature, so blast radius is limited to users who enable it. |
| A3 | Jaccard threshold 0.7 is a reasonable starting point for "near-identical" detection | Loop Bounding | If too lax, loop wastes attempts; if too strict, real reformulations are rejected. Tune in PLAN. |
| A4 | Default `retrieval_min_top_score=0.35` and `retrieval_min_context_chars=800` are reasonable v1 starting points | Sufficiency Signals | Per CONTEXT this is Claude's discretion — planner must sample existing failure cases before locking. |
| A5 | Stripping `prompt-cache` opportunity for reformulation/judge calls is acceptable (no shared prefix with main stream) | Local-LLM Constraints | True per llama.cpp behavior; verifiable by checking llama.cpp logs in spot-check. |
| A6 | The codebase has no `pyproject.toml` test config that would conflict with new test files | Validation Architecture | Verifiable by `cat pyproject.toml`; existing `tests/` layout suggests no special config needed. |
| A7 | `ChatSession._apply_carry_forward` running once before orchestrator (and never inside) is sound | Pitfalls / Code Examples | High confidence based on reading the implementation; integration test pins it. |

**If any A1–A4 assumption is wrong:** the phase still ships, but defaults and validators may need a follow-up tweak. None are blocking.

## Open Questions

1. **Should `QMDSearchHit` carry a `origin` tag (`"hybrid" | "keyword"`) so per-mode score thresholds are clean?**
   - What we know: Currently `_keyword_fallback` uses `min_score=0.10` for keyword vs `0.30` for hybrid; scores are commingled in result lists.
   - What's unclear: Whether mixed-mode result sets pass deterministic sufficiency in misleading ways.
   - Recommendation: For v1, do NOT modify `QMDSearchHit`. Track origin in the orchestrator by wrapping per-call hit lists. If empirical data shows the threshold is misbehaving on mixed sets, revisit `QMDSearchHit` in a follow-up phase.

2. **Where should the `RetrievalTrace` rendering live — `contracts.py`, a new `trace.py`, or inline in CLI files?**
   - What we know: Aurora keeps contracts pure (frozen dataclasses, no methods beyond properties). CLI files do their own rendering.
   - What's unclear: Whether `RetrievalTrace.to_text()` and `.to_json()` belong on the dataclass.
   - Recommendation: Keep `RetrievalTrace` as a pure dataclass; put rendering helpers in a new `src/aurora/retrieval/trace_render.py` to keep contracts clean. CLI imports the render functions.

3. **Should the loop also fire on `chat` intent if it becomes "ambiguous chat that might need vault"?**
   - What we know: D-04 explicitly excludes chat intent from sufficiency. Phase 04.1 established three-way intent classification.
   - What's unclear: This is a v2 question — out of scope for this phase.
   - Recommendation: Honor D-04. If misclassification ("vault should have been chat" or vice versa) is a real problem, it's an intent-classification phase, not a loop phase.

4. **What does the optional judge prompt do when the context sample is in pt-BR but the query is in another language (CLI-03 says language can change on user request)?**
   - What we know: Existing prompts are pt-BR; CLI-03 allows language switch on request.
   - What's unclear: Whether the judge prompt needs to switch language too.
   - Recommendation: For v1, keep judge prompt in pt-BR — judging "is this enough" doesn't require matching the user's language. Document this as a known limitation.

## Sources

### Primary (HIGH confidence)

- `src/aurora/retrieval/service.py`, `qmd_search.py`, `contracts.py` — read in full this session
- `src/aurora/chat/session.py`, `cli/ask.py`, `cli/chat.py`, `llm/service.py`, `llm/prompts.py`, `llm/streaming.py` — read in full this session
- `src/aurora/runtime/settings.py` — read in full
- `tests/chat/test_session.py`, `tests/chat/test_session_turn_tracking.py` — fixture patterns confirmed
- `.planning/phases/07-iterative-retrieval-loop/07-CONTEXT.md` — locked decisions
- `.planning/phases/04.2-fix-retrieval-quality-.../04.2-CONTEXT.md` — carry-forward composition baseline
- `.planning/REQUIREMENTS.md` — RET-01, RET-03, RET-04, PRIV-03
- `.planning/ROADMAP.md` — Phase 7 entry
- [Self-RAG, Asai et al., ICLR 2024](https://arxiv.org/abs/2310.11511)
- [Corrective RAG (CRAG), Yan et al., 2024](https://arxiv.org/abs/2401.15884)
- [FLARE, Jiang et al., EMNLP 2023](https://arxiv.org/abs/2305.06983)
- [IRCoT, Trivedi et al., ACL 2023](https://arxiv.org/abs/2212.10509)
- [DSPy Multi-Hop tutorial](https://dspy.ai/tutorials/multihop_search/)
- [DSPy Assertions paper, Singhvi et al., 2023](https://arxiv.org/abs/2312.13382)
- [llama.cpp grammars README](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
- [llama.cpp server README — `/v1/chat/completions` `grammar` field](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

### Secondary (MEDIUM confidence)

- [HyDE — Gao et al., 2022](https://arxiv.org/abs/2212.10496) (cited via secondary explainers — Milvus, Haystack, Zilliz)
- [Step-back prompting — Zheng et al., DeepMind](https://arxiv.org/abs/2310.06117) (cited via Unite.AI, LearnPrompting)
- [Phoenix RAG observability](https://phoenix.arize.com/llm-tracing-and-observability-with-arize-phoenix/)
- [Langfuse observability data model](https://langfuse.com/docs/observability/data-model)

### Tertiary (LOW confidence — flagged for verification)

- Latency estimates A1, A2 above (model+hardware-specific; verify on device per Pitfall 6)
- Jaccard threshold 0.7 (A3)

## Metadata

**Confidence breakdown:**
- Standard stack (no new deps): HIGH — confirmed by reading `pyproject.toml`-adjacent imports
- Architecture (orchestrator + composition): HIGH — pattern matches established Aurora conventions exactly
- Sufficiency signal design: HIGH — locked in CONTEXT, well-supported by CRAG literature
- Reformulation prompt design: MEDIUM — pt-BR effectiveness on small models is empirical; A3, A4 assumptions
- Trace shape: HIGH — directly mirrors industry conventions, scoped to local
- Pitfalls: HIGH — derived from concrete codebase risks + RAG literature failure modes
- Latency: MEDIUM — depends on hardware; mitigated by measurement task in PLAN

**Research date:** 2026-05-02
**Valid until:** 2026-06-01 (30 days; iterative-retrieval research is stable; llama.cpp grammar API has been stable since 2024)
