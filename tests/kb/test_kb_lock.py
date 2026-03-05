from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from aurora.kb.lock import KBMutationLockError, acquire_kb_lock
from aurora.runtime.paths import get_kb_lock_path


def test_acquire_kb_lock_creates_and_releases_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))

    with acquire_kb_lock(timeout_seconds=0.2, poll_interval=0.01):
        lock_path = get_kb_lock_path()
        assert lock_path.exists()
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        assert payload["pid"] == os.getpid()

    assert get_kb_lock_path().exists() is False


def test_acquire_kb_lock_times_out_with_actionable_recovery(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))

    with acquire_kb_lock(timeout_seconds=0.2, poll_interval=0.01):
        with pytest.raises(KBMutationLockError) as raised:
            with acquire_kb_lock(timeout_seconds=0.05, poll_interval=0.01):
                pytest.fail("Second KB lock acquisition should not succeed while lock is held.")

    message = str(raised.value).lower()
    assert "kb" in message
    assert "aurora kb scheduler status" in message
    assert "rm" in message


def test_acquire_kb_lock_recovers_stale_lock(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))
    lock_path = get_kb_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "pid": 999_999,
                "process_group_id": 999_999,
                "created_at": "2026-03-05T12:00:00Z",
                "token": "stale-kb-lock",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("aurora.kb.lock._is_process_alive", lambda _pid: False)
    monkeypatch.setattr("aurora.kb.lock._is_process_group_alive", lambda _pgid: False)

    with acquire_kb_lock(timeout_seconds=0.2, poll_interval=0.01):
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        assert payload["token"] != "stale-kb-lock"
