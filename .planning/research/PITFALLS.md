# Pitfalls Research

**Domain:** Privacy-first local Obsidian assistant (QMD + Graphiti + Agno + llama.cpp)
**Researched:** 2026-03-01
**Confidence:** MEDIUM

## Critical Pitfalls

### Pitfall 1: "Local-Only" That Secretly Calls Cloud APIs

**What goes wrong:**
Aurora is presented as local/private, but one or more components silently use cloud providers for inference or embeddings.

**Why it happens:**
Graphiti and many Agno examples default to OpenAI-compatible providers unless explicitly reconfigured.

**How to avoid:**
Create a hard privacy contract in Phase 1: explicit local model/embedding endpoints for every component, block outbound network by default for runtime containers, and add startup checks that fail if cloud API keys are detected in production mode.

**Warning signs:**
- `OPENAI_API_KEY` (or similar cloud keys) appears in runtime env.
- Graphiti/Agno boot logs reference hosted providers.
- Network traces show outbound calls during indexing/chat.

**Phase to address:**
Phase 1 (Privacy Baseline & Runtime Contracts)

---

### Pitfall 2: Graphiti Ingestion Breaks with Local Models

**What goes wrong:**
Graph memory ingestion fails or creates malformed edges/facts, causing unreliable long-term memory.

**Why it happens:**
Graphiti states it works best with providers that support structured output; weaker/smaller local models can fail schema constraints.

**How to avoid:**
Define a strict ingestion boundary in Phase 4: schema validation before write, retry + fallback extraction path, dead-letter queue for failed episodes, and acceptance tests on representative Portuguese/Obsidian notes.

**Warning signs:**
- Frequent ingestion exceptions about schema/output parsing.
- Sudden drop in created entities/edges.
- Memory recalls returning contradictory or empty graph facts.

**Phase to address:**
Phase 4 (Graph Memory Integration)

---

### Pitfall 3: Stale Vector Knowledge Due to Embed Drift

**What goes wrong:**
Vault edits are visible in files but not reflected in semantic retrieval; answers lag behind actual notes.

**Why it happens:**
QMD flow requires explicit embedding generation (`qmd embed`). If re-embed/update flow is not automated, vector index drifts from vault state.

**How to avoid:**
In Phase 2-3, implement deterministic ingestion state: changed-file detection, incremental embed jobs, and index freshness markers surfaced in CLI (`last indexed`, `pending files`).

**Warning signs:**
- BM25 results find new content but vector/hybrid misses it.
- Users report "I updated the note but assistant still answers old version".
- Growing queue of unembedded files.

**Phase to address:**
Phase 2 (Vault Ingestion) and Phase 3 (Retrieval Quality)

---

### Pitfall 4: Obsidian-Specific Markdown Parsed as Generic Markdown

**What goes wrong:**
Links, headings, properties, embeds, and block references are misparsed, breaking retrieval and graph relations.

**Why it happens:**
Obsidian supports wikilinks, encoded markdown links, frontmatter properties, and special link constraints; generic markdown parsers lose semantics.

**How to avoid:**
In Phase 2, create canonical Obsidian fixtures and parser conformance tests for wikilinks (`[[...]]`), heading/block refs, YAML properties, and URL-encoded markdown links.

**Warning signs:**
- Broken link resolution after file rename/move.
- Duplicate entities from alias/path mismatch.
- Missing metadata-derived filters/tags in retrieval.

**Phase to address:**
Phase 2 (Vault Ingestion & Parsing)

---

### Pitfall 5: Memory Contamination Across Users/Sessions

**What goes wrong:**
Memories from one conversation/user bleed into another and pollute responses.

**Why it happens:**
Agno memory sharing depends on shared DB + `user_id`; weak namespace rules cause accidental cross-session reuse.

**How to avoid:**
In Phase 5, define immutable identity scheme (`vault_id`, `user_id`, `session_id`) and enforce it at every memory write/read boundary, with tests that attempt cross-session retrieval.

**Warning signs:**
- Assistant recalls details from unrelated chats.
- Same memory rows reused across different vaults.
- Manual DB inspection shows non-namespaced memory records.

**Phase to address:**
Phase 5 (Agent Orchestration & Memory Policy)

---

### Pitfall 6: Context Budget Collapse (KB + Graph + Chat History)

**What goes wrong:**
Latency and token usage spike; important evidence is truncated; answers degrade under long conversations.

**Why it happens:**
Agno can auto-include memories in context, and memory growth increases token cost over time. Combined with long retrieved note chunks, prompt size explodes.

**How to avoid:**
In Phase 5-6, set strict budget controls: cap retrieved chunks, use `add_memories_to_context=False` where appropriate, schedule memory optimization, and enforce a final context assembler with hard token ceilings.

**Warning signs:**
- Response latency drifts upward with conversation age.
- Frequent truncation/omitted context logs.
- Rising token counts despite stable query complexity.

**Phase to address:**
Phase 5 (Context Assembly) and Phase 6 (Performance Tuning)

---

### Pitfall 7: llama.cpp Capacity Misconfiguration

**What goes wrong:**
System appears stable in light tests, then fails in real usage with OOMs, long stalls, or low-quality outputs.

**Why it happens:**
`llama.cpp` behavior depends on model GGUF format, context sizing, and concurrency (`-c` and `-np`). Wrong presets can unintentionally reduce per-request context or exceed hardware limits.

**How to avoid:**
In Phase 6, benchmark hardware profiles and ship tested presets (light/balanced/quality), plus runtime admission control (reject settings that exceed validated memory envelope).

**Warning signs:**
- Runtime logs show unexpected low effective context per sequence.
- Large-context prompts fail while short prompts pass.
- Throughput drops sharply under concurrent CLI requests.

**Phase to address:**
Phase 6 (Inference Performance & Capacity)

---

### Pitfall 8: Missing End-to-End Privacy Verification

**What goes wrong:**
Each subsystem looks local in isolation, but integrated flows leak sensitive note content via telemetry, logs, or fallback adapters.

**Why it happens:**
Teams test components separately and skip a whole-pipeline privacy gate.

**How to avoid:**
Add a mandatory Phase 7 hardening gate: end-to-end privacy tests (offline mode + packet capture), log redaction checks, and release checklist item "no outbound data by default".

**Warning signs:**
- External DNS/HTTP requests during normal chat.
- Raw note content appears in debug logs.
- Environment enables verbose tracing in production profiles.

**Phase to address:**
Phase 7 (Hardening, Packaging, Release Gates)

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcode one "works on my machine" model preset | Fast first demo | Unreproducible failures on other hardware | Only in throwaway prototype, never after Phase 1 |
| Skip parser conformance tests for Obsidian edge syntax | Faster ingestion MVP | Retrieval/graph corruption that is hard to debug later | Never |
| Store memory without namespace fields | Less schema work initially | Cross-session contamination, privacy regressions | Never |
| Manual re-embed runs (`qmd embed`) only when someone remembers | No automation work now | Stale knowledge index and user trust erosion | Only before automation in early Phase 2 |
| Overload one process with ingest + query + graph updates | Simple initial architecture | Latency contention and fragile failures under load | Acceptable for very early local alpha only |

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Obsidian vault -> QMD | Treating Obsidian links/properties as plain markdown text only | Parse Obsidian constructs explicitly and persist canonical note IDs + link targets |
| QMD -> Agno retrieval | Feeding unlimited snippets directly into prompt | Add retrieval policy layer: top-k, score threshold, dedupe, token budget |
| Agno -> Graphiti memory | Writing every interaction as graph episode blindly | Apply memory worthiness filter + schema validation + retry/dead-letter path |
| Graphiti -> local models | Assuming any local model can satisfy structured extraction | Validate model capability against structured-output requirements before enablement |
| Agent stack -> llama.cpp server | Using generic OpenAI-client defaults without capacity constraints | Tune server params per hardware and enforce safe defaults in CLI config |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full vault re-embedding on every update | Ingestion times become minutes/hours | Incremental embeds with file hashing and queueing | Medium vaults (thousands of notes) |
| Unbounded memory injection into prompt | Latency/token usage grows every week | Memory summarization + selective retrieval | ~50+ memories/user (Agno guidance) |
| High concurrency without calibrated llama.cpp profile | Throughput cliff, OOM, timeout spikes | Profile-based limits for context, parallel requests, and model size | Concurrent CLI users or large contexts |
| Hybrid retrieval without score thresholds | Noisy context, hallucination from weak matches | Minimum score + rerank confidence cutoff | As vault size/diversity grows |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Leaving cloud provider keys configured in "local-only" mode | Silent data exfiltration risk | Startup guardrails that block run when cloud keys are present in strict local profile |
| Logging raw prompts/chunks from private notes | Sensitive info exposed on disk | Structured redaction and configurable "private mode" logging |
| Mixing personal and work vault contexts by default | Cross-domain privacy breach | Separate indices/memory namespaces and explicit collection selection |
| Trusting plugin-generated metadata as safe text | Prompt/context injection vectors | Sanitize metadata fields before retrieval injection |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Hiding index freshness status | User cannot trust answers | Show clear freshness: indexed at, pending updates, last embed duration |
| No explanation of data boundaries | User uncertainty about privacy | Surface "local-only" guarantees and active providers in `aurora status` |
| Slow first response after startup with no feedback | Perceived broken app | Progress logs for model warm-up/index check with ETA hints |
| Inconsistent pt-BR behavior across flows | Feels unreliable for primary audience | Enforce language policy centrally in agent system prompts and tests |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Local mode:** Often missing outbound-network verification — verify with offline-run + packet capture tests.
- [ ] **Vault ingestion:** Often missing Obsidian edge-case fixtures — verify parser test corpus includes wikilinks, properties, embeds, block refs.
- [ ] **Memory:** Often missing identity isolation — verify cross-user/session retrieval tests fail as expected.
- [ ] **Retrieval quality:** Often missing regression dataset — verify fixed benchmark questions and expected evidence files.
- [ ] **Performance:** Often missing hardware-profile validation — verify each preset under sustained concurrent requests.
- [ ] **CLI release:** Often missing install/runtime diagnostics — verify `aurora doctor` checks models, DB, indexes, and privacy mode.

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Cloud egress discovered in local mode | HIGH | Freeze release, revoke keys, patch strict-local guardrail, run incident scan on logs/artifacts |
| Corrupted/malformed graph memory | MEDIUM | Disable graph writes, replay clean episode backlog through validated extractor, rebuild indexes |
| Stale/incorrect vector index | MEDIUM | Run full re-embed, compare retrieval snapshots before/after, re-enable incremental pipeline |
| Cross-session memory contamination | HIGH | Purge contaminated memory partitions, rotate namespace scheme, backfill tests before re-enable |
| Capacity misconfiguration in llama.cpp | LOW/MEDIUM | Auto-fallback to safe preset, persist diagnostics, require explicit opt-in for aggressive profile |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| "Local-only" cloud fallback | Phase 1 | Integration test blocks run when cloud keys present; no outbound traffic in strict-local test |
| Obsidian parsing mismatch | Phase 2 | Parser fixture suite passes for wikilinks/properties/headings/embeds |
| QMD embed drift | Phase 3 | Freshness metrics stay within SLO; changed files appear in hybrid search within target window |
| Graphiti structured output failures | Phase 4 | Ingestion success rate SLO met; dead-letter queue near zero and monitored |
| Agno memory contamination | Phase 5 | Cross-user/session isolation tests pass with same DB backend |
| Context budget collapse | Phase 5/6 | Token budget checks and latency SLO pass on long-session benchmarks |
| llama.cpp capacity mis-tuning | Phase 6 | Preset benchmark matrix passes on target hardware classes |
| End-to-end privacy regressions | Phase 7 | Release gate includes packet-capture proof + log redaction audit |

## Sources

- https://github.com/ggml-org/llama.cpp
- https://github.com/getzep/graphiti
- https://docs.agno.com/memory/working-with-memories/overview
- https://docs.agno.com/agents/knowledge
- https://docs.agno.com/knowledge/markdown
- https://help.obsidian.md/Linking%20notes%20and%20files/Internal%20links
- https://help.obsidian.md/properties
- https://github.com/tobi/qmd

---
*Pitfalls research for: privacy-first local Obsidian assistant stack*
*Researched: 2026-03-01*
