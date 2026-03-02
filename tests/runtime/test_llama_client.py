from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from aurora.runtime.errors import RuntimeDiagnosticError, classify_runtime_error
from aurora.runtime.llama_client import LlamaRuntimeClient


def _http_error(code: int) -> HTTPError:
    return HTTPError(
        url="http://127.0.0.1:8080/health",
        code=code,
        msg="error",
        hdrs=None,
        fp=BytesIO(b"{}"),
    )


def _build_client(
    responses: list[object],
    *,
    retries: int = 2,
) -> tuple[LlamaRuntimeClient, list[float]]:
    queue = list(responses)
    sleep_calls: list[float] = []

    def _fake_request(path: str, timeout_seconds: float) -> dict[str, object]:
        if not queue:
            raise AssertionError(f"No fake response available for path={path}")
        value = queue.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    client = LlamaRuntimeClient(
        endpoint_url="http://127.0.0.1:8080",
        timeout_seconds=0.01,
        max_loading_retries=retries,
        loading_retry_delay=0.0,
        request_json=_fake_request,
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
    )
    return client, sleep_calls


def test_classify_runtime_error_maps_timeout_to_category() -> None:
    error = classify_runtime_error(TimeoutError("late"))

    assert error.category == "timeout"
    assert "aurora doctor" in error.recovery_commands


def test_validate_runtime_classifies_endpoint_offline() -> None:
    client, _ = _build_client([URLError("connection refused")])

    with pytest.raises(RuntimeDiagnosticError) as raised:
        client.validate_runtime(model_id="Qwen3-8B-Q8_0")

    assert raised.value.category == "endpoint_offline"
    assert "aurora doctor" in raised.value.recovery_commands


def test_validate_runtime_classifies_invalid_token() -> None:
    client, _ = _build_client([_http_error(401)])

    with pytest.raises(RuntimeDiagnosticError) as raised:
        client.validate_runtime(model_id="Qwen3-8B-Q8_0")

    assert raised.value.category == "invalid_token"
    assert "aurora model set --private --token <token>" in raised.value.recovery_commands


def test_validate_runtime_requires_model_presence() -> None:
    client, _ = _build_client(
        [
            {"status": "ok"},
            {"data": [{"id": "Qwen3-8B-Q4"}]},
        ]
    )

    with pytest.raises(RuntimeDiagnosticError) as raised:
        client.validate_runtime(model_id="Qwen3-8B-Q8_0")

    assert raised.value.category == "model_missing"
    assert "Qwen3-8B-Q8_0" in raised.value.message
    assert "aurora model set --model Qwen3-8B-Q8_0" in raised.value.recovery_commands


def test_validate_runtime_retries_loading_health_before_timeout() -> None:
    client, sleep_calls = _build_client(
        [{"status": "loading"}, {"status": "loading"}, {"status": "loading"}],
        retries=2,
    )

    with pytest.raises(RuntimeDiagnosticError) as raised:
        client.validate_runtime(model_id="Qwen3-8B-Q8_0")

    assert raised.value.category == "timeout"
    assert "carregando" in raised.value.message.lower()
    assert len(sleep_calls) == 2


def test_validate_runtime_returns_models_when_ready() -> None:
    client, sleep_calls = _build_client(
        [
            {"status": "loading"},
            {"status": "ok"},
            {"data": [{"id": "Qwen3-8B-Q8_0"}, {"id": "Qwen3-8B-Q4"}]},
        ]
    )

    result = client.validate_runtime(model_id="Qwen3-8B-Q8_0")

    assert result.endpoint_state == "ready"
    assert result.model_id == "Qwen3-8B-Q8_0"
    assert result.available_models == ("Qwen3-8B-Q8_0", "Qwen3-8B-Q4")
    assert len(sleep_calls) == 1
