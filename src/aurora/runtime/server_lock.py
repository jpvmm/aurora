from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4

from aurora.runtime.paths import ensure_config_dir, get_server_lock_path


@dataclass(frozen=True)
class LifecycleLockError(Exception):
    """Lock acquisition failure with actionable recovery guidance."""

    message: str
    recovery_commands: tuple[str, ...]

    def __str__(self) -> str:
        commands = "\n".join(f"- {command}" for command in self.recovery_commands)
        return f"{self.message}\nComandos de recuperacao:\n{commands}"


@contextmanager
def acquire_lifecycle_lock(
    *,
    timeout_seconds: float = 5.0,
    poll_interval: float = 0.1,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Iterator[Path]:
    """Acquire global lifecycle transition lock across terminals."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds deve ser maior que zero.")
    if poll_interval <= 0:
        raise ValueError("poll_interval deve ser maior que zero.")

    ensure_config_dir()
    lock_path = get_server_lock_path()
    token = uuid4().hex
    deadline = time.monotonic() + timeout_seconds

    while True:
        if _try_create_lock(lock_path, token=token):
            break

        if _reclaim_stale_lock(lock_path):
            continue

        if time.monotonic() >= deadline:
            raise _build_timeout_error(lock_path=lock_path, timeout_seconds=timeout_seconds)

        sleep_fn(poll_interval)

    try:
        yield lock_path
    finally:
        _release_lock(lock_path, token=token)


def _try_create_lock(lock_path: Path, *, token: str) -> bool:
    lock_payload = {
        "pid": os.getpid(),
        "process_group_id": _current_process_group_id(),
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "token": token,
    }
    serialized = json.dumps(lock_payload, ensure_ascii=False, indent=2, sort_keys=True)

    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(lock_path, flags, 0o600)
    except FileExistsError:
        return False

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"{serialized}\n")
    return True


def _reclaim_stale_lock(lock_path: Path) -> bool:
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return True
    except (json.JSONDecodeError, OSError):
        return _remove_lock_file(lock_path)

    if not isinstance(payload, dict):
        return _remove_lock_file(lock_path)

    pid = _extract_positive_int(payload.get("pid"))
    process_group_id = _extract_positive_int(payload.get("process_group_id"))
    if pid is None and process_group_id is None:
        return _remove_lock_file(lock_path)

    pid_alive = _is_process_alive(pid) if pid is not None else False
    group_alive = _is_process_group_alive(process_group_id) if process_group_id is not None else False
    if pid_alive or group_alive:
        return False

    return _remove_lock_file(lock_path)


def _release_lock(lock_path: Path, *, token: str) -> None:
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    except (json.JSONDecodeError, OSError):
        _remove_lock_file(lock_path)
        return

    if not isinstance(payload, dict):
        _remove_lock_file(lock_path)
        return

    if payload.get("token") == token:
        _remove_lock_file(lock_path)


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _is_process_group_alive(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _current_process_group_id() -> int | None:
    try:
        return os.getpgid(0)
    except OSError:
        return None


def _extract_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _remove_lock_file(lock_path: Path) -> bool:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _build_timeout_error(*, lock_path: Path, timeout_seconds: float) -> LifecycleLockError:
    return LifecycleLockError(
        message=(
            "Nao foi possivel obter o lock de ciclo de vida do servidor. "
            f"Tempo limite atingido ({timeout_seconds:.2f}s). "
            "Outro terminal pode estar executando start/stop neste momento."
        ),
        recovery_commands=(
            "aurora model status",
            f"rm \"{lock_path}\"  # use somente se nao houver processo ativo",
        ),
    )


__all__ = ["LifecycleLockError", "acquire_lifecycle_lock"]
