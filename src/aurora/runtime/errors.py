from __future__ import annotations

import socket
from dataclasses import dataclass
from typing import Literal
from urllib.error import HTTPError, URLError

RuntimeErrorCategory = Literal[
    "endpoint_offline",
    "timeout",
    "model_missing",
    "invalid_token",
    "confirmation_required",
    "binary_missing",
    "port_conflict_exhausted",
    "startup_timeout",
    "lock_timeout",
    "crash_restart_failed",
]


@dataclass
class RuntimeDiagnosticError(Exception):
    """Typed runtime diagnostic error with pt-BR guidance."""

    category: RuntimeErrorCategory
    message: str
    recovery_commands: tuple[str, ...]

    def __str__(self) -> str:
        return self.message


def build_runtime_error(
    category: RuntimeErrorCategory,
    *,
    model_id: str | None = None,
    available_models: tuple[str, ...] = (),
    detail: str | None = None,
) -> RuntimeDiagnosticError:
    if category == "endpoint_offline":
        message = "Nao foi possivel conectar ao endpoint local llama.cpp."
        commands = (
            "aurora model set --endpoint http://127.0.0.1:8080",
            "aurora doctor",
        )
    elif category == "timeout":
        message = "Timeout ao validar o runtime local."
        commands = (
            "aurora doctor",
            "aurora model set --endpoint http://127.0.0.1:8080",
        )
    elif category == "model_missing":
        expected_model = model_id or "<modelo>"
        message = f"O modelo '{expected_model}' nao foi encontrado no endpoint local."
        if available_models:
            listed = ", ".join(available_models[:5])
            message = f"{message} Modelos ativos: {listed}"
        commands = (
            f"aurora model set --model {expected_model}",
            "aurora doctor",
        )
    elif category == "confirmation_required":
        message = "Acao bloqueada: confirmacao explicita obrigatoria para continuar."
        commands = (
            "aurora model start --yes",
            "aurora model start --force",
        )
    elif category == "binary_missing":
        message = "Nao foi possivel iniciar o runtime local: binario `llama-server` nao encontrado."
        commands = (
            "aurora doctor",
            "aurora model start",
        )
    elif category == "port_conflict_exhausted":
        message = "Nao foi possivel iniciar o runtime: portas candidatas estao ocupadas."
        commands = (
            "aurora model set --endpoint http://127.0.0.1:8081",
            "aurora model start",
        )
    elif category == "startup_timeout":
        message = "Timeout ao aguardar inicializacao do llama.cpp."
        commands = (
            "aurora model status",
            "aurora model start",
        )
    elif category == "lock_timeout":
        message = "Nao foi possivel obter lock de ciclo de vida para start/stop."
        commands = (
            "aurora model status",
            "aurora model start",
        )
    elif category == "crash_restart_failed":
        message = "Falha ao recuperar runtime gerenciado apos queda inesperada."
        commands = (
            "aurora model status",
            "aurora model start",
        )
    else:
        message = "Falha de autenticacao no endpoint local (token invalido ou ausente)."
        commands = (
            "aurora model set --private --token <token>",
            "aurora doctor",
        )

    if detail:
        message = f"{message} Detalhe: {detail}"

    return RuntimeDiagnosticError(
        category=category,
        message=message,
        recovery_commands=commands,
    )


def classify_runtime_error(
    error: Exception,
    *,
    model_id: str | None = None,
) -> RuntimeDiagnosticError:
    if isinstance(error, RuntimeDiagnosticError):
        return error

    if isinstance(error, HTTPError):
        if error.code in {401, 403}:
            return build_runtime_error("invalid_token", model_id=model_id)
        if error.code in {408, 504}:
            return build_runtime_error("timeout", model_id=model_id)
        return build_runtime_error("endpoint_offline", model_id=model_id, detail=str(error))

    if isinstance(error, (TimeoutError, socket.timeout)):
        return build_runtime_error("timeout", model_id=model_id, detail=str(error))

    if isinstance(error, URLError):
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            return build_runtime_error("timeout", model_id=model_id, detail=str(error.reason))
        return build_runtime_error("endpoint_offline", model_id=model_id, detail=str(error.reason))

    if isinstance(error, OSError):
        if isinstance(error, TimeoutError):
            return build_runtime_error("timeout", model_id=model_id, detail=str(error))
        return build_runtime_error("endpoint_offline", model_id=model_id, detail=str(error))

    return build_runtime_error("endpoint_offline", model_id=model_id, detail=str(error))


__all__ = [
    "RuntimeDiagnosticError",
    "RuntimeErrorCategory",
    "build_runtime_error",
    "classify_runtime_error",
]
