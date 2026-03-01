# Stack Research

**Domain:** Local-first, privacy-preserving Obsidian assistant (Markdown KB + long-term memory graph + local OSS LLM serving)
**Researched:** 2026-03-01
**Confidence:** MEDIUM-HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| Obsidian Desktop | 1.12.4 | Source of truth for vault notes and user workflows | This is the current app baseline, so building against it minimizes plugin/API drift risk. | HIGH |
| Python | 3.13.12 | Primary assistant runtime (CLI + orchestration + integrations) | Python remains the best-supported runtime across local LLM, agent, and graph-memory tooling; 3.13 is modern but safer than jumping straight to 3.14 for binary-heavy AI deps. | MEDIUM |
| `uv` | 0.10.7 | Env + dependency + lockfile management | Fast, reproducible, and now the de-facto Python project manager for local AI apps. | HIGH |
| `llama.cpp` | b8184 | Local open-source model serving (GGUF) | Most standard low-level local inference stack in 2026; excellent hardware coverage and OpenAI-compatible serving. | HIGH |
| Agno | 2.5.5 | Agent runtime/tool orchestration for CLI assistant | Clean local-first orchestration with straightforward provider abstraction for local model endpoints. | MEDIUM |
| QMD (`@tobilu/qmd`) | 1.0.7 | Local Markdown ingestion + hybrid retrieval (BM25 + vector + reranking) | Built specifically for local document memory and agent workflows; reduces custom ingestion/search plumbing for vault-first assistants. | MEDIUM |
| Graphiti Core + FalkorDB | 0.28.1 + 4.16.5 | Long-term memory graph with entity/relationship evolution | Graphiti is purpose-built for agent memory graphs and supports lighter local backends; FalkorDB keeps ops simpler than full Neo4j for v1 local deployments. | MEDIUM |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `graphiti-core[falkordb]` | 0.28.1 | Graph memory layer and backend adapter | Use when you need persistent relationship memory across sessions and not just retrieval snippets. |
| `qdrant-client` | 1.17.0 | Optional Python-native vector client | Use only if you outgrow QMD retrieval or need a dedicated vector service boundary. |
| `sentence-transformers` | 5.2.3 | Local embedding generation fallback/customization | Use when you need custom embedding models or reproducible offline embedding pipelines outside QMD defaults. |
| `watchfiles` | 1.1.1 | Incremental vault re-index triggers | Use for background CLI daemon mode that updates index/memory on file changes. |
| `typer` | 0.24.1 | CLI command surface | Use for production-grade CLI UX (subcommands, help, typed options). |
| `rich` | 14.3.3 | Terminal UX and long-task visibility | Use for ingestion/progress/log rendering so local-first workflows stay observable. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Node.js | 24.14.0 LTS (Krypton) | Plugin/build tooling runtime | Use LTS for plugin build scripts and QMD npm workflows. |
| TypeScript | 5.8.3 | Obsidian plugin authoring baseline | Matches current official sample plugin baseline; safest default for API typings/plugins. |
| esbuild | 0.25.5 | Fast plugin bundle builds | Same baseline as official sample plugin; minimizes template divergence. |
| Ruff | 0.15.4 | Lint/format for Python codebase | Fast enough to run on every commit/hook without workflow friction. |
| Pytest | 9.0.2 | CLI/UAT-aligned test runner | Keep tests close to end-user CLI behavior and retrieval/memory invariants. |

## Installation

```bash
# Python runtime and project bootstrap
uv python install 3.13.12
uv venv --python 3.13.12

# Core Python stack
uv add agno==2.5.5 graphiti-core[falkordb]==0.28.1 typer==0.24.1 rich==14.3.3 watchfiles==1.1.1

# Optional vector/embedding extensions
uv add qdrant-client==1.17.0 sentence-transformers==5.2.3

# Markdown ingestion/search engine
npm install -g @tobilu/qmd@1.0.7

# Dev tooling
uv add --dev ruff==0.15.4 pytest==9.0.2 mypy==1.19.1 pre-commit==4.5.1
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `llama.cpp` b8184 | Ollama v0.17.4 | Choose Ollama when operator simplicity (model pull/run UX) is more important than low-level runtime control/tuning. |
| QMD 1.0.7 | Qdrant 1.17.0 + custom Markdown pipeline | Choose custom Qdrant pipeline when you need service-level scaling, explicit schema control, or non-Markdown multimodal ingestion. |
| Graphiti + FalkorDB | Graphiti + Neo4j | Choose Neo4j when you need enterprise-grade graph tooling and mature Cypher operational ecosystem. |
| Agno 2.5.5 | LangGraph (latest) | Choose LangGraph if your roadmap requires explicit durable state-machine graphs and complex human-in-the-loop branching from day one. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Hosted LLM APIs as primary path (OpenAI/Anthropic SaaS) | Violates privacy-first local guarantee; creates data egress and vendor coupling. | `llama.cpp` local GGUF serving (or Ollama local). |
| Hosted vector DB as default (Pinecone/managed SaaS) | Vault content leaves device/network boundary; adds avoidable ops/cost for single-user local-first v1. | QMD local index, or local Qdrant if needed. |
| Heavy indexing/retrieval directly inside Obsidian UI thread | Large-vault ingestion can freeze UX and hurt trust in assistant responsiveness. | Separate local CLI/background service, expose results to plugin/UI. |
| Unpinned `latest` package/model/container tags | Reproducibility and debugging degrade quickly in local AI stacks. | Pin exact tool/package versions and model artifacts per milestone. |

## Stack Patterns by Variant

**If CLI-first single-user (recommended for v1):**
- Use Python (`uv`) + Agno + Graphiti + QMD + `llama.cpp` server.
- Because this keeps architecture simple while preserving strict local/privacy guarantees.

**If plugin-first Obsidian UX (v1.5+):**
- Add a thin Obsidian plugin (TS/esbuild) that talks to the local Aurora service over loopback HTTP.
- Because plugin UX improves discoverability, while heavy ingestion/memory stays outside the Electron UI process.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `graphiti-core@0.28.1` | Neo4j 5.26 / FalkorDB 1.1.2 / Kuzu 0.11.2 | Compatibility stated in Graphiti README; pick FalkorDB for lighter local ops. |
| `qdrant-client@1.17.0` | Qdrant server `v1.17.0` | Keep client/server majors aligned to reduce API mismatch risk. |
| Obsidian `1.12.4` | TypeScript `5.8.3` + esbuild `0.25.5` | Mirrors official sample plugin baseline and current app release. |
| Agno `2.5.5` | Python `>=3.7` (`<4`) | Runtime supports 3.13; keep project pinned to 3.13.x for stability. |

## Sources

- https://github.com/obsidianmd/obsidian-releases/releases/tag/v1.12.4 — current Obsidian app release (HIGH)
- https://raw.githubusercontent.com/obsidianmd/obsidian-sample-plugin/master/package.json — official plugin tooling baseline (HIGH)
- https://www.python.org/downloads/ — current Python release train (3.14.x latest, 3.13.x available) (HIGH)
- https://github.com/astral-sh/uv/releases/tag/0.10.7 — current `uv` release (HIGH)
- https://github.com/ggml-org/llama.cpp/releases/tag/b8184 — current `llama.cpp` release (HIGH)
- https://github.com/agno-agi/agno/releases/tag/v2.5.5 — current Agno release (HIGH)
- https://github.com/getzep/graphiti/releases/tag/v0.28.1 — current Graphiti release (HIGH)
- https://raw.githubusercontent.com/getzep/graphiti/main/README.md — Graphiti backend compatibility matrix (MEDIUM)
- https://github.com/FalkorDB/FalkorDB/releases/tag/v4.16.5 — current FalkorDB release (HIGH)
- https://github.com/tobi/qmd/releases/tag/v1.0.7 — current QMD release (HIGH)
- https://raw.githubusercontent.com/tobi/qmd/main/README.md — QMD local hybrid retrieval architecture and install path (MEDIUM)
- https://github.com/qdrant/qdrant/releases/tag/v1.17.0 — current Qdrant server release (HIGH)
- https://pypi.org/project/qdrant-client/1.17.0/ — current qdrant-client Python version (HIGH)
- https://nodejs.org/dist/index.json — current Node LTS line/version (HIGH)
- https://github.com/ollama/ollama/releases/tag/v0.17.4 — Ollama alternative release (HIGH)

---
*Stack research for: local-first privacy-preserving Obsidian assistant*
*Researched: 2026-03-01*
