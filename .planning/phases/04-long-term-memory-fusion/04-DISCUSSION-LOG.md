# Phase 4: Long-Term Memory Fusion - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-04
**Phase:** 04-long-term-memory-fusion
**Areas discussed:** Memory storage backend, Memory capture strategy, Memory + KB fusion, Memory management UX, Preferences file format, Memory file naming/structure, Recency and staleness, Chat exit + summary flow

---

## Memory Storage Backend

| Option | Description | Selected |
|--------|-------------|----------|
| Graphiti + Neo4j | Rich relationship modeling, requires Docker | |
| SQLite with embeddings | Zero extra infra, no relationships | |
| Extend existing JSONL + QMD | Persist as markdown, index with QMD | ✓ |

**User's choice:** Extend existing JSONL + QMD

| Option | Description | Selected |
|--------|-------------|----------|
| Separate markdown files | One .md per memory, QMD indexes individually | ✓ |
| Single JSONL file | All memories in one file | |

**User's choice:** Separate markdown files

| Option | Description | Selected |
|--------|-------------|----------|
| Separate QMD collection | New 'aurora-memory' collection | ✓ |
| Mixed with vault notes | Same collection as KB | |

**User's choice:** Separate collection

| Option | Description | Selected |
|--------|-------------|----------|
| Aurora config dir | ~/Library/Application Support/aurora/memory/ | ✓ |
| Inside Obsidian vault | .aurora/memory/ in vault | |

**User's choice:** Aurora config dir

---

## Memory Capture Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Automatic after every chat session | Summarize on exit | ✓ |
| Automatic per vault turn only | Only vault Q&A saved | |
| User-triggered only | Explicit /save command | |
| Automatic + user can flag | Auto + explicit flagging | |

**User's choice:** Automatic after every chat session

| Option | Description | Selected |
|--------|-------------|----------|
| LLM-generated summary | Model summarizes key points | ✓ |
| Full transcript | Entire conversation | |
| Key Q&A pairs only | Extracted pairs | |

**User's choice:** LLM-generated summary

| Option | Description | Selected |
|--------|-------------|----------|
| Both ask and chat | Every interaction creates memory | |
| Only chat | Ask stays stateless | ✓ |

**User's choice:** Only chat creates memories

---

## Memory + KB Fusion

| Option | Description | Selected |
|--------|-------------|----------|
| Unified answer | Weave both sources naturally | ✓ |
| Separated sections | Explicit vault/memory sections | |

**User's choice:** Unified answer

| Option | Description | Selected |
|--------|-------------|----------|
| Vault always wins | Current content is truth | ✓ |
| Present both conflicts | Show contradiction | |

**User's choice:** Vault always wins

| Option | Description | Selected |
|--------|-------------|----------|
| Always retrieve both | Parallel KB + memory search every turn | ✓ |
| Memory only when relevant | LLM decides first | |

**User's choice:** Always retrieve both

| Option | Description | Selected |
|--------|-------------|----------|
| [memoria: titulo] prefix | Same brackets, different prefix | ✓ |
| (memoria: titulo) parens | Different marker type | |

**User's choice:** Same format with prefix

---

## Two-Tier Architecture (research-informed)

| Option | Description | Selected |
|--------|-------------|----------|
| Two-tier (prefs + episodic) | CLAUDE.md-inspired preferences + QMD-indexed summaries | ✓ |
| Episodic only | No preferences tier | |

**User's choice:** Two-tier

---

## Memory Management UX

Selected commands: `aurora memory list`, `aurora memory search <query>`, `aurora memory edit`

| Option | Description | Selected |
|--------|-------------|----------|
| aurora memory clear | Delete episodic memories, keep prefs + KB | ✓ |
| aurora chat --clear extend | Extend existing flag | |
| Both commands | Different scopes | |

**User's choice:** aurora memory clear

---

## Preferences File Format

| Option | Description | Selected |
|--------|-------------|----------|
| Free-form markdown (CLAUDE.md style) | No schema, user writes anything | ✓ |
| Structured sections | Predefined ## sections | |

**User's choice:** Free-form markdown

| Option | Description | Selected |
|--------|-------------|----------|
| Aurora config dir: preferences.md | Alongside settings.json | ✓ |
| Home directory: ~/.aurora.md | Dotfile in home | |

**User's choice:** Aurora config dir

---

## Memory File Naming/Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Timestamp: 2026-04-04T19-30.md | ISO date-time, auto-sorted | ✓ |
| Topic-based slug | LLM-generated name | |
| Timestamp + topic | Combined | |

**User's choice:** Timestamp-based

| Option | Description | Selected |
|--------|-------------|----------|
| YAML frontmatter | date, topic, turn_count, source | ✓ |
| No metadata | Pure summary text | |

**User's choice:** YAML frontmatter

---

## Recency and Staleness

| Option | Description | Selected |
|--------|-------------|----------|
| Accumulate forever, QMD handles relevance | No TTL, no decay | ✓ |
| Recency-weighted scoring | Boost recent memories | |
| TTL with consolidation | Auto-merge old memories | |

**User's choice:** Accumulate forever

---

## Chat Exit + Summary Flow

| Option | Description | Selected |
|--------|-------------|----------|
| Blocking summary before exit | User waits for save | |
| Background async save | Exit immediately, save in background | ✓ |
| Save only if vault turns | Skip general-chat-only sessions | |

**User's choice:** Background async save

| Option | Description | Selected |
|--------|-------------|----------|
| Log warning to file | Silent failure, no user notification | |
| Print warning on next start | Deferred notification | |
| You decide | Claude picks | ✓ |

**User's choice:** Claude's discretion (log + optional next-start notification)

| Option | Description | Selected |
|--------|-------------|----------|
| At least 2 turns | Skip single-turn sessions | ✓ |
| Save everything | Even 1 turn | |

**User's choice:** At least 2 turns

---

## Claude's Discretion

- Summary generation prompt design
- Preferences injection strategy in system prompts
- Memory retrieval top-K and min-score thresholds
- Background process implementation
- Exact frontmatter fields
- Failure notification strategy (log + optional next-start warning)

## Deferred Ideas

- Graphiti graph memory backend — future migration
- Memory pinning, forgetting, decay rules — v2 scope (MEMG-01, MEMG-02, MEMG-03)
- `aurora ask` reading memories — keep stateless for now
- Recency-weighted scoring — QMD handles relevance
- TTL/auto-consolidation — accumulate forever
