---
phase: 05
slug: operational-command-surface
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-05
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/cli/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/cli/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | CLI-02 | unit | `uv run pytest tests/cli/test_status_command.py -x -q` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | CLI-02 | unit | `uv run pytest tests/cli/test_config_consolidation.py -x -q` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | CLI-04 | unit | `uv run pytest tests/cli/test_doctor.py -x -q` | ✅ | ⬜ pending |
| 05-03-01 | 03 | 2 | CLI-02 | unit | `uv run pytest tests/cli/test_entrypoint.py -x -q` | ✅ | ⬜ pending |
| 05-03-02 | 03 | 2 | CLI-02 | integration | `uv run aurora status --json` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/cli/test_status_command.py` — stubs for aurora status command
- [ ] `tests/cli/test_config_consolidation.py` — stubs for config namespace moves

*Existing test infrastructure covers doctor and entrypoint testing.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Shell completions install | CLI-02 | Requires interactive shell | Run `aurora --install-completion bash`, verify `~/.bashrc` updated |
| Deprecation warnings visible | CLI-02 | Requires visual inspection of stderr | Run `aurora kb --help`, verify deprecation message appears |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
