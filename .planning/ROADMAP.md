# Roadmap: Aurora

**Defined:** 2026-03-01
**Depth:** comprehensive
**Coverage:** 24/24 v1 requirements mapped

## Phases

- [x] **Phase 1: Local Runtime Baseline** - Local-only runtime, global CLI entrypoint, and model connectivity guardrails.
- [ ] **Phase 2: Vault Knowledge Base Lifecycle** - Ingest, scope, and maintain Obsidian knowledge state via CLI.
- [ ] **Phase 3: Grounded Retrieval Experience** - Deliver trusted KB-grounded answers with citations and language policy.
- [ ] **Phase 4: Long-Term Memory Fusion** - Persist and retrieve memory, then fuse it with KB evidence.
- [ ] **Phase 5: Operational Command Surface** - Provide explicit command set and health diagnostics for daily operation.
- [ ] **Phase 6: Runtime Profiles and Safe Observability** - Support model profile switching with privacy-safe default logs.

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Local Runtime Baseline | 5/5 | Complete    | 2026-03-02 |
| 2. Vault Knowledge Base Lifecycle | 5/6 | In progress | - |
| 3. Grounded Retrieval Experience | 0/1 | Not started | - |
| 4. Long-Term Memory Fusion | 0/1 | Not started | - |
| 5. Operational Command Surface | 0/1 | Not started | - |
| 6. Runtime Profiles and Safe Observability | 0/1 | Not started | - |

## Phase Details

### Phase 1: Local Runtime Baseline
**Goal**: User can run Aurora locally with safe defaults and validated local model connectivity.
**Depends on**: Nothing (first phase)
**Requirements**: CLI-01, MOD-01, MOD-03, PRIV-01, PRIV-04
**Success Criteria** (what must be TRUE):
1. User can invoke `aurora` globally from any terminal directory after installation.
2. User can configure local `llama.cpp` endpoint and model through CLI configuration.
3. User receives actionable error messages when model endpoint is unavailable.
4. Aurora runs in local-only mode by default with telemetry disabled.
**Plans**: 5 plans
- [x] `01-01-PLAN.md` - Bootstrap packaging, global CLI entrypoint, and command-surface placeholders. (`01-01-SUMMARY.md`, 2026-03-02)
- [x] `01-02-PLAN.md` - Implement `aurora model set` with HF source parsing, cache-aware downloads, and local-only guardrails. (`01-02-SUMMARY.md`, 2026-03-02)
- [x] `01-03-PLAN.md` - Deliver first-run wizard, runtime diagnostics, and actionable connectivity error handling. (`01-03-SUMMARY.md`, 2026-03-02)
- [x] `01-04-PLAN.md` - Create global settings persistence and local-only privacy policy foundation. (`01-04-SUMMARY.md`, 2026-03-02)
- [x] `01-05-PLAN.md` - Close verification regression by aligning root entrypoint smoke tests with implemented setup/config/doctor behavior. (`01-05-SUMMARY.md`, 2026-03-02)

### Phase 01.1: llama.cpp server lifecycle via CLI (auto start/stop + health/status) (INSERTED)

**Goal:** User can manage local `llama.cpp` server lifecycle directly from Aurora CLI with auto-start, explicit start/stop, and actionable runtime health/status diagnostics.
**Requirements**: CLI-02, CLI-04, MOD-03, PRIV-01
**Depends on:** Phase 1
**Plans:** 5/5 plans complete

Plans:
- [x] `01.1-01-PLAN.md` - Build global lifecycle state + cross-terminal lock foundation for managed runtime ownership. (`01.1-01-SUMMARY.md`, 2026-03-02)
- [x] `01.1-02-PLAN.md` - Implement runtime lifecycle service (background start/stop, external reuse, port fallback, crash restart, health/status payloads). (`01.1-02-SUMMARY.md`, 2026-03-02)
- [x] `01.1-03-PLAN.md` - Expose `aurora model start|stop|status|health`, JSON/text UX, model-change confirmations, and auto-start bootstrap integration. (`01.1-03-SUMMARY.md`, 2026-03-03)
- [x] `01.1-04-PLAN.md` - Close verification gap by adding PID/uptime to `model health` runtime payload + CLI text/json rendering with regression tests. (`01.1-04-SUMMARY.md`, 2026-03-03)
- [x] `01.1-05-PLAN.md` - Close remaining verification gap by aligning setup-wizard `LifecycleHealth` fixtures and re-running broad runtime/CLI regressions. (`01.1-05-SUMMARY.md`, 2026-03-03)

### Phase 2: Vault Knowledge Base Lifecycle
**Goal**: User can build and maintain a scoped, current knowledge base from Obsidian markdown files.
**Depends on**: Phase 1
**Requirements**: KB-01, KB-02, KB-03, KB-04, KB-05, PRIV-02
**Success Criteria** (what must be TRUE):
1. User can ingest a vault path containing `.md` files from CLI.
2. User can define include/exclude path scopes that control what gets indexed.
3. User can run incremental updates so only changed notes are reprocessed.
4. User can delete notes from the index and trigger a full rebuild when needed.
5. User can see readable progress logs and final ingestion stats in CLI output.
**Plans**: 6 plans

Plans:
- [x] `02-01-PLAN.md` - Create KB command namespace, shared contracts, and global scope/settings persistence baseline. (`02-01-SUMMARY.md`, 2026-03-03)
- [x] `02-02-PLAN.md` - Implement scoped markdown scanner and templater pre-processing with privacy-safe metadata/log counters. (`02-02-SUMMARY.md`, 2026-03-03)
- [x] `02-03-PLAN.md` - Build manifest/delta/QMD adapter foundations for incremental update, delete, and rebuild semantics. (`02-03-SUMMARY.md`, 2026-03-03)
- [x] `02-04-PLAN.md` - Wire full `aurora kb` ingest/update/delete/rebuild lifecycle with progress/final stats and CLI integration tests. (`02-04-SUMMARY.md`, 2026-03-03)
- [x] `02-05-PLAN.md` - Close real-backend verification gap by implementing concrete QMD transport and wiring lifecycle/service integration. (`02-05-SUMMARY.md`, 2026-03-04)
- [ ] `02-06-PLAN.md` - Automate remaining verification via CLI readability contracts and real QMD end-to-end integration tests.

### Phase 3: Grounded Retrieval Experience
**Goal**: User can ask questions and receive trustworthy, evidence-grounded responses from vault content.
**Depends on**: Phase 2
**Requirements**: RET-01, RET-02, RET-03, RET-04, CLI-03
**Success Criteria** (what must be TRUE):
1. User can ask questions in CLI and receive answers grounded in indexed vault notes.
2. Each grounded answer includes citations with note path and section reference.
3. Evidence selection uses hybrid retrieval (keyword + semantic) for queries.
4. User receives explicit insufficient-evidence responses when vault context is not enough.
5. Assistant responds in pt-BR by default and changes language only when requested.
**Plans**: TBD

### Phase 4: Long-Term Memory Fusion
**Goal**: User can carry useful context across sessions and get responses that combine memory with KB evidence.
**Depends on**: Phase 3
**Requirements**: MEM-01, MEM-02, MEM-03, MEM-04
**Success Criteria** (what must be TRUE):
1. User interactions persist as long-term memory across CLI sessions.
2. Assistant retrieves relevant long-term memories when handling new questions.
3. Assistant combines KB evidence and memory evidence in one response flow.
4. User can clear session memory context without deleting the knowledge base.
**Plans**: TBD

### Phase 5: Operational Command Surface
**Goal**: User can operate Aurora end-to-end through explicit commands and built-in diagnostics.
**Depends on**: Phase 4
**Requirements**: CLI-02, CLI-04
**Success Criteria** (what must be TRUE):
1. User can run dedicated commands for ingest, update, delete, ask, and status operations.
2. User can check current system state through status command output.
3. User can run `aurora doctor` to validate runtime dependencies and model readiness with actionable guidance.
**Plans**: TBD

### Phase 6: Runtime Profiles and Safe Observability
**Goal**: User can tune model behavior safely while preserving privacy-first logging defaults.
**Depends on**: Phase 5
**Requirements**: MOD-02, PRIV-03
**Success Criteria** (what must be TRUE):
1. User can switch model profiles via configuration/CLI without changing application code.
2. Default logs avoid leaking sensitive note content while preserving operational diagnostics.
**Plans**: TBD

## Coverage Validation

| Requirement | Phase |
|-------------|-------|
| KB-01 | Phase 2 |
| KB-02 | Phase 2 |
| KB-03 | Phase 2 |
| KB-04 | Phase 2 |
| KB-05 | Phase 2 |
| RET-01 | Phase 3 |
| RET-02 | Phase 3 |
| RET-03 | Phase 3 |
| RET-04 | Phase 3 |
| MEM-01 | Phase 4 |
| MEM-02 | Phase 4 |
| MEM-03 | Phase 4 |
| MEM-04 | Phase 4 |
| CLI-01 | Phase 1 |
| CLI-02 | Phase 5 |
| CLI-03 | Phase 3 |
| CLI-04 | Phase 5 |
| MOD-01 | Phase 1 |
| MOD-02 | Phase 6 |
| MOD-03 | Phase 1 |
| PRIV-01 | Phase 1 |
| PRIV-02 | Phase 2 |
| PRIV-03 | Phase 6 |
| PRIV-04 | Phase 1 |

Mapped: 24/24
Orphans: 0
Duplicates: 0

---
*Last updated: 2026-03-04 after executing plan 02-05*
