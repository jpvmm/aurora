# Phase 5: Operational Command Surface - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-05
**Phase:** 05-operational-command-surface
**Areas discussed:** Unified status command, Doctor completeness, Output consistency, Missing operations

---

## Unified Status Command

| Option | Description | Selected |
|--------|-------------|----------|
| Full dashboard | Model state, KB state, Memory state, Config summary | ✓ |
| Minimal operational | One-liner per section (up/down, yes/no) | |
| Model + KB only | Skip memory/config | |

**User's choice:** Full dashboard
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Report only | Just show state, no side effects | ✓ |
| Offer to start | Prompt to start model if stopped | |
| Auto-start | Auto-start model before showing status | |

**User's choice:** Report only

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, --json flag | Structured JSON with all sections | ✓ |
| No, human-only | Scripts call individual subcommands | |

**User's choice:** Yes, --json flag

### Command Consolidation (emerged from status discussion)

User requested: "let's try to reduce the quantity of different commands and compact them in a few that the user can use the most"

| Option | Description | Selected |
|--------|-------------|----------|
| Core 4 commands | ask, chat, status, doctor. Rest under config | ✓ |
| Core 3 + setup | ask, chat, doctor (absorbs status). Rest under config | |
| Keep current + add status | All 8 groups as-is, plus status | |

**User's choice:** Core 4 commands (ask, chat, status, doctor)

| Option | Description | Selected |
|--------|-------------|----------|
| Aliases with deprecation warning | Old commands work with warning, remove after one cycle | ✓ |
| Hard move, no aliases | Remove old top-level commands immediately | |
| Keep both permanently | Both paths work forever | |

**User's choice:** Aliases with deprecation warning

---

## Doctor Completeness

| Option | Description | Selected |
|--------|-------------|----------|
| QMD availability | Check qmd binary, correct version | ✓ |
| KB health | Check collection exists, has documents, embeddings | ✓ |
| Memory index health | Check aurora-memory collection, embeddings | ✓ |
| Disk/dependencies | Python version, disk space, packages | ✓ |

**User's choice:** All four checks (multiSelect)

| Option | Description | Selected |
|--------|-------------|----------|
| Report + suggest commands | Show issue + exact fix command | ✓ |
| Auto-fix with confirmation | Prompt to fix each issue inline | |
| Report only | Just pass/fail, no suggestions | |

**User's choice:** Report + suggest commands

---

## Output Consistency

| Option | Description | Selected |
|--------|-------------|----------|
| Universal --json | Every command gets --json | ✓ |
| Only data commands | Only status, doctor, ask, memory list | |
| Keep current mix | Each command decides independently | |

**User's choice:** Universal --json

| Option | Description | Selected |
|--------|-------------|----------|
| Structured error pattern | what failed + why + recovery command. Exit 1 user, 2 system | ✓ |
| Simple message + exit 1 | Clear message, exit 1 for any failure | |
| You decide | Claude picks best pattern | |

**User's choice:** Structured error pattern

---

## Missing Operations

| Option | Description | Selected |
|--------|-------------|----------|
| aurora version | Show versions in one line | |
| aurora config kb ingest (consolidate) | Move KB ops under config namespace | ✓ |
| Improved --help text | Audit all help strings, add examples | ✓ |
| Shell completions | bash/zsh/fish via Typer | ✓ |

**User's choice:** Consolidate KB, improve help, shell completions (multiSelect, no version command)

---

## Claude's Discretion

- Status dashboard layout and formatting
- Doctor check ordering and grouping
- Deprecation warning styling
- Shell completion installation instructions

## Deferred Ideas

- `aurora version` standalone command — version in status instead
- Doctor auto-fix mode — future iteration
