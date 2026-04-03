---
phase: 03-grounded-retrieval-experience
plan: 01
subsystem: retrieval
tags: [qmd, llama-cpp, sse, streaming, rag, grounded-qa, intent-classification]

# Dependency graph
requires:
  - phase: 02-vault-knowledge-base-lifecycle
    provides: QMDCliBackend shell-out pattern, kb_qmd_index_name/collection_name in RuntimeSettings
  - phase: 01.1-llama-cpp-server-lifecycle-via-cli-auto-start-stop-health-status
    provides: LlamaRuntimeClient, endpoint_url/model_id in RuntimeSettings

provides:
  - RetrievalService: search->fetch->dedup->truncate->context assembly (src/aurora/retrieval/service.py)
  - QMDSearchBackend: qmd query + qmd get shell-out transport (src/aurora/retrieval/qmd_search.py)
  - Retrieval contracts: QMDSearchHit, QMDSearchResponse, RetrievedNote, RetrievalResult (src/aurora/retrieval/contracts.py)
  - LLMService: ask_grounded, chat_turn, classify_intent via llama.cpp (src/aurora/llm/service.py)
  - SSE streaming parser for /v1/chat/completions with 120s timeout (src/aurora/llm/streaming.py)
  - System prompts enforcing pt-BR, inline citations, grounding rules (src/aurora/llm/prompts.py)
  - RuntimeSettings extended with retrieval_top_k (5-10), retrieval_min_score, chat_history_max_turns

affects:
  - 03-02 (aurora ask CLI command consuming RetrievalService + LLMService)
  - 03-03 (aurora chat CLI command with intent routing and session persistence)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - QMDSearchBackend mirrors QMDCliBackend constructor pattern (injectable command_runner + settings_loader)
    - SSE streaming uses urllib.request with injectable urlopen_fn for testability
    - LLMService injects stream_fn/sync_fn for unit test isolation (no real HTTP calls in tests)
    - RetrievalService uses MAX_CONTEXT_CHARS=12000 truncation with score-descending priority

key-files:
  created:
    - src/aurora/retrieval/__init__.py
    - src/aurora/retrieval/contracts.py
    - src/aurora/retrieval/qmd_search.py
    - src/aurora/retrieval/service.py
    - src/aurora/llm/__init__.py
    - src/aurora/llm/prompts.py
    - src/aurora/llm/streaming.py
    - src/aurora/llm/service.py
    - tests/retrieval/__init__.py
    - tests/retrieval/test_qmd_search.py
    - tests/retrieval/test_retrieval_service.py
    - tests/llm/__init__.py
    - tests/llm/test_prompts.py
    - tests/llm/test_streaming.py
    - tests/llm/test_llm_service.py
  modified:
    - src/aurora/runtime/settings.py

key-decisions:
  - "QMDSearchBackend.search() formats min_score as f'{value:.2f}' string for qmd --min-score flag"
  - "RetrievalService.retrieve() returns immutable _INSUFFICIENT sentinel for empty/failed searches"
  - "LLMService.classify_intent() sends only single intent-formatted message — no conversation history passed to classifier"
  - "stream_chat_completions uses 120s timeout (STREAM_TIMEOUT_SECONDS) separate from 3s health probe"
  - "RuntimeSettings.retrieval_top_k enforces 5-10 range via field_validator"

patterns-established:
  - "Injectable transport functions (stream_fn, sync_fn, urlopen_fn) enable unit testing without HTTP"
  - "CommandRunner type alias (Callable[[tuple[str, ...]], CommandResult]) used for QMD shell-out injection"
  - "SSE parsing: check 'data: ' prefix, handle '[DONE]' sentinel, skip non-data lines"

requirements-completed: [RET-01, RET-02, RET-03, RET-04, CLI-03]

# Metrics
duration: 4min
completed: 2026-04-03
---

# Phase 03 Plan 01: Retrieval and LLM Foundation Summary

**QMD-backed RetrievalService (search->fetch->dedup->truncate) and LLMService (SSE streaming + intent classification) with pt-BR grounding prompts and 47 new unit tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-03T23:16:38Z
- **Completed:** 2026-04-03T23:20:00Z
- **Tasks:** 2
- **Files modified:** 16 (15 created, 1 modified)

## Accomplishments

- RetrievalService orchestrates QMD search -> fetch full notes -> dedup by path -> truncate to 12,000 chars context
- LLMService streams grounded responses and classifies intent via non-streaming sync call
- System prompts enforce pt-BR, inline citations (`[caminho/nota.md]`), vault-only grounding, and citation deduplication
- RuntimeSettings extended with `retrieval_top_k` (5-10 validated), `retrieval_min_score`, `chat_history_max_turns`
- 47 unit tests passing: 23 retrieval + 24 LLM

## Task Commits

Each task was committed atomically (TDD: test -> feat):

1. **Task 1: Retrieval contracts, QMDSearchBackend, RetrievalService (RED)** - `e576ddb` (test)
2. **Task 1: Retrieval contracts, QMDSearchBackend, RetrievalService (GREEN)** - `5e4c3cd` (feat)
3. **Task 2: LLM prompts, streaming parser, LLMService (RED)** - `fb1c23b` (test)
4. **Task 2: LLM prompts, streaming parser, LLMService (GREEN)** - `ce19fdd` (feat)

_Note: TDD tasks have two commits each (failing tests → passing implementation)_

## Files Created/Modified

- `src/aurora/retrieval/contracts.py` - Frozen dataclasses: QMDSearchHit, QMDSearchResponse, QMDSearchDiagnostic, RetrievedNote, RetrievalResult
- `src/aurora/retrieval/qmd_search.py` - QMDSearchBackend: search() calls qmd query --json, fetch() calls qmd get with collection-prefixed path
- `src/aurora/retrieval/service.py` - RetrievalService: orchestrates search->fetch->dedup->truncate (MAX_CONTEXT_CHARS=12000)
- `src/aurora/llm/prompts.py` - SYSTEM_PROMPT_GROUNDED (pt-BR, citations, grounding, dedup), SYSTEM_PROMPT_CHAT, INTENT_PROMPT, INSUFFICIENT_EVIDENCE_MSG
- `src/aurora/llm/streaming.py` - stream_chat_completions (SSE 120s), chat_completion_sync (non-streaming for intent)
- `src/aurora/llm/service.py` - LLMService: ask_grounded, chat_turn, classify_intent
- `src/aurora/runtime/settings.py` - Added retrieval_top_k (validated 5-10), retrieval_min_score=0.30, chat_history_max_turns=10
- `tests/retrieval/test_qmd_search.py` - 11 tests for QMDSearchBackend subprocess args, JSON parsing, error handling
- `tests/retrieval/test_retrieval_service.py` - 12 tests for RetrievalService flow, truncation, dedup, RuntimeSettings fields
- `tests/llm/test_prompts.py` - 8 tests verifying prompt content requirements
- `tests/llm/test_streaming.py` - 6 tests for SSE parsing, timeout, endpoint URL
- `tests/llm/test_llm_service.py` - 10 tests for ask_grounded, chat_turn, classify_intent behavior

## Decisions Made

- `QMDSearchBackend.search()` formats `min_score` as `f"{value:.2f}"` to match expected `0.30` string format in subprocess args
- `RetrievalService._INSUFFICIENT` is a module-level sentinel constant returned for all empty/failed search cases, avoiding repeated object creation
- `LLMService.classify_intent()` sends only a single message to the LLM (no history) — explicitly per D-14 and Pitfall 5 from RESEARCH.md
- `STREAM_TIMEOUT_SECONDS = 120` is clearly separated from the 3s health probe timeout used by LlamaRuntimeClient

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The 3 pre-existing test failures in `tests/cli/test_kb_command.py` and `tests/runtime/test_kb_service.py` were documented as expected in the plan verification spec.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- RetrievalService and LLMService are wired and tested — ready to be consumed by `aurora ask` (plan 03-02) and `aurora chat` (plan 03-03)
- RuntimeSettings has all required fields for retrieval and chat tuning
- System prompts are hardcoded and grounding-compliant; the CLI commands only need to assemble the user-facing flow

---
*Phase: 03-grounded-retrieval-experience*
*Completed: 2026-04-03*

## Self-Check: PASSED

All created files confirmed on disk. All task commits verified in git history.
