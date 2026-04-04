---
phase: 04-long-term-memory-fusion
plan: 01
subsystem: memory
tags: [pyyaml, episodic-memory, memory-store, retrieval, settings]

# Dependency graph
requires:
  - phase: 02-vault-knowledge-base-lifecycle
    provides: paths.py pattern (get_config_dir, constants), settings.py validators, contracts.py frozen dataclasses
  - phase: 03-grounded-retrieval-experience
    provides: RetrievedNote dataclass, retrieval contracts layer
provides:
  - get_memory_dir() and get_preferences_path() path helpers in paths.py
  - MEMORY_DIRNAME and PREFERENCES_FILENAME constants
  - EpisodicMemoryStore class with write/list/clear operations
  - MEMORY_COLLECTION constant ('aurora-memory')
  - source field on RetrievedNote (defaults to 'vault', supports 'memory')
  - RuntimeSettings.memory_top_k (default 5, range 3-10) and memory_min_score (default 0.25)
  - PyYAML direct dependency for YAML frontmatter parsing
affects:
  - 04-02 (memory retrieval service needs EpisodicMemoryStore)
  - 04-03 (memory-fused chat pipeline needs store + contracts)

# Tech tracking
tech-stack:
  added: [pyyaml>=6.0.3]
  patterns:
    - Episodic memory files as YAML-frontmatter markdown (date/topic/turn_count/source fields)
    - Collision-safe file naming with -2/-3 suffix appending
    - Defensive frontmatter parsing with empty-dict fallback
    - source field on frozen dataclasses for vault vs memory distinction

key-files:
  created:
    - src/aurora/memory/__init__.py
    - src/aurora/memory/store.py
    - tests/memory/__init__.py
    - tests/memory/test_store.py
    - tests/runtime/test_memory_paths_and_settings.py
  modified:
    - pyproject.toml (pyyaml dependency)
    - src/aurora/runtime/paths.py (get_memory_dir, get_preferences_path, MEMORY_DIRNAME, PREFERENCES_FILENAME)
    - src/aurora/runtime/settings.py (memory_top_k, memory_min_score, _validate_memory_top_k)
    - src/aurora/retrieval/contracts.py (source field on RetrievedNote)

key-decisions:
  - "EpisodicMemoryStore accepts memory_dir injection for testability; defaults to get_memory_dir() for production"
  - "source field defaults to 'vault' on RetrievedNote for full backward compatibility with existing retrieval code"
  - "memory_top_k range 3-10 mirrors retrieval_top_k pattern with pt-BR validation error messages"
  - "YAML frontmatter uses yaml.dump(allow_unicode=True) to preserve non-ASCII characters in topic/summary"

patterns-established:
  - "Path helpers follow get_X() naming convention, always delegating to get_config_dir() / CONSTANT"
  - "Episodic memory files: YYYY-MM-DDTHH-MM.md with YAML frontmatter block delimited by ---"
  - "Collision suffix pattern: base.md -> base-2.md -> base-3.md (not base-1.md)"

requirements-completed: [MEM-01, MEM-04]

# Metrics
duration: 15min
completed: 2026-04-03
---

# Phase 04 Plan 01: Memory Foundation Layer Summary

**PyYAML-backed episodic memory file store with YAML frontmatter, path helpers for memory/preferences dirs, source-aware RetrievedNote, and RuntimeSettings memory fields**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-03T00:00:00Z
- **Completed:** 2026-04-03T00:15:00Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Added pyyaml as direct dependency for YAML frontmatter parsing in episodic memory files
- Extended paths.py with get_memory_dir(), get_preferences_path(), MEMORY_DIRNAME, PREFERENCES_FILENAME
- Added source field (default "vault") to RetrievedNote frozen dataclass for dual-source retrieval distinction
- Extended RuntimeSettings with memory_top_k (default 5, range 3-10) and memory_min_score (default 0.25)
- Created EpisodicMemoryStore with write/list/clear operations, collision handling, and defensive frontmatter parsing
- 24 new unit tests (8 for paths/settings/contracts, 16 for EpisodicMemoryStore) — all 110 tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Add PyYAML dep, path helpers, settings fields, source field on contracts** - `b25d1a8` (feat)
2. **Task 2: Create EpisodicMemoryStore with write, list, and clear operations** - `c43b492` (feat)

_Note: TDD tasks followed RED -> GREEN flow; no REFACTOR pass needed._

## Files Created/Modified
- `pyproject.toml` - Added pyyaml>=6.0.3 direct dependency
- `src/aurora/runtime/paths.py` - Added get_memory_dir(), get_preferences_path(), MEMORY_DIRNAME, PREFERENCES_FILENAME
- `src/aurora/runtime/settings.py` - Added memory_top_k (default 5, range 3-10), memory_min_score (default 0.25), _validate_memory_top_k validator
- `src/aurora/retrieval/contracts.py` - Added source: str = "vault" field to RetrievedNote
- `src/aurora/memory/__init__.py` - New memory module init
- `src/aurora/memory/store.py` - EpisodicMemoryStore class with MEMORY_COLLECTION constant
- `tests/memory/__init__.py` - Test module init
- `tests/memory/test_store.py` - 16 unit tests for EpisodicMemoryStore
- `tests/runtime/test_memory_paths_and_settings.py` - 8 unit tests for path helpers and settings fields

## Decisions Made
- EpisodicMemoryStore accepts optional memory_dir parameter for testability; defaults to get_memory_dir() for production
- source field defaults to "vault" on RetrievedNote preserving full backward compatibility — existing retrieval code unaffected
- memory_top_k validation range 3-10 mirrors retrieval_top_k pattern with pt-BR error messages
- YAML dump uses allow_unicode=True to preserve non-ASCII characters in topic/summary text

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Memory foundation complete: EpisodicMemoryStore ready for use by plan 04-02 (memory retrieval service)
- source field on RetrievedNote enables dual-source context assembly in plan 04-03
- RuntimeSettings memory fields ready for memory retrieval service parameterization

---
*Phase: 04-long-term-memory-fusion*
*Completed: 2026-04-03*
