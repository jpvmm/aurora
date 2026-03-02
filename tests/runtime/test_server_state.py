from __future__ import annotations

import json
from pathlib import Path

import pytest

from aurora.runtime.paths import get_server_state_path
from aurora.runtime.server_state import (
    ServerLifecycleState,
    ServerStateError,
    clear_server_state,
    load_server_state,
    save_server_state,
)


def test_load_server_state_returns_none_when_file_is_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))

    assert load_server_state() is None


def test_server_state_round_trip_is_deterministic(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))
    state = ServerLifecycleState(
        ownership="managed",
        pid=1234,
        process_group_id=1234,
        endpoint_url="http://127.0.0.1:8080",
        port=8080,
        model_id="Qwen3-8B-Q8_0",
        started_at="2026-03-02T22:00:00Z",
        last_transition_reason="manual_start",
        crash_count=1,
        restart_count=2,
    )

    save_server_state(state)
    loaded = load_server_state()
    path = get_server_state_path()
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert loaded == state
    assert path.name == "server-state.json"
    assert list(payload.keys()) == sorted(payload.keys())


def test_load_server_state_reports_actionable_error_for_invalid_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))
    path = get_server_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ estado: invalido", encoding="utf-8")

    with pytest.raises(ServerStateError) as raised:
        load_server_state()

    message = str(raised.value).lower()
    assert "estado de ciclo de vida" in message
    assert "rm" in message


def test_load_server_state_reports_actionable_error_for_invalid_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))
    path = get_server_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "ownership": "managed",
                "pid": "invalid",
                "process_group_id": 321,
                "endpoint_url": "http://127.0.0.1:8080",
                "port": 8080,
                "model_id": "Qwen3-8B-Q8_0",
                "started_at": "2026-03-02T22:00:00Z",
                "last_transition_reason": "manual_start",
                "crash_count": 0,
                "restart_count": 0,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ServerStateError) as raised:
        load_server_state()

    message = str(raised.value).lower()
    assert "corrigido" in message
    assert "aurora model status" in message


def test_clear_server_state_removes_persisted_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))
    state = ServerLifecycleState(
        ownership="external",
        pid=None,
        process_group_id=None,
        endpoint_url="http://127.0.0.1:8080",
        port=8080,
        model_id="Qwen3-8B-Q8_0",
        started_at="2026-03-02T22:00:00Z",
        last_transition_reason="external_detected",
        crash_count=0,
        restart_count=0,
    )
    save_server_state(state)
    assert get_server_state_path().exists()

    clear_server_state()

    assert get_server_state_path().exists() is False
