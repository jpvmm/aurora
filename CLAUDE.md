# Aurora — project instructions

## Always reinstall after code changes

The global `aurora` on the user's PATH (`/Users/jp/.local/bin/aurora`) is a uv-tool snapshot install — NOT editable. Source edits in this repo do not propagate to the global CLI until the tool is reinstalled.

**After ANY change that touches `src/aurora/**` (new commands, flags, behavior, fixes), run before reporting "done":**

```bash
uv tool install --reinstall /Users/jp/Projects/Personal/aurora
```

Do NOT use `uv tool upgrade aurora` — it only fires when the project version in `pyproject.toml` bumps (currently pinned at `0.1.0`), so it silently no-ops during local development. `--reinstall` rebuilds the wheel from source unconditionally.

Then verify the change is visible by invoking the global `aurora` from outside the repo (`cd ~ && aurora <command>`), not via `.venv/bin/aurora` (which always reflects live source and gives false confidence).

This applies to:
- Phase execution (every `feat(NN-MM)` commit that changes `src/`)
- Bug fixes
- New CLI flags
- Anything the user might want to try via `aurora <whatever>` after we ship it

Skip only when the change is purely:
- Tests (`tests/**`)
- Docs (`.planning/**`, `doc/**`, `*.md`)
- Project tooling (`.claude/**`, `scripts/` that aren't `src/`)
