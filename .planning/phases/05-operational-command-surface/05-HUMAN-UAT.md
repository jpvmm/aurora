---
status: partial
phase: 05-operational-command-surface
source: [05-VERIFICATION.md]
started: 2026-04-11T15:10:49Z
updated: 2026-04-11T15:10:49Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Triage REVIEW.md WR-01: doctor crash on corrupted settings file
expected: Decide whether to fix WR-01 (catch `RuntimeSettingsLoadError` in `run_doctor_checks`) before shipping or defer to a follow-up plan. Current behavior: any malformed settings file produces an unhandled traceback from `aurora doctor` instead of a structured diagnostic.
result: [pending]

### 2. Triage REVIEW.md WR-03: destructive recovery for memory_index_missing
expected: Decide whether `_check_memory_index` should keep recommending `aurora config memory clear --yes` (destructive — deletes both files and index) as the recovery, or be changed to a non-destructive reindex path or an explicit warning. Current behavior: doctor tells users to delete their own memory files when only the QMD index is missing.
result: [pending]

### 3. Triage REVIEW.md WR-02: false-positive `httpx` package missing
expected: Decide whether `_check_required_packages` should drop `httpx` (and possibly `pydantic`) from the required-package list since neither is a direct dep in `pyproject.toml`. Current behavior: a user without `httpx` in their environment sees a bogus "pacote httpx nao instalado" diagnostic.
result: [pending]

### 4. Triage REVIEW.md WR-04: substring matching against `qmd collection list`
expected: Decide whether to fix `_check_kb_embeddings` and `_check_memory_index` to use exact line-match instead of `name in stdout`. Current behavior: works correctly for default long collection names but produces false positives/negatives if a user configures a shorter collection name that is a substring of another.
result: [pending]

### 5. Triage REVIEW.md WR-05: duplicated qmd diagnostics when qmd is broken
expected: Decide whether to thread a "qmd is functional" sentinel so `_check_kb_embeddings` / `_check_memory_index` short-circuit when `_check_qmd_version` already failed. Current behavior: a single broken qmd install can produce 3 near-identical issues, hiding the root cause.
result: [pending]

### 6. Manual UAT of `aurora status` against real running llama-server + indexed vault
expected: Verifier already smoke-tested `aurora status` and `aurora status --json` against the developer's live environment (llama-server running on 127.0.0.1:8080, 337 indexed notes, 4 memories). Output rendered all four sections with real data. Human should confirm the dashboard format meets UX expectations.
result: [pending]

### 7. Manual UAT of `aurora doctor` happy path on real environment
expected: Verifier already smoke-tested `aurora doctor` and `aurora doctor --json` against the live environment. Both exited 0 with no issues, confirming `validate_runtime` + 8 new checks all pass on a healthy install. Human should confirm the diagnostic header and pt-BR text feel right.
result: [pending]

## Summary

total: 7
passed: 0
issues: 0
pending: 7
skipped: 0
blocked: 0

## Gaps
