from __future__ import annotations

import errno
import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Literal, Protocol
from urllib.parse import SplitResult, urlsplit

from aurora.runtime.errors import RuntimeDiagnosticError, build_runtime_error, classify_runtime_error
from aurora.runtime.llama_client import LlamaRuntimeClient
from aurora.runtime.model_registry import resolve_cached_model
from aurora.runtime.model_source import ModelSourceValidationError, parse_hf_target
from aurora.runtime.server_lock import LifecycleLockError, acquire_lifecycle_lock
from aurora.runtime.server_state import (
    ServerLifecycleState,
    ServerOwnership,
    clear_server_state,
    load_server_state,
    save_server_state,
)
from aurora.runtime.settings import RuntimeSettings, load_settings, save_settings

LifecycleState = Literal["running", "stopped", "crashed"]
ExternalReuseDecision = Callable[["LifecycleStatus"], bool]
ModelBootstrapCallback = Callable[[RuntimeSettings], str | RuntimeSettings | None]


class ProcessLike(Protocol):
    pid: int

    def poll(self) -> int | None: ...


LaunchProcessFn = Callable[..., ProcessLike]
ClientFactoryFn = Callable[[str], LlamaRuntimeClient]
SettingsLoaderFn = Callable[[], RuntimeSettings]
SettingsSaverFn = Callable[[RuntimeSettings], RuntimeSettings]
StateLoaderFn = Callable[[], ServerLifecycleState | None]
StateSaverFn = Callable[[ServerLifecycleState], ServerLifecycleState]
StateClearerFn = Callable[[], None]
LockAcquirerFn = Callable[..., object]
NowFn = Callable[[], datetime]
SleepFn = Callable[[float], None]
PidAliveFn = Callable[[int], bool]
WhichFn = Callable[[str], str | None]


@dataclass(frozen=True)
class LifecycleStatus:
    lifecycle_state: LifecycleState
    ownership: ServerOwnership | None
    endpoint_url: str
    port: int
    model_id: str
    pid: int | None
    process_group_id: int | None
    uptime_seconds: int | None
    ready: bool
    message: str | None = None
    error_category: str | None = None
    recovery_commands: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "lifecycle_state": self.lifecycle_state,
            "ownership": self.ownership,
            "endpoint_url": self.endpoint_url,
            "port": self.port,
            "model_id": self.model_id,
            "pid": self.pid,
            "process_group_id": self.process_group_id,
            "uptime_seconds": self.uptime_seconds,
            "ready": self.ready,
            "message": self.message,
            "error_category": self.error_category,
            "recovery_commands": list(self.recovery_commands),
        }


@dataclass(frozen=True)
class LifecycleHealth:
    ok: bool
    endpoint_url: str
    port: int
    model_id: str
    ownership: ServerOwnership | None
    category: str | None
    message: str
    recovery_commands: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "endpoint_url": self.endpoint_url,
            "port": self.port,
            "model_id": self.model_id,
            "ownership": self.ownership,
            "category": self.category,
            "message": self.message,
            "recovery_commands": list(self.recovery_commands),
        }


@dataclass(frozen=True)
class EnsureRuntimeResult:
    settings: RuntimeSettings
    status: LifecycleStatus
    health: LifecycleHealth


class ServerLifecycleService:
    """Runtime lifecycle orchestration for managed and external servers."""

    def __init__(
        self,
        *,
        settings_loader: SettingsLoaderFn = load_settings,
        settings_saver: SettingsSaverFn = save_settings,
        state_loader: StateLoaderFn = load_server_state,
        state_saver: StateSaverFn = save_server_state,
        state_clearer: StateClearerFn = clear_server_state,
        lock_acquirer: LockAcquirerFn = acquire_lifecycle_lock,
        client_factory: ClientFactoryFn | None = None,
        launch_process: LaunchProcessFn | None = None,
        now_fn: NowFn | None = None,
        sleep_fn: SleepFn = time.sleep,
        is_pid_alive: PidAliveFn | None = None,
        kill_process: Callable[[int, bool], None] | None = None,
        which_fn: WhichFn = shutil.which,
        startup_timeout_seconds: float = 20.0,
        startup_probe_interval_seconds: float = 0.2,
        lock_timeout_seconds: float = 5.0,
        max_port_attempts: int = 5,
        restart_limit: int = 1,
    ) -> None:
        self._settings_loader = settings_loader
        self._settings_saver = settings_saver
        self._state_loader = state_loader
        self._state_saver = state_saver
        self._state_clearer = state_clearer
        self._lock_acquirer = lock_acquirer
        self._client_factory = client_factory or (
            lambda endpoint: LlamaRuntimeClient(endpoint_url=endpoint)
        )
        self._launch_process = launch_process or subprocess.Popen
        self._now_fn = now_fn or (lambda: datetime.now(UTC))
        self._sleep_fn = sleep_fn
        self._is_pid_alive = is_pid_alive or _is_process_alive
        self._kill_process = kill_process or _kill_process
        self._which_fn = which_fn
        self._startup_timeout_seconds = startup_timeout_seconds
        self._startup_probe_interval_seconds = startup_probe_interval_seconds
        self._lock_timeout_seconds = lock_timeout_seconds
        self._max_port_attempts = max_port_attempts
        self._restart_limit = restart_limit

    def start_server(
        self,
        *,
        external_reuse_decision: ExternalReuseDecision | None = None,
        allow_external_reuse: bool | None = None,
        non_interactive: bool = False,
        reason: str = "manual_start",
    ) -> LifecycleStatus:
        try:
            with self._acquire_lock():
                settings = self._settings_loader()
                parsed = _parse_endpoint(settings.endpoint_url)
                existing = self._state_loader()
                if existing is not None and existing.ownership == "managed" and existing.pid:
                    if self._is_pid_alive(existing.pid):
                        return self._build_status(existing, settings=settings)

                endpoint_ready = self._is_runtime_ready(
                    endpoint_url=settings.endpoint_url,
                    model_id=settings.model_id,
                )
                if endpoint_ready:
                    decision = self._resolve_external_reuse_decision(
                        allow_external_reuse=allow_external_reuse,
                        external_reuse_decision=external_reuse_decision,
                        non_interactive=non_interactive,
                        settings=settings,
                        parsed=parsed,
                    )
                    if decision:
                        state = ServerLifecycleState(
                            ownership="external",
                            pid=None,
                            process_group_id=None,
                            endpoint_url=settings.endpoint_url,
                            port=parsed.port,
                            model_id=settings.model_id,
                            started_at=self._now_iso(),
                            last_transition_reason="external_reused",
                        )
                        self._state_saver(state)
                        return self._build_status(state, settings=settings, ready=True)

                process, active_settings, active_endpoint = self._launch_managed_with_fallback(
                    settings=settings
                )
                managed_state = ServerLifecycleState(
                    ownership="managed",
                    pid=process.pid,
                    process_group_id=_process_group_id(process.pid),
                    endpoint_url=active_settings.endpoint_url,
                    port=active_endpoint.port,
                    model_id=active_settings.model_id,
                    started_at=self._now_iso(),
                    last_transition_reason=reason,
                )
                self._state_saver(managed_state)
                return self._build_status(managed_state, settings=active_settings, ready=True)
        except LifecycleLockError as error:
            raise build_runtime_error("lock_timeout", detail=str(error)) from error

    def stop_server(self, *, force: bool = False) -> LifecycleStatus:
        try:
            with self._acquire_lock():
                settings = self._settings_loader()
                state = self._state_loader()
                if state is None:
                    return self._build_stopped_status(settings=settings)

                if state.ownership == "external" and not force:
                    return self._build_status(state, settings=settings)

                target = state.process_group_id if state.process_group_id is not None else state.pid
                if target is not None:
                    self._kill_process(target, is_group=state.process_group_id is not None)
                self._state_clearer()
                return self._build_stopped_status(settings=settings)
        except LifecycleLockError as error:
            raise build_runtime_error("lock_timeout", detail=str(error)) from error

    def get_status(self) -> LifecycleStatus:
        settings = self._settings_loader()
        state = self._state_loader()
        if state is None:
            return self._build_stopped_status(settings=settings)

        if state.ownership == "managed" and state.pid is not None and not self._is_pid_alive(state.pid):
            restarted = self._attempt_single_restart(state=state, settings=settings)
            if restarted is not None:
                new_state, settings = restarted
                return self._build_status(new_state, settings=settings, ready=True)

            category = "crash_restart_failed"
            error = build_runtime_error(
                category,
                detail="Reinicio automatico indisponivel ou falhou.",
            )
            failed_state = ServerLifecycleState(
                ownership="managed",
                pid=None,
                process_group_id=None,
                endpoint_url=state.endpoint_url,
                port=state.port,
                model_id=state.model_id,
                started_at=state.started_at,
                last_transition_reason="crash_restart_failed",
                crash_count=state.crash_count + 1,
                restart_count=min(state.restart_count + 1, self._restart_limit),
            )
            self._state_saver(failed_state)
            return self._build_status(
                failed_state,
                settings=settings,
                ready=False,
                lifecycle_state="crashed",
                message=error.message,
                error_category=error.category,
                recovery_commands=error.recovery_commands,
            )
        return self._build_status(state, settings=settings)

    def check_health(self) -> LifecycleHealth:
        status = self.get_status()
        if status.lifecycle_state == "crashed" and status.error_category is not None:
            return LifecycleHealth(
                ok=False,
                endpoint_url=status.endpoint_url,
                port=status.port,
                model_id=status.model_id,
                ownership=status.ownership,
                category=status.error_category,
                message=status.message or "Runtime em estado de falha.",
                recovery_commands=status.recovery_commands,
            )
        if status.lifecycle_state == "stopped":
            error = build_runtime_error("endpoint_offline")
            return LifecycleHealth(
                ok=False,
                endpoint_url=status.endpoint_url,
                port=status.port,
                model_id=status.model_id,
                ownership=status.ownership,
                category=error.category,
                message=error.message,
                recovery_commands=error.recovery_commands,
            )

        client = self._client_factory(status.endpoint_url)
        try:
            client.validate_runtime(model_id=status.model_id)
        except RuntimeDiagnosticError as error:
            return LifecycleHealth(
                ok=False,
                endpoint_url=status.endpoint_url,
                port=status.port,
                model_id=status.model_id,
                ownership=status.ownership,
                category=error.category,
                message=error.message,
                recovery_commands=error.recovery_commands,
            )
        except Exception as error:
            diagnostic = classify_runtime_error(error, model_id=status.model_id)
            return LifecycleHealth(
                ok=False,
                endpoint_url=status.endpoint_url,
                port=status.port,
                model_id=status.model_id,
                ownership=status.ownership,
                category=diagnostic.category,
                message=diagnostic.message,
                recovery_commands=diagnostic.recovery_commands,
            )

        return LifecycleHealth(
            ok=True,
            endpoint_url=status.endpoint_url,
            port=status.port,
            model_id=status.model_id,
            ownership=status.ownership,
            category=None,
            message="Runtime pronto para inferencia.",
            recovery_commands=(),
        )

    def _launch_managed_with_fallback(
        self,
        *,
        settings: RuntimeSettings,
    ) -> tuple[ProcessLike, RuntimeSettings, SplitResult]:
        parsed = _parse_endpoint(settings.endpoint_url)
        base_port = parsed.port
        last_conflict: OSError | None = None

        for offset in range(self._max_port_attempts):
            port = base_port + offset
            candidate_endpoint_url = _endpoint_with_port(settings.endpoint_url, port=port)
            candidate_settings = settings.model_copy(update={"endpoint_url": candidate_endpoint_url})
            candidate_endpoint = _parse_endpoint(candidate_endpoint_url)
            try:
                process = self._launch_managed_server_once(
                    settings=candidate_settings,
                    parsed=candidate_endpoint,
                )
            except OSError as error:
                if _is_port_conflict(error):
                    last_conflict = error
                    continue
                raise

            if candidate_settings.endpoint_url != settings.endpoint_url:
                settings = self._settings_saver(candidate_settings)
            else:
                settings = candidate_settings
            return process, settings, candidate_endpoint

        raise build_runtime_error(
            "port_conflict_exhausted",
            detail=str(last_conflict) if last_conflict is not None else None,
        )

    def _launch_managed_server_once(self, *, settings: RuntimeSettings, parsed: SplitResult) -> ProcessLike:
        binary = self._which_fn("llama-server")
        if not binary:
            raise build_runtime_error(
                "binary_missing",
                detail="Binario `llama-server` nao encontrado no PATH.",
            )

        command = _build_launch_command(binary=binary, settings=settings, port=parsed.port)
        try:
            process = self._launch_process(
                tuple(command),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except OSError as error:
            if _is_port_conflict(error):
                raise
            raise build_runtime_error("startup_timeout", detail=str(error)) from error
        deadline = time.monotonic() + self._startup_timeout_seconds

        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise build_runtime_error(
                    "startup_timeout",
                    detail="Processo `llama-server` encerrou durante o startup.",
                )
            if self._is_runtime_ready(endpoint_url=settings.endpoint_url, model_id=settings.model_id):
                return process
            self._sleep_fn(self._startup_probe_interval_seconds)

        raise build_runtime_error("startup_timeout", detail="Timeout aguardando readiness do llama.cpp.")

    def _attempt_single_restart(
        self,
        *,
        state: ServerLifecycleState,
        settings: RuntimeSettings,
    ) -> tuple[ServerLifecycleState, RuntimeSettings] | None:
        if state.restart_count >= self._restart_limit:
            return None

        restart_settings = settings.model_copy(update={"endpoint_url": state.endpoint_url})
        try:
            process, active_settings, active_endpoint = self._launch_managed_with_fallback(
                settings=restart_settings
            )
        except Exception:
            return None

        restarted_state = ServerLifecycleState(
            ownership="managed",
            pid=process.pid,
            process_group_id=_process_group_id(process.pid),
            endpoint_url=active_settings.endpoint_url,
            port=active_endpoint.port,
            model_id=active_settings.model_id,
            started_at=self._now_iso(),
            last_transition_reason="auto_restart_after_crash",
            crash_count=state.crash_count + 1,
            restart_count=state.restart_count + 1,
        )
        self._state_saver(restarted_state)
        return restarted_state, active_settings

    def _resolve_external_reuse_decision(
        self,
        *,
        allow_external_reuse: bool | None,
        external_reuse_decision: ExternalReuseDecision | None,
        non_interactive: bool,
        settings: RuntimeSettings,
        parsed: SplitResult,
    ) -> bool:
        if allow_external_reuse is not None:
            return allow_external_reuse

        status = LifecycleStatus(
            lifecycle_state="running",
            ownership="external",
            endpoint_url=settings.endpoint_url,
            port=parsed.port,
            model_id=settings.model_id,
            pid=None,
            process_group_id=None,
            uptime_seconds=None,
            ready=True,
            message="Servidor externo detectado.",
        )

        if external_reuse_decision is not None:
            return bool(external_reuse_decision(status))
        return not non_interactive

    def _build_stopped_status(self, *, settings: RuntimeSettings) -> LifecycleStatus:
        parsed = _parse_endpoint(settings.endpoint_url)
        return LifecycleStatus(
            lifecycle_state="stopped",
            ownership=None,
            endpoint_url=settings.endpoint_url,
            port=parsed.port,
            model_id=settings.model_id,
            pid=None,
            process_group_id=None,
            uptime_seconds=None,
            ready=False,
            message="Servidor nao esta em execucao.",
        )

    def _build_status(
        self,
        state: ServerLifecycleState,
        *,
        settings: RuntimeSettings,
        ready: bool | None = None,
        lifecycle_state: LifecycleState = "running",
        message: str | None = None,
        error_category: str | None = None,
        recovery_commands: tuple[str, ...] = (),
    ) -> LifecycleStatus:
        if ready is None:
            ready = self._is_runtime_ready(
                endpoint_url=state.endpoint_url,
                model_id=state.model_id,
            )

        return LifecycleStatus(
            lifecycle_state=lifecycle_state,
            ownership=state.ownership,
            endpoint_url=state.endpoint_url,
            port=state.port,
            model_id=state.model_id,
            pid=state.pid,
            process_group_id=state.process_group_id,
            uptime_seconds=_uptime_seconds(
                started_at=state.started_at,
                now=self._now_fn(),
            ),
            ready=ready,
            message=message,
            error_category=error_category,
            recovery_commands=recovery_commands,
        )

    def _is_runtime_ready(self, *, endpoint_url: str, model_id: str) -> bool:
        client = self._client_factory(endpoint_url)
        try:
            client.validate_runtime(model_id=model_id)
        except RuntimeDiagnosticError as error:
            if error.category in {"endpoint_offline", "timeout"}:
                return False
            raise
        except Exception:
            return False
        return True

    def _acquire_lock(self):
        return self._lock_acquirer(timeout_seconds=self._lock_timeout_seconds)

    def _now_iso(self) -> str:
        return self._now_fn().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_runtime_for_inference(
    *,
    lifecycle_service: ServerLifecycleService | None = None,
    non_interactive: bool = False,
    model_bootstrap_callback: ModelBootstrapCallback | None = None,
) -> EnsureRuntimeResult:
    service = lifecycle_service or ServerLifecycleService()
    settings = service._settings_loader()
    if not settings.model_id.strip():
        settings = _bootstrap_model_if_missing(
            service=service,
            settings=settings,
            callback=model_bootstrap_callback,
        )

    status = service.start_server(non_interactive=non_interactive, reason="inference_auto_start")
    health = service.check_health()
    if health.category == "model_missing":
        settings = _bootstrap_model_if_missing(
            service=service,
            settings=service._settings_loader(),
            callback=model_bootstrap_callback,
        )
        status = service.start_server(
            non_interactive=non_interactive,
            reason="inference_auto_start_retry",
        )
        health = service.check_health()

    if not health.ok:
        raise RuntimeDiagnosticError(
            category=health.category or "endpoint_offline",
            message=health.message,
            recovery_commands=health.recovery_commands,
        )
    settings = service._settings_loader()
    return EnsureRuntimeResult(settings=settings, status=status, health=health)


def _bootstrap_model_if_missing(
    *,
    service: ServerLifecycleService,
    settings: RuntimeSettings,
    callback: ModelBootstrapCallback | None,
) -> RuntimeSettings:
    if callback is None:
        raise build_runtime_error("model_missing", model_id=settings.model_id or "<modelo>")

    selected = callback(settings)
    if isinstance(selected, RuntimeSettings):
        updated_settings = selected
    elif isinstance(selected, str):
        model_id = selected.strip()
        if not model_id:
            raise build_runtime_error("model_missing", model_id="<modelo>")
        updated_settings = settings.model_copy(update={"model_id": model_id})
    else:
        raise build_runtime_error("model_missing", model_id="<modelo>")

    return service._settings_saver(updated_settings)


def _build_launch_command(*, binary: str, settings: RuntimeSettings, port: int) -> list[str]:
    parsed_source = _resolve_model_path(settings)
    parsed_endpoint = _parse_endpoint(settings.endpoint_url)
    host = parsed_endpoint.hostname or "127.0.0.1"

    command = [binary, "--host", host, "--port", str(port)]
    if parsed_source is not None:
        command.extend(["-m", parsed_source])
    command.extend(["--alias", settings.model_id])
    return command


def _resolve_model_path(settings: RuntimeSettings) -> str | None:
    try:
        target = parse_hf_target(settings.model_source)
    except ModelSourceValidationError:
        return None
    resolution = resolve_cached_model(target)
    return str(resolution.local_path)


def _endpoint_with_port(endpoint_url: str, *, port: int) -> str:
    parsed = urlsplit(endpoint_url)
    hostname = parsed.hostname
    if not parsed.scheme or not hostname:
        raise ValueError("endpoint_url invalido para lifecycle.")
    netloc = hostname if port in {80, 443} else f"{hostname}:{port}"
    return f"{parsed.scheme}://{netloc}{parsed.path or ''}"


def _parse_endpoint(endpoint_url: str) -> SplitResult:
    parsed = urlsplit(endpoint_url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("endpoint_url invalido para lifecycle.")
    port = parsed.port or 8080
    netloc = parsed.hostname if port in {80, 443} else f"{parsed.hostname}:{port}"
    return SplitResult(parsed.scheme, netloc, parsed.path or "", parsed.query, parsed.fragment)


def _process_group_id(pid: int) -> int | None:
    try:
        return os.getpgid(pid)
    except OSError:
        return None


def _kill_process(pid_or_group: int, is_group: bool) -> None:
    signal_type = signal.SIGTERM
    if is_group:
        os.killpg(pid_or_group, signal_type)
    else:
        os.kill(pid_or_group, signal_type)


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _uptime_seconds(*, started_at: str, now: datetime) -> int | None:
    try:
        started = datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None
    delta = now.astimezone(UTC) - started
    return max(int(delta.total_seconds()), 0)


def _is_port_conflict(error: OSError) -> bool:
    if error.errno in {errno.EADDRINUSE, 48, 98}:
        return True
    return "address already in use" in str(error).lower()


__all__ = [
    "EnsureRuntimeResult",
    "ExternalReuseDecision",
    "LifecycleHealth",
    "LifecycleStatus",
    "ModelBootstrapCallback",
    "ServerLifecycleService",
    "ensure_runtime_for_inference",
]
