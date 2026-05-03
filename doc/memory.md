# How Aurora's Memory Works

> **Reading map.** This is a walkthrough aimed at someone who wants to *understand* — not just use — Aurora's memory system. Read it top-to-bottom the first time, then use it as a map into the code. Every concept links to the specific file and line where it lives. Estimated time: 25–35 minutes.

---

## Table of Contents

1. [Why an agent needs memory at all](#1-why-an-agent-needs-memory-at-all)
2. [The mental model: two tiers](#2-the-mental-model-two-tiers)
3. [Where memories live on disk](#3-where-memories-live-on-disk)
4. [The write path: a conversation becomes a memory](#4-the-write-path-a-conversation-becomes-a-memory)
5. [The read path: memories shape the next answer](#5-the-read-path-memories-shape-the-next-answer)
6. [Tier 1: the preferences file](#6-tier-1-the-preferences-file)
7. [Operational commands](#7-operational-commands)
8. [Design decisions and tradeoffs](#8-design-decisions-and-tradeoffs)
9. [Exercises — trace it yourself](#9-exercises--trace-it-yourself)
10. [Where to go next](#10-where-to-go-next)

---

## 1. Why an agent needs memory at all

A language model is **stateless by default**. Each call to `llama-server` is a fresh context window: whatever you sent in is all the model knows. If you chatted with Aurora yesterday about your thesis topic, and today you open a new session and say "continua o que falamos sobre a minha tese", a vanilla LLM has zero idea what you mean.

There are three well-known ways to give an agent memory:

1. **Fit it all in context.** Re-send the entire history every turn. Works for short sessions; dies the moment you exceed the context window or want continuity across days.
2. **Fine-tune the model.** Bake the memories into the weights. Slow, expensive, irreversible, and terrible at forgetting — you *don't* want to forever fine-tune every passing preference.
3. **Retrieval-augmented memory.** Store summaries externally, search them on each new turn, and inject only the relevant pieces into the prompt.

Aurora uses option 3. This is the same architecture as the vault knowledge base — the only difference is what's being retrieved from.

> **Key insight:** in Aurora, "memory" and "vault" are the *same mechanism* (vector search over markdown files), pointed at different corpora. The retrieval code at `src/aurora/retrieval/service.py` works uniformly on both.

---

## 2. The mental model: two tiers

Aurora deliberately splits "memory" into two very different things. This is worth understanding before you look at a single line of code, because the split shapes everything downstream.

```
┌───────────────────────────────────────────────────────────────┐
│                       TIER 1 — Preferences                    │
│                                                               │
│  One file.   Always loaded.   Injected into every prompt.     │
│  You author it by hand.       Small (a few paragraphs).       │
│                                                               │
│  Example content:                                             │
│    - "Responda em pt-BR."                                     │
│    - "Quando falo 'aurora', e este projeto."                  │
│    - "Prefira bullet points a paragrafos longos."             │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                    TIER 2 — Episodic memory                   │
│                                                               │
│  Many files. Retrieved on demand (vector search + threshold). │
│  Written automatically when a chat session ends.              │
│  Grows without bound; you prune explicitly.                   │
│                                                               │
│  Each file is one past session's summary:                     │
│    date, topic, turn_count, "what we talked about"            │
└───────────────────────────────────────────────────────────────┘
```

| | **Tier 1 — Preferences** | **Tier 2 — Episodic** |
|---|---|---|
| **Who writes it** | You (text editor) | Aurora (background summarization) |
| **How it's loaded** | Read verbatim, every turn | Retrieved by vector similarity when relevant |
| **Size over time** | Stays small | Grows monotonically |
| **Failure mode if misused** | Pollutes every prompt if too long | Hallucinated "memories" if summarization is bad |
| **File(s) on disk** | `preferences.md` (singular) | `memory/YYYY-MM-DDTHH-MM.md` (many) |

The tiering is doing real work: **things that should influence every answer** go in Tier 1, **things that should surface only when relevant** go in Tier 2. If you tried to collapse them into one, you'd either miss persistent preferences (Tier 1 drops out of retrieval on short queries) or drown the prompt (Tier 2 always loaded).

---

## 3. Where memories live on disk

Aurora stores **all** state in a single per-user config directory, resolved by `platformdirs.user_config_dir()` at `src/aurora/runtime/paths.py:23-29`.

On macOS that's `~/Library/Application Support/aurora/`. On Linux, `~/.config/aurora/`. You can override with the `AURORA_CONFIG_DIR` environment variable — very useful for writing tests (see `tests/cli/test_kb_command.py`).

The memory-relevant layout:

```
~/Library/Application Support/aurora/
├── preferences.md                  ← Tier 1: the one always-loaded file
├── memory/                         ← Tier 2: one file per past session
│   ├── 2026-04-18T22-11.md
│   ├── 2026-04-19T09-03.md
│   └── 2026-04-21T17-45.md
├── kb-qmd-corpus/                  ← (unrelated — this is vault KB, not memory)
└── settings.json
```

Each Tier-2 file is a normal markdown document with YAML frontmatter:

```markdown
---
date: '2026-04-21T17:45'
source: chat
topic: Refatoracao da camada de retrieval para carry-forward
turn_count: 7
---
Data da sessao: 2026-04-21

## Topicos
- Decisao de herdar ate 3 paths do turno anterior
- Escolha entre vault-first e memory-first

## Decisoes
- Implementar em `_apply_carry_forward`

## Contexto
Conversamos sobre como evitar perda de contexto...
```

This is not a special format — **it's a regular markdown file Aurora treats the same way it treats a vault note**. That's what makes memory and vault retrieval share code. Frontmatter schema: `src/aurora/memory/store.py:48-56`.

Filename convention is ISO 8601 minute-precision (`YYYY-MM-DDTHH-MM.md`). Collisions resolve by appending `-2`, `-3`, ... before the extension.

---

## 4. The write path: a conversation becomes a memory

Let's trace exactly what happens from "user types `sair`" to "a file exists on disk."

### 4.1 Trigger

When a chat session ends, the CLI chat loop runs the memory-save logic at `src/aurora/cli/chat.py:81-92`. Three gates must pass:

1. **`turn_count >= 2`** — sessions with a single turn (or less) aren't worth summarizing.
2. **LLM service is available** — if the endpoint died mid-session, we can't summarize.
3. **Memory backend is configured** — QMD must be reachable.

If all three pass, Aurora spawns a **background daemon thread**:

```python
# Conceptually (see src/aurora/cli/chat.py:26-37)
def _background_save(session_history, llm_service, memory_store):
    try:
        summarizer.summarize_and_save(session_history, llm_service, memory_store)
    except Exception as e:
        # Logged, not raised — memory save must never block the user
        logger.warning(...)

thread = threading.Thread(target=_background_save, ..., daemon=True)
thread.start()
```

> **Why a background thread?** Because the user already typed `sair` — they expect the prompt back immediately. Summarization requires another LLM round-trip (seconds of latency). Blocking would feel broken. If the thread crashes, nobody notices except the log.
>
> The main process waits up to 30 seconds before exiting to give the thread a chance to finish — a small compromise between "lose the memory" and "feel sluggish."

### 4.2 Summarization

The thread calls `summarize_and_save()` at `src/aurora/memory/summarizer.py:18-35`. This does three things in order:

**Step 1: Ask the LLM for a summary.**

The prompt lives at `src/aurora/llm/prompts.py:116-135` (`SUMMARIZE_SESSION_PROMPT`). It tells the model:

- First line = the *topic* (max 60 chars).
- Remainder = markdown with `Data da sessao: {date}` followed by three sections: `## Topicos`, `## Decisoes`, `## Contexto`.

This specific structure isn't arbitrary — it mirrors what the retrieval system looks for later. `## Decisoes` is gold for queries like "o que decidimos sobre X".

**Step 2: Parse the response.**

`_parse_response()` at `src/aurora/memory/summarizer.py:37-48` splits the LLM output into `(topic, body)`. The first line becomes `topic`, the rest becomes `body`. There's a safety net that prepends `Data da sessao:` if the LLM forgot it.

**Step 3: Write to disk + register with QMD.**

`store.write()` at `src/aurora/memory/store.py:32-59`:

1. Generate a filename from `datetime.now()` (ISO minute precision).
2. If the file exists, suffix with `-2`, `-3`, ... until unique.
3. Serialize YAML frontmatter + body.
4. Write to `{memory_dir}/{filename}.md`.
5. Call `_qmd_update()` — a subprocess `qmd --index aurora-kb update` + `embed` on the `aurora-memory` collection (see `src/aurora/memory/store.py:137-149`).

The memory file is now on disk **and** indexed in the QMD vector store, searchable by the read path.

### 4.3 ASCII flow

```
 user types "sair"
       │
       ▼
┌──────────────────┐
│  chat CLI exits  │  ─── main thread returns prompt to user
└────────┬─────────┘
         │
         │ if turn_count >= 2:
         ▼
┌──────────────────────────┐
│  background daemon thread│
└────────┬─────────────────┘
         │
         ▼
┌──────────────────┐   llama-server HTTP
│  summarize_...() │ ◄──────────────►  topic + body
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  write .md file  │   ← memory/YYYY-MM-DDTHH-MM.md
└────────┬─────────┘
         │
         ▼
┌──────────────────┐   qmd subprocess
│  _qmd_update()   │ ──►  index + embed → aurora-memory collection
└──────────────────┘
```

---

## 5. The read path: memories shape the next answer

Now the interesting half. You've accumulated memories over weeks. How do they influence the *next* answer?

### 5.1 Intent classification — the traffic cop

Every user turn in `aurora chat` goes through an **intent classifier** first. The code path: `src/aurora/chat/session.py:150-156` calls `llm.classify_intent()`, using the prompt at `src/aurora/llm/prompts.py:61-109`.

The classifier buckets each question into one of three categories:

| Intent | Meaning | Retrieval behavior |
|---|---|---|
| `vault` | The user is asking about notes (their knowledge base). | Retrieve from vault first; *also* pull a small set of memory candidates as supplementary context. |
| `memory` | The user is asking about a past conversation or decision. | Retrieve from memory first; vault is secondary. |
| `chat` | Small talk, meta questions, reformulations. | No retrieval — just a chat response. |

> **Why ask the LLM twice?** Because deciding *where to search* is itself a reasoning task. A naive system would always search both and let the ranker sort it out, but that wastes latency and often surfaces irrelevant memories on plain vault queries. Paying one extra LLM call to route saves retrieval cost *and* produces better prompts.

### 5.2 Retrieval

Once the intent is known, one of two service methods fires:

- **`retrieve_memory_first()`** — `src/aurora/retrieval/service.py:122-176`. Used for `memory` intent.
- **`retrieve_with_memory()`** — `src/aurora/retrieval/service.py:178-232`. Used for `vault` intent with memory configured.

Both do the same primitives (vector query against QMD, dedupe by path, keep highest score), differing only in *ordering* and *top-K split*.

Defaults from `src/aurora/runtime/settings.py:43-44`:

| Setting | Vault | Memory |
|---|---|---|
| `top_k` | 15 | 5 |
| `min_score` | 0.30 | 0.25 |

Memory gets a **lower min_score** on purpose — fewer memories exist than notes, so the bar for inclusion is a touch lower.

### 5.3 Carry-forward (a small but clever detail)

Look at `_apply_carry_forward()` at `src/aurora/chat/session.py:100-139`. After each turn, the session tracks `_last_retrieved_paths` (up to 3 paths). On the next turn, if fresh retrieval doesn't include those paths, Aurora re-fetches their content and appends them as supplementary notes with `score=0.0`.

Why? Because follow-up questions often drop the topic keyword. If I ask "o que a Maria disse sobre a roadmap?" and next turn say "e sobre a phase 6?", retrieval might miss the Maria note even though it's clearly what I was referring to. Carry-forward fixes it without needing full conversational state.

This is added to the phase 04.2 work and is the single subtlest feature in the memory system.

**Composition with the iterative retrieval loop (Phase 7).** When the [iterative loop](retrieval.md#12-iterative-retrieval--when-one-attempt-isnt-enough) is enabled, carry-forward applies *exactly once*, *before* the first retrieval — never on the loop's second attempt. ChatSession is the layer that owns this: it calls `_apply_carry_forward()` to augment the first attempt's result, then passes that augmented result to `IterativeRetrievalOrchestrator.run(..., first_attempt=...)`. The orchestrator never re-applies carry-forward on attempt 2; if it did, carry-forward notes would get re-counted as "new evidence" by the second sufficiency check, falsely passing the gate even when the reformulated query alone is still thin. This was a load-bearing invariant during Phase 7 design — the orchestrator is deliberately ignorant of carry-forward so the composition can't drift over time.

### 5.4 Context assembly and prompt injection

Retrieved notes (memory + vault, in intent-determined order) get assembled into a single context blob at `src/aurora/retrieval/service.py:330-353`:

```
--- notes/projects/aurora.md ---
<content>

--- memory/2026-04-21T17-45.md ---
<content>

...
```

Truncated at 24,000 characters (`MAX_CONTEXT_CHARS` at line 14).

Then a system prompt is chosen based on the intent and whether memory was found:

- `chat` intent, no retrieval → `get_system_prompt_chat()`
- `vault` intent, no memory → `get_system_prompt_grounded()`
- `vault` intent, memory present → `get_system_prompt_grounded_with_memory()`
- `memory` intent → `get_system_prompt_memory_first()`

Finally, preferences (Tier 1) are *prepended* to whichever system prompt was picked, via `build_system_prompt_with_preferences()` at `src/aurora/llm/prompts.py:169-178`:

```
## Preferencias do usuario

{contents of preferences.md}

{the system prompt chosen above}
```

So every turn's prompt layers:

```
preferences  ─── always-on
   +
chosen system prompt  ─── intent-aware
   +
retrieved context  ─── similarity-ranked
   +
user's current question
```

### 5.5 ASCII flow

```
 user asks question
        │
        ▼
┌───────────────────────┐
│  classify_intent()    │  ── LLM call #1 (cheap, fast)
└───────────┬───────────┘
            │
   ┌────────┼────────┐
   ▼        ▼        ▼
 vault   memory    chat
   │        │        │
   ▼        ▼        │
┌──────────────────┐ │
│  QMD retrieval   │ │     memory top_k=5,  min=0.25
│  (dedupe, rank)  │ │     vault  top_k=15, min=0.30
└────────┬─────────┘ │
         │           │
         ▼           │
┌──────────────────┐ │
│ carry-forward    │ │    up to 3 prior-turn paths
│ supplement       │ │
└────────┬─────────┘ │
         │           │
         ▼           ▼
┌─────────────────────────────────┐
│  assemble system prompt:        │
│    preferences.md  (Tier 1)     │
│    chosen system prompt         │
│    assembled context (Tier 2 +  │
│       vault notes, 24K chars)   │
└────────────────┬────────────────┘
                 │
                 ▼
       LLM call #2 — stream answer
```

---

## 6. Tier 1: the preferences file

Tier 1 is dead simple. It's one markdown file at `{config_dir}/preferences.md` (see `get_preferences_path()` at `src/aurora/runtime/paths.py:79`).

**Loading.** `build_system_prompt_with_preferences()` at `src/aurora/llm/prompts.py:169-178`:

```python
# Conceptually:
content = preferences_path.read_text(encoding="utf-8").strip()
if content:
    return f"## Preferencias do usuario\n\n{content}\n\n{base_prompt}"
return base_prompt
```

**Editing.** `aurora config memory edit` at `src/aurora/cli/memory.py:83-98` spawns `$EDITOR` on the path. No validation on save — you're trusted to write sensible markdown.

**Format.** Free-form. Suggested structure:

```markdown
# Preferencias

## Linguagem
- Responda em pt-BR, a menos que eu peca em outro idioma.

## Estilo
- Prefira bullet points a paragrafos.
- Nao use emojis a menos que eu use primeiro.

## Contexto pessoal
- Quando eu falo "aurora", me refiro a este projeto.
- Meu stack principal e Python + Typer + QMD.

## Coisas para nao fazer
- Nao adicione disclaimers.
- Nao sugira que eu "consulte um profissional".
```

**Rule of thumb on size.** Preferences are paid for on *every* turn. Every 1 KB you add is 1 KB of context every time. Under 2 KB is fine. If you're at 10 KB you're doing it wrong — some of that belongs in Tier 2 or in the vault itself.

---

## 7. Operational commands

Everything under `aurora config memory ...`, backed by `src/aurora/cli/memory.py`.

### `list` — `src/aurora/cli/memory.py:19-39`

Globs `*.md` in the memory dir, parses YAML frontmatter, renders:

```
2026-04-21T17:45  [7 turnos]  Refatoracao da camada de retrieval para carry-forward
2026-04-19T09:03  [3 turnos]  Planejamento da phase 5
2026-04-18T22:11  [12 turnos] Debug do bug de paths relativos no KB
```

`--json` for scripting.

### `search "<query>"` — `src/aurora/cli/memory.py:42-80`

Vector search via `QMDSearchBackend` on the `aurora-memory` collection. Top-K=5, min-score=0.25. Renders each hit as `[score]  title  → snippet`. This is the same mechanism chat uses internally, exposed as a CLI.

Useful for sanity-checking "is this memory actually findable?".

### `edit` — `src/aurora/cli/memory.py:83-98`

Opens `preferences.md` in `$EDITOR` (defaults to `nano`). Creates the file if it doesn't exist.

### `clear` — `src/aurora/cli/memory.py:101-132`

**Destructive.** Two-step cleanup:

1. Delete every `.md` file in `memory/` via `store.clear()` at `src/aurora/memory/store.py:80-93`.
2. Run `qmd --index aurora-kb collection remove aurora-memory` to drop the vector collection.

Requires `--yes` when non-interactive (matches the KB `delete` ergonomic).

**Important:** this does *not* delete `preferences.md`. If you want a total reset, remove that file separately.

---

## 8. Design decisions and tradeoffs

A few non-obvious choices that shape how the system feels:

### 8.1 Memory and vault share one QMD index, two collections

Both the vault corpus (`aurora-kb-managed`) and the memory corpus (`aurora-memory`) live as *collections* inside the single `aurora-kb` QMD index (`src/aurora/memory/store.py:15-16`).

**Why:** sharing an index means one vector space, one embedding model, and one set of operational primitives. `qmd` can query across collections with consistent semantics.

**Cost:** you can't use a different embedding model for memory vs vault. If you ever need to, you'd split them.

### 8.2 Summarization is an LLM call, not an extractive heuristic

You could summarize a session by concatenating user turns, or by TF-IDF, or by any number of lightweight methods. Aurora delegates to the LLM because:

- The model already has the full chat history in context.
- Generative summaries capture *intent* (`## Decisoes` section) in a way keyword methods can't.

**Cost:** summaries can hallucinate. The prompt at `src/aurora/llm/prompts.py:116-135` is carefully constrained, but bugs in summarization become false memories. Worth watching for.

### 8.3 The background-thread save is fire-and-forget

If the summarization thread crashes after the user exited, nothing tells them. Aurora logs a warning and moves on.

**Why:** the alternative (block, show a spinner, retry) makes exit feel slow. The small risk of silently losing one session's memory beats user-visible latency on every `sair`.

**Mitigation:** the 30-second wait at exit gives most sessions time to finish. Long sessions on slow models may hit the timeout.

### 8.4 Carry-forward is bounded to 3

The carry-forward at `src/aurora/chat/session.py:100-139` retains at most 3 paths from the previous turn. Why not all of them?

- Unbounded growth would dilute retrieval with stale results.
- 3 is empirically enough for most follow-up questions without drowning the prompt.

This is tuned — you might tune differently for a domain with longer cross-turn references.

The 3-path cap also keeps the [Phase 7 iterative loop](retrieval.md#12-iterative-retrieval--when-one-attempt-isnt-enough) honest: carry-forward augments attempt 1 and only attempt 1 (§5.3), so the sufficiency check never sees a runaway pile of carry-forward notes that would falsely pass the threshold. Cap + once-only application together make the composition deterministic.

### 8.5 Preferences are prepended, not appended

Look at line 169-178 of `prompts.py` — preferences come *before* the base system prompt. Models weight earlier system messages more heavily. If you want a preference to *actually* shape output, it needs to be near the top.

---

## 9. Exercises — trace it yourself

Best way to cement this: follow one real request through the code.

1. **Start a chat.** `aurora chat` → ask "resume o que conversamos sobre aurora ontem".
2. **Find the intent classification.** Set a breakpoint (or print) in `src/aurora/chat/session.py` around line 150. What category did your question get?
3. **Find the retrieval call.** Which service method ran? How many memory results? How many vault results?
4. **Find the assembled context.** Log the system prompt right before the LLM call. Was your `preferences.md` prepended? Which memories made it in?
5. **End the session.** Watch `memory/` — does a new file appear within 30 seconds? What's in its frontmatter?

If you can describe what happens at each of those five points *in your own words*, you've understood the memory system.

Extra credit: break it on purpose.
- Set `memory_top_k = 0` in `settings.json`. What happens on a memory-intent query?
- Write a preferences file that's 50 KB. How does that affect response latency?
- Exit a chat after 1 turn. Does a memory file get written? Why or why not?

---

## 10. Where to go next

| To understand... | Read... |
|---|---|
| How QMD's vector index actually works | External — [tobi/qmd README](https://github.com/tobi/qmd) |
| How the chat loop is structured | `src/aurora/cli/chat.py` and `src/aurora/chat/session.py` |
| How prompts are built end-to-end | `src/aurora/llm/prompts.py` (read top-to-bottom — it's the most educational single file in the repo) |
| How retrieval ranks and dedupes | `src/aurora/retrieval/service.py` |
| How to change the summarization prompt | Edit `SUMMARIZE_SESSION_PROMPT` at `src/aurora/llm/prompts.py:116` and run a chat session |
| How settings get validated | `src/aurora/runtime/settings.py` (Pydantic model, explicit validators) |
| How tests mock the memory flow | `tests/memory/` and `tests/chat/` |

---

**Appendix — one-sentence summary per concept, to memorize:**

- **Preferences (Tier 1)** — one file you write; loaded verbatim every turn.
- **Episodic memory (Tier 2)** — one file per past session, summarized by the LLM, retrieved by vector similarity.
- **Intent classifier** — a cheap LLM call that decides whether to search vault, memory, or nothing at all.
- **Carry-forward** — up to 3 paths from the prior turn always re-fetched, so follow-up questions don't lose context.
- **Background save** — summarization runs off the critical path; exit is never blocked by memory writes.
- **Shared QMD index** — vault and memory are two collections in one vector store; one retrieval engine serves both.
