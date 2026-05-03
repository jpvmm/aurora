"""Test isolation for the memory layer.

`EpisodicMemoryStore.__init__` calls `_ensure_qmd_collection`, which runs
`qmd --index aurora-kb collection add <memory_dir> --name aurora-memory ...`
against the GLOBAL QMD index. Without isolation, every test that constructs
`EpisodicMemoryStore` registers its `tmp_path/memory` directory in QMD's
persistent global state — and the last test to run "wins", leaving
production memory retrieval broken until manually fixed via
`qmd collection remove aurora-memory && qmd collection add ...`.

This was caught in production: a test from this file (likely
`test_write_creates_markdown_file_in_memory_dir`) had registered
`/private/var/folders/.../pytest-of-jp/pytest-39/.../memory` as the
aurora-memory collection. After the tmpdir was cleaned, the production
chat memory retrieval silently returned 0 hits for weeks.

The autouse fixture below patches `subprocess.run` in `aurora.memory.store`
to a no-op that returns a successful CompletedProcess. Both
`_ensure_qmd_collection` and `_qmd_update` treat returncode == 0 as
success and proceed silently, so production-path code keeps running but
no QMD subprocess actually fires.
"""
from __future__ import annotations

import subprocess

import pytest


@pytest.fixture(autouse=True)
def isolate_qmd_subprocess(monkeypatch):
    from aurora.memory import store

    def _fake_run(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", ())
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="",
            stderr="",
        )

    monkeypatch.setattr(store.subprocess, "run", _fake_run)
