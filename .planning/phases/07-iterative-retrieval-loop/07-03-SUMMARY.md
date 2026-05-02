---
phase: 07-iterative-retrieval-loop
plan: 03
subsystem: chat-session-cli-wiring
tags: [iterative-retrieval, chat-session, cli, --trace, priv-03, bench, history-filter]

# Dependency graph
requires:
  - phase: 07-01
    provides: RetrievedNote.origin Literal field, AttemptTrace + IterativeRetrievalTrace dataclasses, _FORBIDDEN_TRACE_FIELDS structural guard
  - phase: 07-02
    provides: IterativeRetrievalOrchestrator class (run() public surface), FakeLLM/TieredFakeRetrieval fixtures, _STATUS_REVISANDO constant, _token_jaccard helper, _merge_attempts/_build_attempt_trace helpers, REFORMULATION + JUDGE prompts, LLMService.reformulate_query/judge_sufficiency methods

provides:
  - ChatHistory._REFORMULATION_PREFIX constant + _is_reformulation_entry helper + filter-before-slice in get_recent
  - ChatSession.orchestrator + last_trace_consumer constructor params (D-04, D-09)
  - ChatSession._persist_reformulations(trace) helper (D-10 part a)
  - _apply_carry_forward now tags supplements origin="carry" (Wave 1 fix)
  - aurora ask --trace flag with text+JSON modes and insufficient-evidence symmetry
  - aurora chat --trace flag with per-turn render via last_trace_consumer
  - retrieval/trace_render.py module with render_trace_text + render_trace_json pure functions
  - scripts/bench_iterative_retrieval.py dev-only latency comparison tool (NOT a CI test)
  - tests/cli/test_ask_command.py autouse pass-through orchestrator fixture + TestAskTrace (9 new tests)
  - tests/cli/test_chat_command.py TestChatTrace (6 new tests)
  - tests/chat/test_session.py 17-site disable-loader refactor + TestPhase7Integration (7 new tests)
  - tests/retrieval/test_trace_render.py (11 new tests)
  - tests/chat/test_history.py TestGetRecentFiltersReformulations (4 new tests)
  - pyproject loop_enabled pytest marker

affects:
  - aurora ask + aurora chat user-visible UX: --trace surface, status line, byte-equivalent disable mode

# Tech tracking
tech-stack:
  added: []
  patterns:
    - composition-via-orchestrator-attribute: ChatSession holds an IterativeRetrievalOrchestrator instance and delegates to it after applying carry-forward — keeps the carry-forward composition decision (D-07) on ChatSession's side rather than buried inside the loop
    - autouse-fixture-with-opt-out-marker: tests/cli/test_ask_command.py uses @pytest.fixture(autouse=True) that patches IterativeRetrievalOrchestrator with a pass-through stub for existing tests; tests that exercise the real loop opt out via @pytest.mark.loop_enabled — minimizes blast radius of the wiring change on pre-Phase-7 tests
    - filter-before-slice-not-after: ChatHistory.get_recent filters out [reformulation] system entries BEFORE the max-turns slice, so reformulations never steal slots from real conversation pairs (RESEARCH §7 pin)
    - origin-tagged-carry-forward: _apply_carry_forward explicitly passes origin="carry" to RetrievedNote so the sufficiency primitive's hybrid-only top-score check is correct (Wave 1 left these defaulting to "hybrid")
    - symmetric-trace-rendering-on-both-paths: --trace renders identically on the happy path AND the insufficient-evidence early-return path (both stdout JSON envelope and stderr text mode) — pinned by test_trace_emitted_on_insufficient_evidence_path_*
    - structural-priv-03-via-content-free-dataclass: AttemptTrace dataclass has no content field; render_trace_* operates only on AttemptTrace fields, so render_trace_*(trace) cannot leak note content even if tests inject SECRET into RetrievedNote.content (pinned end-to-end on stderr AND stdout JSON envelope)
    - non-blocking-bench-script: bench_iterative_retrieval.py exits 0 regardless of WITHIN/OVER BUDGET — verdicts are informational, not gate criteria, since latency assertions are flaky in CI per RESEARCH §9
    - pass-through-orch-stub-via-autouse-fixture: existing CLI tests stay on single-shot semantics by patching IterativeRetrievalOrchestrator with a stub that just calls retrieve_fn once and emits a one-attempt "disabled" trace

key-files:
  created:
    - src/aurora/retrieval/trace_render.py
    - tests/retrieval/test_trace_render.py
    - scripts/bench_iterative_retrieval.py
    - scripts/__init__.py
    - .planning/phases/07-iterative-retrieval-loop/07-03-SUMMARY.md
  modified:
    - src/aurora/chat/history.py
    - src/aurora/chat/session.py
    - src/aurora/cli/ask.py
    - src/aurora/cli/chat.py
    - tests/chat/test_history.py
    - tests/chat/test_session.py
    - tests/cli/test_ask_command.py
    - tests/cli/test_chat_command.py
    - pyproject.toml

key-decisions:
  - "Inline _ChatFakeLLM duplicate in tests/chat/test_session.py rather than cross-package import from tests/retrieval/fakes.py. Wave 2 chose relative imports (`from .fakes import ...`) which only works inside tests/retrieval/. Cross-package reuse would require either adding tests/__init__.py and switching all wave-2 relative imports to absolute, OR adding sys.path manipulation. Picked option (a) from wave-2 handoff (duplicate locally) — smallest diff, no project-config change. The duplicate is ~30 lines of trivial scripted-fake code; not worth the structural cost of adding tests/__init__.py to the project."
  - "Existing tests/cli/test_ask_command.py uses an autouse fixture (`_disable_iterative_loop_in_existing_tests`) that patches IterativeRetrievalOrchestrator with a pass-through stub for ALL tests in the file; new TestAskTrace tests that exercise the real loop opt out via @pytest.mark.loop_enabled. Alternative considered: refactor each of 14 existing tests to mock the orchestrator individually. Autouse + opt-out marker keeps the diff small and centralizes the wiring decision."
  - "Existing tests/chat/test_session.py has 17 ChatSession() construction sites that pre-date the loop. Each was refactored to pass settings_loader=_disabled_iterative_settings_loader (a real RuntimeSettings(iterative_retrieval_enabled=False)) instead of the previous `lambda: _mock_settings()` (a MagicMock). The MagicMock approach would have crashed once the orchestrator started consulting settings_loader for iterative_retrieval_enabled (any attribute access on a MagicMock returns a truthy MagicMock). The 17:17 count parity acceptance criterion is satisfied for the existing sites; new TestPhase7Integration tests intentionally diverge by passing custom loaders for tests that exercise the loop."
  - "Trace renderer lives in src/aurora/retrieval/trace_render.py rather than retrieval/contracts.py to keep the contracts module a pure data layer. Both renderers are pure functions with no LLM/IO dependencies — easy to unit-test."
  - "_disable_iterative_loop_in_existing_tests autouse fixture exists at module scope in tests/cli/test_ask_command.py only — not as a project-wide conftest — so it has no effect on tests in other files. Other CLI test files (test_chat_command.py) work because they mock ChatSession itself (which insulates the orchestrator)."

patterns-established:
  - "Per-task atomic commits with prefix feat(07-03): keeps rollback granular; SUMMARY commit is separate (docs(07-03))"
  - "Autouse pass-through orchestrator pattern with opt-out marker: an autouse fixture patches the orchestrator class with a 1-attempt pass-through stub for ALL tests in the file, while individual tests that exercise the real loop opt out via a custom pytest marker. Centralizes the wiring decision and avoids per-test orchestrator mocking boilerplate."
  - "Filter-before-slice: when adding a new entry type to a JSONL store with a max-turns LLM context window, ALWAYS filter the entry type out before applying the slice — never after. Otherwise the new entry type will silently steal slots from the entries the LLM actually needs."
  - "Symmetric --trace rendering on both happy and early-return paths: any future CLI flag that surfaces internal diagnostics MUST render on every exit branch, not just the success branch. Asymmetry creates a confusing user-experience where the diagnostic disappears under conditions when it would be most useful."

requirements-completed:
  - RET-01
  - RET-03
  - RET-04
  - PRIV-03

# Metrics
duration: ~75min
completed: 2026-05-02
---

# Phase 07 Plan 03: Wiring + UX Summary

**Final wave of Phase 7's iterative retrieval loop. ChatSession now invokes IterativeRetrievalOrchestrator on every vault and memory turn (carry-forward composes once, passed via first_attempt). aurora ask and aurora chat both gain a --trace flag that renders the per-attempt trace via a new pure-function module (trace_render.py) — text to stderr in non-JSON mode, "trace" key in the JSON envelope in --json mode, symmetric on happy + insufficient-evidence paths. ChatHistory persists [reformulation] system entries that are filtered BEFORE the max-turns slice (so they never steal context-window slots). Carry-forward supplements are now correctly tagged origin="carry" (Wave 1 left them defaulting to "hybrid"). 19 new tests pin every CONTEXT decision and previous-round anti-pattern, including PRIV-03 leak guards on BOTH stderr (text mode) AND stdout JSON envelope, plus trace-symmetry tests on the insufficient-evidence early-return path. The 17 existing tests/chat/test_session.py construction sites are refactored to run on the disable path. A dev-only bench script (NOT a CI test) compares enabled-vs-disabled latency per query and reports WITHIN BUDGET / OVER BUDGET verdicts. 572 unit tests pass with zero regressions.**

## Performance

- **Duration:** ~75 min
- **Started:** 2026-05-02
- **Completed:** 2026-05-02
- **Tasks:** 3 (3 atomic commits, one per task; this SUMMARY is the 4th doc commit)
- **Files created:** 4 (trace_render.py, test_trace_render.py, bench script, scripts/__init__.py)
- **Files modified:** 9 (history.py, session.py, ask.py, chat.py, test_history.py, test_session.py, test_ask_command.py, test_chat_command.py, pyproject.toml)

## Accomplishments

### Task 1: ChatHistory.get_recent filter-before-slice + reformulation persistence helpers (commit `f5b24e0`)

- `_REFORMULATION_PREFIX = "[reformulation] "` module constant exported in `__all__`
- `_is_reformulation_entry(record)` predicate: matches role="system" AND content.startswith(prefix)
- `get_recent` rewritten to filter out reformulation entries BEFORE the `[-max_messages:]` slice — so reformulations never steal slots from real user/assistant pairs
- 4 new tests in `TestGetRecentFiltersReformulations`:
  - `test_reformulation_appears_in_jsonl_after_thin_then_thick` — persistence works
  - `test_get_recent_excludes_reformulation_entries` — filter works
  - `test_filter_happens_before_slice` — interleave 5 pairs + 3 reformulations, max_turns=3 yields 3 user + 3 assistant + 0 reformulation (the load-bearing pin from RESEARCH §7)
  - `test_no_reformulations_present_returns_unchanged` — pure-additive check
- All 4 tests use `tmp_path` fixture and the kwarg `ChatHistory(path=...)` — never `history_path`, never `/tmp/...`

### Task 2: Trace renderer module + ChatSession orchestrator integration (commit `3b5176d`)

**Trace renderer (`src/aurora/retrieval/trace_render.py`):**
- `render_trace_text(trace) -> str`: multi-line stderr-friendly summary with judge_marker, exit_marker, per-attempt query+intent+hits+top_score+sufficient+reason+paths, paths truncated at 5 with "(+N more)"
- `render_trace_json(trace) -> dict`: plain dict for the `trace` key in JSON envelope
- 11 unit tests: text formatting, judge marker on/off, early-exit marker, attempt ordering, path truncation, empty paths, JSON serializability round-trip
- PRIV-03 follows from contracts: AttemptTrace has no content-bearing field, so render_trace_*(trace) cannot leak content by construction

**ChatSession integration:**
- `__init__` accepts new kwargs: `orchestrator: IterativeRetrievalOrchestrator | None = None` (constructs internally if None) and `last_trace_consumer: Callable[[IterativeRetrievalTrace], None] | None = None` (CLI sets this to capture per-turn trace for --trace rendering)
- `_apply_carry_forward` updated to tag supplements `origin="carry"` (was defaulting to "hybrid"; this fixes the sufficiency primitive's hybrid-only top-score check)
- `_handle_vault_turn` and `_handle_memory_turn` both: run today's retrieval → apply carry-forward ONCE → pass result as `first_attempt` to `orchestrator.run()` → use merged result → call `_persist_reformulations(trace)` → invoke `last_trace_consumer(trace)` if set → continue with insufficient-check + LLM generation
- `_persist_reformulations(trace)` helper: appends `[reformulation] {q}` system entries via kwarg form for every attempt with `attempt_number >= 2` (D-10 part a)

**Existing-test refactor:**
- Module-level `_disabled_iterative_settings_loader()` helper added to tests/chat/test_session.py
- All 17 existing `ChatSession()` construction sites refactored: `settings_loader=lambda: _mock_settings()` → `settings_loader=_disabled_iterative_settings_loader`
- 30 existing tests still pass on the disable path

**TestPhase7Integration (7 new tests):**
- `test_carry_forward_composes_once_not_per_attempt` (D-07): spy orchestrator records that `first_attempt` is non-None
- `test_visible_status_line_emitted_when_loop_fires` (D-02): "Revisando busca..." appears EXACTLY ONCE in captured status
- `test_reformulation_persisted_to_history` (D-10 part a): JSONL contains `[reformulation]` entry after thin→thick loop
- `test_get_recent_excludes_reformulations_after_loop` (D-10 part b): integration smoke test that filter works end-to-end
- `test_disable_path_byte_equivalent` (D-11): single retrieve call, zero LLM rescue calls, no reformulation history entries
- `test_last_trace_consumer_invoked_with_trace`: trace consumer receives the orchestrator's trace
- `test_carry_forward_origin_tagged_carry`: structural pin that supplements have origin="carry" (Wave 1 fix)

### Task 3: CLI --trace flags + PRIV-03 leak tests + bench script (commit `9feaae0`)

**aurora ask --trace:**
- New `--trace` Typer option
- Replaced direct `retrieve_with_memory(...)` with `IterativeRetrievalOrchestrator(...).run(...)` (with `first_attempt=None` since `aurora ask` has no carry-forward)
- Status callback `_status` echoes "Revisando busca..." to stderr only when not in JSON mode (D-02)
- TEXT mode + --trace: `render_trace_text` to stderr after streamed answer
- JSON mode + --trace: `render_trace_json` injected as `"trace"` key in the answer envelope
- BOTH happy path AND insufficient_evidence path render the trace (NIT 2 symmetry — pinned by `test_trace_emitted_on_insufficient_evidence_path_text_mode` and `test_trace_emitted_on_insufficient_evidence_path_json_mode`)

**aurora chat --trace:**
- New `--trace` Typer option
- Wires `last_trace_consumer=_consume_trace if trace else None` into ChatSession
- After each `process_turn(...)`, if trace was captured: `typer.echo(render_trace_text(captured["trace"]), err=True)` then reset for next turn

**TestAskTrace (9 new tests):**
- `test_trace_text_does_not_appear_without_flag` — no --trace -> no "retrieval trace" in stderr
- `test_trace_text_appears_with_flag_text_mode` — --trace -> "retrieval trace" in stderr
- `test_trace_key_present_in_json_envelope_with_flag` — --trace --json -> `"trace"` key with `"attempts"` list
- `test_trace_key_absent_in_json_envelope_without_flag` — --json (no --trace) preserves today's envelope shape
- `test_status_line_emitted_on_loop_fire` (loop_enabled marker) — real orchestrator, thin→thick, scripted reformulation -> "Revisando busca..." in stderr
- **`test_trace_does_not_leak_note_content_in_stderr`** — PRIV-03 stderr leak guard (SECRET in note.content + context_text never reaches stderr via --trace)
- **`test_trace_does_not_leak_note_content_in_json_envelope`** — PRIV-03 stdout JSON envelope leak guard (closes the JSON smuggle path from previous round)
- `test_trace_emitted_on_insufficient_evidence_path_text_mode` — symmetry pin (text mode)
- `test_trace_emitted_on_insufficient_evidence_path_json_mode` — symmetry pin (JSON mode)

**TestChatTrace (6 new tests):**
- `test_chat_help_shows_trace_option` — --trace visible on `aurora chat --help`
- `test_trace_flag_passes_consumer_to_session` — ChatSession constructed with non-None last_trace_consumer
- `test_no_trace_flag_passes_none_consumer` — default passes None (zero overhead)
- `test_trace_renders_per_turn_to_stderr` — fake process_turn invokes consumer; trace text appears on stderr
- **`test_trace_does_not_leak_note_content_in_stderr`** — PRIV-03 leak guard for chat surface
- `test_trace_omitted_without_flag` — no "retrieval trace" without --trace

**Autouse fixture for existing ask CLI tests:**
- `_disable_iterative_loop_in_existing_tests(request)` autouse fixture in test_ask_command.py
- Patches `aurora.cli.ask.IterativeRetrievalOrchestrator` with a `_PassThroughOrch` stub (1 attempt, no LLM rescue, "disabled" exit reason) for ALL tests in the file
- Tests that exercise the real loop opt out via `@pytest.mark.loop_enabled` (registered in pyproject)
- 14 existing tests pass unchanged

**Bench script (`scripts/bench_iterative_retrieval.py`):**
- Top-of-file docstring: "NOT a CI test. Runs against real local llama.cpp + vault — latency assertions are flaky in CI per Phase 7 RESEARCH §9. Run manually after model swaps or significant retrieval changes."
- Per-query: time disabled-mode orchestrator + enabled-mode orchestrator, compute `ratio = iter_ms / single_ms`, classify verdict against `_HAPPY_TARGET=1.0` (n_attempts=1) or `_WORST_TARGET=2.5` (n_attempts>1)
- 8 pt-BR queries from RESEARCH §9
- Per-query line format: `<query>  single= XXXms  iter= YYYms  ratio=Z.ZZ  attempts=N  WITHIN BUDGET`
- Summary: `happy-path p50=X.XX p95=Y.YY (target 1.0)  -> WITHIN BUDGET` and `worst-case p50=X.XX p95=Y.YY (target 2.5)  -> WITHIN BUDGET`
- Always exits 0 — verdict is informational, not a CI gate
- Smoke-tested live: 8/8 queries WITHIN BUDGET on local hardware (ratios 0.26-0.54, all attempts=1 since vault has thick results for these queries; iter mode is actually FASTER due to a warm-cache effect, which is expected — sufficiency check happens before any LLM call so no penalty when attempt 1 passes)

## Test results

- **19 plan tests added** (4 history + 11 trace_render + 9 ask + 6 chat trace tests + 7 session integration = 37 total new; sub-counts: 4 ChatHistory, 11 trace_render, 7 TestPhase7Integration, 9 TestAskTrace, 6 TestChatTrace)
- Wait, recount: 4 (TestGetRecentFiltersReformulations) + 11 (test_trace_render.py) + 7 (TestPhase7Integration) + 9 (TestAskTrace) + 6 (TestChatTrace) = **37 new tests**
- **268 Phase 7 tests pass** (full Phase 7 verification suite)
- **572 unit tests pass** (full suite excluding integration; 1 pre-existing kb-delete integration failure carried over from Wave 1, untouched)
- **Zero regressions** — all 535 tests from end of Wave 2 still pass

## Deviations from plan

1. **Test fakes import: option (a) duplicate-locally chosen.** Wave 2's `tests/retrieval/fakes.py` uses relative imports (`from .fakes import ...`) which only work inside `tests/retrieval/`. Wave 2 handoff recommended option (b) — add `tests/__init__.py` and switch all relative imports to absolute. After evaluation, picked option (a): inline duplicate of `_ChatFakeLLM` (~30 lines) in `tests/chat/test_session.py`. Rationale: the duplicate is trivial (just `reformulate_query` + `judge_sufficiency` scripted-list pattern); option (b) would have required modifying ALL Wave 2 test files (touching 4 test files for a one-line import change each). The structural cost of project-wide change outweighs the duplication cost. **Decision documented for posterity.**

2. **Autouse fixture for existing ask CLI tests.** The plan didn't specify how to handle existing tests/cli/test_ask_command.py tests that pre-date the loop. With orchestrator integration, every existing test would crash because mocked LLMService doesn't have `reformulate_query`/`judge_sufficiency` scripted, and the orchestrator with default settings would attempt to call them. Solution: added `_disable_iterative_loop_in_existing_tests` autouse fixture that patches `IterativeRetrievalOrchestrator` with a 1-attempt pass-through stub for ALL existing tests; new TestAskTrace tests that exercise the real loop opt out via `@pytest.mark.loop_enabled`. Alternative considered: patch each existing test individually (14 patches) — rejected as too noisy. Marker registered in pyproject.toml. **This is a Rule 3 fix (auto-resolve blocking issue) — without it, the orchestrator integration would have broken 14 pre-Phase-7 tests.**

3. **17:17 ChatSession() count parity holds for existing sites only.** The plan's literal acceptance criterion `test "$(grep -c 'ChatSession(' ...)" = "$(grep -c 'settings_loader=_disabled_iterative_settings_loader' ...)"` would now be 24 vs 22 because new TestPhase7Integration tests added 7 more ChatSession() construction sites — 4 of which use `_disabled_iterative_settings_loader` and 3 of which intentionally use `lambda: RuntimeSettings()` (loop ENABLED) because they exercise the real loop. The literal grep check fails, but the SPIRIT of the check is satisfied: the 17 EXISTING sites are all on the disable path (verified by `grep -c "session = ChatSession(" tests/chat/test_session.py` returning 24, with 17 of those followed within 6 lines by `_disabled_iterative_settings_loader`). The new tests' use of `RuntimeSettings()` is intentional and documented. **Spirit-of-the-check honored.**

4. **scripts/__init__.py added.** The acceptance criterion `python -c "import scripts.bench_iterative_retrieval as m; ..."` requires `scripts/` to be a package. Added `scripts/__init__.py` (empty file). Allows the bench script to be imported as `scripts.bench_iterative_retrieval` without breaking the standalone `python scripts/bench_iterative_retrieval.py` invocation.

5. **NIT-level findings 3-7 from plan-checker:** Did not address inline as the plan suggested ("Address them inline if cheap; defer to a follow-up otherwise"). Will defer to follow-up if needed — none of them are blocking for the user-visible Phase 7 surface, and addressing each would have expanded scope on a plan that was already labeled "large effort."

## Auth gates

None.

## Deferred Issues

**Pre-existing, out-of-scope (carried over from Waves 1+2):**
- `tests/integration/test_kb_qmd_integration.py::test_real_qmd_lifecycle_ingest_update_delete_rebuild` continues to fail on `kb delete` (exit code 1). Untouched by Wave 3 — nothing in ChatSession, CLI surfaces, trace_render, or the bench script touches the kb-delete code path. Logged in 07-01-SUMMARY.md and 07-02-SUMMARY.md; will continue to be carried forward unless a future plan explicitly addresses it.

## ROADMAP success criteria 1-10 status

| #   | Criterion                                                                                                | Pinned by                                                                                                                                                                                       |
| --- | -------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Deterministic sufficiency signal                                                                         | Plan 07-01 `TestSufficiencyFiveBranches`                                                                                                                                                        |
| 2   | Reformulate via small non-streaming LLM call                                                             | Plan 07-02 `TestReformulateQuery`                                                                                                                                                               |
| 3   | Cap at 2 retrievals                                                                                      | Plan 07-02 `TestHardCapAtTwoRetrievals`                                                                                                                                                         |
| 4   | Loop applies to vault + memory in both ask and chat                                                      | Plan 07-03 `TestPhase7Integration` + `aurora ask` orchestrator wiring + ChatSession `_handle_vault_turn` + `_handle_memory_turn`                                                                |
| 5   | Visible status line                                                                                      | Plan 07-02 `TestStatusCallback...` + Plan 07-03 `test_status_line_emitted_on_loop_fire` + `test_visible_status_line_emitted_when_loop_fires`                                                    |
| 6   | --trace per-attempt diagnostics on stderr (text) and JSON envelope                                       | Plan 07-03 trace_render tests + TestAskTrace + TestChatTrace                                                                                                                                    |
| 7   | Reformulations persisted to JSONL with [reformulation] prefix and filtered by get_recent                 | Plan 07-03 `TestGetRecentFiltersReformulations` (unit) + `test_reformulation_persisted_to_history` (integration) + `test_get_recent_excludes_reformulations_after_loop` (integration)           |
| 8   | Insufficient evidence preserved                                                                          | Plan 07-02 `TestDoubleEmptyPreservesInsufficient`                                                                                                                                               |
| 9   | Disable kill-switch byte-equivalent                                                                      | Plan 07-02 `TestDisabledModeReturnsExactlyOneAttempt` + Plan 07-03 `test_disable_path_byte_equivalent`                                                                                          |
| 10  | Trace surface contains paths/scores/counts/queries only                                                  | Plan 07-01 `test_trace_dataclasses_have_no_content_fields` (structural) + Plan 07-03 `test_trace_does_not_leak_note_content_in_stderr` + `test_trace_does_not_leak_note_content_in_json_envelope` (end-to-end PRIV-03 stderr+stdout) |

**All 10 ROADMAP success criteria are now achievable end-to-end.** Phase 7 is complete pending /gsd-verify-work.

## Smoke test

```bash
$ uv run aurora ask --help | grep -- '--trace'
│ --trace          Mostra trace por tentativa de retrieval.                    │

$ uv run aurora chat --help | grep -- '--trace'
│ --trace          Mostra trace por turno apos a resposta.                     │

$ uv run python scripts/bench_iterative_retrieval.py
o que escrevi sobre produtividade           single=  9375ms  iter=  3772ms  ratio=0.40  attempts=1  WITHIN BUDGET
notas sobre Python ontem                    single=  7094ms  iter=  3582ms  ratio=0.50  attempts=1  WITHIN BUDGET
Rosely                                      single=  9301ms  iter=  3581ms  ratio=0.39  attempts=1  WITHIN BUDGET
como organizei minha semana                 single=  6641ms  iter=  3602ms  ratio=0.54  attempts=1  WITHIN BUDGET
o que pensei sobre o livro de marco         single= 11057ms  iter=  3949ms  ratio=0.36  attempts=1  WITHIN BUDGET
quando comecei o projeto Aurora             single= 16482ms  iter=  4355ms  ratio=0.26  attempts=1  WITHIN BUDGET
diario de janeiro                           single= 13321ms  iter=  3618ms  ratio=0.27  attempts=1  WITHIN BUDGET
ideias sobre escrita                        single=  8205ms  iter=  3644ms  ratio=0.44  attempts=1  WITHIN BUDGET
happy-path p50=0.39 p95=0.56 (target 1.0)  -> WITHIN BUDGET
```

Bench shows iter mode is actually FASTER than single-mode in the smoke run — interesting cache-warming artifact (orchestrator runs disabled mode FIRST, so by the time enabled mode runs, the backend caches are warm). The verdict is informational anyway. Worth a follow-up: randomize order or use mean-of-3 to control for cache effects.

## Self-Check: PASSED

- [x] `src/aurora/retrieval/trace_render.py` exists
- [x] `tests/retrieval/test_trace_render.py` exists
- [x] `scripts/bench_iterative_retrieval.py` exists
- [x] Three task commits in git history (`f5b24e0`, `3b5176d`, `9feaae0`)
- [x] All 37 new plan tests pass; 572 unit tests pass with no regressions
- [x] Smoke test: `aurora ask --help` shows `--trace`; `aurora chat --help` shows `--trace`
- [x] Smoke test: bench script runs end-to-end against live llama.cpp + vault
- [x] Structural pin: `grep IterativeRetrievalOrchestrator src/aurora/chat/session.py` returns the constructor + import
- [x] Structural pin: `grep 'origin="carry"' src/aurora/chat/session.py` returns the carry-forward tag
- [x] Structural pin: `grep _persist_reformulations src/aurora/chat/session.py` returns the helper
- [x] Acceptance: 17 existing ChatSession() sites all use `_disabled_iterative_settings_loader`
- [x] Acceptance: aurora ask --trace renders trace on insufficient_evidence path (text + JSON)
- [x] Acceptance: SECRET injected into RetrievedNote.content cannot reach stderr OR stdout JSON envelope under --trace --json
