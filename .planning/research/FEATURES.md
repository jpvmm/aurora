# Feature Research

**Domain:** Privacy-first local Obsidian knowledge assistant (CLI-first)
**Researched:** 2026-03-01
**Confidence:** MEDIUM-HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Vault ingestion + incremental re-indexing | Competitors already offer index refresh/sync and document watch modes; stale indexes break trust quickly | MEDIUM | Must support `.md` vaults first; include `force reindex`, periodic sync, and selective watch mode for changed notes only |
| Hybrid retrieval baseline (keyword + semantic) | Semantic lookup is now standard in Obsidian AI plugins; keyword-only feels outdated | MEDIUM | Needs chunking strategy, embedding model config, and fallback when embeddings unavailable |
| Grounded Q&A with citations to source note/section | Local assistants are expected to show where answers came from | MEDIUM | Cite file path + heading/block; make “no answer found” explicit |
| Local model support + provider abstraction | Users expect Ollama/llama.cpp/LM Studio style local model options | MEDIUM | Adapter layer required; keep OpenAI-compatible interface for future flexibility |
| Context-aware commands (summarize/rewrite/extract actions) | In-note actions and command palette style workflows are common expectations | LOW-MEDIUM | Start with CLI subcommands and selected-text workflow via stdin/file targets |
| Privacy controls for indexing scope | Users expect include/exclude folders/tags and local-only behavior controls | MEDIUM | Must support deny-by-default paths and explicit allowlists for sensitive folders |
| Operational observability (index progress, logs, resource mode) | Local workflows fail without transparent progress/error visibility | LOW-MEDIUM | Add structured logs, indexing counters, and “low-RAM” mode guidance |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Memory fusion: vault KB + long-term interaction graph retrieval | Aurora can answer with continuity across notes and user history, not just nearest chunks | HIGH | Core differentiator; requires retrieval orchestrator that merges QMD KB and Graphiti memory with scoring policy |
| Privacy guarantee mode (“no egress”) | Strong trust signal: enforceable local-only execution, not just marketing language | MEDIUM-HIGH | Add startup checks + runtime guardrails (blocked network tool paths, redacted logs) |
| PT-BR first-class assistant behavior | Better UX for target users vs generic English-biased defaults | LOW-MEDIUM | System prompts, command outputs, and templates default to pt-BR with explicit override |
| CLI-first automation workflows | Fits power-user Obsidian audience and scripting habits better than heavy UI | MEDIUM | Global CLI install, batch commands, and machine-readable outputs (`json`) |
| Memory governance controls (pin/forget/decay) | Turns long-term memory into controllable feature instead of unpredictable drift | HIGH | Needs memory metadata, user controls, and retrieval-time weighting/expiry |
| “Thinking partner” workflows (idea synthesis from vault themes) | Moves from Q&A tool to creative copilot grounded in user corpus | HIGH | Depends on robust retrieval + memory quality; should be opt-in and transparent |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Cloud fallback when local model is slow | “Always get an answer” convenience | Violates privacy-first promise and creates hidden data egress risk | Explicit “offline strict” default + optional user-enabled external profile (off by default) |
| Auto-editing notes without confirmation | Feels magical/productive | High risk of silent corruption of knowledge base | Preview + diff + explicit apply step |
| Full-vault real-time re-embedding on every file event | Sounds “always up to date” | Expensive, fragile, and can corrupt or thrash local indexes | Incremental queue with debounce, batch windows, and manual `rebuild` |
| Multi-user RBAC/tenant features in v1 | Looks enterprise-ready | Scope explosion away from single-user validated use case | Keep v1 single-user; revisit after PMF |
| Broad multimodal ingestion (audio/video/OCR) in v1 | Feature checklist pressure | Adds heavy deps and instability before core Markdown flow is reliable | Markdown-first + PDF optional later |
| Autonomous background agents that mutate vault continuously | Promise of “hands-free” organization | High trust/safety risk and hard-to-debug behavior | User-invoked workflows with dry-run summaries |

## Feature Dependencies

```
[Vault ingestion]
    └──requires──> [Chunking + metadata extraction]
                       └──requires──> [Embedding pipeline]

[Grounded Q&A with citations]
    └──requires──> [Hybrid retrieval baseline]
                       └──requires──> [Vault ingestion + indexing]

[Memory fusion retrieval]
    ├──requires──> [Graphiti memory store]
    ├──requires──> [Hybrid retrieval baseline]
    └──requires──> [Retrieval orchestration + ranking policy]

[Thinking partner workflows]
    └──enhances──> [Memory fusion retrieval]

[Privacy guarantee mode]
    └──conflicts──> [Cloud fallback default path]

[CLI automation workflows]
    └──requires──> [Stable command surface + machine-readable outputs]
```

### Dependency Notes

- **Grounded Q&A requires hybrid retrieval baseline:** without retrieval quality, citations become low-value or misleading.
- **Memory fusion requires Graphiti + retrieval orchestrator:** memory must be queryable and rankable alongside vault chunks.
- **Thinking partner workflows enhance memory fusion:** synthesis quality depends directly on memory and retrieval precision.
- **Privacy guarantee mode conflicts with cloud fallback defaults:** strict local guarantees are incompatible with silent external provider failover.
- **CLI automation requires stable command contracts:** scripts depend on predictable output shape and exit codes.

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to validate the concept.

- [ ] Vault ingestion + incremental indexing for Obsidian Markdown vaults
- [ ] Hybrid retrieval baseline (keyword + semantic) with citation-backed answers
- [ ] Local model execution path (llama.cpp/Ollama-compatible) with clear config
- [ ] CLI-first chat and note-action commands in pt-BR by default
- [ ] Privacy controls (include/exclude paths, no-cloud default) and observability logs

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] Memory fusion retrieval (KB + Graphiti interaction memory) once baseline answer quality is stable
- [ ] Memory governance controls (pin/forget/decay) once users report memory drift pain
- [ ] PDF ingestion and richer context selectors after Markdown flow performance is solid

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] Desktop GUI for non-CLI users after CLI adoption plateaus
- [ ] Multi-user/tenant mode if team scenarios become a validated demand
- [ ] Advanced autonomous agents only with strong trust/safety controls and auditability

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Vault ingestion + incremental indexing | HIGH | MEDIUM | P1 |
| Hybrid retrieval + citations | HIGH | MEDIUM | P1 |
| Local model adapter layer | HIGH | MEDIUM | P1 |
| CLI-first workflows (pt-BR default) | HIGH | MEDIUM | P1 |
| Privacy controls + no-cloud default | HIGH | MEDIUM | P1 |
| Memory fusion retrieval | HIGH | HIGH | P2 |
| Memory governance controls | MEDIUM-HIGH | HIGH | P2 |
| Thinking partner synthesis workflows | MEDIUM-HIGH | HIGH | P2 |
| PDF and broader file ingestion | MEDIUM | MEDIUM | P2 |
| Desktop GUI | MEDIUM | HIGH | P3 |
| Multi-user RBAC | LOW-MEDIUM (current audience) | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Competitor A (Copilot for Obsidian) | Competitor B (Smart Connections / Khoj) | Aurora Approach |
|---------|--------------------------------------|------------------------------------------|-----------------|
| Vault Q&A + indexing controls | Vault QA with indexing strategy and exclusions | Semantic lookup/similar notes + periodic sync patterns | Ship robust Markdown-first indexing + explicit freshness controls |
| Local model compatibility | Supports custom/local models (Ollama/LM Studio paths) | Local-first embeddings and on-device retrieval emphasized | Default local model path; cloud disabled by default |
| Semantic retrieval UX | Relevant notes and embedding configuration | Real-time related notes + semantic search by meaning | CLI semantic retrieval with citation fidelity and deterministic behavior |
| Memory over time | Conversation settings and saved chats | Focus mostly on retrieval/similarity | Differentiate with Graphiti long-term memory fused with vault KB |
| Privacy posture | Mixed local + cloud provider ecosystem | Local-first messaging; some products include telemetry or paid/cloud tiers | Enforceable no-egress mode and explicit privacy controls as product principle |

## Sources

- https://docs.khoj.dev/clients/obsidian/
- https://www.obsidiancopilot.com/en/docs/settings
- https://www.obsidiancopilot.com/en/pricing
- https://smartconnections.app/smart-connections/
- https://github.com/pfrankov/obsidian-local-gpt
- https://docs.privategpt.dev/manual/document-management/ingestion
- https://docs.privategpt.dev/manual/user-interface/gradio-manual
- https://docs.anythingllm.com/features/all-features
- https://docs.anythingllm.com/features/privacy-and-data-handling
- https://docs.anythingllm.com/features/security-and-access
- https://docs.anythingllm.com/beta-preview/active-features/live-document-sync

---
*Feature research for: privacy-first local Obsidian assistant*
*Researched: 2026-03-01*
