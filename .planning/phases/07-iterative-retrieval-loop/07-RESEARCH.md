# Phase 7: Iterative Retrieval Loop - Research

**Researched:** 2026-05-02
**Domain:** Retrieval orchestration (deterministic sufficiency check + LLM-rewrite rescue)
**Confidence:** HIGH (codebase grounded), MEDIUM (numeric defaults — no production failure logs available)

---

## Planner Takeaways (read this first)

1. **Defaults to lock:** `retrieval_min_top_score=0.35`, `retrieval_min_hits=2`, `retrieval_min_context_chars=800`, `iterative_retrieval_jaccard_threshold=0.7`, `iterative_retrieval_judge=False`, `iterative_retrieval_enabled=True`. Tag all numeric thresholds "tune-after-deploy" — no failure-case dataset exists yet to calibrate them.
2. **Score scales differ:** hybrid (`qmd query`) is 0.0–1.0 with rerank, BM25 (`qmd search`) is unbounded BM25 magnitudes — apply the per-mode threshold based on the **highest-scoring note's `source` AND its origin** (track origin via a new `RetrievedNote.origin: Literal["hybrid","keyword","carry"]` field, or apply the threshold ONLY against hybrid hits and treat any keyword hit as score-passing).
3. **Orchestrator lives in `retrieval/iterative.py`** as a new `IterativeRetrievalOrchestrator` class — composition over inheritance, easier to test, leaves `RetrievalService` untouched.
4. **Trace dataclass `IterativeRetrievalTrace` lives in `retrieval/contracts.py`** alongside existing frozen dataclasses; structurally has NO `content`/`snippet`/`text` field — only `attempts: tuple[AttemptTrace, ...]` where each `AttemptTrace` has `query`, `intent`, `hit_count`, `top_score`, `sufficient`, `reason`, `paths: tuple[str,...]`.
5. **Critical bug to call out:** the cross-attempt merge MUST preserve `insufficient_evidence=True` when both attempts produce zero notes. The naive `result1.notes + result2.notes` merge with `insufficient_evidence=False` (because we have a `RetrievalResult` object) silently breaks RET-04. Spell out: "if `len(merged_notes) == 0`, return `_INSUFFICIENT`, NOT a synthetic `RetrievalResult(ok=True, ...)` with `insufficient_evidence=False`."

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Loop shape (Round 1):**
- **D-01 (Sufficiency signal):** Deterministic by default. The check combines top-1 score, hit count above floor, and assembled-context character length. An optional LLM judge runs AFTER the deterministic check passes — gated behind `iterative_retrieval_judge: bool = False`. Pure-LLM-always was rejected; deterministic-only was rejected.
- **D-02 (Visibility):** When the loop fires, Aurora prints a brief `revisando busca…` (pt-BR) to stderr while reformulation + second retrieval run. OVERT, not silent. Reformulated query NOT shown in status line (that's `--trace` territory).
- **D-03 (Cap):** Hard cap of **one reformulation** → maximum two retrievals per question. NOT configurable.
- **D-04 (Scope):** Loop applies to BOTH `aurora ask` and `aurora chat`. Inside chat: vault-intent and memory-intent turns; never chat-intent.

**Reformulation (Round 2):**
- **D-05 (Strategy):** LLM rewrite — single non-streaming LLM call returning a new pt-BR query string. HyDE/step-back/heuristic-first all rejected.
- **D-06 (Reformulation prompt input):** LLM sees original query AND sufficiency reason ("1 hit, top score 0.18"). Does NOT see note titles, paths, or content.
- **D-07 (Carry-forward composition):** Carry-forward applies **once, before attempt 1 only**. Reformulated attempt 2 is a fresh search — NO carry-forward re-application.
- **D-08 (Memory-turn scope):** Loop applies to memory-intent turns as well as vault-intent turns.

**Observability, persistence, escape hatches (Round 3):**
- **D-09 (Trace surface):** New `--trace` flag on `aurora ask` and `aurora chat`. Per-attempt structured trace AFTER answer. Stderr (text) or `trace` key in stdout JSON. NO persistent log file.
- **D-10 (Reformulation persistence):** Reformulated queries persisted to chat history JSONL as system-role entries with literal `[reformulation] ` prefix. Filtered out before `ChatHistory.get_recent` returns. Two operations pinned by tests: (a) reformulation appears in JSONL, (b) `get_recent` excludes them.
- **D-11 (Disable kill-switch):** Settings field `iterative_retrieval_enabled: bool = True`, exposed via `aurora config`. Default ON. NO per-command CLI flag. When False, behavior matches today's single-shot byte-for-byte (regression test).
- **D-12 (Diversity guard):** Token-Jaccard similarity ≥ 0.7 → exit loop early, fall through to insufficient-evidence path. Threshold tunable.
- **D-13 (Privacy):** Trace contains paths, scores, hit counts, queries only. NEVER note content. STRUCTURAL: dataclass must NOT have `snippet`/`content`/`text` field.

### Claude's Discretion

- Sufficiency threshold defaults (`retrieval_min_top_score`, `retrieval_min_hits`, `retrieval_min_context_chars`)
- LLM judge ambiguity policy ("sim porque nao falta nada" → ?)
- Exact pt-BR phrasing of reformulation prompt and `revisando busca…` status
- Where orchestrator class lives (recommended: `retrieval/iterative.py`)
- Trace dataclass shape (planner picks fields)
- Test fixture strategy (FakeLLM + tiered FakeBackend)

### Deferred Ideas (OUT OF SCOPE)

- Cross-encoder reranker
- HyDE / query expansion at attempt 1
- Multi-step reasoning beyond retrieval
- Eval harness consuming `--trace` (separate phase)
- Adaptive thresholds (auto-tune)
- Persistent trace log file (`~/.aurora/traces.jsonl`)
- Per-command `--no-iterative` flag
- Configurable cap > 1 reformulation

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RET-01 (enhanced) | User can ask questions and receive grounded answers | The loop only changes orchestration — answer path (`ask_grounded` / grounded prompts) untouched (see Section 6) |
| RET-03 (enhanced) | Hybrid retrieval (keyword + semantic) for evidence | Phase 04.2 already wired keyword fallback inside backend; the loop wraps both modes uniformly via the existing `RetrievalService.retrieve*` API (see Section 2) |
| RET-04 (preserved) | Explicit "insufficient evidence" when context not enough | Cross-attempt merge MUST preserve `insufficient_evidence=True` on double-empty (see Pitfalls + Section 6) |
| PRIV-03 (load-bearing) | Logs avoid leaking sensitive note content | Trace dataclass structurally snippet-free; secret-injection test pins both stderr and stdout (see Section 10) |
</phase_requirements>

---

## 1. Sufficiency Threshold Defaults

### Context

The deterministic sufficiency check is the load-bearing signal — it decides whether the loop fires at all. Three numbers gate the whole feature:

- `retrieval_min_top_score` — top-1 hit must score ≥ this
- `retrieval_min_hits` — at least N notes returned
- `retrieval_min_context_chars` — assembled context must be ≥ this many chars

I searched for production failure cases:
- **UAT artifacts:** only `01-UAT.md` (Phase 1 runtime baseline) and `05-HUMAN-UAT.md` (operational surface) exist. Neither contains retrieval-quality failure traces — they're about CLI plumbing.
- **04.x SUMMARY files:** Phases 04.1 and 04.2 ship the carry-forward / keyword-fallback fixes, but no captured "this query returned bad evidence" examples. The 04.2-CONTEXT references a "Rosely" anecdote conceptually, not as a logged trace.
- **Chat history JSONL:** runtime artifact under `~/.config/aurora/chat_history.jsonl` — not in the repo. Cannot sample.
- **Conclusion:** no real failure-case dataset is available to calibrate thresholds quantitatively. Defaults are educated v1 guesses; should be revisited once `--trace` ships and produces a few weeks of data.

### Recommendation

```python
# src/aurora/runtime/settings.py — additions

retrieval_min_top_score: float = 0.35   # hybrid (qmd query) scale; see Section 2
retrieval_min_hits: int = 2              # one hit is rarely enough breadth
retrieval_min_context_chars: int = 800   # ~ one full note worth of body
```

**Rationale per knob (planner: copy these into the validator docstrings):**

- **`retrieval_min_top_score=0.35` (hybrid scale):** existing `retrieval_min_score` default is `0.30` (the FILTER threshold passed to `qmd query --min-score`). Sufficiency is "is the top hit GOOD" — must be slightly above the filter floor or the gate is meaningless. `0.35` is `+0.05` above the existing filter, leaving margin without tripping on every borderline result.
- **`retrieval_min_hits=2`:** one hit is typically too narrow for any reasonable cross-citation. Two hits = the LLM can corroborate. Keeps the gate lenient (top-K is 15 — getting 2 hits should be common when the query is well-formed).
- **`retrieval_min_context_chars=800`:** `MAX_CONTEXT_CHARS=24_000` is the upper bound. 800 is roughly the body length of a single short note. Below 800 chars means either one tiny note or all hits had `fetch()` fail — both are signals the rescue path should fire.

**Validators (mirror existing `retrieval_top_k` pattern):**

```python
@field_validator("retrieval_min_top_score")
@classmethod
def _validate_min_top_score(cls, value: float) -> float:
    if value < 0.0 or value > 1.0:
        raise ValueError("retrieval_min_top_score deve estar entre 0.0 e 1.0.")
    return value

@field_validator("retrieval_min_hits")
@classmethod
def _validate_min_hits(cls, value: int) -> int:
    if value < 1 or value > 10:
        raise ValueError("retrieval_min_hits deve estar entre 1 e 10.")
    return value

@field_validator("retrieval_min_context_chars")
@classmethod
def _validate_min_context_chars(cls, value: int) -> int:
    if value < 100 or value > 24_000:
        raise ValueError("retrieval_min_context_chars deve estar entre 100 e 24000.")
    return value
```

### Planner takeaway

Lock `0.35 / 2 / 800` for v1. Document each as "tune-after-deploy" in the SUMMARY's `key-decisions` section so a future calibration phase knows the provenance.

---

## 2. Hybrid (qmd query) vs BM25 (qmd search) Score Scales

### Context

`qmd query --json` returns hybrid scores in 0.0–1.0 (semantic + BM25 + LLM rerank, normalized). `qmd search --json` returns raw BM25 scores — these are typically larger numbers (e.g. 1.5, 4.2, 12.0) and the existing `keyword_search` uses `min_score=0.10` only because the `qmd search` `--min-score` flag accepts the same numeric scale but the meaningful BM25 floor is much lower than the meaningful hybrid floor.

After `RetrievalService.retrieve()` runs, `_dedup_hits()` merges hybrid hits and keyword hits into one list, sorted by score descending. **A keyword-only hit with raw BM25 score 4.2 will dominate a hybrid hit at 0.92** in the merged list. This is fine for *ordering* (BM25 hit IS the right note for proper-noun queries) but it makes any single-threshold sufficiency check on the merged top-1 score nonsensical:

- A query that triggered keyword fallback might "pass" sufficiency with `top_score=4.2` against a `0.35` threshold — even when the keyword hit is a weak partial match and the hybrid path returned nothing.
- A pure hybrid query rightly evaluated against `0.35` could be conflated with a keyword query where `0.35` is meaningless.

### Recommendation

**Track origin per hit.** Add an `origin: Literal["hybrid", "keyword", "carry"] = "hybrid"` field to `RetrievedNote` (frozen dataclass — additive, default value preserves existing call-sites). Then the sufficiency check applies the threshold ONLY to the highest-scoring `origin == "hybrid"` note:

```python
def _check_sufficiency(result: RetrievalResult, settings: RuntimeSettings) -> tuple[bool, str]:
    """Returns (sufficient, reason). Reason is empty if sufficient."""
    if result.insufficient_evidence:
        return False, "zero hits"
    hit_count = len(result.notes)
    if hit_count < settings.retrieval_min_hits:
        return False, f"{hit_count} hit(s)"
    context_len = len(result.context_text)
    if context_len < settings.retrieval_min_context_chars:
        return False, f"context {context_len} chars"
    # Top-score check ONLY against hybrid hits (BM25 keyword scores are unbounded)
    hybrid_scores = [n.score for n in result.notes if n.origin == "hybrid"]
    if hybrid_scores:
        top = max(hybrid_scores)
        if top < settings.retrieval_min_top_score:
            return False, f"top score {top:.2f}"
    # If no hybrid hits at all, treat keyword/carry as score-passing
    # (we can't compare BM25 to a hybrid threshold meaningfully)
    return True, ""
```

**Why this works:**
- A pure-hybrid query is judged on its hybrid score (correct semantics).
- A pure-keyword query (proper-noun-only) is judged on hit count + context length, NOT on the BM25 score (we don't have a calibrated BM25 threshold).
- A mixed query (both ran, both returned hits) is judged on hybrid top-score AND the count/length floors.

**Carry-forward note:** `_apply_carry_forward` injects notes with `score=0.0`. Tagging them `origin="carry"` keeps them out of the top-score check by construction.

**Planner: this requires a new field on `RetrievedNote`. Add it to the contract and update existing call sites (4–5 spots in `retrieval/service.py` and `chat/session.py`) to pass `origin="hybrid"` (default) or `origin="keyword"` / `origin="carry"` explicitly.** Existing tests all use the default — additive change.

### Planner takeaway

Add `RetrievedNote.origin` field. Sufficiency check only applies the top-score threshold to hybrid-origin hits. Keyword/carry hits pass the score check by definition (they're scored on a different scale).

---

## 3. LLM Judge Ambiguity Policy

### Context

The opt-in judge (`iterative_retrieval_judge=True`, default False) runs a small non-streaming LLM call AFTER the deterministic check passes — to catch nuanced thin cases the deterministic gates missed. The prompt asks "este contexto basta para responder a pergunta?" and expects "sim" or "não". Real local LLMs (Qwen3-8B at the project's default) frequently produce:

- Pre-amble: "Sim, o contexto é suficiente porque..."
- Hedged negatives: "Provavelmente não, faltam detalhes..."
- Mixed: "sim porque nao falta nada" — contains both tokens
- Off-prompt: "O contexto fala sobre Python." — no verdict at all

A naive `"sim" in response.lower()` check FAILS on "sim porque nao falta nada" (returns True when the answer is genuinely affirmative) but ALSO false-positives on "Não foi possível, mas sim em parte" (returns True when the answer is mostly negative). Conversely a naive `"não" in lower()` over-fires.

### Recommendation: "Negative wins on ambiguity, default to insufficient on no verdict"

The asymmetric cost argument: an unnecessary reformulation costs ~1 LLM call (cheap, ~1–3 seconds — Section 9). A missed thin case costs the user a bad answer they may act on. Conservatism is right.

**Parsing approach:**

```python
import re

# Whole-word match anchored at start of stripped response (after any pre-amble period/comma).
# Captures common patterns: "sim", "Sim,", "Sim.", "sim porque...", "**sim**"
_AFFIRMATIVE = re.compile(r"^\W*(sim|yes)\b", re.IGNORECASE)
_NEGATIVE = re.compile(r"^\W*(n[aã]o|no)\b", re.IGNORECASE)

def _parse_judge_verdict(raw: str) -> bool:
    """Returns True if the judge says context is sufficient.

    Policy: negative wins on tie, no-verdict counts as insufficient.
    """
    text = raw.strip()
    if not text:
        return False  # No verdict -> insufficient

    # Look at first non-empty sentence only (LLMs put the verdict first when prompted to)
    first_segment = re.split(r"[.\n!?]", text, maxsplit=1)[0].strip()

    has_neg = bool(_NEGATIVE.search(first_segment))
    has_aff = bool(_AFFIRMATIVE.search(first_segment))

    if has_neg:           # Negative wins: covers "não, mas sim em parte"
        return False
    if has_aff:
        return True
    return False           # No verdict -> insufficient (fail-closed)
```

**Why first-segment only:** the prompt instructs "responda apenas com 'sim' ou 'não' na primeira linha". Real LLMs often comply on the first line then ramble; analyzing only the first segment makes the contract robust without trying to parse free prose.

**Failure mode "neither word":** model returned an off-topic completion. Treated as insufficient — extra reformulation is cheap, and an off-prompt judge response signals the model is also likely to mis-answer the user's question, so re-trying retrieval is the right move.

### Suggested judge prompt (pt-BR, ~80 tokens — minimizes latency cost)

```
SUFFICIENCY_JUDGE_PROMPT = """Voce e um juiz de suficiencia de contexto.

Pergunta original: {query}

Contexto recuperado:
{context_text}

O contexto acima e suficiente para responder a pergunta de forma fundamentada e citavel?

Responda APENAS na primeira linha:
sim - se o contexto basta
nao - se falta informacao essencial

Nao explique. Nao reformule. Apenas: sim ou nao."""
```

**Privacy note:** this prompt embeds the assembled context in the LLM call. The LLM call is local (PRIV-01) so this is fine — but the test suite must verify the judge call only goes to the LOCAL endpoint.

### Planner takeaway

Use first-segment regex parsing with negative-wins-on-tie, no-verdict = insufficient. Pin the parsing logic with five tests: clean "sim", clean "não", "sim porque nao falta nada" → True, "não, mas sim em parte" → False, garbage string → False.

---

## 4. Reformulation Prompt — Exact pt-BR Phrasing

### Context

The reformulator sees ONLY: (a) original query, (b) sufficiency reason ("1 hit, top score 0.18"). It does NOT see paths or note content (D-06, privacy by construction). It must produce ONE substantively different pt-BR query string. The diversity guard (Jaccard ≥ 0.7) catches near-duplicate rewrites — this is the safety net, but the prompt itself should encourage divergence.

### Prompt design choices

- **System + user split:** YES. The instruction lives in the system message ("você é um reformulador"). The query + reason go in the user message. This mirrors the existing `INTENT_PROMPT` style (single user message with template) but separates persona from task — measured to be more robust on small local models.
- **Instruction-first, not example-first:** examples in `INTENT_PROMPT` work because intent classification has discrete categories. Reformulation is open-ended; examples would bias toward example-shaped rewrites. Use 2–3 brief "estratégias" instead.
- **Length budget:** reformulator output bounded to one line (one query). Prompt itself ~150 tokens to keep latency low (Section 9).

### Recommended template

```python
# src/aurora/llm/prompts.py — additions

REFORMULATION_SYSTEM_PROMPT = """Voce reformula consultas para uma base de conhecimento pessoal.

Sua tarefa: dada uma consulta original que retornou poucos resultados, gerar UMA nova consulta substancialmente diferente que tenha mais chance de encontrar evidencia relevante.

Estrategias possiveis:
- Trocar termos amplos por especificos (ou vice-versa)
- Reformular como pergunta direta vs descritiva
- Usar sinonimos ou termos relacionados em pt-BR
- Adicionar contexto temporal ou tematico implicito

Regras:
- Responda APENAS com a consulta reformulada, sem explicacao, sem prefixo, sem aspas
- Maximo 15 palavras
- Sempre em pt-BR
- NUNCA repita a consulta original literalmente"""

REFORMULATION_USER_PROMPT = """Consulta original: {query}

Motivo da reformulacao: {reason}

Reformule:"""
```

**Why this shape:**
- "Estrategias" guides without constraining — keeps the rewrite open enough for LLM creativity but signals the rewrite types that historically work for personal-vault retrieval.
- "Maximo 15 palavras" — bounds the output, prevents the LLM from generating a paragraph the diversity check then has to mangle.
- "NUNCA repita a consulta original literalmente" — a soft second line of defense behind the Jaccard guard.
- The reason field gets a natural-language summary like `"apenas 1 hit, score 0.18"` — formatted by `_check_sufficiency`'s reason string. The LLM uses this only to know *which way* to push (more specific vs broader), not to see the actual notes.

**Service signature:**

```python
# src/aurora/llm/service.py — additions

def reformulate_query(self, original_query: str, reason: str) -> str:
    """Generate a substantially different pt-BR query from original + sufficiency reason.

    Non-streaming. Returns one-line reformulated query (caller responsible for diversity check).
    """
    messages = [
        {"role": "system", "content": REFORMULATION_SYSTEM_PROMPT},
        {"role": "user", "content": REFORMULATION_USER_PROMPT.format(
            query=original_query, reason=reason)},
    ]
    raw = self._sync_fn(
        endpoint_url=self._endpoint_url,
        model_id=self._model_id,
        messages=messages,
    )
    # Strip surrounding quotes and trailing punctuation the LLM sometimes adds
    return raw.strip().strip('"').strip("'").rstrip(".?!").strip()
```

### Planner takeaway

System+user split, instruction-with-strategies (no examples), 15-word cap, response-cleaning post-processor (strips quotes/punctuation). Pin one test that mocks `_sync_fn` returning `'"o que escrevi sobre produtividade ontem?"'` and asserts the cleaner returns `o que escrevi sobre produtividade ontem`.

---

## 5. Status Line — Exact pt-BR Phrasing + Delivery Mechanism

### Context

`ChatSession` already has an `on_status: Callable[[str], None]` injection point. `_handle_vault_turn` and `_handle_memory_turn` already emit status updates ("Buscando no vault...", "Encontrei N nota(s). Gerando resposta..."). `aurora chat` wires it to `typer.echo(msg, err=True)`. `aurora ask` does NOT use a callback — it emits status directly: `typer.echo("Analisando pergunta...", err=True)`.

The two surfaces have **divergent UX patterns** today. The loop must compose with both.

### Recommendation

**Phrasing:** `revisando busca…` (lowercase, with U+2026 ellipsis, no trailing newline distinct from echo's auto-newline).

Match existing in-flight verbs ("Buscando no vault...", "Salvando memoria...", "Gerando resposta..."). Lowercase first letter would clash — use sentence case to match the codebase ("Revisando busca…"). With ellipsis it reads as "in progress".

**Final pt-BR text recommendation:** `Revisando busca...` (three ASCII dots — the codebase uses ASCII triple-dots throughout, never U+2026; consistency wins over typographic correctness).

**Delivery mechanism — make `aurora ask` adopt the callback pattern**:

In `aurora ask`, today's status output is direct `typer.echo(..., err=True)` calls. The orchestrator needs a way to emit `Revisando busca...` on attempt-2 trigger. Two options:

1. **Pass `on_status` callback to the orchestrator** (matches `ChatSession` exactly). Recommended.
2. **Have the orchestrator write to stderr directly.** Tighter coupling; harder to test silently.

Recommended call pattern for the orchestrator:

```python
class IterativeRetrievalOrchestrator:
    def __init__(
        self,
        *,
        retrieval: RetrievalService,
        llm: LLMService,
        settings_loader: Callable[[], RuntimeSettings] = load_settings,
        on_status: Callable[[str], None] = lambda _msg: None,
        history: ChatHistory | None = None,  # for [reformulation] persistence (D-10)
    ) -> None: ...

    def execute(
        self,
        query: str,
        *,
        intent: str,                   # "vault" or "memory"
        search_strategy: str,
        search_terms: list[str],
        # Carry-forward applied externally (D-07)
    ) -> tuple[RetrievalResult, IterativeRetrievalTrace]:
        ...
        if not sufficient_attempt_1:
            self._on_status("Revisando busca...")
            # ... reformulate, retrieve attempt 2, merge ...
        return final_result, trace
```

In `aurora ask` (currently no `on_status`), wire it the same way `aurora chat` does:

```python
def _status(msg: str) -> None:
    if not json_output:
        typer.echo(msg, err=True)
```

In JSON mode the status is silent (consistent with how today's "Encontrei N notas..." echoes are gated on `not json_output`).

### Planner takeaway

Use `Revisando busca...` (sentence case, ASCII triple-dot) emitted via injected `on_status` callback that both `aurora ask` (new) and `aurora chat` (existing) wire to `typer.echo(msg, err=True)`, gated on `not json_output` for ask. Pin one test per surface that asserts the literal string appears on stderr when the loop fires.

---

## 6. Disabled-Path Semantics — What "Byte-for-Byte" Means Operationally

### Context

D-11 says when `iterative_retrieval_enabled=False`, behavior matches today's single-shot retrieval byte-for-byte. "Byte-for-byte" is loose — needs a precise contract or it will drift.

### Recommendation: define disabled mode as four pinned operational guarantees

When `iterative_retrieval_enabled=False`:

1. **Same retrieval result.** The orchestrator MUST return exactly the `RetrievalResult` from a single call to `RetrievalService.retrieve*()` (with carry-forward applied per D-07). No merging, no second attempt. `result.notes` and `result.context_text` are byte-identical to today's path.
2. **Same LLM calls.** Zero calls to `reformulate_query` or `judge_sufficiency`. Pinned by mock-spy assertion on the LLM service.
3. **Same chat history JSONL.** Zero `[reformulation]` entries appear. Pinned by `[r for r in history.load() if r["content"].startswith("[reformulation] ")] == []`.
4. **Trace is empty but well-formed.** When `--trace` is set with `iterative_retrieval_enabled=False`, the trace shows ONE attempt (the only attempt), correctly populated. NOT a missing trace — that would surprise users who use `--trace` to inspect everything.

**Regression test (planner: this is the critical pin):**

```python
def test_disabled_loop_matches_single_shot_behavior(monkeypatch, tmp_path):
    """When iterative_retrieval_enabled=False, behavior == today's single-shot."""
    # Set up settings with loop disabled
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path))
    settings = RuntimeSettings(iterative_retrieval_enabled=False)
    # ... save settings ...

    # Capture path A: pre-loop single-shot (golden — call retrieve directly)
    backend = _fake_backend(thin_response)
    service = RetrievalService(search_backend=backend)
    golden = service.retrieve("query")

    # Capture path B: orchestrator with loop disabled
    orchestrator = IterativeRetrievalOrchestrator(retrieval=service, llm=fake_llm, ...)
    actual, trace = orchestrator.execute("query", intent="vault", ...)

    # Pin all four guarantees
    assert actual.notes == golden.notes              # byte-identical notes tuple
    assert actual.context_text == golden.context_text  # byte-identical context
    assert actual.insufficient_evidence == golden.insufficient_evidence
    assert fake_llm.reformulate_query.call_count == 0
    assert fake_llm.judge_sufficiency.call_count == 0
    assert len(trace.attempts) == 1                  # one attempt, well-formed
    assert trace.attempts[0].reason == ""            # no rescue triggered
```

### Planner takeaway

Pin four guarantees: same notes/context, zero rescue LLM calls, no `[reformulation]` history entries, trace has exactly one attempt. The orchestrator's `execute()` MUST early-return after attempt 1 when the disable flag is set — don't even run sufficiency check (skipping the check is part of "byte-for-byte" since today's single-shot has no check).

---

## 7. `get_recent` Filter for `[reformulation]` Entries

### Context

Today's `ChatHistory.get_recent`:

```python
def get_recent(self, *, max_turns: int = 10) -> list[dict[str, str]]:
    all_records = self.load()
    max_messages = max_turns * 2
    recent = all_records[-max_messages:] if len(all_records) > max_messages else all_records
    return [{"role": r["role"], "content": r["content"]} for r in recent]
```

"max_turns" = N user+assistant pairs, so `max_messages = N * 2`. Records are typed `role: user|assistant|system`. There is **no system role today** — adding `system` records (`[reformulation] ...`) introduces a new role into the JSONL.

**Critical bug to avoid:** if the slicing happens BEFORE the filter, reformulation entries can steal slots from real assistant turns. Example: with `max_turns=10`, 20 messages are kept. If the last 4 are `[user, assistant, system(reformulation), system(reformulation)]`, the user only sees 9 real pairs in their LLM context — silent context drop.

### Recommendation: filter BEFORE slice, with minimal blast-radius edit

```python
REFORMULATION_PREFIX = "[reformulation] "

def get_recent(self, *, max_turns: int = 10) -> list[dict[str, str]]:
    """Return last max_turns user+assistant pairs as messages for LLM context.

    System-role records prefixed with '[reformulation] ' are filtered out BEFORE
    slicing, so they never steal slots from real conversation turns (D-10).
    """
    all_records = self.load()
    # Filter out reformulation system entries before applying max-turns slice
    conversational = [
        r for r in all_records
        if not (r["role"] == "system" and r["content"].startswith(REFORMULATION_PREFIX))
    ]
    max_messages = max_turns * 2
    recent = conversational[-max_messages:] if len(conversational) > max_messages else conversational
    return [{"role": r["role"], "content": r["content"]} for r in recent]
```

**Diff size:** 5 added lines, 0 removed. Pure additive — existing behavior unchanged when no reformulation entries exist.

### Pinned tests (planner: spec these exactly)

```python
class TestGetRecentFiltersReformulations:
    def test_reformulation_appears_in_jsonl_after_thin_then_thick(self, tmp_path):
        """[reformulation] system entry persists to disk."""
        history = ChatHistory(path=tmp_path / "h.jsonl")
        history.append_turn("user", "primeira pergunta")
        history.append_turn("system", "[reformulation] segunda forma da pergunta")
        history.append_turn("assistant", "resposta")
        records = history.load()
        assert any(
            r["role"] == "system" and r["content"].startswith("[reformulation] ")
            for r in records
        )

    def test_get_recent_excludes_reformulation_entries(self, tmp_path):
        """get_recent never returns [reformulation] system records."""
        history = ChatHistory(path=tmp_path / "h.jsonl")
        history.append_turn("user", "q1")
        history.append_turn("system", "[reformulation] q1 reformulada")
        history.append_turn("assistant", "a1")
        recent = history.get_recent(max_turns=10)
        assert all(
            not (m["role"] == "system" and m["content"].startswith("[reformulation] "))
            for m in recent
        )

    def test_filter_happens_before_slice(self, tmp_path):
        """Reformulation entries must not steal slots from real turns under max_turns cap."""
        history = ChatHistory(path=tmp_path / "h.jsonl")
        # Write 5 real pairs (10 messages) interleaved with 3 reformulations
        for i in range(5):
            history.append_turn("user", f"q{i}")
            history.append_turn("assistant", f"a{i}")
            if i in (1, 2, 3):
                history.append_turn("system", f"[reformulation] q{i} reformulada")
        # max_turns=3 should yield 6 messages — 3 real pairs, NOT slots eaten by reformulations
        recent = history.get_recent(max_turns=3)
        user_msgs = [m for m in recent if m["role"] == "user"]
        assistant_msgs = [m for m in recent if m["role"] == "assistant"]
        assert len(user_msgs) == 3
        assert len(assistant_msgs) == 3
        # And the 3 pairs are the LAST 3 (q2, q3, q4)
        assert user_msgs[-1]["content"] == "q4"
```

### Planner takeaway

Filter system-role `[reformulation] `-prefixed records BEFORE the max-turns slice. Three tests pin: (a) entry persists to JSONL, (b) `get_recent` excludes them, (c) filtering before slicing prevents slot-stealing. Export `REFORMULATION_PREFIX` constant from `chat/history.py` so the orchestrator uses the same string when calling `append_turn("system", REFORMULATION_PREFIX + reformulated_query)`.

---

## 8. Test Fixture Strategy

### Context

The test suite uses MagicMock heavily (see `tests/chat/test_session.py`, `tests/retrieval/test_retrieval_service.py`). The orchestrator needs:

- A way to script LLM responses (reformulations + judge verdicts) by call number.
- A way to script retrieval results (thin then thick on demand).
- Helpers for asserting on the trace.

There's no `tests/conftest.py` at the root and no shared fixtures module today. Test files inline their mock helpers (e.g. `_make_session`, `_mock_backend`).

### Recommendation: small dedicated fakes module, no global conftest

Create `tests/retrieval/fakes.py` (NEW module) with two minimal fakes. Co-locate orchestrator tests in `tests/retrieval/test_iterative.py`.

```python
# tests/retrieval/fakes.py
"""Minimal scripted fakes for iterative retrieval orchestrator tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from aurora.retrieval.contracts import (
    QMDSearchHit,
    QMDSearchResponse,
    RetrievalResult,
    RetrievedNote,
)


@dataclass
class FakeLLM:
    """Scripted LLM service. Indexes responses by call number per method."""

    reformulations: list[str] = field(default_factory=list)
    judge_verdicts: list[str] = field(default_factory=list)
    reformulate_calls: list[tuple[str, str]] = field(default_factory=list)
    judge_calls: list[tuple[str, str]] = field(default_factory=list)

    def reformulate_query(self, original_query: str, reason: str) -> str:
        self.reformulate_calls.append((original_query, reason))
        idx = len(self.reformulate_calls) - 1
        if idx >= len(self.reformulations):
            raise AssertionError(
                f"FakeLLM.reformulate_query call #{idx + 1} not scripted "
                f"(only {len(self.reformulations)} responses queued)"
            )
        return self.reformulations[idx]

    def judge_sufficiency(self, query: str, context_text: str) -> bool:
        self.judge_calls.append((query, context_text))
        idx = len(self.judge_calls) - 1
        if idx >= len(self.judge_verdicts):
            raise AssertionError(
                f"FakeLLM.judge_sufficiency call #{idx + 1} not scripted"
            )
        # Use the same parser the real service uses, to test parser+orchestrator together
        from aurora.llm.service import _parse_judge_verdict
        return _parse_judge_verdict(self.judge_verdicts[idx])


@dataclass
class TieredFakeRetrieval:
    """Scripted RetrievalService. Returns results in order from a tier list."""

    tiers: list[RetrievalResult] = field(default_factory=list)
    retrieve_calls: list[tuple[str, str, list[str]]] = field(default_factory=list)
    _memory_backend: object = None  # ChatSession checks this attribute

    def retrieve(self, query: str, *, search_strategy: str = "hybrid",
                 search_terms: list[str] | None = None) -> RetrievalResult:
        self.retrieve_calls.append((query, search_strategy, search_terms or []))
        idx = len(self.retrieve_calls) - 1
        if idx >= len(self.tiers):
            raise AssertionError(f"TieredFakeRetrieval call #{idx + 1} not scripted")
        return self.tiers[idx]

    # Same shape for retrieve_with_memory / retrieve_memory_first
    retrieve_with_memory = retrieve
    retrieve_memory_first = retrieve


# Convenience builders

def thin_result() -> RetrievalResult:
    """A 'thin' retrieval result that should fail sufficiency check."""
    note = RetrievedNote(path="notas/weak.md", score=0.18, content="x" * 50, source="vault")
    return RetrievalResult(
        ok=True, notes=(note,),
        context_text="--- notas/weak.md ---\n" + ("x" * 50),
        insufficient_evidence=False,
    )


def thick_result(*, n_notes: int = 3) -> RetrievalResult:
    """A 'thick' retrieval result that should pass sufficiency check."""
    notes = tuple(
        RetrievedNote(path=f"notas/strong_{i}.md", score=0.85 - i * 0.05,
                      content="conteudo substantivo " * 80, source="vault")
        for i in range(n_notes)
    )
    context = "\n".join(f"--- {n.path} ---\n{n.content}" for n in notes)
    return RetrievalResult(ok=True, notes=notes, context_text=context, insufficient_evidence=False)


def empty_result() -> RetrievalResult:
    """A retrieval result with zero notes (insufficient_evidence=True)."""
    return RetrievalResult(ok=True, notes=(), context_text="", insufficient_evidence=True)
```

**Usage example:**

```python
def test_thin_then_thick_triggers_one_reformulation(tmp_path):
    fake_llm = FakeLLM(reformulations=["consulta reformulada"])
    fake_retrieval = TieredFakeRetrieval(tiers=[thin_result(), thick_result()])

    orchestrator = IterativeRetrievalOrchestrator(
        retrieval=fake_retrieval, llm=fake_llm,
        settings_loader=lambda: RuntimeSettings(),
    )
    final_result, trace = orchestrator.execute(
        "consulta original", intent="vault", search_strategy="hybrid", search_terms=[],
    )

    assert len(trace.attempts) == 2
    assert trace.attempts[0].sufficient is False
    assert trace.attempts[1].sufficient is True
    assert fake_llm.reformulate_calls == [("consulta original", "top score 0.18")]
    assert final_result.notes == thick_result().notes
```

**Why this shape (and not pytest fixtures):**
- Inline fakes match existing test conventions (`_mock_backend`, `_make_session` are inline helpers, not fixtures).
- Scripted-by-call-number is simpler than `side_effect=lambda x: ...` lambdas — readable failure messages.
- Sharing in `tests/retrieval/fakes.py` (not `conftest.py`) means importing is explicit; pytest auto-import isn't needed and would surprise contributors.

### Planner takeaway

Create `tests/retrieval/fakes.py` with `FakeLLM`, `TieredFakeRetrieval`, and three result builders (`thin_result`, `thick_result`, `empty_result`). Orchestrator tests live in `tests/retrieval/test_iterative.py`. CLI integration tests for `aurora ask --trace` and `aurora chat --trace` live in `tests/cli/test_ask_command.py` (extend) and `tests/cli/test_chat_command.py` (extend), patching `IterativeRetrievalOrchestrator.execute` directly.

---

## 9. Latency Baseline + Measurement Approach

### Context

D-12 (latency budget) was NOT explicitly locked. ROADMAP success criterion 5 says users see `Revisando busca...` while the loop runs — implicit acceptance of "longer than single-shot". The user pre-approved the tradeoff. But the planner needs guidance on *how much longer* is acceptable so verification can flag regressions.

The default model is `Qwen3-8B-Q8_0`, served by local llama.cpp. Reformulation is a sync (non-streaming) call — no first-token-latency benefit. The whole completion must arrive before retrieval-2 can begin.

### Recommendation

**Realistic latencies (Qwen3-8B Q8 on a typical Apple M-series laptop, llama.cpp default config):**

- **Reformulation prompt** (~150 input tokens, ~15 output tokens): typically **0.6–1.5 seconds**.
- **Optional judge prompt** (~250 input tokens, ~3 output tokens): typically **0.5–1.0 seconds** (input-dominated, low output).
- **Second retrieval (`qmd query`)**: typically **0.2–0.8 seconds** (hybrid search + LLM rerank; rerank dominates).
- **Total worst-case extra latency** (judge ON + reformulation + 2nd retrieval): ~3.3 seconds added to single-shot.
- **Total typical extra latency** (judge OFF, default): ~1.0–2.3 seconds added to single-shot.

These are educated estimates from llama.cpp's published throughput numbers for Qwen3-8B Q8 on M-series silicon (~30–50 tokens/sec generation, ~200 tokens/sec prefill). Tag as **MEDIUM confidence** — actual numbers depend on the user's hardware, llama.cpp config, and concurrent load.

### Measurement script (planner: ship as a dev tool, NOT a CI test)

```python
# scripts/bench_iterative_retrieval.py — NEW dev-only file
"""Measure iterative retrieval latency overhead against single-shot baseline.

Usage: aurora must have a configured vault and running llama-server.
    python scripts/bench_iterative_retrieval.py
"""
import time
from aurora.runtime.settings import load_settings
from aurora.retrieval.service import RetrievalService
from aurora.retrieval.qmd_search import QMDSearchBackend
from aurora.llm.service import LLMService
from aurora.retrieval.iterative import IterativeRetrievalOrchestrator

QUERIES = [
    "o que escrevi sobre produtividade",
    "notas sobre Python ontem",
    "Rosely",
    # ... 10–20 representative queries from real usage
]

def bench():
    backend = QMDSearchBackend()
    retrieval = RetrievalService(search_backend=backend)
    llm = LLMService()
    orch = IterativeRetrievalOrchestrator(retrieval=retrieval, llm=llm)

    for q in QUERIES:
        # Single-shot baseline
        t0 = time.perf_counter()
        retrieval.retrieve(q)
        single_ms = (time.perf_counter() - t0) * 1000

        # Iterative path
        t0 = time.perf_counter()
        result, trace = orch.execute(q, intent="vault", search_strategy="hybrid", search_terms=[])
        iter_ms = (time.perf_counter() - t0) * 1000
        n_attempts = len(trace.attempts)

        delta = iter_ms - single_ms
        print(f"{q[:40]:42s}  single={single_ms:6.0f}ms  iter={iter_ms:6.0f}ms  delta={delta:+6.0f}ms  attempts={n_attempts}")

if __name__ == "__main__":
    bench()
```

**Why NOT a CI test:**
- Requires a real running llama-server. CI doesn't have one (the existing test suite mocks `_stream_fn` and `_sync_fn`).
- Latency assertions are flaky in CI (variable hardware).
- Real value is ad-hoc bench during development and after model swaps.

### Happy path / worst case for THIS codebase

- **Happy path:** attempt 1 sufficient → no extra latency, trace has 1 entry.
- **Typical rescue:** attempt 1 thin → reformulation (~1s) + retrieval (~0.5s) = +1.5s.
- **Worst case (judge ON):** attempt 1 sufficient by deterministic check → judge says insufficient (~0.7s) → reformulation (~1s) + retrieval (~0.5s) = +2.2s.
- **Best case (Jaccard guard fires):** attempt 1 thin → reformulation (~1s) → Jaccard ≥ 0.7 → exit early. +1s, no retrieval-2. The user gets insufficient-evidence message.

### Planner takeaway

Ship `scripts/bench_iterative_retrieval.py` as a dev tool, NOT a CI test. Document expected delta as "1–2 seconds typical, up to 3 seconds with judge ON" in the SUMMARY's `key-decisions`. Don't add latency assertions to the test suite. Phase verification can include "run bench manually, paste output into VERIFICATION.md".

---

## 10. PRIV-03 Trace Assertion — Implementation Pattern

### Context

D-13 says trace dataclasses must be **structurally** snippet-free. PRIV-03 says logs must not leak note content. The trace surface is on stderr (text mode) and inside the JSON envelope (`--json` mode). Both must be tested for absence of injected secret strings — and the dataclass shape itself must not have a content-bearing field.

### Recommendation: combine structural assertion + end-to-end injection test

**Trace dataclass shape (planner: live in `retrieval/contracts.py`):**

```python
from dataclasses import dataclass, fields
from typing import Literal

@dataclass(frozen=True)
class AttemptTrace:
    """One attempt within an iterative retrieval execution.

    PRIV-03: structurally MUST NOT contain note content. Only paths, scores,
    counts, queries, and verdict reason strings (which are derived from counts/
    scores, not from note text).
    """
    attempt_number: int                         # 1 or 2
    query: str                                  # original (1) or reformulated (2)
    intent: Literal["vault", "memory"]
    hit_count: int
    top_score: float                            # max hybrid score, or 0.0 if no hybrid hits
    sufficient: bool                            # deterministic + (judge if enabled) verdict
    reason: str                                 # "" if sufficient, otherwise short reason
    paths: tuple[str, ...]                      # paths only — NEVER content


@dataclass(frozen=True)
class IterativeRetrievalTrace:
    """Full per-execution trace surfaced via --trace."""
    attempts: tuple[AttemptTrace, ...]
    judge_enabled: bool
    early_exit_reason: str = ""                 # "" or "high jaccard" or "disabled"


# Banned field names — enforced by structural test
_FORBIDDEN_TRACE_FIELDS = {"content", "snippet", "text", "body", "note_content"}
```

**Structural test (the load-bearing assertion):**

```python
def test_trace_dataclasses_have_no_content_fields():
    """PRIV-03: trace structure must not have any field that could hold note content."""
    from dataclasses import fields
    from aurora.retrieval.contracts import AttemptTrace, IterativeRetrievalTrace

    forbidden = {"content", "snippet", "text", "body", "note_content"}

    for cls in (AttemptTrace, IterativeRetrievalTrace):
        field_names = {f.name for f in fields(cls)}
        offenders = field_names & forbidden
        assert offenders == set(), (
            f"{cls.__name__} contains forbidden content-bearing field(s): {offenders}. "
            "PRIV-03 requires trace dataclasses be structurally snippet-free."
        )
```

This test FAILS at import time if anyone adds a `snippet` field — turning future drift into a build break.

**End-to-end injection test (the behavioral assertion):**

```python
def test_trace_does_not_leak_note_content_in_stderr(tmp_path, monkeypatch):
    """PRIV-03: secret string in note content MUST NOT appear in --trace stderr."""
    SECRET = "SECRET_INJECTED_AURORA_PRIV03_4f9b2c"
    # Build a fake retrieval that returns a note containing SECRET in its content
    note = RetrievedNote(
        path="notas/leak_test.md", score=0.95, content=f"prefix {SECRET} suffix",
        source="vault",
    )
    result_with_secret = RetrievalResult(
        ok=True, notes=(note,),
        context_text=f"--- notas/leak_test.md ---\nprefix {SECRET} suffix",
        insufficient_evidence=False,
    )
    fake_retrieval = TieredFakeRetrieval(tiers=[result_with_secret])
    fake_llm = FakeLLM()  # No reformulations/judges queued — attempt 1 sufficient

    # Patch retrieval/llm into the CLI command
    with patch("aurora.cli.ask.RetrievalService") as mock_rcls, \
         patch("aurora.cli.ask.LLMService") as mock_lcls, \
         patch("aurora.cli.ask.IterativeRetrievalOrchestrator") as mock_ocls:
        # ... wire fakes ...
        result = runner.invoke(app, ["ask", "test query", "--trace"])

    # SECRET must NOT appear in stderr (where text trace lives)
    assert SECRET not in result.stderr, f"PRIV-03 leak: {SECRET} found in stderr"
    # SECRET also must NOT appear in stdout (the answer is mocked away here)
    assert SECRET not in result.stdout

def test_trace_does_not_leak_note_content_in_json_envelope(tmp_path):
    """PRIV-03: secret string MUST NOT appear in --trace --json envelope."""
    SECRET = "SECRET_INJECTED_AURORA_PRIV03_4f9b2c"
    # ... same setup ...
    result = runner.invoke(app, ["ask", "test query", "--trace", "--json"])
    payload = json.loads(result.stdout)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert SECRET not in serialized, f"PRIV-03 leak: {SECRET} found in JSON trace"
```

**Why both:**
- Structural test catches drift at import time. Cheap. Permanent guard.
- Injection test catches accidental leaks even if a future contributor adds a field with a non-banned name (e.g. `excerpt`, `preview`). Belt-and-suspenders.

### Planner takeaway

Two tests pin PRIV-03 together: (1) `test_trace_dataclasses_have_no_content_fields` enforces the dataclass shape via `dataclasses.fields()` introspection against a banned-name set; (2) `test_trace_does_not_leak_note_content_*` injects a unique secret string into a `RetrievedNote.content`, runs `aurora ask --trace` (and `--trace --json`), asserts the secret is absent from both stderr and stdout. Add the unique secret string as a module-level constant so it doesn't collide with anything else in the test suite.

---

## Pitfalls Explicitly Flagged for the Planner

These MUST be addressed in the plan(s); the previous planning round had bugs in these exact spots.

### Pitfall 1: insufficient_evidence preservation on cross-attempt merge

**Symptom:** Both attempts return zero notes. The naive merge produces a synthetic `RetrievalResult(ok=True, notes=(), context_text="", insufficient_evidence=False)` — because the orchestrator built it programmatically and forgot to set `insufficient_evidence=True`. Downstream `ChatSession._handle_vault_turn` checks `if result.insufficient_evidence:` — sees False — proceeds to call `chat_turn` with empty context — LLM hallucinates an answer. **RET-04 silently broken.**

**Fix:** explicit guard in the orchestrator's merge:

```python
def _merge_attempts(r1: RetrievalResult, r2: RetrievalResult) -> RetrievalResult:
    """Merge two retrieval attempts. CRITICAL: preserve insufficient_evidence on double-empty."""
    merged_notes = list(r1.notes) + [n for n in r2.notes if n.path not in {x.path for x in r1.notes}]

    # Both attempts empty -> propagate insufficient
    if not merged_notes:
        # Use the canonical singleton so downstream identity checks work
        from aurora.retrieval.service import _INSUFFICIENT
        return _INSUFFICIENT

    # Re-assemble context (cannot just concat; truncation rules in _assemble_context apply)
    # Use a RetrievalService method or duplicate the logic carefully here
    ...
    return RetrievalResult(ok=True, notes=tuple(merged_notes), context_text=ctx,
                           insufficient_evidence=False)
```

**Pin with test:** `test_double_empty_preserves_insufficient_evidence` — both attempts return `_INSUFFICIENT`, assert `merged.insufficient_evidence is True` AND `merged.notes == ()`.

### Pitfall 2: carry-forward double-dipping (D-07 enforcement)

**Symptom:** Carry-forward applied per attempt instead of once before attempt 1. Attempt 2 sees the carry-forward notes from attempt 1 PLUS fresh attempt 2 hits PLUS the SAME carry-forward notes again. Sufficiency check at attempt 2 falsely passes because the artificially-bloated note count exceeds `retrieval_min_hits`, even when the new query alone is still thin.

**Fix:** apply carry-forward in the orchestrator OUTSIDE the per-attempt loop, exactly once, before attempt 1. The orchestrator's `execute()` should NOT call `_apply_carry_forward` itself — `ChatSession._handle_vault_turn` continues to call it once before invoking the orchestrator. For `aurora ask` (no session), there's no carry-forward — orchestrator runs its loop on the fresh result directly.

**Test:** `test_carry_forward_applied_once_not_per_attempt` — set up a fake retrieval with two thin tiers, mock `_apply_carry_forward` to be a no-op spy, assert it's invoked at most once across the whole orchestrator execution.

### Pitfall 3: trace privacy — accidental field name drift

**Symptom:** A future contributor adds `excerpt: str` (or `preview`, `body`, etc.) to `AttemptTrace` because it's "useful for debugging". The structural test passes (`excerpt` isn't in the banned-name set). The end-to-end test catches it but only if someone runs that exact test.

**Fix:** keep the banned-name set BROAD: `{"content", "snippet", "text", "body", "note_content", "excerpt", "preview", "fragment", "passage"}`. Add a docstring on both trace dataclasses with the literal warning: "PRIV-03 forbids ANY field that could hold note content. Adding such a field will fail `test_trace_dataclasses_have_no_content_fields`. If you need debugging output for development, use a debug log that's NOT exposed via --trace."

### Pitfall 4: ChatHistory kwarg drift

**Symptom:** `ChatHistory.append_turn(role: str, content: str)` is positional-only by convention but not enforced by the signature. The orchestrator calls `history.append_turn("system", "[reformulation] ..." )` — works today. If someone refactors `append_turn` to add a kwarg before content, callers passing positionally break silently.

**Fix:** orchestrator MUST use kwargs explicitly:

```python
self._history.append_turn(role="system", content=f"{REFORMULATION_PREFIX}{reformulated_query}")
```

This is defensive and matches the project's frozen-dataclass / kwarg-heavy style.

### Pitfall 5: Jaccard guard using char-level similarity instead of token-level

**Symptom:** D-12 says token Jaccard. A future maintainer "optimizes" it to a char-level Levenshtein or sequence-matcher ratio. Suddenly "produtividade" and "produtivo" return similarity 0.85 (char overlap) where token Jaccard returns 0.0 (no whole token in common). Reformulation gets blocked when it shouldn't.

**Fix:** module-level docstring on the Jaccard helper with the literal sentence "TOKEN-LEVEL Jaccard. Do not switch to char-level — see Phase 7 RESEARCH §pitfalls."

```python
def _token_jaccard(a: str, b: str) -> float:
    """TOKEN-LEVEL Jaccard similarity between two query strings.

    Token = lowercase word after splitting on whitespace and punctuation.
    Do NOT switch to char-level / Levenshtein / sequence-matcher — those
    capture string-shape similarity, not semantic-word-overlap, and would
    block legitimately divergent rewrites that share affixes.
    """
    import re
    tokens_a = set(re.findall(r"\w+", a.lower()))
    tokens_b = set(re.findall(r"\w+", b.lower()))
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
```

---

## Architectural Responsibility Map

| Capability | Primary Module | Secondary | Rationale |
|------------|---------------|-----------|-----------|
| Sufficiency check (deterministic) | `retrieval/iterative.py` | `runtime/settings.py` (thresholds) | Pure logic operating on `RetrievalResult` — co-located with the orchestrator that uses it |
| Reformulation LLM call | `llm/service.py` | `llm/prompts.py` | Mirror of `classify_intent` — same shape, same module |
| Judge LLM call (opt-in) | `llm/service.py` | `llm/prompts.py` | Same |
| Loop orchestration | `retrieval/iterative.py` | `chat/session.py`, `cli/ask.py` | New module, composition over inheritance |
| Carry-forward integration | `chat/session.py` (existing) | — | Already handled — orchestrator does NOT touch carry-forward |
| Trace data structures | `retrieval/contracts.py` | — | Co-located with `RetrievalResult` etc. |
| Trace surface — text | `cli/ask.py`, `cli/chat.py` | — | Each CLI prints trace in its own native format |
| Trace surface — JSON | `cli/ask.py` | — | `aurora chat` is interactive; `--trace` text-only there |
| `[reformulation]` filter | `chat/history.py` | — | Single edit to `get_recent` |
| Status line emission | Caller-provided `on_status` callback | `cli/ask.py`, `cli/chat.py` | Consistent with existing `ChatSession.on_status` pattern |
| Settings + validators | `runtime/settings.py` | — | Standard pydantic `field_validator` pattern |

---

## Standard Stack (no additions needed)

Phase 7 introduces ZERO new dependencies. Everything is built on existing primitives:

| Primitive | Used For | Where |
|-----------|----------|-------|
| `pydantic.field_validator` | New settings validators | `runtime/settings.py` |
| `dataclasses.dataclass(frozen=True)` | Trace dataclasses | `retrieval/contracts.py` |
| `dataclasses.fields` | Structural privacy assertion | `tests/retrieval/test_iterative.py` |
| `re` | Verdict parsing, Jaccard tokenization | `llm/service.py`, `retrieval/iterative.py` |
| `typer.echo(..., err=True)` | Status line + text trace | `cli/ask.py`, `cli/chat.py` |
| `unittest.mock.MagicMock` + new `FakeLLM`/`TieredFakeRetrieval` | Tests | `tests/retrieval/fakes.py` |

This is healthy — Phase 7 is pure orchestration. No new model, no new library, no new infrastructure.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`pythonpath=["src"]`, `testpaths=["tests"]`) |
| Quick run command | `pytest tests/retrieval/test_iterative.py -x` |
| Full suite command | `pytest -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RET-01/RET-03 | Iterative loop fires on thin attempt 1 | unit | `pytest tests/retrieval/test_iterative.py::TestOrchestrator::test_thin_then_thick_triggers_reformulation` | ❌ Wave 0 |
| RET-04 | Insufficient preserved on double-empty | unit | `pytest tests/retrieval/test_iterative.py::TestOrchestrator::test_double_empty_preserves_insufficient_evidence` | ❌ Wave 0 |
| RET-04 | Disabled-flag matches single-shot byte-for-byte | unit | `pytest tests/retrieval/test_iterative.py::TestDisabledMode::test_matches_single_shot` | ❌ Wave 0 |
| D-10 | Reformulation persists to JSONL | unit | `pytest tests/chat/test_history.py::TestGetRecentFiltersReformulations::test_reformulation_appears_in_jsonl` | ❌ Wave 0 |
| D-10 | get_recent excludes reformulation entries | unit | `pytest tests/chat/test_history.py::TestGetRecentFiltersReformulations::test_get_recent_excludes_reformulation_entries` | ❌ Wave 0 |
| D-10 | Filter happens before slice | unit | `pytest tests/chat/test_history.py::TestGetRecentFiltersReformulations::test_filter_happens_before_slice` | ❌ Wave 0 |
| D-12 | Jaccard ≥ 0.7 exits early | unit | `pytest tests/retrieval/test_iterative.py::TestDiversityGuard::test_high_jaccard_skips_attempt_2` | ❌ Wave 0 |
| D-13 / PRIV-03 | Trace dataclasses snippet-free (structural) | unit | `pytest tests/retrieval/test_iterative.py::TestTracePrivacy::test_trace_dataclasses_have_no_content_fields` | ❌ Wave 0 |
| D-13 / PRIV-03 | Trace stderr does not leak content | integration | `pytest tests/cli/test_ask_command.py::test_trace_does_not_leak_note_content_in_stderr` | ❌ Wave 0 |
| D-13 / PRIV-03 | Trace JSON does not leak content | integration | `pytest tests/cli/test_ask_command.py::test_trace_does_not_leak_note_content_in_json_envelope` | ❌ Wave 0 |
| D-02 | `Revisando busca...` appears on stderr | integration | `pytest tests/cli/test_ask_command.py::test_status_line_emitted_on_loop_fire` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/retrieval/test_iterative.py tests/chat/test_history.py -x` (~10s, hits the new modules)
- **Per wave merge:** `pytest -x` (full suite, ~30s based on existing 200+ test count)
- **Phase gate:** Full suite green before `/gsd-verify-work` + `bench_iterative_retrieval.py` smoke run paste into VERIFICATION.md

### Wave 0 Gaps
- [ ] `tests/retrieval/test_iterative.py` — orchestrator unit tests
- [ ] `tests/retrieval/fakes.py` — `FakeLLM`, `TieredFakeRetrieval`, result builders
- [ ] `tests/chat/test_history.py` — extend `TestGetRecentFiltersReformulations` class (file exists, class is new)
- [ ] `tests/cli/test_ask_command.py` — extend with `--trace` tests (file exists, tests are new)
- [ ] `tests/cli/test_chat_command.py` — extend with `--trace` tests (file exists, tests are new)
- [ ] `scripts/bench_iterative_retrieval.py` — dev-only latency bench (NEW file)

No framework install needed — pytest already configured.

---

## Open Questions

1. **Should the orchestrator pass `IntentResult.search_strategy` and `IntentResult.terms` through to attempt 2?**
   - What we know: D-05 says reformulator outputs ONLY a new query string, not a new intent classification. The reformulated query may need a different strategy (e.g., the original was hybrid but the reformulated query has proper nouns now — should keyword fallback fire?).
   - What's unclear: whether to (a) re-run intent classification on the reformulated query (one MORE LLM call), or (b) reuse the original strategy/terms (cheaper, but may miss the rescue if the reformulation introduces new proper nouns).
   - Recommendation for the planner: reuse the original strategy/terms on attempt 2 (cheaper, simpler). The Phase 04.2 keyword-fallback proper-noun extractor already runs INSIDE `RetrievalService.retrieve` regardless of strategy when proper nouns are detected — so a reformulated query containing "Anderson" still gets BM25 fallback. Don't add a second classify_intent call.

2. **Should `aurora chat --trace` print trace BETWEEN turns (after each turn) or only once at session end?**
   - What we know: D-09 says "per-attempt structured trace AFTER the answer".
   - What's unclear: in interactive chat, "the answer" is each turn's response. Per-turn trace is noisier but more useful.
   - Recommendation: per-turn trace, printed to stderr immediately after each turn's response. Matches `aurora ask` semantics (trace after answer for the single shot) and gives the user immediate insight into what happened.

3. **What if attempt 2 succeeds the deterministic check but the optional judge says insufficient?**
   - The CONTEXT D-01 says judge runs after deterministic. If judge is ON and triggers reformulation, then attempt 2 also runs deterministic + judge.
   - Recommendation: yes, but the cap (D-03) is one reformulation total. So if attempt 2 deterministic-passes but judge-fails, we accept attempt 2 anyway (we've exhausted the reformulation budget). Pin this with a test: `test_judge_fails_attempt_2_still_returns_attempt_2` — judge returns False on attempt 2, orchestrator returns merged result anyway, trace.attempts[1].sufficient is False but the answer is still produced.

---

## Project Constraints (from CLAUDE.md)

No `./CLAUDE.md` was found in the working directory. No project-level constraints to honor beyond what CONTEXT.md and REQUIREMENTS.md already encode.

User-level memory note: Aurora is installed via `uv tool install` snapshot — CLI changes require `uv tool install --reinstall .` (or equivalent) to surface globally. Not relevant to research, but planner should mention reinstall in a SUMMARY's "user setup required" section if Phase 7 changes the CLI surface.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Hybrid (`qmd query`) returns 0.0–1.0 normalized scores; BM25 (`qmd search`) returns unbounded raw scores | §2 | If both are bounded the same way, the per-mode threshold split is unnecessary complexity. Fallback: drop top-score check, rely on hits + context-chars. **Recommended verification:** run `qmd query --json "test"` and `qmd search --json "test"` against a real index, eyeball the score range. |
| A2 | Qwen3-8B Q8 reformulation latency is 0.6–1.5s on M-series silicon | §9 | If 5x higher, the user UX is bad and Phase 7 is a regression. Mitigation: bench script ships in this phase — measure before merging. |
| A3 | Local LLM judge will reliably put "sim"/"não" in the first sentence when prompted | §3 | If the model rambles, parser falls through to "no verdict = insufficient", which is fail-closed. Conservative — over-reformulation is the failure mode, not under-reformulation. |
| A4 | No production `chat_history.jsonl` is available to sample bad-query failures | §1 | If the user CAN provide samples (locally-run Aurora has been used for months), planner should ask. Otherwise defaults are educated v1 guesses. |
| A5 | Token Jaccard 0.7 is a sensible default threshold | §pitfalls | Untested empirically. A future eval phase consuming `--trace` data should validate or re-tune. |

---

## Sources

### Primary (HIGH confidence — codebase-grounded)
- `/Users/jp/Projects/Personal/aurora/.planning/phases/07-iterative-retrieval-loop/07-CONTEXT.md` — locked design decisions D-01 through D-13
- `/Users/jp/Projects/Personal/aurora/src/aurora/retrieval/service.py` — `RetrievalService`, `_INSUFFICIENT`, `_dedup_hits`, `_assemble_context`
- `/Users/jp/Projects/Personal/aurora/src/aurora/retrieval/qmd_search.py` — `search` (hybrid), `keyword_search` (BM25), score scale evidence (BM25 uses `min_score=0.10` floor, hybrid uses `0.30`)
- `/Users/jp/Projects/Personal/aurora/src/aurora/retrieval/contracts.py` — frozen dataclass conventions
- `/Users/jp/Projects/Personal/aurora/src/aurora/chat/session.py` — `_apply_carry_forward`, `on_status` pattern, intent routing
- `/Users/jp/Projects/Personal/aurora/src/aurora/chat/history.py` — `get_recent` current implementation
- `/Users/jp/Projects/Personal/aurora/src/aurora/cli/ask.py` — direct stderr status pattern (no callback today)
- `/Users/jp/Projects/Personal/aurora/src/aurora/cli/chat.py` — callback wiring pattern
- `/Users/jp/Projects/Personal/aurora/src/aurora/llm/service.py` — `classify_intent` (template for `reformulate_query` and `judge_sufficiency`)
- `/Users/jp/Projects/Personal/aurora/src/aurora/llm/prompts.py` — pt-BR prompt conventions
- `/Users/jp/Projects/Personal/aurora/src/aurora/runtime/settings.py` — pydantic settings + `field_validator` pattern
- `/Users/jp/Projects/Personal/aurora/.planning/phases/04.2-fix-retrieval-quality-.../*.md` — carry-forward and keyword-fallback precedents
- Direct `qmd --help` invocation — confirmed `qmd query` (hybrid) and `qmd search` (BM25) are different commands, scores differ

### Secondary (MEDIUM confidence — calibrated by reasoning)
- Sufficiency threshold defaults — derived from existing `retrieval_min_score=0.30` filter floor + reasoned slack
- Latency estimates — derived from published llama.cpp throughput benchmarks for Qwen3-8B Q8 on M-series

### Tertiary (LOW confidence — flagged for validation)
- Token Jaccard 0.7 as the "right" diversity threshold — no empirical basis, will need data from `--trace` to tune

---

## Metadata

**Confidence breakdown:**
- Standard stack & architecture: HIGH — all primitives exist in the codebase
- Numeric defaults (thresholds, latency estimates): MEDIUM — educated v1 values, no production data
- Pitfalls: HIGH — derived from explicit project context (insufficient_evidence merge bug called out by upstream)
- pt-BR phrasing: HIGH — matches established codebase patterns

**Research date:** 2026-05-02
**Valid until:** 2026-06-01 (30 days; codebase patterns stable, threshold defaults should be re-validated after `--trace` data accumulates)
