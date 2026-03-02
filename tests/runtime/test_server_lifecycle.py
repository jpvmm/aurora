from __future__ import annotations

import errno
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aurora.runtime.server_state import ServerLifecycleState
from aurora.runtime.settings import RuntimeSettings


class FakeRuntimeClient:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.calls: list[tuple[str, str]] = []

    def validate_runtime(self, *, model_id: str):  # pragma: no cover - behavior used by service
        self.calls.append(("validate_runtime", model_id))
        if not self.ready:
            raise RuntimeError("offline")
        return {"status": "ok"}


class FakeProcess:
    def __init__(self, *, pid: int = 2_001, pgid: int = 2_001, poll_value: int | None = None) -> None:
        self.pid = pid
        self.pgid = pgid
        self._poll_value = poll_value
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self._poll_value

    def terminate(self) -> None:
        self.terminated = True
        self._poll_value = 0

    def kill(self) -> None:
        self.killed = True
        self._poll_value = -9

    def wait(self, timeout: float | None = None) -> int:  # pragma: no cover - compatibility only
        _ = timeout
        return 0


@contextmanager
def _no_lock(*args, **kwargs):
    _ = (args, kwargs)
    yield Path("/tmp/fake-lock")


def _build_settings(*, endpoint: str = "http://127.0.0.1:8080", model: str = "Qwen3-8B-Q8_0") -> RuntimeSettings:
    return RuntimeSettings(
        endpoint_url=endpoint,
        model_id=model,
        model_source="Qwen/Qwen3-8B-GGUF:Qwen3-8B-Q8_0.gguf",
        local_only=True,
        telemetry_enabled=False,
    )


def _build_state(
    *,
    ownership: str = "managed",
    pid: int | None = 2_001,
    process_group_id: int | None = 2_001,
    started_at: str | None = None,
    endpoint_url: str = "http://127.0.0.1:8080",
    port: int = 8080,
    model_id: str = "Qwen3-8B-Q8_0",
    crash_count: int = 0,
    restart_count: int = 0,
) -> ServerLifecycleState:
    return ServerLifecycleState(
        ownership=ownership,
        pid=pid,
        process_group_id=process_group_id,
        endpoint_url=endpoint_url,
        port=port,
        model_id=model_id,
        started_at=started_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        last_transition_reason="test_seed",
        crash_count=crash_count,
        restart_count=restart_count,
    )


def test_start_server_launches_managed_ownership_and_persists_state() -> None:
    from aurora.runtime.server_lifecycle import ServerLifecycleService

    settings = _build_settings()
    current_state: ServerLifecycleState | None = None
    launched: list[tuple[str, ...]] = []
    runtime_client = FakeRuntimeClient(ready=True)

    def _state_loader() -> ServerLifecycleState | None:
        return current_state

    def _state_saver(state: ServerLifecycleState) -> ServerLifecycleState:
        nonlocal current_state
        current_state = state
        return state

    def _launch(command: tuple[str, ...], **kwargs) -> FakeProcess:
        _ = kwargs
        launched.append(command)
        return FakeProcess()

    service = ServerLifecycleService(
        settings_loader=lambda: settings,
        settings_saver=lambda updated: updated,
        state_loader=_state_loader,
        state_saver=_state_saver,
        state_clearer=lambda: None,
        lock_acquirer=_no_lock,
        client_factory=lambda _endpoint: runtime_client,
        launch_process=_launch,
        is_pid_alive=lambda _pid: True,
        which_fn=lambda _name: "/usr/local/bin/llama-server",
        now_fn=lambda: datetime(2026, 3, 2, 22, 0, tzinfo=UTC),
    )

    status = service.start_server(non_interactive=True)

    assert status.lifecycle_state == "running"
    assert status.ownership == "managed"
    assert status.pid == 2_001
    assert status.endpoint_url == "http://127.0.0.1:8080"
    assert status.port == 8080
    assert current_state is not None
    assert current_state.ownership == "managed"
    assert launched
    assert "--port" in launched[0]


def test_start_server_reuses_external_ownership_when_callback_accepts() -> None:
    from aurora.runtime.server_lifecycle import ServerLifecycleService

    settings = _build_settings()
    current_state: ServerLifecycleState | None = None
    launches: list[tuple[str, ...]] = []

    def _state_loader() -> ServerLifecycleState | None:
        return current_state

    def _state_saver(state: ServerLifecycleState) -> ServerLifecycleState:
        nonlocal current_state
        current_state = state
        return state

    service = ServerLifecycleService(
        settings_loader=lambda: settings,
        settings_saver=lambda updated: updated,
        state_loader=_state_loader,
        state_saver=_state_saver,
        state_clearer=lambda: None,
        lock_acquirer=_no_lock,
        client_factory=lambda _endpoint: FakeRuntimeClient(ready=True),
        launch_process=lambda command, **kwargs: launches.append(command),  # pragma: no cover
        is_pid_alive=lambda _pid: True,
        which_fn=lambda _name: "/usr/local/bin/llama-server",
        now_fn=lambda: datetime(2026, 3, 2, 22, 0, tzinfo=UTC),
    )

    status = service.start_server(
        external_reuse_decision=lambda _status: True,
        non_interactive=False,
    )

    assert status.lifecycle_state == "running"
    assert status.ownership == "external"
    assert current_state is not None
    assert current_state.ownership == "external"
    assert launches == []


def test_stop_server_only_stops_managed_ownership_by_default() -> None:
    from aurora.runtime.server_lifecycle import ServerLifecycleService

    settings = _build_settings()
    external_state = _build_state(ownership="external", pid=None, process_group_id=None)
    current_state: ServerLifecycleState | None = external_state
    kill_calls: list[tuple[int, bool]] = []

    def _state_loader() -> ServerLifecycleState | None:
        return current_state

    def _state_saver(state: ServerLifecycleState) -> ServerLifecycleState:
        nonlocal current_state
        current_state = state
        return state

    def _state_clearer() -> None:
        nonlocal current_state
        current_state = None

    service = ServerLifecycleService(
        settings_loader=lambda: settings,
        settings_saver=lambda updated: updated,
        state_loader=_state_loader,
        state_saver=_state_saver,
        state_clearer=_state_clearer,
        lock_acquirer=_no_lock,
        client_factory=lambda _endpoint: FakeRuntimeClient(ready=True),
        launch_process=lambda command, **kwargs: FakeProcess(),
        is_pid_alive=lambda _pid: True,
        kill_process=lambda pid, *, is_group: kill_calls.append((pid, is_group)),
        which_fn=lambda _name: "/usr/local/bin/llama-server",
        now_fn=lambda: datetime(2026, 3, 2, 22, 0, tzinfo=UTC),
    )

    status = service.stop_server()

    assert status.lifecycle_state == "running"
    assert status.ownership == "external"
    assert kill_calls == []
    assert current_state == external_state


def test_stop_server_terminates_managed_ownership_process_and_clears_state() -> None:
    from aurora.runtime.server_lifecycle import ServerLifecycleService

    settings = _build_settings()
    current_state: ServerLifecycleState | None = _build_state(
        ownership="managed",
        pid=3_333,
        process_group_id=3_333,
    )
    kill_calls: list[tuple[int, bool]] = []

    def _state_loader() -> ServerLifecycleState | None:
        return current_state

    def _state_saver(state: ServerLifecycleState) -> ServerLifecycleState:
        nonlocal current_state
        current_state = state
        return state

    def _state_clearer() -> None:
        nonlocal current_state
        current_state = None

    service = ServerLifecycleService(
        settings_loader=lambda: settings,
        settings_saver=lambda updated: updated,
        state_loader=_state_loader,
        state_saver=_state_saver,
        state_clearer=_state_clearer,
        lock_acquirer=_no_lock,
        client_factory=lambda _endpoint: FakeRuntimeClient(ready=True),
        launch_process=lambda command, **kwargs: FakeProcess(),
        is_pid_alive=lambda _pid: True,
        kill_process=lambda pid, *, is_group: kill_calls.append((pid, is_group)),
        which_fn=lambda _name: "/usr/local/bin/llama-server",
        now_fn=lambda: datetime(2026, 3, 2, 22, 0, tzinfo=UTC),
    )

    status = service.stop_server()

    assert status.lifecycle_state == "stopped"
    assert status.ownership is None
    assert kill_calls == [(3_333, True)]
    assert current_state is None


def test_get_status_reports_runtime_payload_for_ownership_mode() -> None:
    from aurora.runtime.server_lifecycle import ServerLifecycleService

    settings = _build_settings()
    seeded = _build_state(
        ownership="managed",
        pid=7_777,
        process_group_id=7_777,
        started_at=(datetime.now(UTC) - timedelta(seconds=120)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    service = ServerLifecycleService(
        settings_loader=lambda: settings,
        settings_saver=lambda updated: updated,
        state_loader=lambda: seeded,
        state_saver=lambda state: state,
        state_clearer=lambda: None,
        lock_acquirer=_no_lock,
        client_factory=lambda _endpoint: FakeRuntimeClient(ready=True),
        launch_process=lambda command, **kwargs: FakeProcess(),
        is_pid_alive=lambda _pid: True,
        which_fn=lambda _name: "/usr/local/bin/llama-server",
        now_fn=lambda: datetime.now(UTC),
    )

    status = service.get_status()

    assert status.lifecycle_state == "running"
    assert status.ownership == "managed"
    assert status.model_id == settings.model_id
    assert status.endpoint_url == settings.endpoint_url
    assert status.port == 8080
    assert status.pid == 7_777
    assert status.uptime_seconds is not None
    assert status.uptime_seconds >= 100


def test_start_server_fallback_switches_port_and_persists_updated_endpoint() -> None:
    from aurora.runtime.server_lifecycle import ServerLifecycleService

    settings = _build_settings(endpoint="http://127.0.0.1:8080")
    persisted_settings: RuntimeSettings | None = None
    current_state: ServerLifecycleState | None = None
    launch_ports: list[int] = []

    def _save_settings(updated: RuntimeSettings) -> RuntimeSettings:
        nonlocal persisted_settings
        persisted_settings = updated
        return updated

    def _state_saver(state: ServerLifecycleState) -> ServerLifecycleState:
        nonlocal current_state
        current_state = state
        return state

    def _launch(command: tuple[str, ...], **kwargs) -> FakeProcess:
        _ = kwargs
        port = int(command[command.index("--port") + 1])
        launch_ports.append(port)
        if port == 8080:
            raise OSError(errno.EADDRINUSE, "Address already in use")
        return FakeProcess(pid=4_808, pgid=4_808)

    service = ServerLifecycleService(
        settings_loader=lambda: settings,
        settings_saver=_save_settings,
        state_loader=lambda: current_state,
        state_saver=_state_saver,
        state_clearer=lambda: None,
        lock_acquirer=_no_lock,
        client_factory=lambda endpoint: FakeRuntimeClient(ready=endpoint.endswith(":8081")),
        launch_process=_launch,
        is_pid_alive=lambda _pid: True,
        which_fn=lambda _name: "/usr/local/bin/llama-server",
        now_fn=lambda: datetime(2026, 3, 2, 22, 0, tzinfo=UTC),
    )

    status = service.start_server(non_interactive=True)

    assert launch_ports == [8080, 8081]
    assert status.port == 8081
    assert current_state is not None
    assert current_state.port == 8081
    assert persisted_settings is not None
    assert persisted_settings.endpoint_url == "http://127.0.0.1:8081"


def test_start_server_reports_diagnostic_when_port_fallback_is_exhausted() -> None:
    from aurora.runtime.errors import RuntimeDiagnosticError
    from aurora.runtime.server_lifecycle import ServerLifecycleService

    service = ServerLifecycleService(
        settings_loader=lambda: _build_settings(),
        settings_saver=lambda updated: updated,
        state_loader=lambda: None,
        state_saver=lambda state: state,
        state_clearer=lambda: None,
        lock_acquirer=_no_lock,
        client_factory=lambda _endpoint: FakeRuntimeClient(ready=False),
        launch_process=lambda _command, **kwargs: (_ for _ in ()).throw(
            OSError(errno.EADDRINUSE, "Address already in use")
        ),
        is_pid_alive=lambda _pid: True,
        which_fn=lambda _name: "/usr/local/bin/llama-server",
        now_fn=lambda: datetime(2026, 3, 2, 22, 0, tzinfo=UTC),
    )

    with pytest.raises(RuntimeDiagnosticError) as raised:
        service.start_server(non_interactive=True)

    assert raised.value.category == "port_conflict_exhausted"
    assert "aurora model set --endpoint" in raised.value.recovery_commands[0]


def test_get_status_attempts_single_restart_after_managed_crash() -> None:
    from aurora.runtime.server_lifecycle import ServerLifecycleService

    settings = _build_settings()
    current_state = _build_state(
        ownership="managed",
        pid=9_001,
        process_group_id=9_001,
        crash_count=0,
        restart_count=0,
    )
    launches = 0

    def _state_loader() -> ServerLifecycleState | None:
        return current_state

    def _state_saver(state: ServerLifecycleState) -> ServerLifecycleState:
        nonlocal current_state
        current_state = state
        return state

    def _launch(command: tuple[str, ...], **kwargs) -> FakeProcess:
        nonlocal launches
        _ = (command, kwargs)
        launches += 1
        return FakeProcess(pid=9_002, pgid=9_002)

    service = ServerLifecycleService(
        settings_loader=lambda: settings,
        settings_saver=lambda updated: updated,
        state_loader=_state_loader,
        state_saver=_state_saver,
        state_clearer=lambda: None,
        lock_acquirer=_no_lock,
        client_factory=lambda _endpoint: FakeRuntimeClient(ready=True),
        launch_process=_launch,
        is_pid_alive=lambda pid: pid == 9_002,
        which_fn=lambda _name: "/usr/local/bin/llama-server",
        now_fn=lambda: datetime(2026, 3, 2, 22, 0, tzinfo=UTC),
    )

    status = service.get_status()

    assert launches == 1
    assert status.lifecycle_state == "running"
    assert status.pid == 9_002
    assert current_state.restart_count == 1
    assert current_state.crash_count == 1


def test_check_health_reports_restart_failure_diagnostic_after_single_attempt() -> None:
    from aurora.runtime.server_lifecycle import ServerLifecycleService

    state = _build_state(
        ownership="managed",
        pid=5_000,
        process_group_id=5_000,
        crash_count=0,
        restart_count=0,
    )

    service = ServerLifecycleService(
        settings_loader=lambda: _build_settings(),
        settings_saver=lambda updated: updated,
        state_loader=lambda: state,
        state_saver=lambda updated: updated,
        state_clearer=lambda: None,
        lock_acquirer=_no_lock,
        client_factory=lambda _endpoint: FakeRuntimeClient(ready=False),
        launch_process=lambda command, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        is_pid_alive=lambda _pid: False,
        which_fn=lambda _name: "/usr/local/bin/llama-server",
        now_fn=lambda: datetime(2026, 3, 2, 22, 0, tzinfo=UTC),
    )

    health = service.check_health()

    assert health.ok is False
    assert health.category == "crash_restart_failed"
    assert "aurora model start" in health.recovery_commands


def test_build_runtime_error_supports_startup_diagnostic_categories() -> None:
    from aurora.runtime.errors import build_runtime_error

    binary_error = build_runtime_error("binary_missing")
    timeout_error = build_runtime_error("startup_timeout")
    lock_error = build_runtime_error("lock_timeout")

    assert binary_error.category == "binary_missing"
    assert "llama-server" in binary_error.message.lower()
    assert timeout_error.category == "startup_timeout"
    assert lock_error.category == "lock_timeout"
