---
phase: 03-grounded-retrieval-experience
plan: "02"
subsystem: cli
tags: [typer, retrieval, llm, streaming, grounded-qa]

# Dependency graph
requires:
  - phase: 03-01
    provides: RetrievalService, LLMService, INSUFFICIENT_EVIDENCE_MSG, retrieval/contracts.py
provides:
  - aurora ask CLI command for single-shot grounded Q&A
  - Streaming vault-grounded answers to terminal
  - JSON output mode with query/answer/sources/insufficient_evidence structure
  - pt-BR refusal on insufficient evidence
affects:
  - 03-03-chat-session
  - any phase that extends or modifies the ask pipeline

# Tech tracking
tech-stack:
  added: []
  patterns:
    - ask_app registered via app.add_typer(ask_app, name='ask') — same pattern as kb_app
    - typer callback with invoke_without_command=True and context_settings allow_interspersed_args=True
    - Streaming output uses print(token, end='', flush=True) not typer.echo (Pitfall 7)
    - JSON mode collects tokens silently then prints final JSON blob
    - Privacy-safe logging: DEBUG logs paths+scores, never note content

key-files:
  created:
    - src/aurora/cli/ask.py
    - src/aurora/retrieval/contracts.py
    - src/aurora/retrieval/service.py
    - src/aurora/retrieval/qmd_search.py
    - src/aurora/llm/service.py
    - src/aurora/llm/prompts.py
    - src/aurora/llm/streaming.py
    - tests/cli/test_ask_command.py
  modified:
    - src/aurora/cli/app.py
    - src/aurora/runtime/settings.py

key-decisions:
  - "Use context_settings={'allow_interspersed_args': True} on ask_app Typer to allow --json after positional QUERY argument"
  - "ask_app uses @ask_app.callback(invoke_without_command=True) so aurora ask 'query' works without extra sub-command level"
  - "RuntimeSettings extended with retrieval_top_k=7, retrieval_min_score=0.30, chat_history_max_turns=10 (from plan 03-01 outputs)"

patterns-established:
  - "Streaming tokens: print(token, end='', flush=True) — never typer.echo for incremental output"
  - "JSON mode token collection: silent lambda collects into list, prints final JSON after streaming completes"
  - "Always retrieve, no intent routing (D-15): ask_command calls RetrievalService unconditionally"

requirements-completed: [RET-01, RET-02, RET-03, RET-04, CLI-03]

# Metrics
duration: 4min
completed: 2026-04-03
---

# Phase 03 Plan 02: Aurora Ask Command Summary

**`aurora ask "query"` streams vault-grounded answers to terminal with inline citations via RetrievalService -> LLMService pipeline, with --json mode, pt-BR refusal on insufficient evidence, and no intent routing.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-04-03T23:26:25Z
- **Completed:** 2026-04-03T23:29:55Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 10

## Accomplishments

- `aurora ask "query"` command wired end-to-end: RetrievalService.retrieve -> LLMService.ask_grounded
- Streaming output via `print(token, end="", flush=True)` correctly updates terminal incrementally
- JSON mode (`--json`) returns structured payload with query, answer, sources list, insufficient_evidence flag
- pt-BR refusal message on insufficient evidence, exit 0 (not error)
- DEBUG logs note paths and scores but never note content (D-07 privacy-safe)
- 9 unit tests covering all behavior paths, all passing

## Task Commits

1. **Task 1 RED: Failing tests** - `4d4d83a` (test)
2. **Task 1 GREEN: Implementation** - `0729fd0` (feat)

## Files Created/Modified

- `src/aurora/cli/ask.py` - ask_app Typer with callback-based ask_command, full grounded Q&A pipeline
- `src/aurora/cli/app.py` - Added ask_app import and registration
- `src/aurora/runtime/settings.py` - Added retrieval_top_k, retrieval_min_score, chat_history_max_turns fields
- `src/aurora/retrieval/contracts.py` - Frozen dataclasses: QMDSearchHit, QMDSearchResponse, RetrievedNote, RetrievalResult
- `src/aurora/retrieval/service.py` - RetrievalService: search -> dedup -> fetch -> context assembly
- `src/aurora/retrieval/qmd_search.py` - QMDSearchBackend: qmd query and qmd get CLI transport
- `src/aurora/llm/service.py` - LLMService: ask_grounded, chat_turn, classify_intent
- `src/aurora/llm/prompts.py` - SYSTEM_PROMPT_GROUNDED, INSUFFICIENT_EVIDENCE_MSG, INTENT_PROMPT
- `src/aurora/llm/streaming.py` - SSE streaming parser for llama.cpp /v1/chat/completions
- `tests/cli/test_ask_command.py` - 9 tests covering all ask command behavior paths

## Decisions Made

- Used `context_settings={"allow_interspersed_args": True}` on `ask_app` Typer — necessary to allow `--json` after positional query argument when registered as a sub-typer. Without this, click's group arg parser raises MissingParameter.
- Retrieval and LLM modules copied from plan 03-01 outputs in main repo (parallel execution context).
- RuntimeSettings extended with retrieval/LLM config fields needed by QMDSearchBackend and LLMService.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] RuntimeSettings missing retrieval_top_k, retrieval_min_score, chat_history_max_turns**
- **Found during:** Task 1 (GREEN phase, after copying retrieval module)
- **Issue:** QMDSearchBackend references `settings.retrieval_top_k` and `settings.retrieval_min_score` which didn't exist in this worktree's RuntimeSettings
- **Fix:** Added three fields with defaults and validator from plan 03-01 output (main repo settings.py)
- **Files modified:** `src/aurora/runtime/settings.py`
- **Verification:** Tests pass, QMDSearchBackend instantiates without AttributeError
- **Committed in:** `0729fd0` (Task 1 GREEN commit)

**2. [Rule 3 - Blocking] ask_app needed `context_settings` to parse --json after positional arg**
- **Found during:** Task 1 (GREEN phase, debugging test_ask_json_output failure)
- **Issue:** `aurora ask "query" --json` returned exit code 2 (MissingParameter) — click group context intercepted `--json` as a subcommand arg, not an option for the callback
- **Fix:** Added `context_settings={"allow_interspersed_args": True}` to `ask_app = typer.Typer(...)`
- **Files modified:** `src/aurora/cli/ask.py`
- **Verification:** `test_ask_json_output` passes, all 9 tests pass
- **Committed in:** `0729fd0` (Task 1 GREEN commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3 - blocking)
**Impact on plan:** Both fixes necessary for correct operation. No scope creep.

## Issues Encountered

- Parallel execution: retrieval and llm modules from plan 03-01 were not yet in this worktree — copied from main repo which had them from the 03-01 agent worktree. This is expected in parallel phase execution.

## Known Stubs

None — ask command is fully wired to real services (RetrievalService and LLMService). No hardcoded responses or placeholders.

## Next Phase Readiness

- `aurora ask` command is fully functional and tested
- RET-01 through RET-04 and CLI-03 requirements satisfied
- Ready for plan 03-03 (chat session / multi-turn) to build on ask_app pattern

---
*Phase: 03-grounded-retrieval-experience*
*Completed: 2026-04-03*
