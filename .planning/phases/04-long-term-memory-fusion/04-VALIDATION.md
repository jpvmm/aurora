---
phase: 04
slug: long-term-memory-fusion
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-04
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q --tb=short` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q --tb=short`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | MEM-01 | unit | TBD | TBD | pending |
| TBD | TBD | TBD | MEM-02 | unit | TBD | TBD | pending |
| TBD | TBD | TBD | MEM-03 | unit | TBD | TBD | pending |
| TBD | TBD | TBD | MEM-04 | unit | TBD | TBD | pending |

*Updated after planner creates PLAN.md files.*

---

## Wave 0 Requirements

- [ ] `tests/memory/` — test directory for memory service tests
- [ ] `tests/memory/conftest.py` — shared fixtures

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Background summary actually saves after chat exit | MEM-01 | Async timing, requires real session | Run `aurora chat`, have 2+ turns, exit, check memory dir for new file |
| Memory citations appear correctly in responses | MEM-03 | Requires LLM output inspection | Ask vault question, verify `[memoria: ...]` citations alongside vault citations |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
