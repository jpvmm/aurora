from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Literal

from aurora.runtime.paths import ensure_config_dir, get_server_state_path

ServerOwnership = Literal["managed", "external"]


@dataclass(frozen=True)
class ServerLifecycleState:
    """Persistent global lifecycle state shared across terminals."""

    ownership: ServerOwnership
    pid: int | None
    process_group_id: int | None
    endpoint_url: str
    port: int
    model_id: str
    started_at: str
    last_transition_reason: str
    crash_count: int = 0
    restart_count: int = 0


@dataclass(frozen=True)
class ServerStateError(Exception):
    """Typed state-loading diagnostic with actionable recovery commands."""

    message: str
    recovery_commands: tuple[str, ...]

    def __str__(self) -> str:
        commands = "\n".join(f"- {command}" for command in self.recovery_commands)
        return f"{self.message}\nComandos de recuperacao:\n{commands}"


def load_server_state() -> ServerLifecycleState | None:
    """Load global server lifecycle state or return None when absent."""
    path = get_server_state_path()
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise _build_state_error(path=str(path), detail=f"JSON invalido ({error.msg}).") from error
    except OSError as error:
        raise _build_state_error(path=str(path), detail=str(error)) from error

    if not isinstance(payload, dict):
        raise _build_state_error(path=str(path), detail="Esperado objeto JSON no arquivo de estado.")

    try:
        return _state_from_payload(payload)
    except ValueError as error:
        raise _build_state_error(path=str(path), detail=str(error)) from error


def save_server_state(state: ServerLifecycleState) -> ServerLifecycleState:
    """Persist global server lifecycle state using deterministic JSON output."""
    ensure_config_dir()
    normalized = _state_from_payload(asdict(state))
    serialized = json.dumps(asdict(normalized), ensure_ascii=False, indent=2, sort_keys=True)
    get_server_state_path().write_text(f"{serialized}\n", encoding="utf-8")
    return normalized


def clear_server_state() -> None:
    """Delete persisted lifecycle state if it exists."""
    path = get_server_state_path()
    if path.exists():
        path.unlink()


def _state_from_payload(payload: dict[str, Any]) -> ServerLifecycleState:
    ownership = _validate_ownership(payload.get("ownership"))
    pid = _validate_optional_pid(payload.get("pid"), field="pid")
    process_group_id = _validate_optional_pid(
        payload.get("process_group_id"),
        field="process_group_id",
    )
    endpoint_url = _validate_non_empty_str(payload.get("endpoint_url"), field="endpoint_url")
    model_id = _validate_non_empty_str(payload.get("model_id"), field="model_id")
    started_at = _validate_non_empty_str(payload.get("started_at"), field="started_at")
    last_transition_reason = _validate_non_empty_str(
        payload.get("last_transition_reason"),
        field="last_transition_reason",
    )
    port = _validate_port(payload.get("port"))
    crash_count = _validate_non_negative_int(payload.get("crash_count"), field="crash_count")
    restart_count = _validate_non_negative_int(payload.get("restart_count"), field="restart_count")

    return ServerLifecycleState(
        ownership=ownership,
        pid=pid,
        process_group_id=process_group_id,
        endpoint_url=endpoint_url,
        port=port,
        model_id=model_id,
        started_at=started_at,
        last_transition_reason=last_transition_reason,
        crash_count=crash_count,
        restart_count=restart_count,
    )


def _validate_ownership(value: Any) -> ServerOwnership:
    if value in {"managed", "external"}:
        return value
    raise ValueError("Campo 'ownership' deve ser 'managed' ou 'external'.")


def _validate_optional_pid(value: Any, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"Campo '{field}' deve ser inteiro positivo ou null.")
    return value


def _validate_non_empty_str(value: Any, *, field: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"Campo '{field}' deve ser texto nao vazio.")


def _validate_port(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Campo 'port' deve ser inteiro entre 1 e 65535.")
    if value < 1 or value > 65535:
        raise ValueError("Campo 'port' deve ser inteiro entre 1 e 65535.")
    return value


def _validate_non_negative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Campo '{field}' deve ser inteiro maior ou igual a zero.")
    return value


def _build_state_error(*, path: str, detail: str) -> ServerStateError:
    return ServerStateError(
        message=(
            "Estado de ciclo de vida corrompido ou desatualizado. "
            f"Arquivo: {path}. Detalhe: {detail} "
            "Use os comandos abaixo para diagnosticar e manter o estado corrigido."
        ),
        recovery_commands=(
            "aurora model status",
            f"rm \"{path}\"",
        ),
    )


__all__ = [
    "ServerLifecycleState",
    "ServerOwnership",
    "ServerStateError",
    "clear_server_state",
    "load_server_state",
    "save_server_state",
]
