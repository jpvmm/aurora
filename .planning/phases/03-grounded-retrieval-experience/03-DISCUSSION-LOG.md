# Phase 3: Grounded Retrieval Experience - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-03
**Phase:** 03-grounded-retrieval-experience
**Areas discussed:** Retrieval strategy, Citation format, Conversation UX, Insufficient evidence

---

## Retrieval Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| QMD search only | Use QMD's built-in search (hybrid). Simpler, fewer moving parts. | ✓ |
| Custom RAG pipeline | Build separate retrieval layer: QMD semantic + BM25/whoosh keyword, merge and re-rank. | |
| You decide | Claude picks the simplest approach for RET-03. | |

**User's choice:** QMD search only
**Notes:** QMD `query` command already does BM25 + vector + LLM rerank natively.

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed top-K (5-10) | Always retrieve fixed number of top results. | ✓ |
| Adaptive by relevance score | Retrieve until relevance drops below threshold. | |
| You decide | Claude picks sensible default. | |

**User's choice:** Fixed top-K

| Option | Description | Selected |
|--------|-------------|----------|
| Relevant chunks only | Send only matched passages/sections. | |
| Full notes | Send entire notes that matched. | ✓ |
| Chunk + surrounding context | Matched chunk plus neighboring sections. | |

**User's choice:** Full notes

| Option | Description | Selected |
|--------|-------------|----------|
| Truncate to fit | Prioritize top-ranked notes, truncate rest. | ✓ |
| Refuse and suggest narrower query | Tell user query matched too much. | |
| Summarize overflow notes | Full text for top, summarized for rest. | |

**User's choice:** Truncate to fit

| Option | Description | Selected |
|--------|-------------|----------|
| Pass through directly | Send user question as-is to QMD. | ✓ |
| LLM-rewritten query | Model rewrites question before searching. | |
| Keyword extraction | Extract keywords programmatically. | |

**User's choice:** Pass through directly

| Option | Description | Selected |
|--------|-------------|----------|
| Hardcoded system prompt | Ship crafted system prompt, user doesn't edit. | ✓ |
| User-customizable | Default with override in settings. | |
| You decide | Claude designs prompting strategy. | |

**User's choice:** Hardcoded system prompt

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, log note paths + scores | Log matches and scores, respects PRIV-03. | ✓ |
| Only with --verbose flag | Silent by default, details on request. | |
| No logging | Keep internals hidden. | |

**User's choice:** Log note paths + scores

---

## Citation Format

| Option | Description | Selected |
|--------|-------------|----------|
| Inline references | Citations inline like [nota.md §Seção]. Compact, terminal-friendly. | ✓ |
| Footnotes at the end | Numbered markers with Sources section at bottom. | |
| Both inline + sources list | Inline markers AND consolidated sources. | |

**User's choice:** Inline references

| Option | Description | Selected |
|--------|-------------|----------|
| Path only: [notas/projeto.md] | Just relative vault path. Clean and short. | ✓ |
| Path + section: [notas/projeto.md §Arquitetura] | Include markdown heading. | |
| Path + line: [notas/projeto.md:42] | File path with line number. | |

**User's choice:** Path only

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, one citation per note | Same note cited once even if multiple chunks used. | ✓ |
| No, cite each chunk separately | Show every source reference. | |
| You decide | Claude picks best approach. | |

**User's choice:** One citation per note

---

## Conversation UX

| Option | Description | Selected |
|--------|-------------|----------|
| Single-shot Q&A | `aurora ask "question"` — one question, one answer, exit. | |
| Interactive chat session | `aurora chat` opens a REPL for multiple questions. | |
| Both modes | Single-shot `aurora ask` AND interactive `aurora chat`. | ✓ |

**User's choice:** Both modes

| Option | Description | Selected |
|--------|-------------|----------|
| Stream tokens | Tokens appear as generated, like ChatGPT. | ✓ |
| Print all at once | Wait for full response, then print. | |
| You decide | Claude picks based on llama.cpp API. | |

**User's choice:** Stream tokens

| Option | Description | Selected |
|--------|-------------|----------|
| In-session only | Chat remembers turns within session, lost on exit. | |
| Persist to disk | Save chat history to resume later. | ✓ |
| You decide | Claude picks simplest approach. | |

**User's choice:** Persist to disk

| Option | Description | Selected |
|--------|-------------|----------|
| Re-retrieve each turn | Fresh QMD search per question. | ✓ |
| Reuse initial retrieval | First question retrieves, follow-ups reuse. | |
| You decide | Claude picks based on chat feel. | |

**User's choice:** Re-retrieve each turn

**Additional decision (user-initiated):** `aurora chat` needs an LLM-based intent router that classifies each message as "vault question" (triggers KB retrieval) or "general chat" (responds directly without retrieval).

| Option | Description | Selected |
|--------|-------------|----------|
| LLM classifies intent | Model classifies each message before retrieval. | ✓ |
| Keyword heuristic | Pattern-match on keywords. | |
| Always retrieve, let model ignore | Run QMD always, model ignores irrelevant results. | |

**User's choice:** LLM classifies intent

| Option | Description | Selected |
|--------|-------------|----------|
| Always retrieve for `ask` | `aurora ask` always searches KB, no intent routing. | ✓ |
| Same intent routing as chat | Even `ask` classifies intent. | |
| You decide | Claude picks per command. | |

**User's choice:** Always retrieve for `ask`

---

## Insufficient Evidence

| Option | Description | Selected |
|--------|-------------|----------|
| QMD min-score threshold | No results pass threshold → refuse. Deterministic. | ✓ |
| LLM self-assessment | Model judges if context supports an answer. | |
| Both gates | QMD threshold + model can still refuse. | |

**User's choice:** QMD min-score threshold

| Option | Description | Selected |
|--------|-------------|----------|
| Clear refusal + suggestion | Actionable pt-BR message, no hallucination. | ✓ |
| Partial answer with caveat | Weak answer with warning. | |
| You decide | Claude picks tone. | |

**User's choice:** Clear refusal + suggestion

| Option | Description | Selected |
|--------|-------------|----------|
| Chat freely | General chat mode responds without grounding. | ✓ |
| Always ground or refuse | Even chat only answers grounded topics. | |
| You decide | Claude picks natural approach. | |

**User's choice:** Chat freely

---

## Claude's Discretion

- Exact system prompt wording and grounding instructions
- Top-K default value (within 5-10 range)
- Min-score threshold value
- Chat history persistence format and storage location
- Intent classification prompt design
- Streaming implementation details

## Deferred Ideas

- User-customizable system prompt — future phase
- LLM-rewritten queries — QMD handles query expansion
- Partial answers with caveats — strict refusal for now
