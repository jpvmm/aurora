# Requirements: Aurora

**Defined:** 2026-03-01
**Core Value:** Privacidade total com memoria util de longo prazo sobre o vault, sem depender de servicos externos.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Knowledge Base

- [x] **KB-01**: User can ingest an Obsidian vault path containing `.md` files via CLI command.
- [x] **KB-02**: User can update index incrementally for changed notes without full reingestion.
- [x] **KB-03**: User can delete notes from the knowledge base via CLI command.
- [x] **KB-04**: User can trigger full rebuild of the knowledge base via CLI command.
- [x] **KB-05**: User can view ingestion progress and final stats in readable CLI logs.

### Retrieval

- [ ] **RET-01**: User can ask questions in CLI and receive answers grounded in vault content.
- [ ] **RET-02**: User receives citations with note path and section reference for each grounded answer.
- [ ] **RET-03**: User query uses hybrid retrieval (keyword + semantic) for evidence selection.
- [ ] **RET-04**: User gets explicit "insufficient evidence" response when vault context is not enough.

### Memory

- [ ] **MEM-01**: User interactions are persisted as long-term memory across CLI sessions.
- [ ] **MEM-02**: Assistant retrieves relevant long-term memories during new questions.
- [ ] **MEM-03**: Assistant combines knowledge base evidence and memory evidence in a single response flow.
- [ ] **MEM-04**: User can clear session memory context without deleting the entire knowledge base.

### Assistant CLI

- [x] **CLI-01**: User can invoke Aurora globally from any terminal directory after installation.
- [x] **CLI-02**: User can use dedicated CLI commands for ingest, update, delete, ask, and status operations.
- [ ] **CLI-03**: Assistant replies in pt-BR by default and only changes language when user requests.
- [x] **CLI-04**: User can run a `doctor` command to validate local runtime dependencies and model readiness.

### Model Setup

- [x] **MOD-01**: User can configure local llama.cpp endpoint/model through CLI configuration.
- [ ] **MOD-02**: User can switch between model profiles without changing application code.
- [x] **MOD-03**: User receives actionable configuration errors when model endpoint is unavailable.

### Privacy & Safety

- [x] **PRIV-01**: User can run Aurora in local-only default mode without cloud API dependency.
- [x] **PRIV-02**: User can define include/exclude scopes for which vault paths are indexed.
- [ ] **PRIV-03**: User logs avoid leaking sensitive note content by default.
- [x] **PRIV-04**: User has telemetry disabled by default.

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Memory Governance

- **MEMG-01**: User can pin specific memories to prioritize retrieval.
- **MEMG-02**: User can forget selected memories explicitly.
- **MEMG-03**: User can configure memory decay rules.

### Privacy Hardening

- **PH-01**: User can enable strict no-egress mode with active network verification checks.
- **PH-02**: User can run privacy audit command with verifiable local-only proof report.

### Product Expansion

- **UI-01**: User can interact through desktop GUI in addition to CLI.
- **COL-01**: Team can use isolated multi-user workspaces with access boundaries.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Cloud fallback for model inference | Conflicts with privacy-first product direction |
| Autonomous background vault mutation | High trust/safety risk for early versions |
| Broad multimodal ingestion (audio/video/OCR) | Adds complexity before Markdown core is stable |
| Enterprise RBAC and tenancy | Not aligned with single-user v1 focus |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| KB-01 | Phase 2 | Complete |
| KB-02 | Phase 2 | Complete |
| KB-03 | Phase 2 | Complete |
| KB-04 | Phase 2 | Complete |
| KB-05 | Phase 2 | Complete |
| RET-01 | Phase 3 | Pending |
| RET-02 | Phase 3 | Pending |
| RET-03 | Phase 3 | Pending |
| RET-04 | Phase 3 | Pending |
| MEM-01 | Phase 4 | Pending |
| MEM-02 | Phase 4 | Pending |
| MEM-03 | Phase 4 | Pending |
| MEM-04 | Phase 4 | Pending |
| CLI-01 | Phase 1 | Complete |
| CLI-02 | Phase 5 | Complete |
| CLI-03 | Phase 3 | Pending |
| CLI-04 | Phase 5 | Complete |
| MOD-01 | Phase 1 | Complete |
| MOD-02 | Phase 6 | Pending |
| MOD-03 | Phase 1 | Complete |
| PRIV-01 | Phase 1 | Complete |
| PRIV-02 | Phase 2 | Complete |
| PRIV-03 | Phase 6 | Pending |
| PRIV-04 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 24 total
- Mapped to phases: 24
- Unmapped: 0

---
*Requirements defined: 2026-03-01*
*Last updated: 2026-03-03 after executing plan 02-03*
