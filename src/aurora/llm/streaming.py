"""SSE streaming parser for llama.cpp /v1/chat/completions endpoint."""
from __future__ import annotations

import json
from typing import Callable
from urllib.request import Request, urlopen

STREAM_TIMEOUT_SECONDS = 120  # Separate from health probe timeout (3s) per Pitfall 4


def stream_chat_completions(
    *,
    endpoint_url: str,
    model_id: str,
    messages: list[dict[str, str]],
    on_token: Callable[[str], None],
    timeout_seconds: float = STREAM_TIMEOUT_SECONDS,
    urlopen_fn: Callable | None = None,
) -> str:
    """Stream tokens from llama.cpp /v1/chat/completions. Returns full response text."""
    _urlopen = urlopen_fn or urlopen
    body = json.dumps({"model": model_id, "messages": messages, "stream": True}).encode("utf-8")
    request = Request(
        f"{endpoint_url.rstrip('/')}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    full_response: list[str] = []
    with _urlopen(request, timeout=timeout_seconds) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            delta = chunk["choices"][0]["delta"]
            if content := delta.get("content"):
                on_token(content)
                full_response.append(content)
    return "".join(full_response)


def chat_completion_sync(
    *,
    endpoint_url: str,
    model_id: str,
    messages: list[dict[str, str]],
    timeout_seconds: float = 30,
    urlopen_fn: Callable | None = None,
) -> str:
    """Non-streaming chat completion for short prompts like intent classification."""
    _urlopen = urlopen_fn or urlopen
    body = json.dumps({"model": model_id, "messages": messages, "stream": False}).encode("utf-8")
    request = Request(
        f"{endpoint_url.rstrip('/')}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with _urlopen(request, timeout=timeout_seconds) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


__all__ = ["stream_chat_completions", "chat_completion_sync", "STREAM_TIMEOUT_SECONDS"]
