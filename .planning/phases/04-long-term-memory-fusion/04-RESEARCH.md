# Phase 04: Long-Term Memory Fusion - Research

**Researched:** 2026-04-03
**Domain:** Long-term episodic memory persistence, QMD multi-collection retrieval, background async session summarization, preferences injection, memory CLI management
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Two-tier memory architecture:
  - **Tier 1 (Preferences):** Free-form markdown file, always injected into system prompt. User-editable. Contains rules, conventions, style preferences.
  - **Tier 2 (Episodic):** Session summaries saved as individual markdown files, indexed by QMD in a separate `aurora-memory` collection. Searched at query time alongside KB.
- **D-02:** No Graphiti/Neo4j/Docker. Memories are plain markdown files indexed by QMD.
- **D-03:** Episodic memory files stored in `~/Library/Application Support/aurora/memory/`.
- **D-04:** Preferences file at `~/Library/Application Support/aurora/preferences.md`. Free-form markdown. Raw text injected into every system prompt.
- **D-05:** Episodic memories stored as separate markdown files (one per session). QMD indexes them as collection `aurora-memory`.
- **D-06:** Episodic files named with timestamp: `2026-04-04T19-30.md`. ISO date-time, no collisions.
- **D-07:** Episodic files have YAML frontmatter: `date`, `topic`, `turn_count`, `source` (chat). Body is LLM-generated summary.
- **D-08:** Automatic memory creation after every `aurora chat` session. When user exits, Aurora summarizes the session using the LLM and saves as a markdown file.
- **D-09:** Only `aurora chat` creates memories. `aurora ask` stays stateless.
- **D-10:** LLM-generated summary of the session (not full transcript, not raw Q&A pairs). Compact, searchable.
- **D-11:** Minimum 2 turns required to create a memory. Single-turn sessions are skipped.
- **D-12:** Summary generated as background async save on chat exit. User exits immediately without waiting.
- **D-13:** Unified answer that naturally weaves vault evidence and memories together. No separate sections. System prompt instructs model to cite both sources.
- **D-14:** Vault always wins when content contradicts an old memory. Model is instructed to prefer current vault evidence over historical memories.
- **D-15:** Always retrieve both KB and memory on every vault turn. Two parallel QMD queries (one per collection). No LLM gate for whether to search memories.
- **D-16:** Memory citations use inline format with prefix: `[memoria: titulo]`. Vault citations stay as `[notas/path.md]`.
- **D-17:** Accumulate forever. No TTL, no auto-consolidation. User can manually clear via CLI.
- **D-18:** `aurora memory list` — show all episodic memories with dates and topics.
- **D-19:** `aurora memory search <query>` — semantic search over memories via QMD.
- **D-20:** `aurora memory edit` — open preferences.md in `$EDITOR`.
- **D-21:** `aurora memory clear` — delete all episodic memory files + remove from `aurora-memory` QMD collection. Preferences file stays. Confirmation required.
- **D-22:** Background async save: user types 'sair' -> exit immediately -> summary generated in background.
- **D-23:** If background save fails, log warning to file silently. Optionally notify on next `aurora chat` start.

### Claude's Discretion

- Summary generation prompt design
- Preferences file injection strategy (how to combine with existing system prompts)
- Memory retrieval top-K and min-score thresholds for the aurora-memory collection
- Background process implementation (fork, thread, subprocess)
- Exact frontmatter fields beyond date/topic/turn_count/source

### Deferred Ideas (OUT OF SCOPE)

- Graphiti graph memory backend
- Memory pinning (MEM-G01)
- Explicit memory forgetting (MEM-G02)
- Memory decay rules (MEM-G03)
- Recency-weighted scoring
- TTL/auto-consolidation
- `aurora ask` reading memories
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MEM-01 | User interactions are persisted as long-term memory across CLI sessions | D-08, D-09, D-11, D-12: `aurora chat` exit triggers background LLM summarization → episodic markdown file in memory dir |
| MEM-02 | Assistant retrieves relevant long-term memories during new questions | D-15: parallel QMD queries against `aurora-memory` collection on every vault turn; QMD `-c` flag confirmed available |
| MEM-03 | Assistant combines knowledge base evidence and memory evidence in a single response flow | D-13, D-14, D-15: unified context assembly merging both collections before LLM call; vault wins on conflict |
| MEM-04 | User can clear session memory context without deleting the entire knowledge base | D-21: `aurora memory clear` deletes only episodic files + `aurora-memory` QMD collection; preferences.md and KB untouched |
</phase_requirements>

---

## Summary

Phase 04 extends the existing chat pipeline with two orthogonal capabilities: (1) durable episodic memory written on chat exit, and (2) memory retrieval fused with vault retrieval on every vault turn. The architecture is entirely local — plain markdown files + QMD CLI, no new infra.

The key integration points are well-understood from reading existing code. `ChatHistory` already persists raw turns; the phase adds a `summarize_session` method to `LLMService` that converts those turns into a compact episodic file on exit. `RetrievalService.retrieve()` is extended to run two parallel `QMDSearchBackend` instances — one for `aurora-kb-managed`, one for `aurora-memory` — and merge their results before context assembly. System prompts in `prompts.py` receive new instructions for dual-source citation and vault-wins-conflicts priority.

The background save (D-12) uses Python `threading.Thread(daemon=True)` — the simplest reliable approach given the project's synchronous CLI architecture. Daemon threads are cleaned up on interpreter exit, and the user-facing exit path is never blocked. Silent failure logging uses Python's standard `logging` module writing to the existing config directory.

**Primary recommendation:** Implement in five sequential waves: (1) paths + memory dir infrastructure, (2) episodic file writer + LLM summarizer, (3) chat exit background save hook, (4) dual-collection retrieval fusion, (5) memory CLI command group.

---

## Standard Stack

### Core (all already in project dependencies — no new installs needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| qmd | 2.0.1 (installed) | Index and query the `aurora-memory` collection | Already the project's search backend; `-c` flag confirmed for collection filtering |
| platformdirs | >=4.3.8 (already declared) | Resolve `~/Library/Application Support/aurora/` on macOS | Already used in `paths.py` via `user_config_dir()` |
| threading (stdlib) | Python 3.13 stdlib | Background async summary save on chat exit | Daemon thread — simplest, no extra deps, safe with synchronous CLI |
| PyYAML | 6.0.3 (transitive via qmd) | Parse and write YAML frontmatter in episodic files | Available in venv; must be added as direct dependency to pyproject.toml |
| typer | >=0.16.0 (already declared) | `aurora memory` command group | Existing pattern for all CLI groups (kb_app, model_app, etc.) |
| logging (stdlib) | Python 3.13 stdlib | Silent failure logging for background save | Existing project-wide logging pattern |

### New Direct Dependency Required

PyYAML is currently a transitive dep (via qmd). Since Aurora code will import it directly to write frontmatter, add it to `pyproject.toml`:

```toml
"pyyaml>=6.0"
```

**Installation (only new dep):**
```bash
uv add pyyaml
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| threading.Thread | asyncio background task | asyncio requires making chat loop async — large refactor, no benefit here |
| threading.Thread | subprocess.Popen (fork) | Fork is heavier, harder to test, same outcome for this workload |
| PyYAML for frontmatter | python-frontmatter lib | python-frontmatter is a nice wrapper but adds a dep; PyYAML + manual `---` delimiters is simpler and already available |
| threading.Thread | multiprocessing.Process | Process isolation is overkill; the summarizer only calls the already-running LLM endpoint |

---

## Architecture Patterns

### New Files to Create

```
src/aurora/
├── memory/
│   ├── __init__.py
│   ├── store.py          # EpisodicMemoryStore: write/list/clear episodic files
│   └── summarizer.py     # MemorySummarizer: LLM session-to-summary generation
├── cli/
│   └── memory.py         # memory_app: list/search/edit/clear commands
```

### Modified Files

```
src/aurora/
├── runtime/
│   ├── paths.py          # + get_memory_dir(), get_preferences_path()
│   └── settings.py       # + memory_top_k, memory_min_score settings
├── llm/
│   ├── prompts.py        # + SYSTEM_PROMPT_GROUNDED_WITH_MEMORY, SUMMARIZE_SESSION_PROMPT
│   └── service.py        # + summarize_session(turns) method
├── retrieval/
│   ├── contracts.py      # + MemoryHit dataclass, MemorySource enum/flag on RetrievedNote
│   └── service.py        # + retrieve_with_memory(query) running dual parallel QMD queries
├── chat/
│   └── session.py        # + _handle_vault_turn uses retrieve_with_memory; exit hook
└── cli/
    ├── chat.py           # + background save on exit
    └── app.py            # + memory_app registration
```

### Pattern 1: EpisodicMemoryStore

**What:** A thin class owning the memory directory. Handles file creation (timestamped YAML frontmatter + body), listing (parse frontmatter), and clearing (delete files + QMD collection removal).

**When to use:** Any code that reads or writes episodic memory files.

```python
# src/aurora/memory/store.py
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml

from aurora.runtime.paths import get_memory_dir

logger = logging.getLogger(__name__)

MEMORY_COLLECTION = "aurora-memory"


class EpisodicMemoryStore:
    """Owns the episodic memory directory: write, list, and clear operations."""

    def __init__(self, *, memory_dir: Path | None = None) -> None:
        self._dir = memory_dir or get_memory_dir()

    def write(self, *, topic: str, turn_count: int, summary: str) -> Path:
        """Write a new episodic memory file. Returns the path written."""
        self._dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC)
        filename = now.strftime("%Y-%m-%dT%H-%M") + ".md"
        path = self._dir / filename
        frontmatter = yaml.dump(
            {"date": now.date().isoformat(), "topic": topic, "turn_count": turn_count, "source": "chat"},
            allow_unicode=True,
            default_flow_style=False,
        ).strip()
        content = f"---\n{frontmatter}\n---\n\n{summary}\n"
        path.write_text(content, encoding="utf-8")
        return path

    def list_memories(self) -> list[dict]:
        """Return list of dicts with frontmatter fields from all episodic files."""
        if not self._dir.exists():
            return []
        result = []
        for f in sorted(self._dir.glob("*.md")):
            meta = _parse_frontmatter(f)
            meta["filename"] = f.name
            result.append(meta)
        return result

    def clear(self) -> int:
        """Delete all episodic files. Returns count deleted."""
        if not self._dir.exists():
            return 0
        deleted = 0
        for f in self._dir.glob("*.md"):
            f.unlink()
            deleted += 1
        return deleted
```

### Pattern 2: Background Summary Save via threading.Thread

**What:** On chat exit, spin a daemon thread to generate and save the session summary. The CLI's exit path returns immediately.

**When to use:** In `cli/chat.py` after the chat loop exits — both on 'sair' and EOFError/KeyboardInterrupt.

```python
# In cli/chat.py (exit flow)
import logging
import threading

logger = logging.getLogger(__name__)


def _background_save(history, llm, store, turn_count: int) -> None:
    """Run in daemon thread — failures are silently logged, never raised."""
    try:
        from aurora.memory.summarizer import MemorySummarizer
        summarizer = MemorySummarizer(llm=llm, store=store)
        summarizer.summarize_and_save(history=history, turn_count=turn_count)
    except Exception:
        logger.warning("Memory background save failed", exc_info=True)


# After exit loop in chat_command():
if session.turn_count >= 2:  # D-11: min 2 turns
    t = threading.Thread(
        target=_background_save,
        args=(history, llm, store, session.turn_count),
        daemon=True,
    )
    t.start()
    # Do NOT join — user already exited (D-12)
```

### Pattern 3: Dual Parallel QMD Retrieval (D-15)

**What:** `RetrievalService` gets a new `retrieve_with_memory()` method that instantiates two `QMDSearchBackend` objects — one per collection — runs both searches sequentially (Python threading adds complexity, two blocking subprocess calls is simpler), and merges results before context assembly.

**Note on "parallel":** D-15 says "two parallel QMD queries" — this means "always query both, not conditionally", not necessarily true concurrent execution. Given the subprocess shell-out pattern and the local LLM context, sequential execution is correct here. Naming should reflect "always-dual" semantics.

```python
# In retrieval/service.py
def retrieve_with_memory(self, query: str) -> RetrievalResult:
    """Query both KB and memory collections; merge and assemble context."""
    kb_response = self._backend.search(query)          # aurora-kb-managed
    mem_response = self._memory_backend.search(query)  # aurora-memory

    all_hits = list(kb_response.hits) + list(mem_response.hits)
    # tag which collection each hit came from for citation generation
    ...
```

### Pattern 4: Source-Tagged RetrievedNote

**What:** `RetrievedNote` and `QMDSearchHit` need a `source` field to distinguish vault from memory hits. Citation format depends on this: `[notas/path.md]` for vault, `[memoria: titulo]` for memory.

```python
# Extended contracts.py
@dataclass(frozen=True)
class RetrievedNote:
    path: str
    score: float
    content: str
    source: str = "vault"  # "vault" | "memory"
```

### Pattern 5: Preferences Injection (Tier 1)

**What:** `preferences.md` is read at session start and prepended to the system prompt. If the file doesn't exist, injection is silently skipped.

```python
# In llm/prompts.py or session.py
def build_system_prompt(base_prompt: str, preferences_path: Path) -> str:
    if preferences_path.exists():
        prefs = preferences_path.read_text(encoding="utf-8").strip()
        if prefs:
            return f"## Preferencias do usuario\n{prefs}\n\n{base_prompt}"
    return base_prompt
```

### Anti-Patterns to Avoid

- **Joining the background thread before exit:** The user must exit immediately (D-12). Never `t.join()` in the CLI exit path.
- **Raising in the background thread:** Any exception in `_background_save` must be caught and logged silently (D-23). Never let it propagate.
- **Single QMDSearchBackend for dual-collection search:** The existing `QMDSearchBackend` stores one `collection_name` at construction. Instantiate two separate backends with different `collection_name` arguments. Do not try to pass multiple `-c` values to one instance.
- **Injecting preferences into non-chat paths:** `aurora ask` is stateless (D-09); do not inject preferences.md there. Only `aurora chat` uses Tier 1.
- **Blocking `aurora memory clear` without confirmation:** Must prompt for confirmation or require `--yes` flag, matching the KB delete pattern (see `qmd_adapter.py`).
- **Using `yaml.safe_load` with the `---` stripped manually:** Use `yaml.safe_load` on the extracted frontmatter block only, not on the entire file including body. The body is raw markdown.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Semantic search over memory files | Custom vector store, custom BM25 index | QMD with `aurora-memory` collection | QMD already handles hybrid retrieval, reranking, min-score filtering |
| Background process for summary | multiprocessing.Process, subprocess.Popen | threading.Thread(daemon=True) | Simpler, no IPC, no serialization, access to same LLMService instance |
| YAML frontmatter parsing | Regex-based custom parser | PyYAML (already in venv) | Edge cases in YAML are non-trivial; PyYAML handles unicode, multiline, special chars |
| File-based timestamp collision prevention | Custom UUID generation | ISO 8601 datetime with minute precision | QMD only supports one session per minute, which matches actual usage pattern |
| Memory staleness scoring | Custom recency decay algorithm | QMD relevance score (natural decay via score) | D-17 explicitly defers this |
| Memory collection registration | Separate service or daemon | QMD `collection add` CLI shell-out | Consistent with how KB collection is registered (`QMDCliBackend._bootstrap_collection`) |

**Key insight:** QMD is already the retrieval substrate; adding a second collection to it costs almost nothing compared to introducing an independent vector store.

---

## Common Pitfalls

### Pitfall 1: Background Thread Keeps Process Alive (Not a Daemon)
**What goes wrong:** If `threading.Thread(daemon=False)` is used (the default), Python waits for it to finish before the interpreter exits. The user sees a hang after typing 'sair'.
**Why it happens:** Python's default thread join-on-exit behavior.
**How to avoid:** Always pass `daemon=True` when creating the background save thread.
**Warning signs:** `aurora chat` hangs for seconds after typing 'sair'.

### Pitfall 2: Turn Count Tracking Not Exposed to CLI
**What goes wrong:** `ChatSession.process_turn()` increments an internal counter, but `cli/chat.py` has no way to access it to gate the background save (D-11).
**Why it happens:** `ChatSession` currently has no public `turn_count` attribute.
**How to avoid:** Add a `turn_count: int` property to `ChatSession` that counts completed turns. The CLI reads this before deciding to spawn the background thread.
**Warning signs:** Memories created for single-turn or zero-turn sessions.

### Pitfall 3: aurora-memory Collection Not Bootstrapped Before First Query
**What goes wrong:** `QMDSearchBackend.search()` for `aurora-memory` returns a parse error or `query_failed` diagnostic if the collection doesn't exist yet.
**Why it happens:** QMD returns non-zero exit code when querying a nonexistent collection.
**How to avoid:** Treat `aurora-memory` query failures as "empty results" (not InsufficientEvidence). The memory backend returns an empty `QMDSearchResponse` gracefully. The collection is bootstrapped only when the first episodic file is written via `collection add`.
**Warning signs:** `aurora chat` vault turns fail entirely on a fresh install.

### Pitfall 4: Context Length Explosion with Dual Sources
**What goes wrong:** Merging KB notes (up to 12,000 chars) and memory snippets without a combined cap causes context overflow to the local LLM.
**Why it happens:** `MAX_CONTEXT_CHARS = 12_000` in `service.py` only applied to the vault. Memory content adds on top.
**How to avoid:** Apply a single shared `MAX_CONTEXT_CHARS` budget across both sources after merging. Vault notes take priority (D-14), so rank-sort vault hits first in the merged list before truncation.
**Warning signs:** LLM responses truncated, slow generation, or model errors on long inputs.

### Pitfall 5: Preferences Injection Breaks Existing Grounding Prompt
**What goes wrong:** Prepending preferences.md to `SYSTEM_PROMPT_GROUNDED` without careful ordering causes the model to blend grounding rules with user preferences in unpredictable ways.
**Why it happens:** The model interprets the system prompt as a unified instruction set.
**How to avoid:** Structure the combined prompt with clear section headers: `## Preferencias do usuario` (from preferences.md) followed by the existing grounding instructions. Never merge free-form text with the structured grounding block directly.
**Warning signs:** Model ignores citation instructions or invents facts not in the vault.

### Pitfall 6: `qmd collection remove aurora-memory` Leaves Corpus Files
**What goes wrong:** `aurora memory clear` deletes the markdown files from disk but the QMD collection still exists (pointing to now-missing files), causing error diagnostics on next query.
**Why it happens:** QMD collection registration and file presence are separate concerns.
**How to avoid:** `aurora memory clear` must: (1) delete all `.md` files from the memory dir, (2) run `qmd --index aurora-kb collection remove aurora-memory`, (3) confirm both succeeded. Match the KB `rebuild` pattern in `QMDCliBackend`.
**Warning signs:** `aurora memory search` returns stale entries or error diagnostics after `clear`.

### Pitfall 7: Timestamp Collision in Filename (D-06)
**What goes wrong:** Two sessions ending within the same minute produce the same filename (`2026-04-03T19-30.md`) and the second write overwrites the first.
**Why it happens:** Minute-level precision is the chosen format.
**How to avoid:** Check for filename existence before writing; append `-2`, `-3` etc. if collision detected. This is an edge case (two simultaneous sessions) but must not silently lose data.
**Warning signs:** User starts two terminal tabs with `aurora chat` simultaneously.

### Pitfall 8: ChatHistory Records vs. Turn Count Mismatch
**What goes wrong:** `ChatHistory.load()` includes all previous sessions if the JSONL file was not cleared. Summarizing "the session" would include old conversation history.
**Why it happens:** `ChatHistory` accumulates across sessions unless cleared.
**How to avoid:** The `MemorySummarizer` must summarize only the turns from the **current** session. Track a `session_start_index` (position in the JSONL before this session's turns were appended) in `ChatSession`, and pass only `history.load()[session_start_index:]` to the summarizer.
**Warning signs:** Memory summaries include context from previous days' conversations.

---

## Code Examples

Verified patterns from existing codebase:

### QMD Collection Bootstrap (from QMDCliBackend._bootstrap_collection pattern)
```python
# Consistent with existing kb/qmd_backend.py approach
# Source: src/aurora/kb/qmd_backend.py
def _bootstrap_memory_collection(self, memory_dir: Path) -> None:
    """Register aurora-memory collection with QMD if not already registered."""
    result = self._run_command((
        "qmd", "--index", self._index_name,
        "collection", "add", str(memory_dir), "--name", MEMORY_COLLECTION,
    ))
    # rc=0 = added, rc=1 = already exists or failed; both are acceptable at bootstrap
```

### QMD Search with Collection Filter (already supported in existing QMDSearchBackend)
```python
# Source: src/aurora/retrieval/qmd_search.py — -c flag already wired
command = (
    "qmd", "--index", self.index_name,
    "query", "--json",
    "-n", str(self.top_k),
    "-c", self.collection_name,     # <-- collection_name="aurora-memory" for memory backend
    "--min-score", min_score_str,
    query,
)
```

### Path Registration Pattern (consistent with existing paths.py)
```python
# Source: src/aurora/runtime/paths.py — new constants follow existing naming
MEMORY_DIRNAME = "memory"
PREFERENCES_FILENAME = "preferences.md"

def get_memory_dir() -> Path:
    """Return the directory for Aurora-managed episodic memory files."""
    return get_config_dir() / MEMORY_DIRNAME

def get_preferences_path() -> Path:
    """Return the path for the Tier 1 preferences markdown file."""
    return get_config_dir() / PREFERENCES_FILENAME
```

### Typer Command Group Pattern (from cli/kb.py structure)
```python
# Source: src/aurora/cli/app.py — existing registration pattern
memory_app = typer.Typer(name="memory", help="Gerencia memorias de longo prazo.")

@memory_app.command("list")
def memory_list() -> None: ...

@memory_app.command("search")
def memory_search(query: str = typer.Argument(...)) -> None: ...

@memory_app.command("edit")
def memory_edit() -> None: ...

@memory_app.command("clear")
def memory_clear(yes: bool = typer.Option(False, "--yes")) -> None: ...

# In app.py:
app.add_typer(memory_app, name="memory")
```

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| qmd CLI | Memory collection index + search | Yes | 2.0.1 | — |
| PyYAML | YAML frontmatter write/parse | Yes (transitive) | 6.0.3 | Add as direct dep to pyproject.toml |
| threading (stdlib) | Background save | Yes | Python 3.13 stdlib | — |
| platformdirs | Memory dir resolution | Yes | >=4.3.8 declared | — |
| Python 3.13 | Project runtime | Yes | 3.13.12 (via uv) | — |
| pytest | Test suite | Yes | 9.0.2 (via uv) | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** PyYAML is a transitive dep — available but should be added to `pyproject.toml` as a direct dependency since Aurora code will import it directly.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/memory/ tests/chat/ tests/cli/test_chat_command.py tests/cli/test_memory_command.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MEM-01 | Episodic file written with correct frontmatter after chat session with >=2 turns | unit | `uv run pytest tests/memory/test_store.py -x` | Wave 0 |
| MEM-01 | No file written when turn_count < 2 | unit | `uv run pytest tests/memory/test_summarizer.py::test_skip_single_turn -x` | Wave 0 |
| MEM-01 | Background thread spawned on chat exit (daemon=True) | unit | `uv run pytest tests/cli/test_chat_command.py::TestChatCommandMemorySave -x` | Wave 0 |
| MEM-02 | Memory QMD backend queried on every vault turn | unit | `uv run pytest tests/chat/test_session.py::TestChatSessionMemoryRetrieval -x` | Wave 0 |
| MEM-02 | Memory backend returns empty result gracefully when collection missing | unit | `uv run pytest tests/retrieval/test_retrieval_service.py::TestRetrieveWithMemory -x` | Wave 0 |
| MEM-03 | Context assembly merges vault and memory hits under shared char budget | unit | `uv run pytest tests/retrieval/test_retrieval_service.py::TestDualSourceContext -x` | Wave 0 |
| MEM-03 | Vault hits ranked before memory hits in merged context (D-14) | unit | `uv run pytest tests/retrieval/test_retrieval_service.py::TestVaultPriority -x` | Wave 0 |
| MEM-04 | `aurora memory clear` deletes episodic files and removes QMD collection | unit | `uv run pytest tests/cli/test_memory_command.py::TestMemoryClear -x` | Wave 0 |
| MEM-04 | `aurora memory clear` prompts confirmation; KB and preferences untouched | unit | `uv run pytest tests/cli/test_memory_command.py::TestMemoryClearConfirmation -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/memory/ tests/chat/ tests/retrieval/ -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/memory/__init__.py` — new module
- [ ] `tests/memory/test_store.py` — covers MEM-01 file write/list/clear
- [ ] `tests/memory/test_summarizer.py` — covers MEM-01 LLM summarizer, min-turn gate
- [ ] `tests/cli/test_memory_command.py` — covers MEM-04 CLI commands
- [ ] `tests/chat/test_session.py` — extend with `TestChatSessionMemoryRetrieval` class (file exists)
- [ ] `tests/cli/test_chat_command.py` — extend with `TestChatCommandMemorySave` class (file exists)
- [ ] `tests/retrieval/test_retrieval_service.py` — extend with dual-source test classes (file exists)

---

## Open Questions

1. **Session history isolation (Pitfall 8)**
   - What we know: `ChatHistory` accumulates all turns across sessions in one JSONL file.
   - What's unclear: Is there a session boundary marker in the JSONL? Currently, no.
   - Recommendation: Add a `session_start_index` tracker to `ChatSession.__init__()` that records `len(history.load())` at session start. The summarizer receives only `turns[session_start_index:]`.

2. **QMD collection add idempotency**
   - What we know: The KB backend calls `collection add` every apply; QMD appears to tolerate the call if the collection exists.
   - What's unclear: Does `qmd collection add` error (rc != 0) if the collection is already registered? If so, bootstrap logic must check `rc in (0, 1)` like KB does.
   - Recommendation: Follow the exact `_bootstrap_collection` pattern in `QMDCliBackend` (non-zero exit on "already exists" is treated as OK).

3. **Preferences.md first-run creation**
   - What we know: The file should not exist on fresh install (D-20 says `aurora memory edit` opens it in `$EDITOR`).
   - What's unclear: Should a starter template be written on first `aurora chat` start, or only created lazily when `aurora memory edit` is first run?
   - Recommendation: Create an empty file (with a pt-BR comment header) on first `aurora chat` if missing, so preferences injection is a no-op on first run but the file is ready for the user to edit. Avoids showing an error on `aurora memory edit` for new users.

4. **Summary generation prompt topic extraction**
   - What we know: The frontmatter `topic` field (D-07) should be a short title, not the full summary.
   - What's unclear: Whether to ask the LLM for both `topic` and `summary` in one call (structured output) or two calls.
   - Recommendation: Single LLM call with a structured prompt asking for a JSON-like output: first line = topic (max 60 chars), rest = summary paragraph. Parse with simple string split. This avoids a second LLM round-trip.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| External memory services (Mem0, Zep, Redis) | Local plain markdown + QMD | Phase 04 design decision | Zero new infra, full privacy |
| Graphiti/Neo4j graph memory | Flat file episodic with QMD semantic search | Phase 04 design decision | No Docker dependency |
| Separate context sections ("From memory: ...") | Unified weaved response with inline citations | D-13 | Cleaner UX, consistent with vault citation style |

**Deprecated/outdated for this phase:**
- Using `aurora ask` for memory-augmented responses — kept stateless per D-09; memory is chat-only.

---

## Project Constraints (from CLAUDE.md)

CLAUDE.md does not exist in this project. The following constraints are inferred from the existing codebase patterns and must be honored:

- **pt-BR in all user-facing text:** All CLI output, error messages, confirmation prompts, and help text must be in pt-BR (consistent with all existing commands).
- **Frozen dataclasses for contracts:** `QMDSearchHit`, `RetrievalResult`, `RetrievedNote` all use `@dataclass(frozen=True)`. Any new contract types (e.g. `MemoryHit`) must follow this pattern.
- **Pydantic validators in RuntimeSettings:** Any new settings fields (e.g. `memory_top_k`, `memory_min_score`) must follow the existing `@field_validator` pattern with range validation.
- **Privacy-safe logging:** No raw note or memory content in log output (PRIV-03 pending). Log paths, counts, categories — not content.
- **Local-only policy:** All new code paths use the local LLM endpoint. No external API calls.
- **Telemetry off by default:** No analytics hooks in new code.
- **`--yes` flag for destructive ops:** `aurora memory clear` must require interactive confirmation or `--yes` flag, matching the KB delete pattern.
- **`_run_command` abstraction for QMD shell-outs:** New QMD calls must use the `CommandRunner` protocol pattern so tests can inject mock runners.

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection: `src/aurora/retrieval/qmd_search.py` — confirmed `-c` flag support and collection_name parameter
- Direct code inspection: `src/aurora/kb/qmd_backend.py` — confirmed `_bootstrap_collection` pattern for `collection add`
- Direct code inspection: `src/aurora/runtime/paths.py` — confirmed `get_config_dir()` returns `~/Library/Application Support/aurora` on macOS
- Direct code inspection: `src/aurora/chat/session.py` — confirmed existing session structure and history integration points
- Direct code inspection: `src/aurora/llm/service.py` — confirmed method signatures for extension
- `qmd --help` + `qmd query --help` — confirmed `-c, --collection <name>` flag is available in qmd 2.0.1
- Python 3.13 stdlib docs — `threading.Thread(daemon=True)` behavior confirmed
- `uv pip list` — PyYAML 6.0.3 confirmed available as transitive dep

### Secondary (MEDIUM confidence)
- QMD collection add idempotency behavior — inferred from existing `_bootstrap_collection` defensive pattern in `QMDCliBackend` (treating non-zero rc as acceptable at bootstrap); not directly tested here

### Tertiary (LOW confidence)
- None — all critical claims are backed by direct code inspection or CLI invocation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries directly verified in the installed environment
- Architecture: HIGH — all integration points read from source; patterns copied from existing code
- Pitfalls: HIGH for Pitfalls 1-4 (verified from code structure); MEDIUM for Pitfalls 5-8 (reasoning-based, consistent with codebase patterns)
- QMD collection behavior: MEDIUM — confirmed `-c` flag and `collection add` exist; edge cases (idempotency) inferred from existing KB bootstrap pattern

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (stable stack, 30-day window)
