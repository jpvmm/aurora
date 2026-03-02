from __future__ import annotations

import pytest

from aurora.privacy.policy import Phase1PolicyError, is_loopback_endpoint
from aurora.runtime.settings import RuntimeSettings, save_settings


def test_loopback_hosts_pass_local_only_validation():
    assert is_loopback_endpoint("http://localhost:11434") is True
    assert is_loopback_endpoint("http://127.0.0.1:8080/v1") is True


def test_non_local_endpoint_is_blocked_with_pt_br_error(tmp_path, monkeypatch):
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "global-config"))

    cloud_settings = RuntimeSettings(
        endpoint_url="https://api.openai.com/v1",
        local_only=True,
    )

    with pytest.raises(Phase1PolicyError, match="Somente endpoints locais"):
        save_settings(cloud_settings)
