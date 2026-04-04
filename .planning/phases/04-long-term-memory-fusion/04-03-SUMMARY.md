---
phase: 04-long-term-memory-fusion
plan: 03
subsystem: retrieval, memory, cli
tags: [dual-retrieval, episodic-memory, preferences, qmd, typer, chat-session]

# Dependency graph
requires:
  - phase: 04-01
    provides: EpisodicMemoryStore, MEMORY_COLLECTION, memory_top_k/memory_min_score settings, get_preferences_path, source field on RetrievedNote
  - phase: 04-02
    provides: ChatSession.turn_count/session_start_index, session.py with memory save pipeline
provides:
  - RetrievalService.retrieve_with_memory() querying both vault KB and aurora-memory QMD collection
  - SYSTEM_PROMPT_GROUNDED_WITH_MEMORY with dual-source citation instructions
  - build_system_prompt_with_preferences() for Tier 1 preferences injection
  - ChatSession accepting memory_backend with dual-retrieval dispatch
  - aurora memory list/search/edit/clear CLI command group

affects:
  - Any future phases using RetrievalService or ChatSession
  - Phase 04 integration testing

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Vault-first ordering in merged retrieval results (D-14)
    - Memory backend failure treated as empty results, not error (Pitfall 3)
    - Shared MAX_CONTEXT_CHARS budget across dual sources (Pitfall 4)
    - System prompt selected based on memory presence (with/without memory variant)
    - Preferences injected as "## Preferencias do usuario" section prepended to system prompt

key-files:
  created:
    - src/aurora/cli/memory.py
    - tests/cli/test_memory_command.py
  modified:
    - src/aurora/retrieval/service.py
    - src/aurora/llm/prompts.py
    - src/aurora/chat/session.py
    - tests/retrieval/test_retrieval_service.py
    - tests/chat/test_session.py

key-decisions:
  - "Vault turns now use chat_turn with manually assembled messages to give full control over system prompt selection and preferences injection, replacing ask_grounded which hardcoded the prompt."
  - "memory_backend=None in RetrievalService: retrieve_with_memory() still works without memory backend, falling back to KB-only results."
  - "ChatSession checks self._retrieval._memory_backend to dispatch retrieve vs retrieve_with_memory, keeping the routing decision in session.py."
  - "memory clear removes QMD collection via _remove_qmd_collection helper that silently ignores FileNotFoundError (qmd may not be installed)."

patterns-established:
  - "Dual-retrieval pattern: _dedup_hits + _fetch_notes helpers extracted for reuse across retrieve() and retrieve_with_memory()"
  - "Prompt injection pattern: build_system_prompt_with_preferences prepends preferences only when file exists and is non-empty"
  - "CLI memory command group follows same Typer patterns as kb.py (--json flag, --yes for destructive ops, pt-BR text)"

requirements-completed:
  - MEM-02
  - MEM-03
  - MEM-04

# Metrics
duration: 45min
completed: 2026-04-04
---

# Phase 04 Plan 03: Memory Retrieval Fusion Summary

**Dual-collection retrieval (vault + episodic memory) wired into chat pipeline via retrieve_with_memory(), with vault-first ordering, preferences injection, and aurora memory list/search/edit/clear CLI commands.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-04-04T22:00:00Z
- **Completed:** 2026-04-04T22:45:27Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- RetrievalService now has retrieve_with_memory() that queries both aurora-kb-managed and aurora-memory QMD collections, merges vault-first, and respects the shared MAX_CONTEXT_CHARS budget
- ChatSession dispatches to retrieve_with_memory when memory_backend is configured, selects SYSTEM_PROMPT_GROUNDED_WITH_MEMORY when memory results present, and injects preferences.md content
- aurora memory CLI group provides list (text/JSON), search (semantic QMD), edit ($EDITOR), and clear (with confirmation + QMD collection removal)

## Task Commits

Each task was committed atomically:

1. **Task 1 TDD RED: failing tests for dual-source retrieval** - `a09cb59` (test)
2. **Task 1 TDD GREEN: dual-source retrieval + memory-aware prompts** - `9997358` (feat)
3. **Task 2 TDD RED: failing tests for aurora memory CLI** - `903158d` (test)
4. **Task 2 TDD GREEN: aurora memory CLI command group** - `9537499` (feat)

_Note: TDD tasks have separate RED/GREEN commits_

## Files Created/Modified

- `src/aurora/retrieval/service.py` - Added memory_backend param, retrieve_with_memory(), extracted _dedup_hits/_fetch_notes/_assemble_context helpers
- `src/aurora/llm/prompts.py` - Added SYSTEM_PROMPT_GROUNDED_WITH_MEMORY, build_system_prompt_with_preferences()
- `src/aurora/chat/session.py` - Added memory_backend param, dual-retrieval dispatch, prompt selection, preferences injection; vault turns now use chat_turn with manually assembled messages
- `src/aurora/cli/memory.py` - New: memory_app Typer group with list/search/edit/clear commands
- `src/aurora/cli/app.py` - Added memory_app registration under "memory"
- `tests/retrieval/test_retrieval_service.py` - Added TestRetrieveWithMemory, TestDualSourceContext, TestVaultPriority, TestMemoryBackendFailure, TestMemoryPrompts
- `tests/chat/test_session.py` - Added TestChatSessionMemoryBackend, updated existing vault turn tests to reflect chat_turn-based implementation
- `tests/cli/test_memory_command.py` - New: comprehensive tests for all memory CLI commands

## Decisions Made

- Vault turns now use `chat_turn` with manually assembled messages (system + user with context) instead of `ask_grounded`. This gives full control over which system prompt is used (SYSTEM_PROMPT_GROUNDED vs SYSTEM_PROMPT_GROUNDED_WITH_MEMORY) and enables preferences injection. ask_grounded hardcoded the prompt.
- Memory backend failure (ok=False from QMD) treated as empty results, not propagated as error — ensures vault results are still returned on memory backend degradation (Pitfall 3).
- `_memory_backend = None` means retrieve_with_memory() falls back to KB-only path — makes the method safe to call without memory configured.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing test suite to reflect vault turns using chat_turn instead of ask_grounded**
- **Found during:** Task 1 GREEN (implementing ChatSession changes)
- **Issue:** Existing test `test_vault_turn_calls_ask_grounded_with_context` and `test_vault_turn_does_not_call_chat_turn` became invalid because vault turns now use `chat_turn` with injected system prompt (needed to support prompt selection)
- **Fix:** Updated 3 existing tests in TestChatSessionVaultIntent and TestChatSessionInsufficientEvidence to assert `chat_turn` called (not `ask_grounded`), added `_memory_backend = None` to mock_retrieval in _make_session helper
- **Files modified:** tests/chat/test_session.py
- **Verification:** 45 tests pass in retrieval + chat suites
- **Committed in:** 9997358 (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug fix in tests to match implementation contract change)
**Impact on plan:** Necessary correction — ask_grounded is still available in LLMService, but vault turns no longer use it since the system prompt needs to vary based on memory presence. Tests correctly reflect the new contract.

## Issues Encountered

- Pre-existing test failure in `test_kb_command.py::test_update_reports_privacy_safe_read_errors_without_forcing_delete` (FrozenInstanceError in KB lock code). Confirmed pre-existing by stash test, not caused by this plan. Deferred to separate fix.

## Next Phase Readiness

- MEM-02 (hybrid retrieval), MEM-03 (preferences injection), MEM-04 (memory CLI) are complete
- Phase 04 can proceed to integration validation or final summary
- aurora memory CLI is functional end-to-end pending QMD aurora-memory collection being populated via plan 02 write path

---
*Phase: 04-long-term-memory-fusion*
*Completed: 2026-04-04*

## Self-Check: PASSED

- src/aurora/cli/memory.py: FOUND
- src/aurora/retrieval/service.py: FOUND
- src/aurora/llm/prompts.py: FOUND
- .planning/phases/04-long-term-memory-fusion/04-03-SUMMARY.md: FOUND
- Commit a09cb59 (test RED task 1): FOUND
- Commit 9997358 (feat GREEN task 1): FOUND
- Commit 903158d (test RED task 2): FOUND
- Commit 9537499 (feat GREEN task 2): FOUND
