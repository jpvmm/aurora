---
phase: 03
slug: grounded-retrieval-experience
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-03
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q --tb=short` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q --tb=short`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-T1 | 01 | 1 | RET-01, RET-03, RET-04 | unit | `uv run pytest tests/retrieval/ -x -q` | ❌ W0 | ⬜ pending |
| 03-01-T2 | 01 | 1 | RET-01, RET-02, CLI-03 | unit | `uv run pytest tests/llm/ -x -q` | ❌ W0 | ⬜ pending |
| 03-02-T1 | 02 | 2 | RET-01, RET-02, RET-04, CLI-03 | unit | `uv run pytest tests/cli/test_ask_command.py -x -q` | ❌ W0 | ⬜ pending |
| 03-03-T1 | 03 | 2 | RET-01, RET-04, CLI-03 | unit | `uv run pytest tests/chat/ -x -q` | ❌ W0 | ⬜ pending |
| 03-03-T2 | 03 | 2 | RET-01, CLI-03 | unit | `uv run pytest tests/cli/test_chat_command.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/retrieval/test_qmd_search.py` — stubs for QMD search backend (RET-03)
- [ ] `tests/retrieval/test_retrieval_service.py` — stubs for retrieval service + truncation (RET-01, RET-04)
- [ ] `tests/llm/test_prompts.py` — stubs for system prompts (RET-02, CLI-03)
- [ ] `tests/llm/test_streaming.py` — stubs for SSE streaming parser
- [ ] `tests/llm/test_llm_service.py` — stubs for LLM service (RET-01)
- [ ] `tests/cli/test_ask_command.py` — stubs for aurora ask command (RET-01)
- [ ] `tests/chat/test_history.py` — stubs for JSONL chat history
- [ ] `tests/chat/test_session.py` — stubs for chat session + intent routing (CLI-03)
- [ ] `tests/cli/test_chat_command.py` — stubs for aurora chat command

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Streaming output renders correctly in terminal | RET-01 | Visual terminal output, timing-dependent | Run `aurora ask "test question"`, verify tokens stream progressively |
| pt-BR default language in responses | CLI-03 | Requires LLM output inspection | Ask question in pt-BR, verify response language |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
