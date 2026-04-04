---
phase: 04-long-term-memory-fusion
verified: 2026-04-03T00:00:00Z
status: passed
score: 12/12 must-haves verified
re_verification: false
---

# Phase 04: Long-Term Memory Fusion — Verification Report

**Phase Goal:** User can carry useful context across sessions and get responses that combine memory with KB evidence.
**Verified:** 2026-04-03
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `get_memory_dir()` returns `~/Library/Application Support/aurora/memory/` (or env override) | VERIFIED | `paths.py:73-75`; spot-check confirms `MEMORY_DIRNAME = "memory"` constant + `get_config_dir() / MEMORY_DIRNAME` |
| 2 | `get_preferences_path()` returns correct path | VERIFIED | `paths.py:78-80`; spot-check output: `/Users/jp/Library/Application Support/aurora/preferences.md` |
| 3 | `EpisodicMemoryStore.write()` creates timestamped `.md` files with YAML frontmatter | VERIFIED | `store.py:28-53`; 269-line test file with 10 write() tests, all pass |
| 4 | `EpisodicMemoryStore.list_memories()` returns parsed frontmatter sorted chronologically | VERIFIED | `store.py:55-72`; 4 list_memories() tests pass |
| 5 | `EpisodicMemoryStore.clear()` deletes all `.md` files and returns count | VERIFIED | `store.py:74-87`; 3 clear() tests pass |
| 6 | `RetrievedNote` has `source` field distinguishing vault from memory hits | VERIFIED | `contracts.py:41` `source: str = "vault"`; spot-check confirms default "vault" and explicit "memory" |
| 7 | `RuntimeSettings` has `memory_top_k` (default 5, range 3-10) and `memory_min_score` (default 0.25) | VERIFIED | `settings.py:43-44, 85-90`; spot-check: `memory_top_k=5`, `memory_min_score=0.25` |
| 8 | `LLMService.summarize_session()` produces topic line + summary body | VERIFIED | `service.py:78-94`; 5 `TestLLMServiceSummarizeSession` tests pass |
| 9 | `MemorySummarizer` coordinates LLM summarization and `EpisodicMemoryStore.write()` with 2-turn minimum gate | VERIFIED | `summarizer.py:17-30`; 7 `TestMemorySummarizer` tests pass including turn_count < 2 early-return |
| 10 | `ChatSession` tracks `turn_count` and `session_start_index`; `aurora chat` exit spawns daemon thread | VERIFIED | `session.py:58-93, 119`; `chat.py:77-84`; 236 tests pass; daemon=True confirmed |
| 11 | `RetrievalService.retrieve_with_memory()` merges vault + memory, vault-first, respects `MAX_CONTEXT_CHARS` | VERIFIED | `service.py:68-121`; `TestRetrieveWithMemory`, `TestVaultPriority`, `TestDualSourceContext` in 450-line test file |
| 12 | `aurora memory` CLI group (list/search/edit/clear) registered and functional | VERIFIED | `memory.py` 148 lines with all 4 commands; `app.py:40`; 324-line test file; spot-check: "memory" in registered groups |

**Score: 12/12 truths verified**

---

### Required Artifacts

| Artifact | Min Lines / Pattern | Status | Details |
|----------|--------------------|---------|---------|
| `src/aurora/runtime/paths.py` | `MEMORY_DIRNAME`, `get_memory_dir`, `get_preferences_path` | VERIFIED | All three present at lines 18, 73, 78 |
| `src/aurora/runtime/settings.py` | `memory_top_k`, `memory_min_score` | VERIFIED | Lines 43-44; validator at 85-90 |
| `src/aurora/retrieval/contracts.py` | `source: str = "vault"` on `RetrievedNote` | VERIFIED | Line 41 |
| `src/aurora/memory/__init__.py` | Module init | VERIFIED | Exists |
| `src/aurora/memory/store.py` | `EpisodicMemoryStore`, `MEMORY_COLLECTION` | VERIFIED | 115 lines, both exports |
| `src/aurora/memory/summarizer.py` | `MemorySummarizer`, min 30 lines | VERIFIED | 47 lines |
| `src/aurora/llm/prompts.py` | `SUMMARIZE_SESSION_PROMPT`, `SYSTEM_PROMPT_GROUNDED_WITH_MEMORY`, `build_system_prompt_with_preferences` | VERIFIED | Lines 42, 14, 54 |
| `src/aurora/llm/service.py` | `def summarize_session` | VERIFIED | Lines 78-94 |
| `src/aurora/chat/session.py` | `turn_count` property, `session_start_index`, `get_session_turns` | VERIFIED | Lines 63-93 |
| `src/aurora/retrieval/service.py` | `def retrieve_with_memory` | VERIFIED | Lines 68-121 |
| `src/aurora/cli/memory.py` | `memory_app`, min 60 lines | VERIFIED | 148 lines, 4 commands |
| `tests/memory/test_store.py` | min 60 lines | VERIFIED | 269 lines |
| `tests/memory/test_summarizer.py` | min 40 lines | VERIFIED | 223 lines |
| `tests/retrieval/test_retrieval_service.py` | `TestRetrieveWithMemory` class | VERIFIED | 450 lines, class present |
| `tests/cli/test_memory_command.py` | `TestMemoryClear` class | VERIFIED | 324 lines, class present |

---

### Key Link Verification

| From | To | Via | Status | Evidence |
|------|----|----|--------|----------|
| `src/aurora/memory/store.py` | `src/aurora/runtime/paths.py` | `from aurora.runtime.paths import get_memory_dir` | WIRED | `store.py:9` |
| `src/aurora/memory/summarizer.py` | `src/aurora/llm/service.py` | `llm.summarize_session()` call | WIRED | `summarizer.py:28` |
| `src/aurora/memory/summarizer.py` | `src/aurora/memory/store.py` | `store.write()` call | WIRED | `summarizer.py:30` |
| `src/aurora/cli/chat.py` | `src/aurora/memory/summarizer.py` | `threading.Thread(daemon=True)` on exit | WIRED | `chat.py:79-84`; daemon=True at line 82 |
| `src/aurora/retrieval/service.py` | `src/aurora/retrieval/qmd_search.py` | Two `QMDSearchBackend` instances (KB + memory) | WIRED | `service.py:33-34`; `self._memory_backend` |
| `src/aurora/chat/session.py` | `src/aurora/retrieval/service.py` | `_handle_vault_turn` calls `retrieve_with_memory` | WIRED | `session.py:126-127` |
| `src/aurora/cli/app.py` | `src/aurora/cli/memory.py` | `app.add_typer(memory_app, name="memory")` | WIRED | `app.py:10, 40`; spot-check confirms group registration |
| `src/aurora/cli/memory.py` | `src/aurora/memory/store.py` | `EpisodicMemoryStore` for list/clear | WIRED | `memory.py:11` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `cli/memory.py:memory_list` | `memories` | `EpisodicMemoryStore.list_memories()` reads `.md` files from disk | Yes — filesystem glob + YAML parse | FLOWING |
| `cli/memory.py:memory_search` | `response` | `QMDSearchBackend.search(query)` calls external `qmd` tool | Yes — live QMD query | FLOWING |
| `chat/session.py:_handle_vault_turn` | `result.notes` | `RetrievalService.retrieve_with_memory()` queries both backends | Yes — dual QMD search + fetch | FLOWING |
| `cli/chat.py:chat_command` | `session.turn_count` / `session.get_session_turns()` | `ChatSession._turn_count` incremented per `process_turn` | Yes — real-time counter | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Result | Status |
|----------|--------|--------|
| `MEMORY_COLLECTION == "aurora-memory"` | `aurora-memory` | PASS |
| `get_memory_dir()` returns platform path under Aurora config | `/Users/jp/Library/Application Support/aurora/memory` | PASS |
| `get_preferences_path()` returns correct path | `/Users/jp/Library/Application Support/aurora/preferences.md` | PASS |
| `RetrievedNote` source defaults to "vault", accepts "memory" | Confirmed both values | PASS |
| `RuntimeSettings` memory_top_k=5, memory_min_score=0.25 | Both confirmed | PASS |
| `RetrievalService.retrieve_with_memory` exists | Confirmed | PASS |
| `ChatSession.turn_count` starts at 0 | 0 confirmed | PASS |
| `memory_app` registered in root CLI app as "memory" group | Confirmed in registered_groups | PASS |
| `236 tests pass` including memory, retrieval, chat, CLI suites | `236 passed in 0.47s` | PASS |

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| MEM-01 | 04-01, 04-02 | User interactions persisted as long-term memory across CLI sessions | SATISFIED | `EpisodicMemoryStore.write()` + `MemorySummarizer.summarize_and_save()` + background daemon thread in `chat.py` on exit |
| MEM-02 | 04-03 | Assistant retrieves relevant long-term memories during new questions | SATISFIED | `RetrievalService.retrieve_with_memory()` queries `aurora-memory` QMD collection; `ChatSession._handle_vault_turn` calls it when `memory_backend` configured |
| MEM-03 | 04-03 | Assistant combines KB evidence and memory evidence in single response flow | SATISFIED | Vault notes prepended before memory notes in `all_notes`; `SYSTEM_PROMPT_GROUNDED_WITH_MEMORY` includes dual-source citation instructions; `_assemble_context()` respects `MAX_CONTEXT_CHARS` across both sources |
| MEM-04 | 04-01, 04-03 | User can clear session memory without deleting entire KB | SATISFIED | `aurora memory clear` deletes episodic `.md` files + removes `aurora-memory` QMD collection; KB (`aurora-kb-managed`) and `preferences.md` are explicitly untouched |

All four requirement IDs from plan frontmatter are accounted for. No orphaned requirements detected (REQUIREMENTS.md maps only MEM-01..04 to Phase 4).

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `memory/store.py:64` | `return []` | Empty return | Info | Legitimate: returns empty list when memory directory doesn't exist — correct guard behavior |
| `memory/store.py:111,114` | `return {}` | Empty return | Info | Legitimate: defensive empty dict on YAML parse failure — correct error handling |

No blockers. No warnings. All empty returns are guarded defensive paths, not stubs.

---

### Human Verification Required

#### 1. End-to-End Background Save

**Test:** Run `aurora chat`, complete 2+ conversational turns with the local LLM running, then type `sair`. Wait ~5 seconds. Check `~/Library/Application Support/aurora/memory/` for a new `.md` file.
**Expected:** A timestamped memory file exists with YAML frontmatter containing date, topic, turn_count, source=chat, and a prose summary body.
**Why human:** Background daemon thread writes after exit — requires a live LLM endpoint and real session.

#### 2. Dual-Source Chat Response

**Test:** With the local LLM running and the KB indexed, run `aurora chat`. Ask something covered by both a vault note and a prior memory. Inspect whether the response cites both `[path/note.md]` and `[memoria: titulo]` style citations.
**Expected:** Response weaves both vault and memory evidence; correct citation formats appear.
**Why human:** Requires live LLM, indexed KB, and at least one existing memory file.

#### 3. aurora memory edit Opens Editor

**Test:** Run `aurora memory edit`. If preferences.md doesn't exist, verify it is created with the pt-BR header. Verify the system `$EDITOR` (or nano fallback) opens with that file.
**Expected:** Editor opens with preferences.md content; file persists after editor closes.
**Why human:** Editor invocation (`subprocess.run`) cannot be verified programmatically in CI without mocking.

---

### Gaps Summary

No gaps. All 12 must-have truths are VERIFIED. All 15 required artifacts pass Levels 1-4. All 8 key links are WIRED. All 4 requirements (MEM-01 through MEM-04) are SATISFIED. The full test suite (236 tests) passes in 0.47s. Behavioral spot-checks confirm correct runtime behavior.

---

_Verified: 2026-04-03T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
