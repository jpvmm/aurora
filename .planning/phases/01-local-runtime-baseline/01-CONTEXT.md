# Phase 1: Local Runtime Baseline - Context

**Gathered:** 2026-03-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a reliable local-only runtime baseline for Aurora: global CLI invocation, first-run setup, model connectivity validation, and privacy-safe defaults. This phase does not add knowledge base ingestion, retrieval quality, or long-term memory behavior.

</domain>

<decisions>
## Implementation Decisions

### Setup Flow
- Primary onboarding path is global install via `uv tool` / `pipx`.
- First run should open a guided wizard when required runtime config is missing.
- Wizard must validate endpoint connectivity and active model before completion.
- Setup completion should show a clear summary and immediate next command (`aurora ask` example).
- If setup validation fails, setup should block and guide user through correction.
- Onboarding language defaults to pt-BR with explicit guidance on changing language.
- User expects model setup to support Hugging Face model path input and local serving flow.

### Config UX
- Configuration UX should support both command-based config and wizard flow.
- Model source input should accept explicit Hugging Face target in `repo/model:arquivo.gguf` form.
- Initial default model should be `Qwen3-8B-Q8_0` (GGUF).
- Config scope is global per user, so Aurora works consistently from any directory.
- Download UX should show detailed progress (percent, size, ETA).
- Model switching should activate new default and keep previously downloaded models.
- Downloaded models should live in a global Aurora directory by default.
- QMD alignment should be inspiration-level (familiar behavior), not strict one-to-one cloning.
- If download fails, CLI should provide guided retry.
- Private Hugging Face models should be supported with secure token prompt in-flow.
- If offline and HF download is requested, CLI should show actionable offline guidance.
- Preferred command naming: `aurora model set`.
- Large downloads should always require explicit confirmation.
- CLI should provide dedicated config inspection command (for example, `aurora config show`).
- If a requested model already exists locally, local cache should be prioritized.

### Model Errors
- Error messages should be direct and actionable, not generic.
- Failure reasons should be grouped by type (endpoint offline, model missing, invalid token, timeout).
- Each error should include exact recovery command(s), with `aurora doctor` available when relevant.
- Error communication remains in clear pt-BR by default.

### Privacy UX
- Startup/status should explicitly show local-only runtime state.
- Telemetry-off default should be visible in configuration/status output.
- Attempting cloud endpoint setup in Phase 1 should be blocked with clear explanation.
- Sensitive paths/content in logs should be masked by default.

### Claude's Discretion
- Exact copywriting and visual formatting of wizard screens and status outputs.
- Exact command output layout for progress blocks and confirmation prompts.
- Precise wording strategy for privacy and error banners while keeping tone practical.

</decisions>

<specifics>
## Specific Ideas

- "the cli must be able to spin up a model from huggingface for llama.cpp based on a hugginface model path name setup by the user."
- "as default lets use Qwen3-8B-Q8_0.gguf for the assistant."
- "check how the QMD lib does it and follow."

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- None yet in repository code (no `src/` or app implementation scaffold present).

### Established Patterns
- Current project only has planning artifacts in `.planning/`; implementation patterns are not established yet.

### Integration Points
- First implementation will define initial CLI/runtime module boundaries and become the baseline integration pattern for later phases.

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 1 scope.

</deferred>

---
*Phase: 01-local-runtime-baseline*
*Context gathered: 2026-03-01*
