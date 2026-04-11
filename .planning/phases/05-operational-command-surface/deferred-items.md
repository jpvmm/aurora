# Deferred Items — Phase 05 Operational Command Surface

Items discovered during execution but deferred because they are out of scope for the
current plan (not caused by plan changes). Tracked here for future cleanup.

## Pre-existing test failures (environment)

### tests/cli/test_kb_command.py::test_update_reports_privacy_safe_read_errors_without_forcing_delete

- **Discovered during:** Plan 05-01 execution (Task 2 verification)
- **Status:** Fails on baseline `e54cea8` before any plan 05-01 changes.
- **Root cause:** `KBServiceError: backend_bootstrap_failed` — the test constructs a real
  `KBService()` and calls `run_ingest`, which attempts to bootstrap a QMD collection. The
  local worktree environment does not have `qmd` CLI installed, so the backend bootstrap
  fails.
- **Why deferred:** Unrelated to CLI command-surface changes. Pre-existing environmental
  failure; the test itself should probably monkeypatch the backend like the other kb tests
  do.
- **Suggested fix (future plan):** Either install qmd in CI or refactor this test to inject
  a fake backend via `monkeypatch.setattr(kb_module, "KBService", ...)` as the other
  privacy-safe tests already do.

### tests/integration/test_kb_qmd_integration.py::test_real_qmd_lifecycle_ingest_update_delete_rebuild

- **Discovered during:** Plan 05-01 execution (full test sweep)
- **Status:** Fails on baseline `e54cea8` before any plan 05-01 changes.
- **Root cause:** Integration test requires real `qmd` binary in PATH. Worktree
  environment does not have it. Marked `@pytest.mark.integration` — intended to run
  only in environments with QMD installed.
- **Why deferred:** Integration test depends on external `qmd` binary. Not regressed by
  namespace move. The test's `_invoke_kb` helper still uses the deprecated `["kb", ...]`
  alias, which still works, but the underlying service call fails because qmd is missing.
- **Note:** The deprecated alias path keeps this test working without modification — the
  warning goes to stderr, exit code is set by the delegated command. When qmd becomes
  available, this test should pass. A future cleanup pass could migrate the helper to
  `["config", "kb", ...]` to adopt the canonical namespace, but both paths are equivalent.
