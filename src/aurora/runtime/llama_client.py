from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, Literal
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from aurora.runtime.errors import RuntimeDiagnosticError, build_runtime_error, classify_runtime_error

RequestJsonFn = Callable[[str, float], dict[str, object]]


@dataclass(frozen=True)
class RuntimeValidationResult:
    endpoint_state: Literal["ready"]
    model_id: str
    available_models: tuple[str, ...]


class LlamaRuntimeClient:
    """Minimal client for local llama.cpp health and model probes."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        timeout_seconds: float = 3.0,
        max_loading_retries: int = 2,
        loading_retry_delay: float = 1.0,
        request_json: RequestJsonFn | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.endpoint_url = endpoint_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_loading_retries = max_loading_retries
        self.loading_retry_delay = loading_retry_delay
        self._request_json = request_json or self._default_request_json
        self._sleep_fn = sleep_fn

    def validate_runtime(self, *, model_id: str) -> RuntimeValidationResult:
        self._probe_health()
        available_models = self._fetch_models()
        if model_id not in available_models:
            raise build_runtime_error(
                "model_missing",
                model_id=model_id,
                available_models=available_models,
            )

        return RuntimeValidationResult(
            endpoint_state="ready",
            model_id=model_id,
            available_models=available_models,
        )

    def _probe_health(self) -> None:
        loading_markers = {"loading", "starting", "initializing", "booting"}
        total_attempts = self.max_loading_retries + 1

        for attempt in range(total_attempts):
            try:
                payload = self._request_json("/health", self.timeout_seconds)
            except Exception as error:  # pragma: no cover - exercised via tests
                raise classify_runtime_error(error) from error

            status = str(payload.get("status", "")).lower()
            state = str(payload.get("state", "")).lower()
            marker = status or state

            if marker in {"ok", "ready", "healthy"} or marker == "":
                return

            if marker in loading_markers:
                if attempt < self.max_loading_retries:
                    self._sleep_fn(self.loading_retry_delay)
                    continue
                raise build_runtime_error(
                    "timeout",
                    detail="Servidor ainda carregando modelo no endpoint local.",
                )

            return

    def _fetch_models(self) -> tuple[str, ...]:
        try:
            payload = self._request_json("/v1/models", self.timeout_seconds)
        except Exception as error:  # pragma: no cover - exercised via tests
            raise classify_runtime_error(error) from error

        data = payload.get("data", [])
        if not isinstance(data, list):
            return ()

        models: list[str] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if isinstance(model_id, str) and model_id:
                models.append(model_id)
        return tuple(models)

    def _default_request_json(self, path: str, timeout_seconds: float) -> dict[str, object]:
        url = urljoin(f"{self.endpoint_url}/", path.lstrip("/"))
        request = Request(url, headers={"Accept": "application/json"})
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read()

        text = payload.decode("utf-8") if payload else ""
        if not text.strip():
            return {}

        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return {"data": parsed}


def validate_runtime(endpoint_url: str, model_id: str) -> RuntimeValidationResult:
    client = LlamaRuntimeClient(endpoint_url=endpoint_url)
    return client.validate_runtime(model_id=model_id)


__all__ = ["LlamaRuntimeClient", "RuntimeValidationResult", "validate_runtime"]
