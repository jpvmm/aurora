# Project Research Summary

**Project:** Aurora
**Domain:** Local-first, privacy-preserving Obsidian assistant (CLI-first, single-user)
**Researched:** 2026-03-01
**Confidence:** MEDIUM-HIGH

## Executive Summary

Aurora is a local knowledge assistant for Obsidian that must combine three capabilities in one cohesive workflow: reliable Markdown vault ingestion, high-quality grounded retrieval, and long-term memory that evolves across interactions. Research across stack, features, architecture, and pitfalls converges on a CLI-first product built around Python (`uv`), QMD for hybrid KB retrieval, Graphiti for memory graphing, Agno for orchestration, and `llama.cpp` for local model serving. The recommended expert pattern is to isolate third-party tooling behind adapters and build deterministic pipelines with explicit state/checkpoints.

The strongest recommendation is to launch with a strict privacy baseline and a retrieval-first MVP before introducing advanced memory behavior. Concretely: ship P1 table-stakes first (incremental ingestion, hybrid retrieval with citations, local model path, pt-BR CLI defaults, privacy controls), then layer memory fusion and governance after retrieval quality is stable. This sequencing reduces confounding variables and gives the fastest path to trustworthy user value.

The highest risks are silent cloud egress, stale or malformed knowledge state (embed drift + parsing errors), and memory quality failures (structured output breakage, session contamination, context-budget collapse). Mitigation requires hard runtime guardrails, conformance fixtures for Obsidian syntax, deterministic ingestion freshness signals, identity isolation at memory boundaries, and end-to-end privacy verification gates before release.

## Key Findings

### Recommended Stack

The research supports a pragmatic local stack with pinned versions and explicit compatibility controls. The stack is strong for v1 because each layer is mature enough independently and can be composed with clean boundaries in a CLI architecture.

**Core technologies:**
- Obsidian Desktop `1.12.4`: source-of-truth note environment — minimizes API/workflow drift for the target user base.
- Python `3.13.12` + `uv` `0.10.7`: runtime and dependency control — best local AI tooling support with reproducible environments.
- `llama.cpp` `b8184`: local LLM serving — OpenAI-compatible local endpoints with broad hardware support.
- Agno `2.5.5`: agent orchestration — clean tool-routing and policy layer for local-first assistants.
- QMD `1.0.7`: Markdown ingestion + hybrid retrieval — reduces custom indexing/search plumbing.
- Graphiti Core `0.28.1` + FalkorDB `4.16.5`: persistent relationship memory — practical local graph-memory baseline for v1.

### Expected Features

The feature research is clear: Aurora must be excellent at local retrieval trustworthiness before adding autonomous or broad-scope capabilities.

**Must have (table stakes):**
- Vault ingestion with incremental re-indexing and selective watch.
- Hybrid retrieval (keyword + semantic) with citation-backed answers.
- Local model provider abstraction (llama.cpp/Ollama-compatible path).
- CLI-first command surface with pt-BR default behavior.
- Privacy controls (include/exclude scope, no-cloud default) and observability.

**Should have (competitive):**
- Memory fusion retrieval (KB + long-term graph memory).
- Privacy guarantee mode with enforceable no-egress checks.
- Memory governance controls (`pin`/`forget`/`decay`).
- Thinking-partner synthesis workflows grounded in vault evidence.

**Defer (v2+):**
- Desktop GUI for non-CLI users.
- Multi-user/RBAC/tenant scope.
- Broad autonomous background vault mutation.

### Architecture Approach

The architecture should follow ports-and-adapters with a two-phase retrieval pipeline (KB + memory retrieval, then composition/rerank) and an offline-first ingestion job model with checkpoints. This directly maps to Aurora's reliability and privacy requirements.

**Major components:**
1. CLI/Application layer (`ingest`, `ask`, maintenance) — user entrypoint and operator UX.
2. Orchestrator/domain services — ingestion, query, and memory use-cases with policy enforcement.
3. Adapter layer (Obsidian, QMD, Graphiti, Agno, llama.cpp) — isolates vendor/tool drift.
4. Core logic (ranking, privacy/language policy, contracts) — deterministic testable behavior.
5. State/observability (manifests, jobs, logs) — resumability, diagnostics, and trust.

### Critical Pitfalls

1. **Silent cloud egress in “local-only” mode** — enforce strict-local startup checks and block cloud-keyed runtime profiles.
2. **Embed/index drift causing stale answers** — implement deterministic incremental embed pipeline with freshness metrics.
3. **Obsidian markdown misparse** — ship parser conformance fixtures for wikilinks, properties, refs, and encoded links.
4. **Graph memory ingestion failures on weaker local models** — add schema validation, retries, and dead-letter handling.
5. **Memory contamination/context collapse** — enforce `vault_id`/`user_id`/`session_id` isolation and hard token-budget assembly.

## Implications for Roadmap

Based on combined research, the roadmap should be structured as seven phases with strict dependency order:

### Phase 1: Privacy Baseline & Runtime Contracts
**Rationale:** Privacy guarantees are the product promise and must be enforced before feature depth.
**Delivers:** Local-only provider contract, startup guardrails, config schema, model endpoint health checks, baseline CLI status diagnostics.
**Addresses:** Local model path, privacy controls, observability table-stakes.
**Avoids:** Silent cloud egress, early privacy regressions.

### Phase 2: Vault Ingestion & Obsidian Parsing Foundation
**Rationale:** Retrieval quality depends on correct canonical document representation.
**Delivers:** Vault scanner, manifest/hash state, incremental ingest queue, Obsidian parser fixtures and conformance tests.
**Addresses:** Ingestion/re-indexing table-stakes.
**Avoids:** Parsing mismatch, broken links/metadata, initial embed drift.

### Phase 3: Retrieval + Citation MVP (KB-Only)
**Rationale:** Validate trustable answers quickly with minimal moving parts.
**Delivers:** Hybrid QMD retrieval, citation formatting, pt-BR `ask` flow, deterministic output contracts.
**Uses:** QMD + Agno + llama.cpp baseline stack.
**Implements:** Query pipeline + retrieval policy boundaries.
**Avoids:** Premature memory complexity masking core retrieval defects.

### Phase 4: Graph Memory Integration & Fusion Composer
**Rationale:** Differentiation starts once baseline retrieval works and can be measured.
**Delivers:** Graphiti episode write/read, KB+memory fusion composer, relevance/ranking policy tuning.
**Addresses:** Memory fusion differentiator.
**Avoids:** Structured-output ingestion breakage and malformed memory graph state.

### Phase 5: Memory Governance & Identity Isolation
**Rationale:** Long-term memory without controls creates trust and privacy failures.
**Delivers:** Namespace enforcement (`vault_id`, `user_id`, `session_id`), `pin/forget/decay`, cross-session contamination tests.
**Addresses:** Memory governance differentiator.
**Avoids:** Memory bleed across sessions and uncontrolled context growth.

### Phase 6: Performance & Capacity Profiles
**Rationale:** Local-first adoption depends on predictable latency on commodity hardware.
**Delivers:** `llama.cpp` hardware presets (light/balanced/quality), concurrency/context limits, token-budget enforcement, benchmark suite.
**Addresses:** Operational reliability and user trust for daily CLI usage.
**Avoids:** OOM/stalls, context-budget collapse, throughput cliffs.

### Phase 7: Hardening, Privacy Verification & Packaging
**Rationale:** Release quality requires whole-system verification, not subsystem confidence.
**Delivers:** End-to-end no-egress tests (including packet-capture checks), log redaction audits, regression datasets, install/release packaging (`uv`/`pipx`) and `aurora doctor` checks.
**Addresses:** Production readiness and safe distribution.
**Avoids:** “Looks done but isn’t” release failures.

### Phase Ordering Rationale

- Privacy/runtime contracts must precede all integrations to prevent architecture rework and guarantee product truth.
- Ingestion/parsing precedes retrieval, and retrieval precedes memory fusion, because each layer depends on quality and observability of the previous one.
- Governance and performance are intentionally separated from initial memory integration to keep risk isolation clear and debugging tractable.
- Final hardening is a gated release phase that validates cross-component behavior, especially privacy and safety claims.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (Graph Memory Integration):** High integration risk with structured-output constraints on local models and Graphiti behavior.
- **Phase 6 (Performance & Capacity):** Hardware-sensitive `llama.cpp` tuning requires target-device benchmark evidence.
- **Phase 7 (Hardening):** Privacy verification methodology (offline + traffic capture + redaction audits) should be codified early.

Phases with standard patterns (can usually skip `/gsd:research-phase`):
- **Phase 1:** Well-established local runtime contracts and guardrail patterns.
- **Phase 2:** Deterministic ingestion/checkpoint patterns are well documented.
- **Phase 3:** Hybrid retrieval + citations is a common, mature pattern.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versions and compatibility are mostly anchored in official release/docs sources with strong alignment to local-first requirements. |
| Features | MEDIUM-HIGH | Table-stakes and differentiators are well-supported by competitor/docs research, but some differentiation hypotheses still require user validation. |
| Architecture | MEDIUM-HIGH | Patterns are robust and standard for agentic local systems, but production behavior depends on implementation rigor and adapter quality. |
| Pitfalls | MEDIUM | Risks are credible and domain-specific, but some mitigation details are inference-heavy and need empirical validation in Aurora benchmarks. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Local-model capability for Graphiti structured extraction:** Validate with Portuguese and Obsidian-style real samples before locking Phase 4 acceptance criteria.
- **Obsidian edge-syntax coverage quality bar:** Define and freeze a representative fixture corpus in planning, not during implementation.
- **Hardware baseline for performance presets:** Establish explicit target device classes and latency/token SLOs prior to Phase 6 execution.
- **Backend choice durability (FalkorDB vs Neo4j path):** Document migration strategy to avoid lock-in if v1 memory scale assumptions fail.

## Sources

### Primary (HIGH confidence)
- https://github.com/obsidianmd/obsidian-releases/releases/tag/v1.12.4 — Obsidian baseline version.
- https://raw.githubusercontent.com/obsidianmd/obsidian-sample-plugin/master/package.json — official plugin toolchain baseline.
- https://github.com/astral-sh/uv/releases/tag/0.10.7 — `uv` version and release details.
- https://github.com/ggml-org/llama.cpp/releases/tag/b8184 — local inference runtime version.
- https://github.com/agno-agi/agno/releases/tag/v2.5.5 — agent framework release baseline.
- https://github.com/getzep/graphiti/releases/tag/v0.28.1 — memory framework release baseline.
- https://github.com/FalkorDB/FalkorDB/releases/tag/v4.16.5 — graph backend version.
- https://github.com/tobi/qmd/releases/tag/v1.0.7 — markdown retrieval engine version.
- https://github.com/qdrant/qdrant/releases/tag/v1.17.0 — vector DB alternative baseline.
- https://help.obsidian.md/data-storage — vault local-file architecture.
- https://help.getzep.com/graphiti/getting-started/quick-start — Graphiti model and flow details.
- https://docs.agno.com/agents/overview — agent orchestration and memory patterns.

### Secondary (MEDIUM confidence)
- https://docs.khoj.dev/clients/obsidian/ — competitor UX/feature expectations.
- https://www.obsidiancopilot.com/en/docs/settings — competitor configuration expectations.
- https://smartconnections.app/smart-connections/ — semantic retrieval baseline expectations.
- https://docs.privategpt.dev/manual/document-management/ingestion — local ingestion UX patterns.
- https://docs.anythingllm.com/features/privacy-and-data-handling — privacy/UX framing patterns.

### Tertiary (LOW confidence)
- None identified as primary decision drivers in current synthesis.

---
*Research completed: 2026-03-01*
*Ready for roadmap: yes*
