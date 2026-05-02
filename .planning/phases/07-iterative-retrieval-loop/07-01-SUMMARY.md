---
phase: 07-iterative-retrieval-loop
plan: 01
subsystem: retrieval
tags: [iterative-retrieval, settings, contracts, sufficiency, origin-tagging, priv-03]

# Dependency graph
requires:
  - phase: 04.2-fix-retrieval-quality
    provides: RetrievalService.retrieve / retrieve_with_memory / retrieve_memory_first, _search_with_strategy, _dedup_hits, _fetch_notes
  - phase: 04.1-fix-memory-pipeline
    provides: RetrievedNote dataclass with source field, RetrievalResult with insufficient_evidence flag

provides:
  - Six new RuntimeSettings fields (iterative_retrieval_enabled, iterative_retrieval_judge, retrieval_min_top_score, retrieval_min_hits, retrieval_min_context_chars, iterative_retrieval_jaccard_threshold) with pt-BR validators
  - RetrievedNote.origin Literal["hybrid","keyword","carry"] additive field with default "hybrid"
  - AttemptTrace and IterativeRetrievalTrace frozen dataclasses + _FORBIDDEN_TRACE_FIELDS structural privacy guard
  - retrieval/sufficiency.py module with SufficiencyVerdict + judge_sufficiency_deterministic (pure function)
  - RetrievalService origin-tagging via _search_with_strategy_split and _fetch_notes_split helpers
  - aurora config show "Iterative retrieval:" section between KB and Privacidade

affects:
  - 07-02 (orchestrator: consumes sufficiency primitive, AttemptTrace, settings)
  - 07-03 (chat session integration: consumes RetrievedNote.origin="carry" tag for carry-forward supplements)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - hybrid-keyword-bucket-split: Search hits split into hybrid_hits/keyword_hits buckets at the _search_with_strategy_split level; each bucket dedupped independently, then cross-origin dedup keeps hybrid when same path appears in both
    - origin-tagged-notes: Every RetrievedNote carries its retrieval-path origin so downstream sufficiency check can apply the calibrated 0..1 top-score floor only against hybrid hits (BM25 scores are unbounded — RESEARCH section 2)
    - structural-privacy-guard: _FORBIDDEN_TRACE_FIELDS frozenset + dataclasses.fields() introspection prevents future trace dataclasses from gaining a content-bearing field by accident (PRIV-03 enforced by test, not by discipline)
    - deterministic-sufficiency-ordering: Sufficiency primitive checks floors in fixed order (zero hits -> count -> context -> hybrid top score) so the "reason" string is reproducible and the orchestrator can hand it to the LLM reformulator

key-files:
  created:
    - src/aurora/retrieval/sufficiency.py
    - tests/retrieval/test_contracts.py
    - tests/retrieval/test_sufficiency.py
  modified:
    - src/aurora/runtime/settings.py
    - src/aurora/retrieval/contracts.py
    - src/aurora/retrieval/service.py
    - src/aurora/cli/config.py
    - tests/runtime/test_settings_defaults.py
    - tests/cli/test_config_show.py
    - tests/retrieval/test_retrieval_service.py

key-decisions:
  - "Promoted iterative_retrieval_jaccard_threshold from a planner-discretion constant to a real RuntimeSettings field per D-12 (planner discretion explicitly allowed either; settings field gives the user a knob to tune the diversity guard without a code change)"
  - "RetrievedNote.origin defaults to 'hybrid' so all existing call sites (including ChatSession._apply_carry_forward) continue working unchanged; Plan 07-03 will explicitly pass origin='carry' for supplements"
  - "Cross-origin dedup intentionally prefers hybrid (semantic) over keyword (BM25) when same path appears in both buckets — semantic ranking is meaningful while BM25 is unbounded. This replaces the prior 'highest score wins' behavior; legacy test_retrieve_deduplicates_both_strategy_results was updated to pin the new contract"
  - "Memory backend hits are tagged origin='hybrid' (memory backend uses semantic search only) — this is correct, not a workaround"
  - "Sufficiency primitive lives in retrieval/sufficiency.py as a pure function (no I/O, no LLM, no logging) so Plan 07-02's orchestrator can compose it with the LLM judge and reformulator without test gymnastics"
  - "Sufficiency floor ordering is fixed (zero-hits -> count -> context -> hybrid top score) so the reason string is reproducible and orchestrator-to-LLM contract is stable"
  - "Top-score check is intentionally skipped when there are zero hybrid notes — applying a 0..1 calibrated threshold to unbounded BM25 scores would be miscalibrated; treat keyword/carry-only results as score-passing"
  - "Singular/plural reason units use English ('1 hit' / '2 hits') because the orchestrator hands this string to the LLM reformulation prompt which is itself bilingual; pt-BR pluralization stays in the user-facing 'revisando busca…' status line in 07-02"

patterns-established:
  - "Per-task atomic commits with prefix feat(07-01): keeps rollback granular; SUMMARY commit is separate (docs(07-01))"
  - "PRIV-03 enforced structurally via dataclasses.fields() introspection against a frozenset of banned names rather than per-field code review"
  - "Pure-function sufficiency primitive isolates the deterministic floors from the orchestrator so each can be tested independently"

requirements-completed:
  - RET-01
  - RET-03
  - RET-04
  - PRIV-03

# Metrics
duration: ~25min
completed: 2026-05-02
---

# Phase 07 Plan 01: Iterative Retrieval Loop — Foundation Summary

**Foundation layer for Phase 7's iterative retrieval loop: six new pt-BR-validated settings, additive origin field on RetrievedNote, snippet-free trace dataclasses, pure deterministic sufficiency primitive, RetrievalService origin tagging, and a new "Iterative retrieval:" section in `aurora config show` — every primitive that Plan 07-02's orchestrator and Plan 07-03's chat-session integration need now exists in isolation, fully tested.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-02
- **Completed:** 2026-05-02
- **Tasks:** 3 (3 atomic commits, one per task)
- **Files created:** 3
- **Files modified:** 7

## Accomplishments

### Settings (Task 1)

- `RuntimeSettings.iterative_retrieval_enabled: bool = True` — kill-switch (D-11)
- `RuntimeSettings.iterative_retrieval_judge: bool = False` — opt-in LLM judge (D-01)
- `RuntimeSettings.retrieval_min_top_score: float = 0.35` — hybrid score floor
- `RuntimeSettings.retrieval_min_hits: int = 2` — hit-count floor
- `RuntimeSettings.retrieval_min_context_chars: int = 800` — context-length floor
- `RuntimeSettings.iterative_retrieval_jaccard_threshold: float = 0.7` — diversity guard (D-12)
- Four pt-BR validators mirror the `retrieval_top_k` pattern with bounded ranges and exact error strings
- `aurora config show` renders new "Iterative retrieval:" section between KB and Privacidade with two-decimal threshold formatting
- Round-trip preservation confirmed via `save_settings + load_settings` test

### Contracts + service origin tagging (Task 2)

- `RetrievedNote.origin: Literal["hybrid", "keyword", "carry"] = "hybrid"` — additive, default keeps all existing call sites working
- `AttemptTrace` frozen dataclass: `attempt_number, query, intent, hit_count, top_score, sufficient, reason, paths` — eight fields, structurally snippet-free
- `IterativeRetrievalTrace` frozen dataclass: `attempts, judge_enabled, early_exit_reason` — three fields, structurally snippet-free
- `_FORBIDDEN_TRACE_FIELDS` frozenset of nine banned names (`content`, `snippet`, `text`, `body`, `note_content`, `excerpt`, `preview`, `fragment`, `passage`); `test_trace_dataclasses_have_no_content_fields` enforces this structurally via `dataclasses.fields()` introspection
- `RetrievalService._fetch_notes` accepts new kw-only `origin: str = "hybrid"` parameter and tags every emitted note
- New `_search_with_strategy_split` helper returns `(hybrid_hits, keyword_hits)` tuples so each bucket can be tagged with its source path
- New `_fetch_notes_split` helper dedups each bucket and applies cross-origin dedup (hybrid wins over keyword for same path)
- All three retrieve methods (`retrieve`, `retrieve_with_memory`, `retrieve_memory_first`) now use the split helpers; memory hits tagged origin="hybrid" (memory backend uses semantic only)

### Sufficiency primitive (Task 3)

- `src/aurora/retrieval/sufficiency.py` — new module with `SufficiencyVerdict(sufficient: bool, reason: str)` frozen dataclass and `judge_sufficiency_deterministic(result, settings) -> SufficiencyVerdict` pure function
- Three deterministic floors checked in fixed order: zero hits -> hit count -> context length -> hybrid top score
- First failing floor short-circuits with reproducible reason: `"zero hits"`, `"1 hit"` / `"3 hits"`, `"context 220 chars"`, `"top score 0.18"`
- Top-score check skipped entirely when result has zero hybrid-origin notes (BM25 scores are unbounded; treating keyword/carry as score-passing is the correct calibration)

## Test results

- **82 plan-foundation tests pass** (settings 14 + contracts 5 + sufficiency 13 + retrieval-service 47 + config-show 3)
- **141 retrieval+chat tests pass** with no regressions
- **501 of 502 total tests pass** (one unrelated pre-existing integration test failure — see Deferred Issues below)

## Deviations from plan

None of substance. All three tasks executed as written. Two minor decisions made within plan latitude:

1. The plan's Task 2 step 5 explicitly authorized updating tests that broke due to the `RetrievedNote` contract change. The legacy test `test_retrieve_deduplicates_both_strategy_results` previously asserted "highest score wins for same path across hybrid+keyword" — this contract was intentionally replaced by "hybrid wins regardless of score" (cross-origin dedup), as pinned by the new `test_cross_origin_dedup_keeps_hybrid_when_same_path` test. The legacy test was rewritten in place to assert the new contract (origin="hybrid", score=0.50 from the hybrid hit) with a docstring explaining the change.

2. `_search_with_strategy` was retained alongside the new `_search_with_strategy_split` helper rather than refactored away. The plan explicitly allowed either ("Update `_search_with_strategy` to return `tuple[tuple[QMDSearchHit, ...], tuple[QMDSearchHit, ...]]` ... OR keep the single-tuple signature and add a parallel helper ... Pick whichever produces a smaller diff"). Adding the parallel helper produced the smaller diff and zero risk of breaking unseen callers.

## Auth gates

None.

## Deferred Issues

**Pre-existing, out-of-scope:** `tests/integration/test_kb_qmd_integration.py::test_real_qmd_lifecycle_ingest_update_delete_rebuild` fails on `kb delete` (exit code 1). This test is unrelated to retrieval/contracts/settings (last modified in commit c0bb303 from Phase 02-06) and exercises the real `qmd` lifecycle. Nothing in Plan 07-01 touches the kb-delete code path. Per the deviation-rules SCOPE BOUNDARY ("only auto-fix issues directly caused by the current task's changes"), this is logged here for the next executor to triage as a pre-existing issue, not fixed under Plan 07-01.

## Notes for wave 2 (07-02)

The orchestrator can rely on these surfaces being stable:

- `RetrievedNote.origin` defaults to `"hybrid"` so existing `_apply_carry_forward` builds (`source="vault"`, no origin specified) keep working — the carry-forward notes will be technically mis-tagged as `"hybrid"` until 07-03 explicitly passes `origin="carry"`. This is acceptable because the orchestrator is not yet wired and the sufficiency primitive's only origin-sensitive logic is the top-score check, which a `score=0.0` carry-forward note would already fail on count/context floors first.
- Settings exposed on `RuntimeSettings`: `iterative_retrieval_enabled`, `iterative_retrieval_judge`, `retrieval_min_top_score`, `retrieval_min_hits`, `retrieval_min_context_chars`, `iterative_retrieval_jaccard_threshold` — all six available via `load_settings()`.
- `judge_sufficiency_deterministic(result, settings)` is the pure-function sufficiency primitive. Reason strings are stable and reproducible: `"zero hits"`, `"{n} hit"` / `"{n} hits"`, `"context {n} chars"`, `"top score {x:.2f}"`. The reformulation prompt (07-02) can interpolate these directly.
- `AttemptTrace` and `IterativeRetrievalTrace` are ready to be populated by the orchestrator. The structural privacy test will fail loudly if 07-02 attempts to add a `content`/`snippet`/`text`/etc. field — the orchestrator must compose its trace from `paths`, `query`, `intent`, `hit_count`, `top_score`, `sufficient`, `reason` only.
- Cross-attempt merge (07-02 work): when both attempts return empty, the merge MUST preserve `insufficient_evidence=True`. The current contracts already support this via `RetrievalResult(insufficient_evidence=True, notes=(), context_text="")`.
- `_search_with_strategy` (legacy single-tuple signature) is retained for any code that depends on it. New code in 07-02 should prefer `_search_with_strategy_split` if it needs origin-aware behavior.
- Singular/plural reason unit is English (`"1 hit"` / `"2 hits"`) — the user-facing `revisando busca…` status string and the LLM reformulation prompt are 07-02's responsibility; the sufficiency reason is internal/orchestrator-facing only.

## Self-Check: PASSED

- [x] `src/aurora/retrieval/sufficiency.py` exists
- [x] `tests/retrieval/test_contracts.py` exists
- [x] `tests/retrieval/test_sufficiency.py` exists
- [x] Three commits in git history (`ef5818a`, `8457d71`, `df37692`)
- [x] All 82 foundation tests pass; 141 retrieval+chat tests pass with no regressions
- [x] Manual smoke check confirms `aurora config show` renders the new "Iterative retrieval:" section with all six values
