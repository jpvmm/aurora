from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Literal

from aurora.runtime.paths import ensure_config_dir, get_kb_state_path

SchedulerRunReason = Literal["scheduled", "catch_up"]


@dataclass(frozen=True)
class KBSchedulerState:
    """Persisted scheduler bookkeeping for deterministic due/catch-up behavior."""

    last_planned_slot_utc: str | None = None
    last_run_started_at_utc: str | None = None
    last_run_completed_at_utc: str | None = None
    last_run_ok: bool | None = None
    last_run_reason: SchedulerRunReason | None = None
    last_error_category: str | None = None


@dataclass(frozen=True)
class KBSchedulerStateError(Exception):
    """Typed scheduler-state loading error with actionable recovery guidance."""

    message: str
    recovery_commands: tuple[str, ...]

    def __str__(self) -> str:
        commands = "\n".join(f"- {command}" for command in self.recovery_commands)
        return f"{self.message}\nComandos de recuperacao:\n{commands}"


def load_kb_scheduler_state() -> KBSchedulerState:
    """Load persisted scheduler state or return default when absent."""
    path = get_kb_state_path()
    if not path.exists():
        return KBSchedulerState()

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


def save_kb_scheduler_state(state: KBSchedulerState) -> KBSchedulerState:
    """Persist scheduler state using deterministic JSON serialization."""
    ensure_config_dir()
    normalized = _state_from_payload(asdict(state))
    serialized = json.dumps(asdict(normalized), ensure_ascii=False, indent=2, sort_keys=True)
    get_kb_state_path().write_text(f"{serialized}\n", encoding="utf-8")
    return normalized


def clear_kb_scheduler_state() -> None:
    """Delete persisted scheduler state if present."""
    path = get_kb_state_path()
    if path.exists():
        path.unlink()


def _state_from_payload(payload: dict[str, Any]) -> KBSchedulerState:
    last_planned_slot_utc = _validate_optional_non_empty_str(
        payload.get("last_planned_slot_utc"),
        field="last_planned_slot_utc",
    )
    last_run_started_at_utc = _validate_optional_non_empty_str(
        payload.get("last_run_started_at_utc"),
        field="last_run_started_at_utc",
    )
    last_run_completed_at_utc = _validate_optional_non_empty_str(
        payload.get("last_run_completed_at_utc"),
        field="last_run_completed_at_utc",
    )
    last_run_ok = _validate_optional_bool(payload.get("last_run_ok"), field="last_run_ok")
    last_run_reason = _validate_optional_run_reason(
        payload.get("last_run_reason"),
        field="last_run_reason",
    )
    last_error_category = _validate_optional_non_empty_str(
        payload.get("last_error_category"),
        field="last_error_category",
    )

    return KBSchedulerState(
        last_planned_slot_utc=last_planned_slot_utc,
        last_run_started_at_utc=last_run_started_at_utc,
        last_run_completed_at_utc=last_run_completed_at_utc,
        last_run_ok=last_run_ok,
        last_run_reason=last_run_reason,
        last_error_category=last_error_category,
    )


def _validate_optional_non_empty_str(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"Campo '{field}' deve ser texto nao vazio ou null.")


def _validate_optional_bool(value: Any, *, field: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"Campo '{field}' deve ser booleano ou null.")


def _validate_optional_run_reason(value: Any, *, field: str) -> SchedulerRunReason | None:
    if value is None:
        return None
    if value in {"scheduled", "catch_up"}:
        return value
    raise ValueError(f"Campo '{field}' deve ser 'scheduled', 'catch_up' ou null.")


def _build_state_error(*, path: str, detail: str) -> KBSchedulerStateError:
    return KBSchedulerStateError(
        message=(
            "Estado do scheduler KB corrompido ou desatualizado. "
            f"Arquivo: {path}. Detalhe: {detail}"
        ),
        recovery_commands=(
            "aurora kb scheduler status",
            f"rm \"{path}\"",
        ),
    )


__all__ = [
    "KBSchedulerState",
    "KBSchedulerStateError",
    "SchedulerRunReason",
    "clear_kb_scheduler_state",
    "load_kb_scheduler_state",
    "save_kb_scheduler_state",
]
