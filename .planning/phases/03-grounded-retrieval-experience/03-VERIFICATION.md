---
phase: 03-grounded-retrieval-experience
verified: 2026-04-03T00:00:00Z
status: passed
score: 13/13 must-haves verified
gaps: []
human_verification:
  - test: "aurora ask 'question' streams tokens incrementally to terminal"
    expected: "Tokens appear one by one as LLM generates, not buffered until complete"
    why_human: "Streaming behaviour requires a live llama.cpp server; cannot verify programmatically without running server"
  - test: "aurora chat interactive loop accepts user input, routes vault vs chat, prints response"
    expected: "Multi-turn session runs end-to-end with intent routing; answers grounded in vault when relevant"
    why_human: "Requires live llama.cpp server and an indexed vault; interactive stdin/stdout cannot be exercised by CliRunner alone"
  - test: "Inline citations appear in the grounded response in [path/note.md] format"
    expected: "Each grounded answer contains at least one citation referencing the source note path"
    why_human: "Citation presence depends on LLM following the system prompt; requires real model execution"
---

# Phase 03: Grounded Retrieval Experience Verification Report

**Phase Goal:** User can ask questions and receive trustworthy, evidence-grounded responses from vault content.
**Verified:** 2026-04-03
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

All truths are drawn from must_haves across the three plans (03-01, 03-02, 03-03).

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | RetrievalService can search QMD and return scored note hits with paths | VERIFIED | `service.py:45` calls `self._backend.search(query)`; hits assembled into `RetrievedNote` tuples |
| 2  | RetrievalService can fetch full note content and assemble truncated context | VERIFIED | `service.py:72-103` fetches per hit, assembles with `--- {path} ---` headers, truncates at `MAX_CONTEXT_CHARS=12000` |
| 3  | RetrievalService returns empty results when no hits pass min-score threshold | VERIFIED | `service.py:47-49` returns `_INSUFFICIENT` sentinel when `not search_response.ok or not search_response.hits` |
| 4  | LLMService can stream tokens from llama.cpp /v1/chat/completions | VERIFIED | `streaming.py:24` builds request to `{endpoint_url}/v1/chat/completions`; SSE lines parsed and `on_token` called per chunk |
| 5  | LLMService can classify intent as vault or chat | VERIFIED | `service.py:78-93` uses `sync_fn` (non-streaming), parses `"vault"` in result string |
| 6  | System prompt mandates pt-BR and inline citation format | VERIFIED | `prompts.py:4-10` — `SYSTEM_PROMPT_GROUNDED` contains `"pt-BR"`, `"[caminho/nota.md]"`, `"SOMENTE com base nas notas"`, `"Deduplique"` |
| 7  | User can run aurora ask 'question' and receive a grounded answer streamed to terminal | VERIFIED | `ask.py:22-91` registered via `app.add_typer(ask_app, name="ask")`; calls `retrieve` then `ask_grounded`; `print(token, end="", flush=True)` |
| 8  | When no evidence found, user sees pt-BR refusal message | VERIFIED | `ask.py:37-53` prints `INSUFFICIENT_EVIDENCE_MSG` on `result.insufficient_evidence` |
| 9  | aurora ask always retrieves from KB — no intent routing | VERIFIED | `ask.py:28-29` unconditionally calls `retrieval.retrieve(query)` |
| 10 | User can run aurora chat to start an interactive multi-turn session | VERIFIED | `chat.py:17-49` registered as `aurora chat`; interactive `input("voce> ")` loop with `ChatSession.process_turn` |
| 11 | Each user message is classified as vault or chat intent before response | VERIFIED | `session.py:55` calls `self._llm.classify_intent(user_message)` on every turn |
| 12 | Conversation history is persisted to disk as JSONL for session resume | VERIFIED | `history.py:19-28` appends JSONL to `get_config_dir() / "chat_history.jsonl"`; `session.py:64-65` persists after each turn |
| 13 | LLM context window is capped to last N turns to prevent unbounded growth | VERIFIED | `history.py:44-54` `get_recent` slices to `max_turns * 2` messages; `session.py:95` passes `max_turns=self._max_turns` |

**Score:** 13/13 truths verified

---

### Required Artifacts

| Artifact | Provides | Lines | Status | Notes |
|----------|----------|-------|--------|-------|
| `src/aurora/retrieval/contracts.py` | `QMDSearchHit`, `QMDSearchResponse`, `RetrievalResult`, `RetrievedNote`, `QMDSearchDiagnostic` | 62 | VERIFIED | All frozen dataclasses with `__all__` exports |
| `src/aurora/retrieval/qmd_search.py` | `QMDSearchBackend` with `search` and `fetch` | 161 | VERIFIED | Mirrors `QMDCliBackend` pattern; injectable `command_runner` |
| `src/aurora/retrieval/service.py` | `RetrievalService` orchestrating search -> fetch -> truncate | 115 | VERIFIED | `MAX_CONTEXT_CHARS = 12_000`; deduplication; `_INSUFFICIENT` sentinel |
| `src/aurora/llm/prompts.py` | `SYSTEM_PROMPT_GROUNDED`, `SYSTEM_PROMPT_CHAT`, `INTENT_PROMPT`, `INSUFFICIENT_EVIDENCE_MSG` | 34 | VERIFIED | pt-BR, citation format, grounding constraint, deduplication instruction all present |
| `src/aurora/llm/streaming.py` | SSE streaming parser for llama.cpp | 68 | VERIFIED | `STREAM_TIMEOUT_SECONDS = 120`; `stream_chat_completions`; `chat_completion_sync`; `[DONE]` sentinel handled |
| `src/aurora/llm/service.py` | `LLMService` with `ask_grounded`, `chat_turn`, `classify_intent` | 96 | VERIFIED | Injectable `stream_fn` / `sync_fn`; `classify_intent` uses sync, not streaming |
| `src/aurora/cli/ask.py` | `aurora ask` CLI command | 91 | VERIFIED | `ask_app` registered; streaming via `print(token, end="", flush=True)`; `--json` mode; `INSUFFICIENT_EVIDENCE_MSG` |
| `src/aurora/cli/chat.py` | `aurora chat` CLI command | 52 | VERIFIED | Interactive loop; `EXIT_COMMANDS`; `KeyboardInterrupt` handled; `--clear` flag |
| `src/aurora/chat/history.py` | `ChatHistory` with JSONL persistence | 62 | VERIFIED | `append_turn`, `load`, `get_recent`, `clear`; `HISTORY_FILENAME = "chat_history.jsonl"` |
| `src/aurora/chat/session.py` | `ChatSession` with per-turn intent routing | 105 | VERIFIED | Vault path: retrieve + `ask_grounded`; chat path: `chat_turn` with history; history persisted after each turn |
| `src/aurora/runtime/settings.py` | Extended with retrieval/chat tuning fields | — | VERIFIED | `retrieval_top_k: int = 7`, `retrieval_min_score: float = 0.30`, `chat_history_max_turns: int = 10`; `field_validator` enforces `retrieval_top_k` in 5–10 |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/aurora/retrieval/qmd_search.py` | `qmd` CLI | `subprocess.run` default runner | WIRED | `_default_command_runner` calls `subprocess.run(argv, ...)` at line 23; command tuple starts with `"qmd", "--index"` at lines 66-67 |
| `src/aurora/llm/streaming.py` | llama.cpp `/v1/chat/completions` | `urllib.request.urlopen` with SSE | WIRED | `Request` built to `{endpoint_url}/v1/chat/completions` at line 24; iterated for SSE lines |
| `src/aurora/retrieval/service.py` | `src/aurora/retrieval/qmd_search.py` | `QMDSearchBackend` injection | WIRED | Constructor at line 32 creates `QMDSearchBackend(settings_loader=settings_loader)` or accepts injected backend |
| `src/aurora/cli/ask.py` | `src/aurora/retrieval/service.py` | `RetrievalService().retrieve(query)` | WIRED | Lines 28-29: instantiation and unconditional call |
| `src/aurora/cli/ask.py` | `src/aurora/llm/service.py` | `LLMService().ask_grounded(...)` | WIRED | Lines 55, 71: instantiation and call with `context_text` and `on_token` |
| `src/aurora/cli/app.py` | `src/aurora/cli/ask.py` | `app.add_typer(ask_app, name="ask")` | WIRED | Line 37 in `app.py` |
| `src/aurora/chat/session.py` | `src/aurora/llm/service.py` | `LLMService.classify_intent` + `ask_grounded` / `chat_turn` | WIRED | Lines 55, 84, 100 |
| `src/aurora/chat/session.py` | `src/aurora/retrieval/service.py` | `RetrievalService.retrieve` on vault-intent turns | WIRED | Line 72 in `_handle_vault_turn` |
| `src/aurora/cli/chat.py` | `src/aurora/chat/session.py` | `ChatSession().run_loop()` → `process_turn` | WIRED | Lines 28, 46 in `chat.py` |
| `src/aurora/chat/history.py` | platformdirs config directory | JSONL file at `get_config_dir() / "chat_history.jsonl"` | WIRED | Line 17 in `history.py`; `append_turn` creates parent dirs at line 26 |

---

### Data-Flow Trace (Level 4)

These artifacts render dynamic data (streamed LLM responses from real vault content); verified that data sources are real rather than hardcoded.

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `ask.py` | `result` (RetrievalResult) | `RetrievalService.retrieve(query)` -> `QMDSearchBackend` -> `subprocess.run("qmd", ...)` | Yes — real `qmd` CLI shell-out | FLOWING |
| `ask.py` | `response` (str) | `LLMService.ask_grounded` -> `stream_chat_completions` -> `urlopen` to llama.cpp | Yes — real HTTP SSE stream | FLOWING |
| `session.py` | `result` (RetrievalResult) | `RetrievalService.retrieve(user_message)` — same pipeline as above | Yes | FLOWING |
| `session.py` | `response` (str) | `LLMService.ask_grounded` or `LLMService.chat_turn` — both use `stream_chat_completions` | Yes | FLOWING |
| `chat/history.py` | records (list[dict]) | JSONL file on disk at `get_config_dir() / "chat_history.jsonl"` | Yes — real file I/O | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `aurora ask --help` shows query argument and `--json` flag | `uv run aurora ask --help` | Help displayed with `QUERY` argument, `--json` option, and "vault" in description | PASS |
| `aurora chat --help` shows `--clear` flag | `uv run aurora chat --help` | Help displayed with `--clear` option | PASS |
| All retrieval + LLM + chat + CLI tests pass | `uv run pytest tests/retrieval/ tests/llm/ tests/chat/ tests/cli/test_ask_command.py tests/cli/test_chat_command.py -x -q` | 108 passed in 0.17s | PASS |
| All module exports importable | `uv run python -c "from aurora.retrieval.contracts import ...; from aurora.llm.service import LLMService; ..."` | "All exports verified OK"; MAX_CONTEXT_CHARS = 12000 | PASS |

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| RET-01 | 03-01, 03-02, 03-03 | User can ask questions in CLI and receive answers grounded in vault content | SATISFIED | `aurora ask` and `aurora chat` both deliver vault-grounded answers via `RetrievalService` + `LLMService.ask_grounded` |
| RET-02 | 03-01, 03-02, 03-03 | User receives citations with note path for each grounded answer | SATISFIED | `SYSTEM_PROMPT_GROUNDED` mandates `[caminho/nota.md]` inline citation format; `ask --json` returns `sources` list of unique note paths |
| RET-03 | 03-01, 03-02, 03-03 | User query uses hybrid retrieval (keyword + semantic) for evidence selection | SATISFIED | `QMDSearchBackend.search()` delegates to `qmd query --json` which performs hybrid search; `-c` collection flag and `--min-score` threshold applied |
| RET-04 | 03-01, 03-02, 03-03 | User gets explicit "insufficient evidence" response when vault context is not enough | SATISFIED | `RetrievalService` returns `_INSUFFICIENT` sentinel; `ask.py` and `session.py` both print `INSUFFICIENT_EVIDENCE_MSG` on this path |
| CLI-03 | 03-01, 03-02, 03-03 | Assistant replies in pt-BR by default and only changes language when user requests | SATISFIED | Both `SYSTEM_PROMPT_GROUNDED` and `SYSTEM_PROMPT_CHAT` contain `"Responda em pt-BR por padrao. Mude o idioma somente se o usuario solicitar explicitamente."` |

No orphaned requirements. All five IDs are claimed by all three plans and verified as implemented.

---

### Anti-Patterns Found

No anti-patterns detected. All 10 artifact files scanned — zero TODOs, FIXMEs, placeholder comments, or stub implementations found.

---

### Human Verification Required

#### 1. Incremental Token Streaming

**Test:** Run `aurora ask "o que e o projeto aurora"` against a running llama.cpp server with an indexed vault.
**Expected:** Tokens appear on the terminal one-by-one as the model generates, not buffered and printed all at once after completion.
**Why human:** Streaming behaviour requires a live llama.cpp server process; `print(token, end="", flush=True)` is verified in code but the perceptual incremental output cannot be confirmed programmatically without running the server.

#### 2. End-to-end aurora chat with Intent Routing

**Test:** Start `aurora chat`, type a question about vault content, then type a general question.
**Expected:** First question triggers retrieval and grounded answer with citation(s); second question gets a free-form response without citations.
**Why human:** Requires live llama.cpp server + indexed vault; interactive stdin cannot be driven by CliRunner for an intent-routing flow.

#### 3. Inline Citations in Grounded Responses

**Test:** Run `aurora ask "question about known vault content"` against an indexed vault.
**Expected:** Response contains at least one `[path/to/note.md]` citation referencing the actual source note.
**Why human:** Citation presence depends on the LLM following the system prompt instruction — requires real model execution to observe.

---

### Gaps Summary

No gaps. All 13 observable truths verified, all 11 artifacts are substantive and wired, all 5 requirement IDs are satisfied. Test suite passes (108 tests, 0 failures). Three human verification items remain for live-server integration testing and are expected at this stage.

---

_Verified: 2026-04-03_
_Verifier: Claude (gsd-verifier)_
