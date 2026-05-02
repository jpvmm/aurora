# Phase 7 Verification

**Verified:** 2026-05-02
**Verifier:** gsd-verifier (autonomous goal-backward audit)
**Verdict:** PASS-WITH-CAVEATS

## Executive summary

Phase 7 delivers the iterative retrieval loop end-to-end. All 10 ROADMAP success criteria are pinned by code AND tests; all 13 CONTEXT decisions (D-01..D-13) are honored, including the load-bearing ones (D-07 carry-forward composition outside the loop, D-10 filter-before-slice, D-13 structurally content-free trace). 572 unit tests pass with zero regressions. Operational smoke (CLI surface, `config show`, bench import) all pass. The only flagged items are NIT/INFO: PRIV-03 is officially mapped to Phase 6 in `REQUIREMENTS.md` while wave SUMMARYs claim it as `requirements-completed` (Phase 7 makes a substantive partial discharge but does not fully close the v1 requirement); the bench script's "iter faster than disabled" result is a known cache-warming artifact (already flagged in SUMMARY); and one pre-existing kb-delete integration failure remains untouched (correctly out of scope).

## Success criteria — 10/10 mapping

| #   | ROADMAP Success Criterion                                                          | Verdict | Pinning code/test                                                                                                                                                                       |
| --- | ---------------------------------------------------------------------------------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Deterministic sufficiency signal + opt-in LLM judge                                | PASS    | `src/aurora/retrieval/sufficiency.py:judge_sufficiency_deterministic` (4 floors: zero hits, hit-count, context-len, hybrid top-score); judge gated by `iterative_retrieval_judge=False` default at `iterative.py:213-221`. Tests: `TestSufficiencyFiveBranches`, `TestJudgeOn::test_judge_on_and_first_sufficient_no_reformulation` |
| 2   | LLM-driven reformulation runs exactly once when thin                               | PASS    | `iterative.py:237` `self._llm.reformulate_query(query, verdict_1.reason)`; called only on deterministic-thin path. Test: `TestThinThenThickTriggersOneReformulation::test_two_attempts_one_reformulation` (asserts `len(llm.reformulate_calls) == 1`) |
| 3   | Loop bounded at 1 reformulation (max 2 retrievals); fixed, not configurable        | PASS    | `iterative.py` has NO loop counter — control flow is attempt-1 then optional attempt-2, with no third path. Settings has NO `retrieval_max_attempts` field. Test: `TestHardCapAtTwoRetrievals::test_never_exceeds_two_attempts` (queues 5 thin tiers; asserts exactly 2 retrieve calls) |
| 4   | Loop applies on vault and memory turns in both `aurora ask` and `aurora chat`; chat-intent unaffected | PASS    | `chat/session.py:_handle_vault_turn` (line 248) and `_handle_memory_turn` (line 317) both call `self._orchestrator.run(...)`. `_handle_chat_turn` (line 352) does NOT. `cli/ask.py:74` uses orchestrator unconditionally. Tests: `TestPhase7Integration::test_carry_forward_composes_once_not_per_attempt` |
| 5   | Visible `Revisando busca...` status line on stderr while loop runs                 | PASS    | `iterative.py:154` `_STATUS_REVISANDO = "Revisando busca..."`; emitted at line 249 BEFORE attempt 2. CLI emits to stderr only when not JSON (`cli/ask.py:62`). Tests: `TestStatusCallbackInvokedBeforeSecondRetrieval`, `test_visible_status_line_emitted_when_loop_fires` |
| 6   | `--trace` flag on ask + chat: stderr in non-JSON, `trace` key in `--json`; symmetric on happy AND insufficient paths | PASS    | `cli/ask.py:118-122` (insufficient text) and `:159` (happy JSON) and `:114` (insufficient JSON) and `:163` (happy text); `cli/chat.py:99` per-turn render. Tests: `TestAskTrace::test_trace_emitted_on_insufficient_evidence_path_text_mode` + `..._json_mode` (NIT-2 symmetry) |
| 7   | Reformulations persisted with `[reformulation]` prefix; filtered out before LLM context | PASS    | `chat/history.py:12` `_REFORMULATION_PREFIX = "[reformulation] "`; `get_recent` line 67 filters BEFORE slicing (line 70). `chat/session.py:_persist_reformulations` (line 166) appends. Tests: `TestGetRecentFiltersReformulations::test_filter_happens_before_slice` (the load-bearing pin: 5 pairs + 3 reformulations interleaved, max_turns=3 yields 3+3+0) |
| 8   | RET-04 "insufficient evidence" path unchanged when both attempts fail              | PASS    | `iterative.py:80-119` `_merge_attempts` returns `_INSUFFICIENT` singleton on double-empty. Test: `TestDoubleEmptyPreservesInsufficient::test_both_empty_returns_insufficient_singleton` (asserts `final is _INSUFFICIENT` — IDENTITY check, not equality) |
| 9   | `iterative_retrieval_enabled=false` restores single-shot behavior byte-for-byte   | PASS    | `iterative.py:188-205` early-return path: 1 attempt, no LLM rescue, well-formed `early_exit_reason="disabled"` trace. Tests: `TestDisabledModeReturnsExactlyOneAttempt::test_disabled_skips_loop_entirely` (asserts result identity to thin_result, no LLM/status calls) AND `TestPhase7Integration::test_disable_path_byte_equivalent` |
| 10  | Trace surface contains paths/scores/queries only — never note content (PRIV-03)    | PASS    | `contracts.py:60-89` `AttemptTrace` + `IterativeRetrievalTrace` have NO content/snippet/text fields; `_FORBIDDEN_TRACE_FIELDS = {content, snippet, text, body, note_content, excerpt, preview, fragment, passage}` (line 92). `trace_render.py` operates only on AttemptTrace fields. Tests: `test_trace_dataclasses_have_no_content_fields` (structural pin enforces freedom of these fields), `test_trace_does_not_leak_note_content_in_stderr` AND `..._in_json_envelope` (end-to-end PRIV-03 leak guards on stderr AND stdout) |

**Score: 10/10 PASS.**

## Locked decisions D-01..D-13

| Decision | Code Reference | Verdict | Notes |
| -------- | -------------- | ------- | ----- |
| D-01 (Sufficiency: deterministic + opt-in LLM judge) | `sufficiency.py:35` (deterministic) + `iterative.py:213-221` (judge gated, runs AFTER deterministic pass) | PASS | Sequencing correct — judge ONLY runs when deterministic check passed |
| D-02 (Visibility: `Revisando busca...` on stderr) | `iterative.py:154` constant + `:249` emission | PASS | Sentence-case + ASCII triple-dot (matches D-02 wording exactly) |
| D-03 (Cap: 1 reformulation, fixed) | No `retrieval_max_attempts` setting; control-flow has no loop counter | PASS | Cap enforced structurally — would require code change to lift |
| D-04 (Scope: vault + memory in ask + chat) | `session.py:248` (vault) + `:317` (memory) + `cli/ask.py:74` (ask) | PASS | Chat-intent path (`_handle_chat_turn`) correctly skips orchestrator |
| D-05 (Reformulation: LLM rewrite, single non-streaming call) | `service.py:128 reformulate_query` uses `_sync_fn` (non-streaming) | PASS | One call returns one new query string; not HyDE/step-back |
| D-06 (Reformulation prompt sees query + reason ONLY, no note content) | `service.py:128` signature `(original_query: str, reason: str)`; no path/title/content arg | PASS | Test `test_secret_in_note_content_does_not_reach_llm` pins this |
| D-07 (Carry-forward composes ONCE, before attempt 1 only) | `session.py:_handle_vault_turn:234` and `:_handle_memory_turn:308` both apply carry-forward BEFORE `orchestrator.run(...)`; orchestrator never re-applies | PASS | Pinned by `TestCarryForwardNotTouchedByOrchestrator::test_orchestrator_does_not_import_chatsession` (structural source-introspection check) |
| D-08 (Memory-turn scope) | `session.py:_handle_memory_turn:317` invokes orchestrator with `intent="memory"` and `retrieve_memory_first` closure | PASS | Memory turns get the same loop |
| D-09 (Trace surface: `--trace` flag on ask + chat) | `cli/ask.py:30-34` + `cli/chat.py:45-49` Typer options; render via `trace_render.py` | PASS | Both surfaces present; JSON envelope vs stderr text correctly routed |
| D-10 (Reformulation persistence with `[reformulation]` prefix; filtered by `get_recent`) | `history.py:12` prefix + `session.py:166 _persist_reformulations`; `history.py:67-71` filter-before-slice | PASS | Open-bracket lowercase close-bracket single space (literal match per D-10) |
| D-11 (Disable kill-switch via `iterative_retrieval_enabled`) | `settings.py:45` `iterative_retrieval_enabled: bool = True`; `iterative.py:188` early-return | PASS | NO per-command CLI flag (kept simple per D-11) |
| D-12 (Diversity guard via token-Jaccard ≥ 0.7) | `iterative.py:36 _token_jaccard` (TOKEN-level, not char/Levenshtein); `:241` early-exit when ≥ threshold | PASS | Threshold promoted to settings field `iterative_retrieval_jaccard_threshold` (D-12 explicitly allowed this) |
| D-13 (Privacy: trace contains paths/scores/queries only) | `contracts.py:_FORBIDDEN_TRACE_FIELDS` structurally bans content fields; render functions use only safe fields | PASS | Structural pin via `test_trace_dataclasses_have_no_content_fields` + end-to-end stderr+stdout leak tests |

**All 13 decisions honored. No silent contradictions detected.**

## Test suite results

```
$ uv run pytest tests/ -x --tb=short --ignore=tests/integration
============================= 572 passed in 11.85s =============================
```

572/572 unit tests pass — exactly matches the wave-3 SUMMARY claim. Zero regressions.

Critical Phase 7 test classes (run individually, all pass):
- `TestDoubleEmptyPreservesInsufficient::test_both_empty_returns_insufficient_singleton` PASS
- `TestHardCapAtTwoRetrievals::test_never_exceeds_two_attempts` PASS
- `TestJaccardGuard::test_high_jaccard_skips_second_retrieval` PASS
- `TestDisabledModeReturnsExactlyOneAttempt::test_disabled_skips_loop_entirely` PASS
- `TestGetRecentFiltersReformulations` (4/4 incl. `test_filter_happens_before_slice`) PASS
- `TestPhase7Integration` (7/7 incl. `test_carry_forward_composes_once_not_per_attempt`, `test_disable_path_byte_equivalent`, `test_carry_forward_origin_tagged_carry`) PASS
- `TestAskTrace` (9/9 incl. PRIV-03 stderr+JSON leak guards + insufficient-path symmetry) PASS
- `TestChatTrace` (6/6 incl. PRIV-03 stderr leak guard) PASS
- `TestTraceDataclassPrivacy::test_trace_dataclasses_have_no_content_fields` PASS (structural)
- LLM judge ambiguity matrix (`TestParseJudgeVerdict` 8/8 incl. all 5 RESEARCH §3 branches): PASS
- `TestReformulateQuery::test_prompt_does_not_see_note_content` PASS

Pre-existing failure (out of scope, documented in all 3 SUMMARYs):
- `tests/integration/test_kb_qmd_integration.py::test_real_qmd_lifecycle_ingest_update_delete_rebuild` (`kb delete` exit 1) — predates Phase 7, not touched by any phase-7 file.

## Operational smoke checks

```
$ uv run aurora --help          # 4 core commands + 3 deprecated visible
$ uv run aurora ask --help      # --trace flag visible: "Mostra trace por tentativa de retrieval"
$ uv run aurora chat --help     # --trace flag visible: "Mostra trace por turno apos a resposta"
$ uv run aurora config show     # Iterative retrieval section renders all 6 fields:
                                # - loop: ativado / judge LLM: desativado
                                # - min top score: 0.35 / min hits: 2 / min context chars: 800
                                # - jaccard threshold: 0.70
$ uv run python -c "import scripts.bench_iterative_retrieval as m;
                    print(m._HAPPY_TARGET, m._WORST_TARGET, len(m._QUERIES))"
                                # 1.0 2.5 8
```

All operational surfaces present and rendering. The local `aurora` global at `~/.local/bin/aurora` is a stale uv-tool snapshot (per user MEMORY note) and does NOT show `--trace`; the user must reinstall to surface Phase 7 changes via the global. **This is not a Phase 7 defect** — it's the documented `aurora install mode`. All verification used `uv run` against the local source.

## Code-reference accuracy spot-checks

1. **`IterativeRetrievalOrchestrator` constructor** — matches wave-2 handoff:
   - `__init__(self, *, llm: LLMService, settings_loader: Callable[[], RuntimeSettings] = load_settings, on_status: Callable[[str], None] | None = None)` — kwargs-only, defaults present. PASS

2. **`ChatHistory.get_recent` filter-before-slice** — confirmed at `history.py:65-74`:
   ```
   conversational = [r for r in all_records if not _is_reformulation_entry(r)]   # filter
   recent = conversational[-max_messages:]                                       # then slice
   ```
   Filter is on line 67, slice on line 70-73 — filter strictly precedes slice. PASS

3. **`RetrievedNote.origin`** — `contracts.py:43`: `origin: Literal["hybrid", "keyword", "carry"] = "hybrid"`. Default is `"hybrid"`. The carry-forward code at `session.py:150` explicitly passes `origin="carry"` — verified via `TestPhase7Integration::test_carry_forward_origin_tagged_carry`. Memory backend tagging: spot-checked `retrieval/service.py` for memory hit construction (out of phase-7 scope but adjacent). PASS

4. **`_apply_carry_forward` integration point** — applied EXACTLY ONCE before `orchestrator.run` in both `_handle_vault_turn` (line 234) and `_handle_memory_turn` (line 308). Result is then passed via `first_attempt=result` (vault: line 254, memory: line 323). Orchestrator never re-applies (proven structurally by `TestCarryForwardNotTouchedByOrchestrator`). PASS

5. **`aurora ask --trace` insufficient_evidence path** — text mode emits to stderr at `ask.py:121`; JSON mode injects under `trace` key at `ask.py:114`. Both pinned by `TestAskTrace::test_trace_emitted_on_insufficient_evidence_path_text_mode` and `..._json_mode`. PASS

## Findings

### F1 [INFO] PRIV-03 traceability mismatch

**Where:** `.planning/REQUIREMENTS.md:111` says `PRIV-03 | Phase 6 | Pending`, but all three Phase 7 SUMMARYs list PRIV-03 under `requirements-completed`. The wave-3 SUMMARY also adds end-to-end stderr + stdout leak guards specifically for PRIV-03.

**Reality:** Phase 7 makes a *substantive* partial discharge of PRIV-03 specifically for the `--trace` surface, including a structural `_FORBIDDEN_TRACE_FIELDS` guard and end-to-end leak tests. The remainder of PRIV-03 (default logs avoiding sensitive content elsewhere — debug logging, error messages, etc.) is still owned by Phase 6.

**Suggested fix:** Update `REQUIREMENTS.md` traceability table to note partial coverage by Phase 7 (e.g., `PRIV-03 | Phase 6 (Phase 7 partial) | Pending`), OR bring REQUIREMENTS.md into alignment with the SUMMARY claims. Not a blocker for Phase 7 completion; just a paper-trail tidy-up.

### F2 [INFO] Bench script "iter faster than disabled" cache-warming artifact

**Where:** `scripts/bench_iterative_retrieval.py:71-110`. The wave-3 smoke output showed iter mode at 0.26-0.54x of disabled mode — ratios well below 1.0, which would mean the "rescue path" is faster than baseline. Cause is order-of-execution: disabled runs first, then enabled — by the time enabled runs, the QMD/embedding caches are warm.

**Reality:** Already flagged in the wave-3 SUMMARY ("Worth a follow-up: randomize order or use mean-of-3 to control for cache effects"). The bench script always exits 0 and is informational, so this does not gate CI. Reading the code, this is a real measurement methodology issue: the ratio is meaningless under serial warm-cache conditions.

**Suggested fix:** Follow-up phase or quick patch to `bench_iterative_retrieval.py` to either (a) randomize order, (b) take mean-of-3 with cache flush between runs, or (c) at minimum warn in the output that the ratio interpretation requires randomized runs. Not a blocker for Phase 7 — bench is a dev tool, not part of the user-facing surface.

### F3 [INFO] Pre-existing kb-delete integration failure persists

**Where:** `tests/integration/test_kb_qmd_integration.py::test_real_qmd_lifecycle_ingest_update_delete_rebuild` exits with code 1 on `kb delete`. Documented in 07-01-SUMMARY.md, 07-02-SUMMARY.md, 07-03-SUMMARY.md.

**Reality:** Confirmed pre-existing — no Phase 7 file touches kb-delete code. Out of scope for Phase 7.

**Suggested fix:** Track separately — open an issue or schedule a maintenance phase. Not a Phase 7 blocker.

### F4 [NIT] ChatSession test count parity drifted (24 vs 22, not 17 vs 17)

**Where:** Wave-3 SUMMARY admits the literal grep `grep -c "ChatSession(" == grep -c "settings_loader=_disabled..."` no longer holds (24 sites total, 18-19 disabled, 5 enabled for `TestPhase7Integration`). Verified myself: 24 ChatSession sites in `tests/chat/test_session.py`, 23 with `_disabled_iterative_settings_loader` immediately following, 5 with `lambda: RuntimeSettings()` (the integration tests intentionally on enabled mode).

**Reality:** The "spirit of the check" is satisfied: every existing pre-Phase-7 test runs on the disable path, and only the new TestPhase7Integration sites that need the enabled loop opt out. The literal acceptance criterion in 07-03 PLAN was a numeric grep that no longer fits the post-integration reality.

**Suggested fix:** Note in next plan template that purely numeric parity grep checks become invalidated when new test classes are added. Not a regression; just a paper-trail observation.

### F5 [NIT] PRIV-03 leak guard in chat command uses a "safe" trace, not adversarial

**Where:** `tests/cli/test_chat_command.py::test_trace_does_not_leak_note_content_in_stderr` constructs a `safe_trace` containing only paths/queries/etc. (no SECRET in any field) and asserts SECRET doesn't reach stderr. The test name suggests an adversarial leak guard but the actual data flow is benign.

**Reality:** The structural pin (`test_trace_dataclasses_have_no_content_fields` in `test_contracts.py`) DOES enforce that AttemptTrace cannot carry content. The chat command's leak test is more of a "ensure trace_render's output doesn't accidentally include the prose response" check. The end-to-end PRIV-03 guard for ask is genuinely adversarial (`_result_with_secret_in_content` puts SECRET in `RetrievedNote.content` and asserts it never reaches `--trace` output via either stderr or stdout JSON envelope), so PRIV-03 is well-pinned overall.

**Suggested fix:** Either rename the chat test to clarify (`test_trace_does_not_render_assistant_response_to_stderr`) or strengthen it to actually inject SECRET into a path/query field that COULD be rendered. Low priority — the structural pin already covers this.

## Deviation assessment

1. **Test fakes option (a) — duplicate-locally chosen.** REASONABLE. The trade-off was: ~30 lines duplicated vs. project-wide tests/__init__.py addition + 4-file relative-to-absolute import refactor. Picking option (a) keeps the diff small and the test fakes module independent. The duplicate is in trivial scripted-fake code (`reformulate_query`/`judge_sufficiency` returning from a list); regression risk is low. Documented for posterity. APPROVED.

2. **Autouse fixture in tests/cli/test_ask_command.py for legacy tests (loop_enabled mark).** REASONABLE — Rule 3 fix. Without the autouse stub, all 14 pre-Phase-7 ask tests would crash because `MagicMock` LLMService doesn't have `reformulate_query`/`judge_sufficiency` scripted, and the orchestrator with default settings WOULD attempt them. Patching each test individually was rejected as too noisy; centralizing via autouse + opt-out marker is the cleanest pattern. The marker is registered in `pyproject.toml`. APPROVED.

3. **ChatSession count parity 24 vs 22 (new tests added sites).** REASONABLE. The literal acceptance criterion is invalidated by adding new test classes that intentionally use enabled mode for integration testing. The intent of the criterion (existing tests run on disable) is satisfied. See F4 above. APPROVED.

4. **`scripts/__init__.py` added.** REASONABLE. The acceptance criterion's `python -c "import scripts.bench_iterative_retrieval"` requires `scripts/` to be a package. Adding an empty `__init__.py` is the minimal change; it does not affect the standalone `python scripts/bench_iterative_retrieval.py` invocation. APPROVED.

5. **NIT findings 3-7 deferred (test polish).** ACCEPTABLE. The wave-3 plan-checker explicitly allowed "Address them inline if cheap; defer to a follow-up otherwise." None of the deferred NITs are blocking, and the user-visible Phase 7 surface is complete. Conservative scope discipline. APPROVED — but log them in a follow-up tracking issue if not already done.

**All 5 deviations are reasonable, defensible, and do not introduce regressions.**

## Recommendation

**READY TO MARK PHASE 7 COMPLETE.**

All 10 ROADMAP success criteria pass with PASS verdicts. All 13 CONTEXT decisions are honored in code with no silent contradictions. 572/572 unit tests pass. Critical risk surfaces (PRIV-03 stderr+stdout leak guards, double-empty `_INSUFFICIENT` preservation, filter-before-slice ordering, jaccard guard, disable byte-equivalence, hard 2-attempt cap) all have load-bearing tests. Operational smoke checks all pass.

The 5 INFO/NIT findings are paper-trail / methodology items, not Phase 7 implementation defects:
- F1: REQUIREMENTS.md traceability paper-trail — fix in next docs commit
- F2: Bench script cache-warming methodology — follow-up patch
- F3: Pre-existing kb-delete failure — track separately
- F4: Test parity grep drift — observation only
- F5: Chat PRIV-03 test could be stronger — structural pin already covers it

**Suggested follow-ups (NON-BLOCKING):**

1. Update `REQUIREMENTS.md` traceability table to reflect Phase 7's partial discharge of PRIV-03 (or merge fully if you consider the trace-surface PRIV-03 fully covered).
2. Patch `scripts/bench_iterative_retrieval.py` to randomize iter-vs-disabled order or take mean-of-3 to eliminate the cache-warming artifact.
3. (Optional) Open a tracking issue for the kb-delete integration failure if not already tracked.
4. Reinstall global `aurora` (per user `MEMORY.md` install-mode note) so `aurora ask --trace` and `aurora chat --trace` surface to the user via PATH.

---

*Verified: 2026-05-02*
*Verifier: Claude (gsd-verifier, autonomous goal-backward audit)*
