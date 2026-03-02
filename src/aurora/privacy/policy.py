from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


class Phase1PolicyError(ValueError):
    """Raised when a Phase 1 local-only privacy policy is violated."""


def is_loopback_endpoint(endpoint_url: str) -> bool:
    """Return True when the endpoint points to localhost or loopback IPs."""
    parsed = urlparse(endpoint_url)
    host = parsed.hostname
    if not host:
        return False

    if host.lower() == "localhost":
        return True

    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_local_endpoint(endpoint_url: str, *, local_only: bool) -> None:
    """Enforce Phase 1 local-only endpoints with actionable pt-BR guidance."""
    if not local_only:
        return

    if is_loopback_endpoint(endpoint_url):
        return

    raise Phase1PolicyError(
        "Somente endpoints locais são permitidos na Fase 1. "
        "Use um endpoint com localhost ou 127.0.0.1."
    )

