# How Aurora Retrieves Knowledge (RAG)

> **Reading map.** This is the densest of the three teaching docs. RAG — *retrieval-augmented generation* — is the piece of any agent that connects a language model to information it wasn't trained on. This doc walks the entire pipeline from "markdown file sitting in an Obsidian vault" to "tokens streaming out of the LLM," with emphasis on *why* each stage exists rather than just *what* it does. Companion to [memory.md](memory.md) (episodic state) and [model.md](model.md) (inference). Estimated time: 30–40 minutes.

---

## Table of Contents

1. [The problem RAG solves](#1-the-problem-rag-solves)
2. [The 30-second mental model](#2-the-30-second-mental-model)
3. [Pre-processing — what happens before embedding](#3-pre-processing--what-happens-before-embedding)
4. [No chunking — a deliberate design choice](#4-no-chunking--a-deliberate-design-choice)
5. [QMD at arm's length](#5-qmd-at-arms-length)
6. [Embedding — when, what, how incremental](#6-embedding--when-what-how-incremental)
7. [The query path — hybrid search](#7-the-query-path--hybrid-search)
8. [Retrieval parameters — top_k and min_score](#8-retrieval-parameters--top_k-and-min_score)
9. [Dedupe and multi-source merging](#9-dedupe-and-multi-source-merging)
10. [Context assembly — from notes to a prompt](#10-context-assembly--from-notes-to-a-prompt)
11. [The "insufficient evidence" path — dual-layer enforcement](#11-the-insufficient-evidence-path--dual-layer-enforcement)
12. [The citation contract](#12-the-citation-contract)
13. [Design decisions and tradeoffs](#13-design-decisions-and-tradeoffs)
14. [Exercises — trace it yourself](#14-exercises--trace-it-yourself)
15. [Where to go next](#15-where-to-go-next)

---

## 1. The problem RAG solves

A language model knows what was in its training data. It does **not** know:

- What you wrote in your notes last Tuesday.
- Your preferences, project names, colleagues.
- Any document published after the model's training cutoff.
- Anything private.

For a personal assistant grounded in *your* knowledge, this is the whole game. Three classic approaches:

| Approach | Why it doesn't work here |
|---|---|
| Put everything in the context window | Your vault is thousands of notes, millions of tokens. Doesn't fit, costs too much, drowns the model. |
| Fine-tune the model on your notes | Slow, expensive, hard to update. Also: would bake private data into weights you might share. |
| **Retrieve only the relevant notes per query, inject into context** | ✅ Fits in context. Fast to update (re-embed on change). Private (never leaves your machine). |

Option 3 is RAG. Aurora is a concrete implementation of it, pointed at an Obsidian vault, running entirely offline.

**The fundamental bet:** at inference time, the user's question is a strong signal of what they want to know about. Embed the question, find notes whose embeddings are close to it, stuff those notes into the prompt, ask the LLM. If the right note is in the top-K, the LLM's answer will be grounded in it.

This bet has a failure mode — you can miss the relevant note, or retrieve the wrong one — and a lot of Aurora's design is about making that failure mode *visible* (refuse to answer) rather than *invisible* (hallucinate).

---

## 2. The 30-second mental model

```
                        ┌────────────────────────┐
                        │    Obsidian vault      │
                        │    (markdown files)    │
                        └────────────┬───────────┘
                                     │
                  ingest / update (write path)
                                     ▼
                       ┌─────────────────────────┐
                       │      Pre-process        │
                       │  (strip Templater tags) │
                       └──────────────┬──────────┘
                                      ▼
                       ┌─────────────────────────┐
                       │    kb-qmd-corpus/       │
                       │   (cleaned markdown)    │
                       └──────────────┬──────────┘
                                      ▼
                       ┌─────────────────────────┐
                       │      QMD: embed         │
                       │  (vectors on disk)      │
                       └─────────────────────────┘


    user query (read path)
            │
            ▼
 ┌──────────────────────┐                ┌─────────────────────┐
 │  Intent classifier   │ ── strategy ──►│ QMD: query / search │
 │  (LLM call #1)       │                │ (semantic + BM25)   │
 └──────────────────────┘                └──────────┬──────────┘
                                                    │
                                                    ▼
                                         ┌─────────────────────┐
                                         │  hits (path, score) │
                                         └──────────┬──────────┘
                                                    │ dedupe, top-K,
                                                    │ min-score gate
                                                    ▼
                                         ┌─────────────────────┐
                                         │   qmd get <path>    │
                                         │   (full content)    │
                                         └──────────┬──────────┘
                                                    ▼
                                         ┌─────────────────────┐
                                         │  Assemble context   │
                                         │  (truncate 24K)     │
                                         └──────────┬──────────┘
                                                    ▼
                                           LLM call #2 (stream)
                                           with grounded prompt
```

Three things to internalize:

1. **Write path and read path are separate.** Ingest/update/rebuild happen on user command; retrieval happens per-question. They share QMD but little else.
2. **QMD is treated as an external tool.** Aurora shells out via subprocess — it does not embed QMD as a library. More on this in §5.
3. **Retrieval is two LLM calls, not one.** One to decide *how* to search (intent + strategy), one to answer *with* the retrieved notes. The first one is small and cheap; the second is the user-visible streaming answer.

---

## 3. Pre-processing — what happens before embedding

Before a markdown file is embedded, Aurora strips content that would pollute the vector space. The file that owns this is `src/aurora/kb/preprocess.py`.

### 3.1 Templater tag stripping

Obsidian users who use the [Templater plugin](https://github.com/SilentVoid13/Templater) sprinkle their notes with dynamic directives:

```markdown
# Journal

Date: <% tp.date.now("YYYY-MM-DD") %>
Mood: <% tp.system.prompt("Mood?") %>

## Entry

Today I worked on…
```

Those `<% ... %>` blocks are **evaluated at file-write time by Templater**, not stored as-is. In a live note you'd see the resolved values. But in the raw file on disk (the version Aurora reads), they're still literal template directives.

Embedding them would be terrible:
- They're not meaningful text — they're tiny programs.
- They cluster in vector space around "looks like code," dragging notes that share templates close to each other even when their semantic content is entirely different.
- They leak implementation details into search results ("what did I write about `tp.date.now`?" would match thousands of notes).

So Aurora strips them. The regex at `src/aurora/kb/preprocess.py:8`:

```python
TEMPLATER_SNIPPET_PATTERN = re.compile(r"<%[-_+*~]*[\s\S]*?[-_+*~]?%>")
```

Matches opening `<%` and optional Templater delimiter characters (`-`, `_`, `+`, `*`, `~`), then lazily consumes everything until the closing `%>`. Every match is removed.

The function `preprocess_markdown()` at `src/aurora/kb/preprocess.py:22` returns a `PreprocessResult`:

```python
@dataclass(frozen=True)
class PreprocessResult:
    relative_path: str
    cleaned_text: str              # after Templater removal
    cleaned_snippet_count: int     # how many blocks were removed
    cleaned_spans: tuple[...]      # byte offsets of what was removed
```

The span information is kept for diagnostics — if you ever wonder "did preprocessing nuke something important?", the spans tell you exactly where.

### 3.2 What *isn't* stripped

Deliberately **kept**:
- **YAML frontmatter** — often contains tags, aliases, project names. These are genuinely useful for semantic matching.
- **Code blocks** — if you wrote a snippet, it's searchable.
- **Wikilinks** (`[[Other Note]]`) — these carry semantic content and relationships.
- **Markdown headings** — structural but also semantic.

A future version could strip more aggressively (e.g., remove code comments, strip URLs), but each thing you strip is a thing you can no longer retrieve by. The current default is deliberately conservative.

### 3.3 `size` vs `cleaned_size` in the manifest

The KB manifest at `src/aurora/kb/manifest.py:14-22` stores both:

```python
@dataclass(frozen=True)
class KBManifestNoteRecord:
    size: int             # raw file size on disk
    cleaned_size: int     # size of cleaned_text (UTF-8 bytes)
    mtime_ns: int
    sha256: str | None    # hash of cleaned content
    indexed_at: str
    templater_tags_removed: int
```

If you see `size: 8012` and `cleaned_size: 6200`, Aurora knows roughly 1,800 bytes of Templater directives were removed from that note. The hash is computed over *cleaned* content — so if a user-visible edit doesn't change the cleaned text, it's treated as "unchanged" by update's detection logic.

---

## 4. No chunking — a deliberate design choice

**Most RAG tutorials you read online will tell you to chunk documents.** Break them into 500-token pieces with some overlap, embed each chunk separately, retrieve at chunk granularity.

Aurora doesn't chunk. Each note is one unit: one embedding, one retrieval result, full content fetched on hit.

### 4.1 Why this works here

The assumption behind chunking is that documents are *long* — PDFs, policy manuals, entire books. One embedding can't capture a 50-page PDF, so you break it up.

But Obsidian notes are typically:
- Short (100–2000 words).
- Single-topic by convention (one note = one idea).
- Already "chunked" by the user's authoring discipline.

At that granularity, one-note-per-embedding makes a lot of sense. The embedding captures the whole note reasonably well, and you never have to reason about chunk boundaries, overlap, or stitching chunks back together.

### 4.2 The cost

When this breaks down:

- A 50-page daily journal with dozens of unrelated topics would embed as one blob; the embedding "averages" across topics and matches weakly on any specific one.
- A note with a weekly log of unrelated meetings has the same problem.

**Mitigation:** Aurora relies on Obsidian users' conventions. Users writing Aurora-friendly vaults keep notes focused. Users with enormous monolithic notes would see worse retrieval and should split them.

### 4.3 Why not chunk anyway?

Chunking adds complexity everywhere:
- Ingestion has to pick chunk boundaries (hard problem).
- Retrieval has to handle chunk-level scoring and possibly re-assemble adjacent chunks.
- Citations become hairy: "see note.md chunk 7 of 14" is not a user-friendly source reference.
- Dedupe becomes path-level *and* chunk-level.

One embedding per note simplifies all of those. It's a tradeoff worth being loud about: **Aurora's retrieval quality depends on the user writing small-ish notes.**

---

## 5. QMD at arm's length

Aurora's vector store is [QMD](https://github.com/tobi/qmd), a separate project that handles:

- Storing embeddings on disk.
- Computing them (sentence-transformers, a classical dense embedding model).
- Running hybrid search (semantic + BM25).
- Optionally re-ranking.

Aurora uses QMD **as a subprocess**, not as a Python library.

### 5.1 The subprocess boundary

Every interaction between Aurora and QMD is a shell-out. Example from `src/aurora/kb/qmd_backend.py`:

```python
def embed(self) -> QMDBackendResponse:
    command = ("qmd", "--index", self.index_name, "embed")
    result = self._run_command(command)
    # parse return code, stdout, stderr
```

Search is the same — `qmd query --json <args>` or `qmd search --json <args>`, then parse JSON stdout.

### 5.2 Why a subprocess?

**Language boundary.** QMD is primarily a Rust/Python tool. Embedding it as a Python library would couple Aurora's Python version to QMD's, force them to share dependencies, and mean any QMD crash kills the Aurora CLI.

**Upgrade safety.** A subprocess boundary means Aurora and QMD can update independently. If QMD releases a new embedding model, users can `uv tool upgrade qmd` without touching Aurora.

**Reproducibility.** Every QMD call is a command-line string. You can log it, replay it, debug it by hand — no stack traces to chase into someone else's library.

**Failure isolation.** A segfault in QMD doesn't crash the CLI; it returns a non-zero exit code that Aurora handles gracefully.

The cost: subprocess overhead per call (tens of ms on macOS). For a tool called at interactive rates (seconds per query), this is noise.

### 5.3 Indices and collections

QMD has two levels of organization:

- **Index** — a top-level namespace. Aurora uses one: `aurora-kb`.
- **Collection** — a named subset of an index, pointing at a corpus directory.

Aurora uses two collections inside that one index:

| Collection | Corpus directory | What's in it |
|---|---|---|
| `aurora-kb-managed` | `~/.config/aurora/kb-qmd-corpus/aurora-kb-managed/` | Cleaned versions of your vault notes |
| `aurora-memory` | `~/.config/aurora/memory/` | Session summaries from past chats (see [memory.md](memory.md)) |

Both collections share one index, one embedding model, one vector space — so a memory and a vault note can be compared directly for similarity. That's what makes `retrieve_with_memory()` a unified pipeline rather than two separate ones.

### 5.4 What's on disk where

```
~/.config/aurora/
├── kb-qmd-corpus/
│   └── aurora-kb-managed/
│       └── <cleaned copies of your vault notes>
├── memory/
│   └── <session summary .md files>
├── kb-manifest.json         ← per-note fingerprints (size, mtime, sha256)
└── kb-state.json            ← last operation history

~/.qmd-indexes/               ← QMD owns this
└── aurora-kb/
    └── <embeddings, metadata, BM25 index — QMD's internals>
```

Aurora owns the corpus (source of truth: cleaned markdown). QMD owns the derived artifacts (embeddings). If the embeddings get corrupted, `aurora config kb rebuild` reconstructs them from the corpus.

---

## 6. Embedding — when, what, how incremental

### 6.1 When embedding fires

The embedding stage runs at the end of `ingest`, `update`, `rebuild`, and `delete` — but only if state actually changed. The guard is at `src/aurora/kb/service.py:741`:

```python
if dry_run or not settings.kb_auto_embeddings_enabled or not state_mutated:
    return self._embedding_not_attempted(), ()
```

Three cases where embedding is skipped:
- Dry run — we said we wouldn't mutate, so we don't.
- `auto-embeddings` config flag is off — user opted out.
- Nothing changed — no point.

Otherwise, `self._adapter.embed()` is called, which triggers the subprocess.

### 6.2 Incrementality

Aurora's job: write cleaned markdown to the corpus dir (for new/changed notes), remove files for deleted notes. That's it.

QMD's job: compare the corpus dir to what it's already indexed, compute embeddings only for new/changed files, update its index.

This is *incremental by construction* — Aurora doesn't need to tell QMD which files changed. QMD figures it out from the corpus. As long as Aurora writes the corpus correctly, embedding is O(changed files), not O(total files).

### 6.3 The embedding model

QMD uses sentence-transformers (a `all-MiniLM-L*` or similar model by default). Dimension is typically 384. This is configurable *in QMD*, not in Aurora — Aurora treats the embedding model as a black box.

**Implication:** if you change QMD's embedding model, you invalidate every existing embedding. `aurora config kb rebuild` is the recovery path.

### 6.4 Partial failure

If QMD's `embed` call fails (disk full, model not downloaded, corpus corrupt), Aurora returns a structured status:

```python
KBEmbeddingStageStatus(
    attempted=True,
    ok=False,
    category="backend_embed_failed",
    recovery_command="aurora kb update",
)
```

The CLI surfaces the category and exits with code **2** — deliberately non-zero so CI scripts catch it, but different from hard failures (exit 1). The user can retry by running the recovery command printed alongside the warning.

---

## 7. The query path — hybrid search

Now the read path. User asks a question → retrieval service kicks in.

### 7.1 Search = semantic + keyword

Two kinds of search, often fused:

- **Semantic (dense)**: embed the query, find notes with similar embeddings. Good at paraphrase ("my thoughts on databases" retrieves notes titled "Postgres vs MongoDB"). Weak at exact matches (embedding blurs rare proper nouns).
- **Keyword (BM25)**: classic term-frequency scoring. Great at names, codes, literal strings. Weak at paraphrase.

**Neither alone is great for a personal assistant.** If you ask "o que a Maria disse sobre a ideia?", semantic search might return topically-related notes but miss the one where "Maria" is a rare proper noun. BM25 would nail "Maria" but miss notes about the idea that don't contain her name.

**Aurora uses both, configurably.** The intent classifier (see [memory.md §5.1](memory.md#51-intent-classification--the-traffic-cop)) outputs a `search_strategy` along with the intent: `hybrid`, `keyword`, or `both`.

### 7.2 How the strategy is applied

Code at `src/aurora/retrieval/service.py:261-287`:

```python
if strategy == "keyword" and terms:
    for term in terms:
        response = backend.keyword_search(term)
        all_hits = all_hits + response.hits
elif strategy == "both":
    response = backend.search(query)              # hybrid (semantic + BM25)
    all_hits = response.hits
    for term in terms:
        kw_response = backend.keyword_search(term)
        all_hits = all_hits + kw_response.hits
else:  # "hybrid" is the default
    response = backend.search(query)
    all_hits = response.hits
```

- **`hybrid`** (the default): one call to `qmd query` — runs semantic + BM25 and merges internally.
- **`keyword`**: run `qmd search` on each extracted term separately. Used when the LLM thinks the question is about specific proper nouns.
- **`both`**: do hybrid *and* per-term keyword, concatenate all hits. Belt and suspenders.

The intent classifier extracts `terms` by asking the LLM: "what are the 1–3 key entities in this question?" So for "o que a Maria disse sobre bancos de dados?", `terms` might be `["Maria"]`.

### 7.3 The actual subprocess call

From `src/aurora/retrieval/qmd_search.py:61`:

```python
command = (
    "qmd", "--index", self.index_name, "query", "--json",
    "-n", str(self.top_k),
    "-c", self.collection_name,
    "--min-score", min_score_str,
    query,
)
```

Simple. The flags map to:
- `--json`: machine-readable stdout.
- `-n 15`: top-K hits.
- `-c aurora-kb-managed`: search this collection.
- `--min-score 0.30`: drop hits below this.

### 7.4 Reranking

QMD's `query` can be configured to run a cross-encoder reranker on the top N candidates before returning them. Whether that runs depends on QMD's config, not Aurora's. From Aurora's perspective, hits come back pre-ranked.

---

## 8. Retrieval parameters — top_k and min_score

From `src/aurora/runtime/settings.py:40-44`:

| Setting | Vault | Memory |
|---|---|---|
| `retrieval_top_k` | 15 | 5 (as `memory_top_k`) |
| `retrieval_min_score` | 0.30 | 0.25 (as `memory_min_score`) |

Two questions worth asking:

### 8.1 Why is vault top-K higher?

Your vault has hundreds or thousands of notes. Your memory has tens of sessions. There's more to pull from in the vault, so we return more candidates. More is also cheaper in the vault — embeddings exist for every note, so retrieving 15 vs 5 is the same ~ms.

### 8.2 Why is memory's min_score lower?

Episodic memories are session summaries — they're *denser* than individual notes (one memory covers many topics), so their embeddings are "averaged" across topics. Getting a 0.30 match against a memory is rare even when the memory is relevant. Lowering the bar to 0.25 catches genuinely relevant memories without flooding results with junk.

These numbers are tuned, not principled. If you change your vault's character (shorter notes, different language mix), you might need to retune.

### 8.3 Bounds

Both settings have pydantic validators (`src/aurora/runtime/settings.py:78-90`) that reject out-of-range values:

```python
@field_validator("retrieval_top_k")
def _validate(cls, value):
    if value < 5 or value > 30:
        raise ValueError("retrieval_top_k deve estar entre 5 e 30.")
    return value
```

The ranges aren't arbitrary. Below 5, you're starving the LLM of context. Above 30, you're drowning the prompt and spending context budget that would be better used on carry-forward notes or memory.

---

## 9. Dedupe and multi-source merging

### 9.1 Dedupe by path

When `strategy == "both"`, the same note can appear in both the hybrid results *and* the keyword results. `_dedup_hits()` at `src/aurora/retrieval/service.py:289`:

1. For each path, keep the highest score.
2. Sort remaining by score descending.
3. Emit unique paths in score order.

Simple, deterministic. No attempt to "combine" scores from different searches — the max score wins.

### 9.2 Merging vault + memory

When retrieval involves both (chat with memory configured), two orderings exist:

| Method | Order | When used |
|---|---|---|
| `retrieve_with_memory()` | vault notes first, then memories | `vault` intent (user is asking about notes) |
| `retrieve_memory_first()` | memories first, then vault | `memory` intent (user is asking about a past conversation) |

Order matters for three reasons:

1. **Context truncation.** The first notes in the context are guaranteed to fit; later ones might be cut. You put the most-relevant-given-intent first.
2. **LLM attention.** Most LLMs weight earlier context higher. Putting memory first in a memory-intent query reinforces "this is the thing you should lean on."
3. **Carry-forward ([memory.md §5.3](memory.md#53-carry-forward-a-small-but-clever-detail))** is appended in the vault slot, so its position depends on which method ran.

---

## 10. Context assembly — from notes to a prompt

Retrieved notes need to become a single string the LLM can read. `_assemble_context()` at `src/aurora/retrieval/service.py:330`:

```python
for note in notes:
    entry = f"--- {note.path} ---\n{note.content}\n"
    remaining = MAX_CONTEXT_CHARS - total_chars
    if remaining <= 0:
        break
    if len(entry) <= remaining:
        context_parts.append(entry)
        total_chars += len(entry)
    else:
        context_parts.append(entry[:remaining])   # truncate the entry
        break
```

The output looks like:

```
--- notes/projects/aurora.md ---
<full content of that note>

--- notes/decisions/retrieval.md ---
<full content of that note>

--- memory/2026-04-19T14-02.md ---
<full content of that memory>
```

### 10.1 Why this format?

- **Path header as delimiter.** The LLM sees exactly which note each block came from. This is what makes `[path/note.md]` citations possible — the LLM has the path in-context.
- **Full content per note, not chunks.** See §4.
- **No re-ordering by the LLM.** The order is set by the retrieval code, so the model sees the most relevant notes first.

### 10.2 `MAX_CONTEXT_CHARS = 24_000`

That's roughly 6,000 tokens — a large fraction of most local models' 8K–32K context windows. The rest of the window is reserved for:

- The system prompt (grounded + preferences + intent-specific guidance): ~1–2K tokens.
- The user's actual question: ~50 tokens.
- Room for the LLM to generate a response: several K tokens.

If you increased this, you'd eat into generation budget. If you decreased it, you'd clip more notes. 24K was chosen empirically as the point where most queries fit their top-K results.

Truncation is **hard** — once we hit the limit we stop. No attempt to summarize notes that don't fit, no intelligent reordering. Later notes are simply dropped from that specific query.

---

## 11. The "insufficient evidence" path — dual-layer enforcement

The most teaching-worthy design decision in the retrieval layer.

### 11.1 The problem

A vanilla RAG system does the naive thing: it *always* retrieves top-K, *always* passes them to the LLM, *always* gets an answer back. If the question is about something not in your vault, the system retrieves *the K least-unrelated notes* and asks the LLM to answer based on them. The LLM — trying to be helpful — will often fabricate an answer that sounds plausible.

This is the hallucination failure mode, and it's catastrophic for a note-taking assistant. An answer like "you mentioned you prefer Postgres for side projects" when the user never wrote any such thing is **worse than no answer**.

### 11.2 Aurora's two-layer defense

**Layer 1 — Hard retrieval gate.** `src/aurora/retrieval/service.py:103-105`:

```python
if not all_hits:
    return _INSUFFICIENT
```

If the search returns *zero* hits above the min_score threshold, the retrieval service returns a sentinel marked `insufficient_evidence=True`. The chat session checks this flag at `src/aurora/chat/session.py:174` and shows a fixed user-facing message — it does **not** call the LLM.

This is deterministic and bypass-proof. No amount of clever prompting can make the system fabricate an answer when retrieval returned nothing.

**Layer 2 — Prompt guardrail.** `src/aurora/llm/prompts.py:13-20`:

```
Voce e Aurora, um assistente pessoal privado.
{date_context}
Responda SOMENTE com base nas notas do vault fornecidas no contexto.
Cite as fontes inline no formato [caminho/nota.md] imediatamente apos a informacao usada.
...
Se a informacao nao estiver no contexto fornecido, diga que nao encontrou evidencia suficiente.
Nao invente informacoes nem extrapole alem do que esta nas notas.
```

When retrieval *does* return hits but they're weakly relevant, Layer 1 doesn't fire (the hits scored above threshold). Layer 2 is the soft guardrail: the prompt explicitly instructs the model to say "não encontrei evidência suficiente" when the returned notes don't actually answer the question.

### 11.3 Why two layers?

You could imagine skipping Layer 1 and relying only on the LLM's instruction-following. **Don't.** LLMs vary in how strictly they follow no-hallucination instructions. Some models will refuse gracefully; others will confabulate confidently. By gating deterministically on retrieval, Aurora is guaranteed-honest when there's nothing to say, and relies on the LLM only for the softer judgment "are these hits actually responsive?"

### 11.4 The tradeoff: false refusals

Layer 1's strictness means queries that *almost* match get no answer. A user asking about a topic covered by a note at score 0.28 (below the 0.30 threshold) gets "insufficient evidence." Lowering `retrieval_min_score` would fix that particular miss but open the door to weaker hits polluting results.

This is a knob to tune per-vault. 0.30 was chosen as a reasonable default for typical Obsidian corpora.

---

## 12. The citation contract

The system prompt tells the LLM to cite sources inline as `[path/note.md]`. This is enforced through:

- **Specification in the system prompt** (`src/aurora/llm/prompts.py:15-16`): "Cite as fontes inline no formato [caminho/nota.md] imediatamente apos a informacao usada."
- **Context format** (§10): each note's content is preceded by `--- path/note.md ---`, giving the LLM the exact string to use.
- **User review**: the final answer gets rendered verbatim; the user sees the citations and can audit them.

**There is no programmatic validation.** Aurora does not parse the answer to check that every claim has a citation, or that cited paths exist. The contract is best-effort: prompt + context format + human review.

This is a deliberate non-choice. Validating citations would require either:
- Parsing the answer for `[...]` markers (fragile, many false positives).
- Asking the LLM to output a structured citation list (complicates streaming).

The simpler world — trust the LLM to cite honestly, let the user verify — is good enough when combined with the insufficient-evidence gate.

---

## 13. Design decisions and tradeoffs

### 13.1 Subprocess isolation for QMD

Gains: language-boundary upgrades, failure isolation, reproducible command lines.
Costs: subprocess startup overhead, no shared-memory optimizations.
Verdict: unambiguously worth it at this scale.

### 13.2 No chunking

Gains: simpler pipeline, clearer citations, one fewer knob.
Costs: worse retrieval on long monolithic notes.
Verdict: a bet on the Obsidian authoring convention. If you break the convention, retrieval degrades gracefully but does degrade.

### 13.3 Two-layer grounding defense (retrieval gate + prompt guardrail)

Gains: deterministic refusal on hard cases, graceful refusal on soft cases.
Costs: the retrieval gate can produce false refusals.
Verdict: the right call for a personal-knowledge assistant. Hallucination is the most dangerous failure mode; false refusal is recoverable (the user rephrases).

### 13.4 Hybrid search with intent-driven strategy

Gains: covers both semantic and keyword failure modes.
Costs: an extra LLM call for intent + strategy extraction per turn.
Verdict: the extra call pays for itself by raising precision.

### 13.5 Shared QMD index across vault and memory

Gains: one embedding model, one vector space, one set of operational primitives.
Costs: can't use a different embedding model for memory vs vault.
Verdict: a constraint, but the simplicity payoff is large. If you ever need domain-specific embeddings, you'd split them.

### 13.6 Aurora writes the corpus; QMD owns the index

Gains: Aurora's source of truth is markdown (human-readable, git-friendly). The vector index is derived and rebuildable.
Costs: rebuilding embeddings after a QMD model change is a separate step the user has to run.
Verdict: the "markdown as source of truth" principle is non-negotiable for an Obsidian-integrated tool.

---

## 14. Exercises — trace it yourself

1. **Trace a hit through the pipeline.** Write a note with a distinctive phrase ("capybaras and typewriters"). Run `aurora config kb update`. Run `aurora ask "capybaras"`. Follow it from `qmd query` subprocess call → JSON parse → dedupe → context assembly → prompt. Which file's code owns each step?

2. **Break Templater stripping.** Create a note containing `<% tp.date.now() %>`. Look at the raw file size vs `cleaned_size` in `kb-manifest.json` after ingestion. By how much did they differ?

3. **Force keyword mode.** Ask a question where the intent classifier is likely to pick `keyword` (use a rare proper noun). Log the `search_strategy` field in the intent result. Compare the hits to what hybrid search would have returned — is BM25 catching something semantic missed?

4. **Force insufficient evidence.** Ask about a topic you've never written about ("my plans for Mars colonization"). Watch the retrieval log: zero hits, sentinel returned, LLM never called. Now lower `retrieval_min_score` to 0.10 and try again — what changes?

5. **Profile the dedupe.** Add a print statement at `_dedup_hits()`. On a strategy=both query, how many raw hits arrive? How many make it through dedupe? What's the spread of scores?

6. **Exhaust the context budget.** Write 20 notes on one topic and `ingest`. Ask a question that retrieves all 20. Are any dropped by the 24K truncation? Which ones — the lowest-scored? How many characters make it into the prompt?

Bonus hard mode:
- **Change the embedding granularity.** Fork the ingest code to split each note into 500-word chunks before writing to the corpus. What breaks first? Citation format? Dedupe? Context assembly?
- **Add a third search strategy.** What would a `"semantic-only"` strategy look like? When would you choose it over `hybrid`?

---

## 15. Where to go next

| To understand... | Read... |
|---|---|
| How episodic memory piggybacks on this | [memory.md](memory.md) §2–§5 |
| The LLM's end of the conversation | [model.md](model.md) |
| The KB lifecycle commands (`ingest`/`update`/`delete`/`rebuild`/`recent`) | `src/aurora/cli/kb.py` — the CLI surface |
| How the corpus is written to disk | `src/aurora/kb/qmd_backend.py` |
| How the adapter translates delta → backend | `src/aurora/kb/qmd_adapter.py` — the boundary between Aurora and QMD |
| The full ingest/update state machine | `src/aurora/kb/service.py` — the densest file in the retrieval layer |
| Test strategies for retrieval | `tests/retrieval/` — fake backends, fixture corpora, intent mocking |
| QMD itself | External: [tobi/qmd](https://github.com/tobi/qmd) |

---

**Appendix — one-sentence summary per concept:**

- **Pre-processing** — Strip Templater directives so runtime scaffolding doesn't pollute the vector space.
- **One-note-per-embedding** — No chunking; each note is one unit. Relies on Obsidian's single-topic-per-note convention.
- **QMD as subprocess** — External tool called via shell; Aurora owns the corpus, QMD owns the index.
- **Hybrid search** — Semantic (paraphrase-friendly) fused with BM25 (exact-match-friendly). Intent-driven strategy picks which to emphasize.
- **Top-K + min-score** — Retrieval returns at most K hits above a threshold. Different values for vault vs memory.
- **Dedupe by path** — When the same note surfaces in multiple searches, keep its best score; drop the rest.
- **Vault-first vs memory-first** — Ordering in context assembly shapes LLM attention and truncation behavior.
- **24K context budget** — Hard truncation after this many chars. Later notes are simply dropped from that query.
- **Insufficient evidence** — Dual-layer: hard refusal when retrieval is empty, soft refusal via prompt when hits are weak.
- **Citation contract** — Prompt-enforced `[path/note.md]` format, user-verified, not programmatically validated.
