---
phase: 03-grounded-retrieval-experience
plan: 03
subsystem: chat
tags: [chat, intent-routing, jsonl, history, session, interactive-cli]

# Dependency graph
requires:
  - phase: 03-01
    provides: LLMService (classify_intent, ask_grounded, chat_turn), RetrievalService (retrieve), system prompts, RuntimeSettings.chat_history_max_turns

provides:
  - ChatHistory: JSONL-persisted conversation turns with get_recent context window capping (src/aurora/chat/history.py)
  - ChatSession: per-turn intent routing loop — vault (retrieval+grounded) vs chat (free-form) (src/aurora/chat/session.py)
  - aurora chat CLI command: interactive multi-turn loop with pt-BR welcome, exit commands, --clear flag (src/aurora/cli/chat.py)

affects:
  - app.py: chat_app registered as 'chat' subcommand

# Tech tracking
tech-stack:
  added: []
  patterns:
    - ChatHistory uses JSONL (one JSON per line) for append-only persistence — trivial replay and streaming writes
    - ChatSession injects history/retrieval/llm via constructor for unit test isolation
    - get_recent strips ts field, returning only role+content for LLM context messages
    - on_token and on_insufficient callbacks allow CLI and test code to intercept output without I/O coupling

key-files:
  created:
    - src/aurora/chat/__init__.py
    - src/aurora/chat/history.py
    - src/aurora/chat/session.py
    - src/aurora/cli/chat.py
    - tests/chat/__init__.py
    - tests/chat/test_history.py
    - tests/chat/test_session.py
    - tests/cli/test_chat_command.py
  modified:
    - src/aurora/cli/app.py

key-decisions:
  - "ChatHistory.get_recent returns role+content dicts only (strips ts) so callers pass directly to LLM messages list"
  - "ChatSession.process_turn persists history AFTER response is computed — avoids persisting failed turns"
  - "EXIT_COMMANDS set includes sair/exit/quit for flexibility while keeping pt-BR default"
  - "on_insufficient callback injected separately from on_token — allows CLI to choose print vs typer.echo independently"

requirements-completed: [RET-01, RET-02, RET-03, RET-04, CLI-03]

# Metrics
duration: 3min
completed: 2026-04-03
---

# Phase 03 Plan 03: Aurora Chat Command Summary

**Interactive `aurora chat` multi-turn session with intent routing, JSONL history persistence, and clean exit handling — 52 unit tests passing**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-03T23:26:55Z
- **Completed:** 2026-04-03T23:30:00Z
- **Tasks:** 2
- **Files modified:** 9 (8 created, 1 modified)

## Accomplishments

- ChatHistory persists turns as JSONL with role/content/ts fields; get_recent caps to max_turns*2 messages
- ChatSession classifies intent per turn using only the latest user message (Pitfall 5, D-14)
- Vault turns trigger fresh KB retrieval per turn (D-13) via RetrievalService then LLMService.ask_grounded
- Chat turns use SYSTEM_PROMPT_CHAT + capped recent history via LLMService.chat_turn
- Insufficient evidence on vault turns calls on_insufficient callback with INSUFFICIENT_EVIDENCE_MSG
- Both user and assistant turns persisted to JSONL after each process_turn call (D-12)
- `aurora chat --clear` wipes history file with pt-BR confirmation
- Clean exit on Ctrl+C, EOFError, and EXIT_COMMANDS (sair/exit/quit)
- 52 unit tests passing: 35 chat core + 17 CLI

## Task Commits

Each task was committed atomically (TDD: test -> feat):

1. **Task 1: ChatHistory and ChatSession (RED)** — `b14126f` (test)
2. **Task 1: ChatHistory and ChatSession (GREEN)** — `19564c7` (feat)
3. **Task 2: aurora chat CLI command (RED)** — `61e50b7` (test)
4. **Task 2: aurora chat CLI command (GREEN)** — `480816a` (feat)

_Note: TDD tasks have two commits each (failing tests → passing implementation)_

## Files Created/Modified

- `src/aurora/chat/history.py` — ChatHistory: append_turn, load, get_recent (capped), clear; HISTORY_FILENAME constant
- `src/aurora/chat/session.py` — ChatSession: process_turn with intent routing, vault/chat handlers, history persistence
- `src/aurora/cli/chat.py` — chat_app Typer, chat_command callback, EXIT_COMMANDS, --clear flag
- `src/aurora/cli/app.py` — Added chat_app import and registration (`app.add_typer(chat_app, name="chat")`)
- `tests/chat/test_history.py` — 20 tests: append, load, get_recent capping, default path, clear
- `tests/chat/test_session.py` — 15 tests: vault intent, chat intent, intent classification, history persistence, insufficient evidence
- `tests/cli/test_chat_command.py` — 17 tests: help output, welcome message, input routing, exit behaviors, --clear, app registration

## Decisions Made

- `ChatHistory.get_recent` strips `ts` field and returns only `{role, content}` so the returned list can be passed directly to the LLM messages array without transformation
- `process_turn` persists history only after the assistant response is computed (not before) — avoids orphaned user records if the LLM call fails
- EXIT_COMMANDS includes English variants (exit, quit) alongside Portuguese (sair) for usability without sacrificing the pt-BR default
- `on_insufficient` is a separate injectable callback (distinct from `on_token`) so the CLI can use different output mechanisms for different message types

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — ChatHistory, ChatSession, and chat CLI are fully wired with real dependencies. The LLM and retrieval backends require a running llama.cpp server and QMD index for actual operation, but this is expected infrastructure dependency, not a code stub.

---
*Phase: 03-grounded-retrieval-experience*
*Completed: 2026-04-03*

## Self-Check: PASSED
