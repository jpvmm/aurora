# Phase 03: Grounded Retrieval Experience - Research

**Researched:** 2026-04-03
**Domain:** RAG pipeline, llama.cpp streaming, CLI conversation UX
**Confidence:** HIGH (codebase verified) / MEDIUM (QMD query interface)

## Summary

This phase adds two CLI commands — `aurora ask` (single-shot grounded Q&A) and `aurora chat`
(multi-turn intent-routed conversation) — on top of the already-working KB indexing stack.
The retrieval side is fully delegated to QMD's `qmd query` and `qmd get` commands, which are
already shell-out patterns in the codebase. The generation side requires extending
`LlamaRuntimeClient` with a streaming `/v1/chat/completions` call. The trickiest new
surface is `aurora chat`: intent classification, per-turn re-retrieval, and chat history
persistence to disk.

The existing `QMDCliBackend` establishes every pattern needed for the retrieval subprocess
calls: `subprocess.run` with `capture_output=True`, `FileNotFoundError` guard, structured
`QMDBackendResponse`/`QMDBackendDiagnostic` dataclasses for error surfacing. The new
retrieval service (`RetrievalService` or equivalent) will mirror this pattern for
`qmd query --json` and `qmd get`.

**Primary recommendation:** Build a `RetrievalService` that shells out to `qmd query --json`
and `qmd get`, a `LLMService` that wraps `/v1/chat/completions` with streaming, and register
`aurora ask` and `aurora chat` commands in `cli/app.py` following the established typer +
service-layer pattern.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Retrieval Strategy**
- D-01: Use QMD's built-in `qmd query` for hybrid search (BM25 + vector + LLM rerank). No custom RAG pipeline.
- D-02: Fixed top-K retrieval (5-10 results). Predictable token usage per query.
- D-03: Send full notes to the model (not just chunks). Use `qmd get` to fetch complete documents.
- D-04: Truncate to fit when retrieved notes exceed model context window. Prioritize top-ranked notes, drop the rest.
- D-05: Pass user query directly to QMD without preprocessing.
- D-06: Hardcoded system prompt that enforces grounding rules, citation format, and pt-BR default. Not user-editable.
- D-07: Log retrieved note paths and relevance scores for debugging/transparency. Respects PRIV-03 by not logging content.

**Citation Format**
- D-08: Inline references in the answer text, format: `[notas/projeto.md]`. Path only, no section or line numbers.
- D-09: Deduplicate citations — one reference per note even if multiple chunks from the same note were used.

**Conversation UX**
- D-10: Two commands: `aurora ask "question"` (single-shot grounded Q&A) and `aurora chat` (interactive multi-turn).
- D-11: Stream tokens to terminal as they're generated. llama.cpp supports SSE streaming.
- D-12: `aurora chat` persists conversation history to disk so sessions can be resumed later.
- D-13: `aurora chat` re-retrieves from KB on each turn (fresh QMD search per question).
- D-14: `aurora chat` uses LLM-based intent routing — classifies each message as "vault question" or "general chat".
- D-15: `aurora ask` always retrieves from KB — no intent routing, always grounded.

**Insufficient Evidence**
- D-16: QMD min-score threshold gates insufficient evidence. If no results pass the threshold, Aurora refuses to answer.
- D-17: Refusal message in pt-BR: "Nao encontrei evidencia suficiente no vault para responder. Tente reformular ou verifique se o topico esta indexado."
- D-18: In `aurora chat` general chat mode (no KB retrieval), the model chats freely without grounding constraints.

### Claude's Discretion
- Exact system prompt wording and grounding instructions
- Top-K default value (within 5-10 range)
- Min-score threshold value for insufficient evidence gate
- Chat history persistence format and storage location
- Intent classification prompt design
- Streaming implementation details

### Deferred Ideas (OUT OF SCOPE)
- User-customizable system prompt
- LLM-rewritten queries for better search recall
- Partial answers with caveats when evidence is weak
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RET-01 | User can ask questions in CLI and receive answers grounded in vault content | `aurora ask` command + retrieval + LLM generation pipeline |
| RET-02 | User receives citations with note path and section reference for each grounded answer | Hardcoded system prompt enforces `[path/note.md]` inline citation format; deduplicated |
| RET-03 | User query uses hybrid retrieval (keyword + semantic) for evidence selection | `qmd query` BM25 + vector + LLM rerank satisfies this natively |
| RET-04 | User gets explicit "insufficient evidence" response when vault context is not enough | QMD min-score threshold gates retrieval; pt-BR refusal message on no results |
| CLI-03 | Assistant replies in pt-BR by default and only changes language when user requests | Hardcoded system prompt mandates pt-BR; can switch only on explicit user request |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| typer | >=0.16.0 (already in project) | CLI command registration | Established pattern in project |
| pydantic / pydantic-settings | already in project | Settings, frozen dataclasses | Established pattern in project |
| subprocess (stdlib) | stdlib | QMD CLI shell-out | Same pattern as QMDCliBackend |
| urllib (stdlib) | stdlib | llama.cpp HTTP calls | Same pattern as LlamaRuntimeClient |
| json (stdlib) | stdlib | Parse QMD --json output | Used throughout codebase |
| pathlib (stdlib) | stdlib | Chat history persistence path | Used throughout codebase |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| qmd CLI | installed (npm/bun) | Hybrid KB search | All retrieval calls |
| llama.cpp server | running locally | LLM inference + streaming | All generation calls |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib urllib for streaming | requests library | requests not in pyproject.toml; urllib handles SSE line-by-line |
| qmd get (full doc) | qmd snippet from query | D-03 locked: full notes required |

**Installation:** No new Python dependencies required. QMD already used by KB layer.

---

## Architecture Patterns

### Recommended Project Structure

New modules that parallel existing KB structure:

```
src/aurora/
├── retrieval/                   # New: retrieval domain
│   ├── __init__.py
│   ├── contracts.py             # RetrievalResult, RetrievedNote, InsufficientEvidenceResult
│   ├── qmd_search.py            # QMDSearchBackend: shells out to qmd query + qmd get
│   └── service.py               # RetrievalService: orchestrates search -> fetch -> truncate
├── llm/                         # New: LLM generation domain
│   ├── __init__.py
│   ├── prompts.py               # SYSTEM_PROMPT_GROUNDED, SYSTEM_PROMPT_CHAT, INTENT_PROMPT
│   ├── streaming.py             # token streaming from /v1/chat/completions
│   └── service.py               # LLMService: ask_grounded, chat_turn, classify_intent
├── chat/                        # New: conversation state
│   ├── __init__.py
│   ├── history.py               # ChatHistory: load/save to disk, append turns
│   └── session.py               # ChatSession: per-turn loop with intent routing
├── cli/
│   ├── app.py                   # Add ask_app + chat_app registrations
│   ├── ask.py                   # `aurora ask "query"` command
│   └── chat.py                  # `aurora chat` interactive command
└── runtime/
    ├── llama_client.py          # Extend with streaming_chat_completions
    └── settings.py              # Add: retrieval_top_k, retrieval_min_score, chat_history_path
```

### Pattern 1: QMD Search Shell-out (mirrors QMDCliBackend)

**What:** Run `qmd --index {index_name} query --json -n {top_k} --min-score {min_score} "{query}"`, parse JSON, return structured results.

**When to use:** Every retrieval call (both `aurora ask` and each vault-question turn in `aurora chat`).

```python
# Source: inferred from QMDCliBackend pattern in src/aurora/kb/qmd_backend.py
def search(self, query: str) -> QMDSearchResponse:
    command = (
        "qmd", "--index", self.index_name,
        "query", "--json",
        "-n", str(self.top_k),
        "--min-score", str(self.min_score),
        query,
    )
    try:
        result = self._run_command(command)
    except FileNotFoundError:
        return self._error("backend_unavailable", "Comando `qmd` nao encontrado.")

    if result.returncode != 0:
        return self._error("search_failed", "Falha na busca QMD.")

    payload = json.loads(result.stdout)
    return QMDSearchResponse(ok=True, hits=_parse_hits(payload))
```

### Pattern 2: QMD Get Full Document

**What:** Run `qmd --index {index_name} get "{collection_name}/{relative_path}"` and capture stdout as document content.

**When to use:** After search returns hits, fetch full note content for context window assembly.

```python
# Source: inferred from integration test conftest.py collection_get pattern
def fetch(self, relative_path: str) -> str | None:
    command = (
        "qmd", "--index", self.index_name,
        "get", f"{self.collection_name}/{relative_path}",
    )
    result = self._run_command(command)
    if result.returncode != 0:
        return None
    return result.stdout
```

### Pattern 3: Streaming Chat Completions (extends LlamaRuntimeClient)

**What:** POST to `/v1/chat/completions` with `stream: true`, read SSE lines, yield content delta tokens.

**When to use:** All LLM generation calls (both grounded and general chat mode).

```python
# Source: llama.cpp OpenAI-compatible server SSE format
# stream=True returns: data: {"choices":[{"delta":{"content":"token"}}]}\n\ndata: [DONE]\n
def stream_chat(
    self,
    messages: list[dict],
    *,
    on_token: Callable[[str], None],
) -> None:
    body = json.dumps({
        "model": self.model_id,
        "messages": messages,
        "stream": True,
    }).encode("utf-8")
    request = Request(
        f"{self.endpoint_url}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=self.timeout_seconds) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            delta = chunk["choices"][0]["delta"]
            if content := delta.get("content"):
                on_token(content)
```

### Pattern 4: Chat History Persistence

**What:** Load/save conversation history as JSON lines (JSONL) to a fixed path under the config directory.

**When to use:** `aurora chat` — load on session start, append on each turn, save after each turn.

```python
# Source: design choice aligned with RuntimeSettings platformdirs pattern
# Stored at: get_config_dir() / "chat_history.jsonl"
# Each line: {"role": "user"|"assistant", "content": "...", "ts": "ISO8601"}
```

### Pattern 5: Intent Classification

**What:** One-shot LLM call (non-streaming) with a compact intent prompt. Returns "vault" or "chat".

**When to use:** Each user turn in `aurora chat` before deciding retrieval path.

```python
# Compact intent prompt (Claude's discretion for exact wording):
INTENT_PROMPT = """Classifique a mensagem do usuario em uma categoria:
- vault: pergunta sobre notas, documentos, informacoes que provavelmente estao no vault pessoal
- chat: conversa geral, tarefa generica, sem relacao com vault

Responda apenas com a palavra: vault ou chat

Mensagem: {message}"""
```

### Pattern 6: Context Window Assembly + Truncation

**What:** Combine retrieved full notes into a context block. Fit top-ranked notes first; truncate remaining if total exceeds max_context_chars.

**When to use:** After fetching full note content via `qmd get`, before LLM call.

```python
# Conservative context limit: 12_000 chars (~3000 tokens) leaves room for
# system prompt + query + answer. Tunable via settings.
MAX_CONTEXT_CHARS = 12_000

def assemble_context(notes: list[tuple[str, str]]) -> str:
    """notes: list of (relative_path, content) sorted by score descending."""
    parts = []
    remaining = MAX_CONTEXT_CHARS
    for path, content in notes:
        chunk = f"--- {path} ---\n{content}\n"
        if len(chunk) > remaining:
            chunk = chunk[:remaining]
        parts.append(chunk)
        remaining -= len(chunk)
        if remaining <= 0:
            break
    return "\n".join(parts)
```

### Pattern 7: Grounded System Prompt

**What:** Hardcoded system prompt that enforces: answer only from vault context, inline citations, pt-BR default.

```python
SYSTEM_PROMPT_GROUNDED = """Voce e Aurora, um assistente pessoal privado.
Responda SOMENTE com base nas notas do vault fornecidas no contexto.
Cite as fontes inline no formato [caminho/nota.md] imediatamente apos a informacao usada.
Deduplique as citacoes: cite cada nota apenas uma vez.
Se a informacao nao estiver no contexto fornecido, diga que nao encontrou evidencia suficiente.
Responda em pt-BR por padrao. Mude o idioma somente se o usuario solicitar explicitamente.
Nao invente informacoes nem extrapole alem do que esta nas notas."""
```

### Anti-Patterns to Avoid

- **Building custom BM25 + vector merge:** QMD already does this. D-01 is locked.
- **Sending chunk snippets instead of full notes:** D-03 is locked — always `qmd get` the full doc.
- **Logging note content:** PRIV-03 requires content-free logs. Log `path` and `score` only.
- **Blocking terminal on streaming:** Always flush stdout tokens immediately (`print(token, end="", flush=True)`).
- **Single global chat history file with no session boundary:** Leads to unbounded context growth. Either truncate to last N turns or use session-keyed files.
- **Non-streaming intent classification:** Intent prompt is short — non-streaming is fine and simpler to implement.
- **Streaming intent classification:** Introduces unnecessary complexity; use `/v1/chat/completions` without `stream: true` for intent.
- **Passing entire chat history to QMD search:** QMD query should be the latest user message only (D-05).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Hybrid search (BM25 + semantic + rerank) | Custom retrieval pipeline | `qmd query` | QMD already implements BM25 + vector + LLM rerank natively (D-01) |
| Document fetching | Custom file reader | `qmd get` | QMD manages the corpus; direct file reads bypass the index abstraction |
| SSE token streaming | Custom HTTP chunked reader | stdlib `urllib.request.urlopen` + line iteration | llama.cpp emits standard `data: {...}\n\n` SSE; line iteration is sufficient |
| Chat history compression | Token-counting summarizer | Fixed window truncation (last N turns) | Phase 4 handles memory; Phase 3 just needs simple history persistence |

**Key insight:** The retrieval complexity is fully absorbed by QMD. The generation complexity is absorbed by llama.cpp's OpenAI-compatible endpoint. This phase is mostly plumbing between these two existing services.

---

## Common Pitfalls

### Pitfall 1: QMD `--index` Flag Required for All Commands
**What goes wrong:** Calling `qmd query` without `--index` searches the default/global index instead of Aurora's dedicated index.
**Why it happens:** QMD supports multiple indexes. Without `--index`, commands silently operate on the wrong index.
**How to avoid:** Every subprocess call to `qmd` must include `--index {self.index_name}` as the second and third argument, matching `QMDCliBackend`'s pattern.
**Warning signs:** Searches return zero results even though notes are indexed, or return results from unrelated documents.

### Pitfall 2: QMD `--collection` vs `--index` Scope in Query
**What goes wrong:** `qmd query` by default searches across all collections in the index. If multiple collections exist, results may include documents outside Aurora's managed collection.
**Why it happens:** QMD separates indexing (collections within an index) from search scope.
**How to avoid:** Always pass `-c {collection_name}` or `--collection {collection_name}` to `qmd query` to scope results to Aurora's managed collection.
**Warning signs:** Citations reference files not in the vault.

### Pitfall 3: `qmd get` Path Format
**What goes wrong:** Calling `qmd get "notes/alpha.md"` instead of `qmd get "collection_name/notes/alpha.md"` returns nothing or the wrong document.
**Why it happens:** QMD's `get` command expects the collection-qualified path: `{collection_name}/{relative_path}`.
**How to avoid:** Verified in `tests/integration/conftest.py` — the integration test uses `self.run_qmd("get", f"{self.collection_name}/{relative_path}")`.
**Warning signs:** `qmd get` returns non-zero exit code or empty stdout for known-good paths.

### Pitfall 4: Streaming Timeout with Long Responses
**What goes wrong:** `urllib.urlopen` timeout fires mid-stream on long LLM responses, cutting off the answer.
**Why it happens:** The timeout applies to the entire connection duration, not just to the initial connection.
**How to avoid:** Use a separate, longer timeout (e.g. `stream_timeout_seconds = 120`) for streaming calls vs. the health probe timeout (3 seconds). Do not reuse `LlamaRuntimeClient.timeout_seconds` for streaming.
**Warning signs:** Long answers get cut off; `urllib.error.URLError: timed out` during streaming.

### Pitfall 5: Intent Classification Prompt Leaking History
**What goes wrong:** Passing full multi-turn conversation history to the intent classifier wastes tokens and makes classification less reliable.
**Why it happens:** Temptation to "give context" to the classifier.
**How to avoid:** Pass only the single latest user message to the intent classification call. The classifier does not need history.
**Warning signs:** Slower turns; misclassification of short messages.

### Pitfall 6: Unbounded Chat History Context
**What goes wrong:** `aurora chat` grows context window unboundedly across a long session, eventually causing llama.cpp to truncate or error.
**Why it happens:** Appending every turn to history without a window cap.
**How to avoid:** Limit messages sent to LLM to last N turns (e.g. last 10 user+assistant pairs). Still persist full history to disk (for future Phase 4 memory). Only the slice sent to LLM is capped.
**Warning signs:** Very long sessions start giving degraded or truncated responses.

### Pitfall 7: Streaming Flush in Typer CLI
**What goes wrong:** Streaming tokens appear all at once at the end instead of incrementally.
**Why it happens:** Typer/Python output buffering. `typer.echo()` buffers by default.
**How to avoid:** Use `print(token, end="", flush=True)` directly for streaming output, not `typer.echo()`. After stream ends, call `print()` for a final newline.
**Warning signs:** No incremental output; tokens appear in a single batch after a delay.

### Pitfall 8: No-Results vs Below-Threshold Distinction
**What goes wrong:** Returning "insufficient evidence" when QMD returned no results (empty list) vs. when results were filtered by min-score (list was non-empty before filtering).
**Why it happens:** QMD `--min-score` filters before returning, so empty results list covers both "no docs found" and "docs found but below threshold."
**How to avoid:** Both cases map to the same insufficient-evidence response (D-16, D-17). No distinction needed in Phase 3.
**Warning signs:** N/A — both cases correctly trigger the refusal message.

---

## Code Examples

### QMD Query Call (verified pattern from QMDCliBackend)
```python
# Source: src/aurora/kb/qmd_backend.py (established shell-out pattern)
command = (
    "qmd", "--index", self.index_name,
    "query", "--json",
    "-n", str(self.top_k),          # e.g. "7"
    "-c", self.collection_name,      # scope to Aurora's collection
    "--min-score", str(self.min_score),  # e.g. "0.3"
    query,
)
result = subprocess.run(command, check=False, capture_output=True, text=True)
```

### QMD Get Full Document (verified from integration conftest)
```python
# Source: tests/integration/conftest.py collection_get()
command = (
    "qmd", "--index", self.index_name,
    "get", f"{self.collection_name}/{relative_path}",
)
result = subprocess.run(command, check=False, capture_output=True, text=True)
full_content = result.stdout  # complete markdown text
```

### SSE Streaming from llama.cpp
```python
# Source: llama.cpp OpenAI-compatible server SSE format (MEDIUM confidence)
# POST /v1/chat/completions with {"stream": true}
# Response lines: "data: {...}\n\n" and final "data: [DONE]\n\n"
import json
from urllib.request import Request, urlopen

body = json.dumps({"model": model_id, "messages": messages, "stream": True}).encode()
req = Request(
    f"{endpoint_url}/v1/chat/completions",
    data=body,
    headers={"Content-Type": "application/json"},
)
with urlopen(req, timeout=120) as resp:
    for raw in resp:
        line = raw.decode("utf-8").strip()
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            break
        delta = json.loads(payload)["choices"][0]["delta"]
        if token := delta.get("content"):
            print(token, end="", flush=True)
print()  # final newline
```

### Chat History JSONL Format
```python
# Source: design choice — JSONL is line-oriented, append-friendly, human-readable
# Location: get_config_dir() / "chat_history.jsonl" (or per-session file)
import json
from datetime import UTC, datetime

def append_turn(path: Path, role: str, content: str) -> None:
    record = {"role": role, "content": content, "ts": datetime.now(UTC).isoformat()}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records
```

### RuntimeSettings Extensions Needed
```python
# Fields to add to RuntimeSettings in src/aurora/runtime/settings.py
retrieval_top_k: int = 7            # within D-02 range of 5-10
retrieval_min_score: float = 0.30   # Claude's discretion
chat_history_max_turns: int = 10    # context window guard
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual BM25 + vector merge | QMD native hybrid query | QMD built-in | No custom retrieval pipeline needed |
| requests library for HTTP | stdlib urllib | This project convention | No new dependencies; existing LlamaRuntimeClient pattern |
| Chunk-based RAG (send snippets) | Full-document RAG (send whole notes) | D-03 decision | Simpler context assembly, higher token cost per query |

**Deprecated/outdated:**
- Custom embedding search: QMD's `qmd vsearch` + `qmd search` separately then merging — `qmd query` does all of this in one call.

---

## Open Questions

1. **QMD query `--json` exact output schema**
   - What we know: QMD returns JSON with per-hit objects containing `docid`, `file`/`displayPath`, `score`, `snippet`, `title` (from GitHub README and WebFetch, MEDIUM confidence)
   - What's unclear: Exact field names may differ between QMD versions. The `file` field may be the bare filename or the collection-relative path.
   - Recommendation: Wave 0 task — run `qmd --index aurora-kb query --json -n 3 "test"` against the real index and capture exact schema. Add a schema fixture to integration tests.

2. **QMD `query` collection scoping flag**
   - What we know: WebFetch shows `-c`/`--collection` flags. The integration conftest uses `ls` and `get` with collection names.
   - What's unclear: Whether `qmd query -c {name}` is the correct flag or `--collection` or something else.
   - Recommendation: Test against real QMD instance. The integration test environment (`qmd_integration_env`) can be extended to run `qmd query --help` and capture flag names.

3. **Context window size of configured model**
   - What we know: Model is Qwen3-8B-Q8_0 by default. The `MAX_CONTEXT_CHARS` constant needs to be calibrated.
   - What's unclear: Exact context window in tokens (Qwen3-8B likely supports 8K-32K context).
   - Recommendation: Default `MAX_CONTEXT_CHARS = 12_000` (~3K tokens) is conservative and safe. Expose as a discretion constant in `prompts.py` or `settings.py`.

4. **Three pre-existing test failures**
   - What we know: `uv run pytest tests/` shows 3 failures before this phase starts:
     - `tests/cli/test_kb_command.py::test_update_reports_privacy_safe_read_errors_without_forcing_delete`
     - `tests/runtime/test_kb_service.py::test_update_fails_fast_on_manifest_divergence`
     - `tests/runtime/test_kb_service.py::test_adapter_diagnostics_surface_as_service_error`
   - What's unclear: Whether these are pre-existing regressions or known intermittent failures.
   - Recommendation: Wave 0 should note these as pre-existing. New tests for Phase 3 must not be blocked by them. Optionally fix the simplest one (FrozenInstanceError in KB service) as part of Wave 0.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv / Python 3.13 | All tests | Yes | project uses uv | — |
| pytest | Test framework | Yes (via uv run) | >=8.4.2 in pyproject.toml | — |
| qmd CLI | Retrieval calls + integration tests | NOT FOUND | — | Unit tests mock subprocess; integration tests skip when absent |
| llama.cpp server | LLM streaming | NOT VERIFIED (runtime dependency) | — | Unit tests mock urlopen; integration/smoke tests require running server |
| typer CliRunner | CLI unit tests | Yes | >=0.16.0 in pyproject.toml | — |

**Missing dependencies with no fallback:**
- qmd CLI: Required for integration tests and live `aurora ask`/`aurora chat` usage. Unit tests can mock subprocess calls and do not require qmd to be installed.
- llama.cpp server: Required for live inference. All unit tests must mock `urlopen` or the LLMService.

**Missing dependencies with fallback:**
- Both are only needed for integration/smoke tests and live usage. All pure unit tests are decoupled via the same injection pattern used in `QMDCliBackend` (`command_runner` injectable) and `LlamaRuntimeClient` (`request_json` injectable).

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.4.2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/cli/test_ask_command.py tests/cli/test_chat_command.py tests/retrieval/ tests/llm/ -x -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RET-01 | `aurora ask "query"` returns grounded answer | unit | `uv run pytest tests/cli/test_ask_command.py -x` | Wave 0 |
| RET-01 | RetrievalService fetches notes and assembles context | unit | `uv run pytest tests/retrieval/test_retrieval_service.py -x` | Wave 0 |
| RET-01 | LLMService streams response from fake endpoint | unit | `uv run pytest tests/llm/test_llm_service.py -x` | Wave 0 |
| RET-02 | System prompt instructs inline citations; CLI output contains `[path/note.md]` | unit | `uv run pytest tests/cli/test_ask_command.py::test_ask_output_contains_citation -x` | Wave 0 |
| RET-03 | RetrievalService calls `qmd query` with hybrid-search flags | unit | `uv run pytest tests/retrieval/test_retrieval_service.py::test_uses_qmd_query -x` | Wave 0 |
| RET-04 | `aurora ask` returns pt-BR refusal when QMD returns empty hits | unit | `uv run pytest tests/cli/test_ask_command.py::test_insufficient_evidence_refusal -x` | Wave 0 |
| CLI-03 | System prompt mandates pt-BR; grounded response in pt-BR | unit | `uv run pytest tests/llm/test_prompts.py::test_system_prompt_mandates_ptbr -x` | Wave 0 |
| CLI-03 | Intent routing in `aurora chat` sends vault question to retrieval path | unit | `uv run pytest tests/cli/test_chat_command.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/cli/test_ask_command.py tests/retrieval/ tests/llm/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -q` (note: 3 pre-existing failures are expected)
- **Phase gate:** All new Phase 3 tests green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/retrieval/__init__.py` — new test package
- [ ] `tests/retrieval/test_retrieval_service.py` — RET-01, RET-03
- [ ] `tests/llm/__init__.py` — new test package
- [ ] `tests/llm/test_llm_service.py` — RET-01 generation
- [ ] `tests/llm/test_prompts.py` — CLI-03 system prompt content
- [ ] `tests/cli/test_ask_command.py` — RET-01, RET-02, RET-04
- [ ] `tests/cli/test_chat_command.py` — RET-01, CLI-03 intent routing
- [ ] `tests/chat/__init__.py` — new test package (if chat/ module created)
- [ ] `tests/chat/test_history.py` — D-12 chat history persistence

---

## Sources

### Primary (HIGH confidence)
- `src/aurora/kb/qmd_backend.py` — established QMD shell-out pattern, command format, error handling
- `src/aurora/runtime/llama_client.py` — existing urllib-based HTTP client, pattern for extension
- `src/aurora/cli/kb.py` — typer command patterns, `--json` flag, service delegation
- `src/aurora/runtime/settings.py` — RuntimeSettings Pydantic model, how to add new fields
- `tests/integration/conftest.py` — verified `qmd get collection_name/path` format

### Secondary (MEDIUM confidence)
- [GitHub: tobi/qmd](https://github.com/tobi/qmd) — QMD query/get/multi-get syntax, `--json` flag, `--min-score`, `-c` collection scoping, JSON output schema
- WebFetch of qmd README — `-n` top-k flag, `--min-score` threshold, `--collection`/`-c` scoping

### Tertiary (LOW confidence)
- WebSearch on llama.cpp SSE streaming — SSE format (`data: {...}`) and `[DONE]` sentinel are well-established OpenAI-compatible patterns; specific flag behavior may vary by llama.cpp version

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all core libraries already in project; no new dependencies
- Architecture: HIGH — all new modules mirror existing patterns exactly
- QMD query/get interface: MEDIUM — README verified via WebFetch but `--collection` flag name and exact JSON schema need live verification in Wave 0
- Streaming implementation: MEDIUM — OpenAI SSE format is standard, but timeout behavior specific to llama.cpp needs testing
- Pitfalls: HIGH — most derived from direct code inspection of QMDCliBackend and integration tests

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (QMD moves fast; re-verify `qmd query --json` schema before Wave 1)
