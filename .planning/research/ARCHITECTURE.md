# Architecture Research

**Domain:** Privacy-first local Obsidian assistant (CLI-first)
**Researched:** 2026-03-01
**Confidence:** MEDIUM-HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLI / Application Layer                           │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │ aurora ingest   │  │ aurora ask      │  │ aurora memory / maintenance │ │
│  └────────┬────────┘  └────────┬────────┘  └──────────────┬──────────────┘ │
│           │                    │                          │                │
├───────────┴────────────────────┴──────────────────────────┴────────────────┤
│                     Orchestration / Domain Services Layer                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Agent Runtime (Agno)                                                  │  │
│  │ - Tool router: KB search, graph memory search, vault ops             │  │
│  │ - Retrieval composer: merge + rerank KB + memory                     │  │
│  │ - Policy: privacy, language default (pt-BR), token/context budgets   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────────┤
│                              Data / Model Layer                             │
│  ┌────────────────────────┐ ┌───────────────────────┐ ┌──────────────────┐ │
│  │ Obsidian Vault (.md)   │ │ Vector KB (QMD index) │ │ Graph Memory DB  │ │
│  │ + .obsidian metadata   │ │ + embeddings/cache    │ │ (Graphiti backend│ │
│  │                        │ │                       │ │  Neo4j/FalkorDB) │ │
│  └───────────┬────────────┘ └───────────┬───────────┘ └────────┬─────────┘ │
│              │                          │                       │           │
│              └──────────────────────────┴──────────────┬────────┘           │
│                                                        │                    │
│                                    ┌───────────────────┴─────────────────┐  │
│                                    │ Local Model Serving (llama.cpp)     │  │
│                                    │ - chat model                          │  │
│                                    │ - embedding/rerank model endpoints    │  │
│                                    └───────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| CLI commands | User entrypoint for ingest/query/admin workflows | `typer` CLI with subcommands (`ingest`, `ask`, `status`, `reindex`) |
| Vault scanner | Discover markdown notes + metadata changes | Filesystem traversal + hash/mtime manifest |
| KB ingestion adapter | Feed vault docs into QMD collections and update index | Shell invocation/wrapper around `qmd collection add`, `qmd update`, `qmd embed` |
| KB retrieval adapter | Execute keyword/vector/hybrid searches from assistant | `qmd search`, `qmd vsearch`, `qmd query` (`--json`) |
| Graph memory adapter | Write and retrieve conversational episodes/facts | Graphiti client with `add_episode` + search APIs |
| Retrieval composer | Merge KB results + graph memory into final context window | Score normalization + source-aware packing |
| Agent runtime | Tool-use loop, prompting policy, response generation | Agno `Agent` with tools + memory/storage hooks |
| Model gateway | Local inference for generation/embeddings/reranking | `llama-server` (OpenAI-compatible) on localhost |
| Persistence/control | Config, manifests, logs, queues, retry states | Local SQLite + JSONL logs + lock files |

## Recommended Project Structure

```text
src/
├── aurora/
│   ├── cli/                     # Typer command surface (ingest/ask/admin)
│   │   ├── app.py               # CLI root
│   │   ├── ingest.py            # Ingestion commands
│   │   ├── ask.py               # Query commands
│   │   └── maintenance.py       # Reindex/status/health
│   ├── orchestrator/            # Application services and use-cases
│   │   ├── ingest_pipeline.py   # Vault -> KB sync
│   │   ├── query_pipeline.py    # Query -> retrieval -> answer
│   │   └── memory_pipeline.py   # Conversation -> graph memory updates
│   ├── adapters/                # Infrastructure boundaries
│   │   ├── obsidian/            # Vault reader + frontmatter/link parsing
│   │   ├── qmd/                 # QMD CLI/MCP integration layer
│   │   ├── graphiti/            # Graphiti integration layer
│   │   ├── agno/                # Agent model/tool wiring
│   │   └── llama_cpp/           # Model endpoint client + health checks
│   ├── core/                    # Pure domain logic
│   │   ├── ranking.py           # Result fusion/rerank
│   │   ├── policies.py          # Privacy/language/guardrails
│   │   └── contracts.py         # DTOs/interfaces
│   ├── state/                   # Local state and metadata
│   │   ├── manifests.py         # File fingerprint state
│   │   ├── jobs.py              # Ingestion/query job records
│   │   └── settings.py          # Local config model
│   └── observability/           # Structured logging/metrics
│       ├── logs.py
│       └── tracing.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── pyproject.toml
```

### Structure Rationale

- **`core/`:** keeps retrieval fusion and policy logic testable and independent from vendor/framework APIs.
- **`adapters/`:** isolates external tool drift (QMD/Graphiti/Agno/llama.cpp changes) from business logic.
- **`orchestrator/`:** explicit use-cases map directly to CLI commands and phase milestones.
- **`state/`:** centralizes all local persistence required for resumable ingestion and deterministic retries.

## Architectural Patterns

### Pattern 1: Ports and Adapters for Tooling

**What:** Define stable internal interfaces (`VectorKB`, `GraphMemory`, `ModelClient`) and keep QMD/Graphiti/llama.cpp behind adapters.
**When to use:** Always, because upstream tooling evolves quickly.
**Trade-offs:** Slight upfront complexity, large payoff in maintainability and testability.

**Example:**
```python
class VectorKB(Protocol):
    def hybrid_search(self, query: str, limit: int) -> list[KBHit]: ...

class QmdVectorKB(VectorKB):
    def hybrid_search(self, query: str, limit: int) -> list[KBHit]:
        # wraps: qmd query --json -n <limit> "<query>"
        ...
```

### Pattern 2: Two-Phase Retrieval (KB + Memory, then Compose)

**What:** Retrieve from vector KB and graph memory independently, then merge/rerank in one composition step.
**When to use:** Multi-source context systems where each source has distinct relevance signals.
**Trade-offs:** More scoring logic, better explainability and recall.

**Example:**
```python
kb_hits = vector_kb.hybrid_search(user_query, limit=12)
mem_hits = graph_memory.search(user_query, limit=8)
context = retrieval_composer.compose(kb_hits=kb_hits, mem_hits=mem_hits, token_budget=6000)
```

### Pattern 3: Offline-First Job Pipeline for Ingestion

**What:** Treat ingestion as resumable jobs with checkpoints and idempotent operations.
**When to use:** Vaults with many files and long-running indexing/embedding tasks.
**Trade-offs:** Requires job state bookkeeping; drastically improves reliability.

## Data Flow

### Request Flow

```text
[aurora ask "<question>"]
    ↓
[CLI handler]
    ↓
[Query Pipeline]
    ↓
[Parallel retrieval]
  ├─> [QMD query/search (KB hits)]
  └─> [Graphiti search (memory/facts)]
    ↓
[Retrieval composer + source attribution]
    ↓
[Agno Agent + llama.cpp model]
    ↓
[Response in pt-BR + cited vault paths/episodes]
    ↓
[Graphiti add_episode (interaction write-back)]
```

### State Management

```text
[Vault files]
    ↓ scan
[Manifest store: hash/mtime/docid map]
    ↓ delta
[Ingest job queue]
    ↓ execute
[QMD index + embedding state]
    ↓
[Query-time retrieval]
```

### Key Data Flows

1. **Vault Ingestion Flow:** Vault scanner reads `.md` files, updates changed-file manifest, calls QMD collection/index/embedding commands, and records ingest checkpoints.
2. **Query Retrieval Flow:** User query triggers KB hybrid search and graph memory search in parallel; composer deduplicates and ranks context slices.
3. **Memory Consolidation Flow:** Final Q/A interaction is stored as Graphiti episode (`text`/`message`) so future searches include temporal conversational memory.
4. **Recovery Flow:** Interrupted ingest resumes from checkpoint manifest and pending job records, avoiding full reindex unless explicitly requested.

## Suggested Build Order

1. **Foundation and local runtime contracts**
   - Define interfaces, config schema, logging, and `llama.cpp` health checks.
   - Implication: prevents later lock-in to direct framework calls across codebase.
2. **Vault ingestion + vector KB (QMD)**
   - Deliver `aurora ingest`, manifest tracking, and deterministic re-index behavior.
   - Implication: creates the first useful vertical slice and baseline retrieval metrics.
3. **Read-only assistant query path (Agno + QMD)**
   - Deliver `aurora ask` using KB-only retrieval and local model inference.
   - Implication: validates CLI UX, prompt policy, and local hardware assumptions early.
4. **Graph memory integration (Graphiti)**
   - Add episode write-back + memory retrieval, then hybrid composer tuning.
   - Implication: memory relevance tuning happens with working KB baseline, reducing confounding variables.
5. **Operational hardening**
   - Add retries, lock handling, telemetry-off defaults, e2e tests, and packaging (`uv/pipx` global CLI).
   - Implication: avoids premature optimization while ensuring reproducible local installs.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1 user, 1 vault (target v1) | Single-process CLI + local `llama-server`, batch ingestion jobs, SQLite manifests |
| Power user, large vaults | Split ingestion worker process from interactive query path; add backpressure and chunked job scheduling |
| Multi-vault / multi-user (future) | Namespaced storage (`vault_id`, `user_id`), isolated graph groups, optional service mode with auth |

### Scaling Priorities

1. **First bottleneck:** embedding/index throughput on large vault updates; fix via incremental ingest and bounded worker concurrency.
2. **Second bottleneck:** query latency from multi-source retrieval + local inference; fix via caching, smaller quantized model tiers, and tighter context packing.

## Anti-Patterns

### Anti-Pattern 1: Tight Coupling to Framework APIs

**What people do:** Call Agno/Graphiti/QMD commands directly from CLI handlers.
**Why it's wrong:** Makes upgrades and testing brittle; behavior spreads across layers.
**Do this instead:** Keep framework/tool calls only inside `adapters/`, expose stable internal contracts.

### Anti-Pattern 2: Full Reindex on Every Ingest

**What people do:** Rebuild everything for any vault change.
**Why it's wrong:** Slow UX, wasted compute, poor laptop battery/thermals.
**Do this instead:** Delta ingest with manifest-based change detection and targeted `qmd update`/embed runs.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Obsidian vault filesystem | Local file reads only | Vault is plain Markdown files in local folder; respect `.obsidian` metadata boundaries |
| QMD CLI/MCP | Subprocess (primary) or MCP HTTP | Use `--json` outputs for deterministic parsing; keep command wrapper centralized |
| Graphiti | Python SDK to local graph backend | Default docs use OpenAI+Neo4j; for privacy-first, configure local-compatible providers/backends before production |
| llama.cpp | OpenAI-compatible local HTTP | Keep localhost-only binding and explicit model profile presets per hardware tier |
| Agno | In-process Python framework | Compose tools/adapters; avoid AgentOS cloud dependencies for v1 |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| CLI ↔ Orchestrator | typed function calls | No direct vendor/tool calls from CLI layer |
| Orchestrator ↔ Adapters | interface contracts | Enables adapter fakes for integration tests |
| Query Pipeline ↔ Retrieval Composer | DTOs with normalized scores | Keep ranking policy deterministic and testable |
| Orchestrator ↔ State Store | repository interface | Abstract SQLite/JSON storage for future migration |

## Quality Gate Check

- [x] Components clearly defined
- [x] Data flow explicit
- [x] Build order implications noted

## Sources

- Obsidian Help: Data storage (vault as local Markdown/plain text): https://help.obsidian.md/data-storage
- QMD official repository/README (hybrid retrieval, index/update/embed, JSON outputs): https://github.com/tobi/qmd
- Agno docs: Agents overview (stateful control loop, memory/knowledge/storage): https://docs.agno.com/agents/overview
- Agno docs: Knowledge base architecture/layers: https://docs.agno.com/knowledge/knowledge-bases
- Agno docs: LlamaCpp provider (local models, OpenAI-compatible server usage): https://docs.agno.com/models/providers/local/llama-cpp/overview
- llama.cpp official repository (`llama-server`, OpenAI-compatible HTTP server): https://github.com/ggml-org/llama.cpp
- Graphiti docs: Quick start (episode model, hybrid search, index setup): https://help.getzep.com/graphiti/getting-started/quick-start
- Graphiti docs: Adding episodes (`text`/`message`/`json`, temporal provenance): https://help.getzep.com/graphiti/core-concepts/adding-episodes
- Graphiti repository (graph DB options and deployment notes): https://github.com/getzep/graphiti

---
*Architecture research for: Privacy-first local Obsidian assistant (Aurora)*
*Researched: 2026-03-01*
