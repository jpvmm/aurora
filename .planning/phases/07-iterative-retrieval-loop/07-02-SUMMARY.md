---
phase: 07-iterative-retrieval-loop
plan: 02
subsystem: retrieval
tags: [iterative-retrieval, orchestrator, llm-primitives, sufficiency-judge, query-reformulation, priv-03]

# Dependency graph
requires:
  - phase: 07-01
    provides: RetrievedNote.origin Literal field, AttemptTrace + IterativeRetrievalTrace dataclasses, _FORBIDDEN_TRACE_FIELDS structural guard, judge_sufficiency_deterministic pure function, six iterative_retrieval_* settings, _INSUFFICIENT singleton, MAX_CONTEXT_CHARS constant

provides:
  - LLMService.reformulate_query(original_query, reason) -> str with quote-stripping cleanup
  - LLMService.judge_sufficiency(query, context_text) -> bool with negative-wins-on-tie ambiguity policy
  - _parse_judge_verdict module-level helper with five-branch coverage (sim, nao, both, neither, empty)
  - REFORMULATION_SYSTEM_PROMPT, REFORMULATION_USER_PROMPT, SUFFICIENCY_JUDGE_PROMPT (verbatim from RESEARCH §3, §4)
  - IterativeRetrievalOrchestrator class with hardcoded 2-attempt cap (D-03)
  - _STATUS_REVISANDO = "Revisando busca..." constant (D-02)
  - _token_jaccard module-level helper (TOKEN-level, not char-level — RESEARCH §pitfalls 5)
  - _merge_attempts module-level helper that returns _INSUFFICIENT singleton on double-empty (RESEARCH §pitfalls 1, RET-04)
  - _build_attempt_trace module-level helper composing AttemptTrace from result + verdict
  - tests/retrieval/fakes.py module: FakeLLM, TieredFakeRetrieval, thin_result/thick_result/empty_result builders

affects:
  - 07-03 (chat session integration: ChatSession will instantiate IterativeRetrievalOrchestrator and pass first_attempt with carry-forward applied)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - composition-over-inheritance: IterativeRetrievalOrchestrator wraps a retrieve_fn callable rather than subclassing RetrievalService — keeps the loop testable without dragging the full service surface into Wave 2
    - first-attempt-injection: orchestrator.run accepts first_attempt parameter so the caller (ChatSession in 07-03) controls carry-forward composition outside the orchestrator (D-07)
    - hardcoded-policy-constants: 2-attempt cap is a `for ... range(2)` equivalent, not a settings field (D-03); _STATUS_REVISANDO is a module constant, not a parameter
    - token-jaccard-via-set-overlap: re.findall(r"\w+", lower) tokenization + set intersection / union ratio — explicit anti-pattern: do NOT use char-level / SequenceMatcher / Levenshtein (RESEARCH §pitfalls 5)
    - structural-source-introspection-test: TestCarryForwardNotTouchedByOrchestrator uses inspect.getsource() + string-absence assertion to enforce architectural boundary at the source level rather than via runtime/discipline
    - production-parser-in-fake: FakeLLM.judge_sufficiency runs scripted raw responses through the production _parse_judge_verdict so parser policy and orchestrator behavior are exercised together rather than mocked separately
    - fail-loud-fakes: FakeLLM and TieredFakeRetrieval raise AssertionError on unscripted call rather than returning a default — tests must declare every expected call

key-files:
  created:
    - src/aurora/retrieval/iterative.py
    - tests/retrieval/fakes.py
    - tests/retrieval/test_iterative.py
    - tests/llm/test_service_reformulate_judge.py
  modified:
    - src/aurora/llm/prompts.py
    - src/aurora/llm/service.py

key-decisions:
  - "_NEGATIVE/_AFFIRMATIVE regex uses unanchored \\b...\\b boundaries (not ^\\W*) so 'sim porque nao falta nada' is correctly classified as ambiguous-then-False per RESEARCH §3. The plan's draft regex (^\\W*...) would have only matched verdict tokens at the very start of the first segment, missing the conservative-tie case the policy depends on. Pinned by test_sim_porque_nao_falta_nada_negative_wins_returns_false."
  - "tests/retrieval/fakes.py imported via relative import (from .fakes import ...) rather than absolute (from tests.retrieval.fakes ...). pyproject sets pythonpath=['src'] so absolute tests.* imports are not on sys.path; relative imports work cleanly because tests/retrieval/__init__.py exists. This avoids modifying pythonpath or adding tests/__init__.py."
  - "Orchestrator docstring deliberately uses 'prior-turn note injection' instead of 'carry-forward' wording in the top-level module docstring so TestCarryForwardNotTouchedByOrchestrator's literal 'ChatSession' substring check passes (the original draft said 'applied once by ChatSession before invoking run()' — same architectural meaning, but the literal string ChatSession is forbidden by structural test). The class docstring still says 'Carry-forward is the caller's concern (D-07)' to make the boundary visible to readers."
  - "Cap of 2 retrievals is enforced by control flow (no loop, just attempt 1 then optional attempt 2), not by a counter — pinned structurally by TestHardCapAtTwoRetrievals which queues 5 thin tiers and asserts exactly 2 retrieve calls"
  - "Optional LLM judge intentionally NOT invoked on attempt 2 (RESEARCH Open Q3): even if the judge would mark attempt 2 as thin, the reformulation budget is already exhausted per D-03, so calling it would just waste latency"
  - "_merge_attempts dedups by path with hybrid-origin preference (matching the cross-origin dedup behavior 07-01 established in RetrievalService._fetch_notes_split) — same path appearing in both attempts collapses to one note, hybrid wins over keyword/carry, then highest score within the same origin tier"
  - "Status callback fires AFTER the Jaccard guard check, not before — pinned by TestJaccardGuard.assert status_calls == [] when guard fires"

patterns-established:
  - "Per-task atomic commits with prefix feat(07-02): keeps rollback granular; SUMMARY commit is separate (docs(07-02))"
  - "Production parser used inside fake LLM so verdict policy and orchestrator integration are tested through the same code path"
  - "Architectural boundary enforced via inspect.getsource() string-absence test rather than mock-based or discipline-based prevention"

requirements-completed:
  - RET-01
  - RET-03
  - RET-04
  - PRIV-03

# Metrics
duration: ~30min
completed: 2026-05-02
---

# Phase 07 Plan 02: Iterative Retrieval Loop — Orchestrator + LLM Primitives Summary

**Orchestrator + LLM-primitives layer for Phase 7's iterative retrieval loop: REFORMULATION + SUFFICIENCY-JUDGE prompts and the two LLMService methods that consume them, the IterativeRetrievalOrchestrator with hardcoded 2-attempt cap and conservative ambiguity policy, the FakeLLM/TieredFakeRetrieval fixtures module, and 28 unit tests pinning every CONTEXT decision and RESEARCH pitfall — Wave 3's chat-session integration only has to wire the existing pieces.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-05-02
- **Completed:** 2026-05-02
- **Tasks:** 3 (3 atomic commits, one per task)
- **Files created:** 4
- **Files modified:** 2

## Accomplishments

### LLM primitives + prompts (Task 1)

- `REFORMULATION_SYSTEM_PROMPT`, `REFORMULATION_USER_PROMPT`, `SUFFICIENCY_JUDGE_PROMPT` added to `src/aurora/llm/prompts.py` verbatim from RESEARCH §3 and §4 (pt-BR, no improvisation)
- `LLMService.reformulate_query(original_query, reason) -> str` — system+user message via `_sync_fn`, strips surrounding quotes (both single and double), strips trailing `.?!`, returns cleaned single-line query
- `LLMService.judge_sufficiency(query, context_text) -> bool` — single user message via `_sync_fn`, parses through `_parse_judge_verdict`
- `_parse_judge_verdict` module-level: splits on first `[.\n!?]`, regex-matches `\b(sim|yes)\b` and `\b(n[aã]o|no)\b` (unanchored within first segment), negative wins on tie, no-verdict fail-closed
- 14 tests covering all 5 ambiguity branches (sim, nao, both, neither, empty) plus first-segment splitting and quote-stripping cleanup

### Fakes module (Task 2)

- `tests/retrieval/fakes.py` (NOT a conftest — explicit imports per existing `_mock_backend`/`_make_session` conventions)
- `FakeLLM`: scripted `reformulations` and `judge_verdicts` queues, AssertionError on overflow, runs production `_parse_judge_verdict` on judge responses so parser+orchestrator are tested together
- `TieredFakeRetrieval`: scripted `tiers` queue, `retrieve` / `retrieve_with_memory` / `retrieve_memory_first` all share the same scripted method, records `(query, search_strategy, search_terms)` per call
- Builders: `thin_result()` (1 hybrid hit, score=0.18, content="x"*50 → fails count + context floors), `thick_result(n_notes=3)` (3 hybrid hits, scores 0.85→0.75, content "conteudo substantivo "*80 each → passes all floors), `empty_result()` (mirrors `_INSUFFICIENT` semantics)

### Orchestrator (Task 3)

- `IterativeRetrievalOrchestrator(*, llm, settings_loader=load_settings, on_status=None)` — `on_status` defaults to `lambda _msg: None` so call-site never has to None-check
- `run(query, *, intent, retrieve_fn, search_strategy, search_terms, first_attempt=None) -> tuple[RetrievalResult, IterativeRetrievalTrace]` is the only public method
- Disabled mode (D-11): bypasses sufficiency check entirely, returns single AttemptTrace with `sufficient=True`, trace `early_exit_reason="disabled"`, zero LLM calls
- Enabled mode: attempt 1 → deterministic verdict → optional LLM judge if `iterative_retrieval_judge=True` and deterministic passed → if sufficient, return; else reformulate → check Jaccard guard → if `>= settings.iterative_retrieval_jaccard_threshold`, return result_1 with `early_exit_reason="high jaccard"` (NO status callback); else emit status, run attempt 2, merge
- `_token_jaccard(a, b)`: token-level (`re.findall(r"\w+", lower)`) — explicitly NOT char-level (RESEARCH §pitfalls 5). Empty-vs-empty returns 1.0; empty-vs-nonempty returns 0.0
- `_merge_attempts(r1, r2)`: dedup by path with hybrid-origin preference, then highest score within same origin tier; preserves r1 path order, then appends r2-only paths; **returns `_INSUFFICIENT` singleton when merged_notes empty** (RET-04 preservation, identity-checked)
- `_build_attempt_trace`: composes `AttemptTrace` from `result + verdict`, top_score from max hybrid score (0.0 if no hybrid hits)
- `_STATUS_REVISANDO = "Revisando busca..."` — module constant, sentence case, ASCII triple-dot
- 20 tests pin all CONTEXT decisions: thin→thick triggers one reformulation, hard cap at 2 retrievals (5 thin tiers → exactly 2 calls), double-empty preserves insufficient (singleton identity), Jaccard guard skips retrieval+status, status-before-second-retrieval, mode skips top-score for non-hybrid, reformulation prompt secret-injection privacy pin, disabled mode zero-LLM-calls, judge on/off branches, carry-forward structural absence, first_attempt parameter direct use, token-vs-char Jaccard, merge dedup hybrid-prefer

## Test results

- **34 plan tests pass** (LLM 14 + orchestrator 20)
- **89 Wave 2 tests pass** (`tests/llm/` + `test_iterative.py` + `test_contracts.py` + `test_sufficiency.py`)
- **153 retrieval+chat+LLM tests pass** with no regressions to Wave 1 work
- **535 unit tests pass** (full suite excluding integration tests; 1 pre-existing integration failure carried over from Wave 1, untouched)

## Deviations from plan

Two within-latitude adjustments documented inline:

1. **Regex anchoring in `_parse_judge_verdict`.** The plan's literal regex draft was `^\W*(sim|yes)\b` and `^\W*(n[aã]o|no)\b`. With `re.search`, `^` anchors to start-of-string, so the negative pattern only matched if "nao" was the first word in the first segment. This contradicted the pinned test `test_sim_porque_nao_falta_nada_negative_wins_returns_false` (which asserts that "nao" anywhere in the first segment of "sim porque nao falta nada" causes a False verdict per RESEARCH §3 conservative-tie policy). Switched both regexes to `\b(...)\b` (unanchored within first segment). This matches the policy intent ("negative wins on tie") rather than the literal regex draft. All 14 parser tests pass with this regex.

2. **Top-level docstring wording.** The orchestrator's top-level module docstring originally referenced "ChatSession" by name to explain the carry-forward boundary. The pinned `TestCarryForwardNotTouchedByOrchestrator` does a literal `assert "ChatSession" not in source` check via `inspect.getsource()`, so the docstring would have broken its own boundary-enforcement test. Rewrote the top-level docstring to use "prior-turn note injection" / "the caller" terminology — same architectural meaning, satisfies the structural test. The class-level docstring still says "Carry-forward is the caller's concern (D-07)" because the test allows the substring "carry-forward" (only the literal "ChatSession" and "_apply_carry_forward" are forbidden).

3. **Test import path.** The plan's test skeleton used `from tests.retrieval.fakes import ...` (absolute). pyproject sets `pythonpath = ["src"]` (not `["src", "."]`), and `tests/__init__.py` does not exist, so `tests.retrieval.fakes` is not importable as an absolute path. Switched to `from .fakes import ...` (relative). `tests/retrieval/__init__.py` exists, so the relative import resolves cleanly. No change to project configuration.

## Auth gates

None.

## Deferred Issues

**Pre-existing, out-of-scope (carried over from Wave 1):** `tests/integration/test_kb_qmd_integration.py::test_real_qmd_lifecycle_ingest_update_delete_rebuild` continues to fail on `kb delete` (exit code 1). Untouched by Wave 2 — nothing in the orchestrator or LLM primitives layer is on the kb-delete code path. Logged in 07-01-SUMMARY.md as well; will continue to be carried forward unless a future plan explicitly addresses it.

## Notes for wave 3 (07-03)

The orchestrator surface is stable for ChatSession integration:

- **Constructor:** `IterativeRetrievalOrchestrator(*, llm: LLMService, settings_loader=load_settings, on_status: Callable[[str], None] | None = None)`. Inject `on_status=lambda msg: print(msg, file=sys.stderr)` (or whatever the chat session's existing diagnostic-output convention is) to surface "Revisando busca..." to the user during reformulation.
- **Public method:** `run(query, *, intent, retrieve_fn, search_strategy, search_terms, first_attempt=None) -> tuple[RetrievalResult, IterativeRetrievalTrace]`. ChatSession passes:
  - `query` = user question (pt-BR)
  - `intent="vault"` or `intent="memory"` — whichever the existing intent classifier picked
  - `retrieve_fn=retrieval.retrieve_with_memory` (vault intent) or `retrieve_fn=retrieval.retrieve_memory_first` (memory intent) — whichever single-shot method the chat session was using before
  - `search_strategy` and `search_terms` from the existing intent classification
  - `first_attempt` = the result of running attempt 1 manually (with carry-forward applied via the existing `_apply_carry_forward`). The orchestrator will then skip its own attempt 1 and start sufficiency evaluation immediately.
- **Carry-forward composition (D-07):** ChatSession owns this. Apply `_apply_carry_forward` BEFORE calling `orchestrator.run`, pass the result as `first_attempt`. Tag carry-forward notes with `origin="carry"` per Wave 1's plan (currently they default to "hybrid" — fix it explicitly in 07-03 as the existing summary noted). Carry-forward is NOT re-applied for attempt 2 (the orchestrator never sees it).
- **Reformulation persistence to chat history (D-10):** ChatSession's responsibility. After `orchestrator.run` returns, if `len(trace.attempts) == 2`, call `history.append_turn(role="system", content=f"[reformulation] {trace.attempts[1].query}")`. Then make sure `ChatHistory.get_recent` filters out lines starting with `"[reformulation] "` before passing context to the LLM (this is the second piece of D-10 wiring, not yet built — Wave 3 needs to add the filter).
- **Trace surface (D-09):** Wave 3 also wires `--trace` flag on `aurora ask` and `aurora chat`. The orchestrator returns the full `IterativeRetrievalTrace`; CLI just needs to render it (stderr text mode, or `trace` key in `--json` envelope). PRIV-03 is structurally enforced — the trace dataclasses cannot contain note content even if a future maintainer tries to add it (Wave 1's `_FORBIDDEN_TRACE_FIELDS` test catches it).
- **Single-shot fallback / disabled mode:** When `settings.iterative_retrieval_enabled=False`, `orchestrator.run` returns a single AttemptTrace and a result that is byte-equivalent to today's single-shot retrieval (test `TestDisabledModeReturnsExactlyOneAttempt` pins this — `result == thin_result()` equality check). Wave 3's chat session can call the orchestrator unconditionally; the kill-switch is honored internally.
- **Status callback ordering pin:** `on_status("Revisando busca...")` fires BEFORE the second retrieval and AFTER the Jaccard guard check. NOT before reformulation, NOT before the Jaccard check, NOT after the second retrieval. Pinned by `TestStatusCallbackInvokedBeforeSecondRetrieval` and `TestJaccardGuard`. Wave 3 doesn't need to re-test this — just inject the callback.
- **Fakes module location:** `tests/retrieval/fakes.py` uses relative import — Wave 3's chat-session tests can import it via `from tests.retrieval.fakes import FakeLLM, TieredFakeRetrieval, ...` only if Wave 3's test files are inside `tests/retrieval/` AS WELL. If Wave 3's chat session tests live in `tests/chat/`, they need to either re-establish the path setup, copy the fakes pattern, or the project should add `tests/__init__.py` + change relative imports to absolute. Recommend the third option if Wave 3 wants cross-package fake reuse — but it's a config decision worth flagging.

## Self-Check: PASSED

- [x] `src/aurora/retrieval/iterative.py` exists
- [x] `tests/retrieval/fakes.py` exists
- [x] `tests/retrieval/test_iterative.py` exists
- [x] `tests/llm/test_service_reformulate_judge.py` exists
- [x] Three task commits in git history (`1a4c00c`, `df6b132`, `03a17a2`)
- [x] All 34 plan tests pass; 153 retrieval+LLM+chat tests pass with no regressions
- [x] Smoke test: orchestrator with FakeLLM + TieredFakeRetrieval emits "Revisando busca..." after thin→thick attempt sequence
- [x] Structural pin: `grep ChatSession src/aurora/retrieval/iterative.py` returns nothing
- [x] Structural pin: `grep _apply_carry_forward src/aurora/retrieval/iterative.py` returns nothing
