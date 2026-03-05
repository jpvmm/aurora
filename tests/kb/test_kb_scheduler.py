from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from aurora.kb.scheduler import KBSchedulerService
from aurora.kb.service import KBServiceError
from aurora.runtime.settings import RuntimeSettings, load_settings, save_settings


@dataclass
class FakeKBService:
    fail: bool = False
    update_calls: int = 0

    def run_update(self) -> object:
        self.update_calls += 1
        if self.fail:
            raise KBServiceError(
                category="backend_apply_failed",
                message="falha update",
                recovery_commands=("aurora kb update",),
            )
        return object()


def test_scheduler_defaults_disabled_and_local_hour_present() -> None:
    settings = RuntimeSettings()

    assert settings.kb_scheduler_enabled is False
    assert settings.kb_scheduler_hour_local == 9


def test_scheduler_enable_disable_persists_operational_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(RuntimeSettings(kb_vault_path="/vault"))
    fake_service = FakeKBService()
    scheduler = KBSchedulerService(kb_service_factory=lambda: fake_service)

    before = scheduler.status(now=datetime(2026, 3, 5, 12, 0, tzinfo=UTC))
    assert before.enabled is False

    enabled = scheduler.enable(hour_local=7, now=datetime(2026, 3, 5, 12, 0, tzinfo=UTC))
    assert enabled.enabled is True
    assert enabled.local_hour == 7
    assert load_settings().kb_scheduler_enabled is True
    assert load_settings().kb_scheduler_hour_local == 7

    disabled = scheduler.disable(now=datetime(2026, 3, 5, 12, 30, tzinfo=UTC))
    assert disabled.enabled is False
    assert load_settings().kb_scheduler_enabled is False


def test_run_due_executes_one_catch_up_for_missed_slot(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(
        RuntimeSettings(
            kb_vault_path="/vault",
            kb_scheduler_enabled=True,
            kb_scheduler_hour_local=9,
        )
    )
    fake_service = FakeKBService()
    scheduler = KBSchedulerService(kb_service_factory=lambda: fake_service)
    now = datetime(2026, 3, 5, 15, 0, tzinfo=UTC)

    first = scheduler.run_due(now=now)
    second = scheduler.run_due(now=now)

    assert first.ran is True
    assert first.reason == "catch_up"
    assert first.success is True
    assert second.ran is False
    assert fake_service.update_calls == 1


def test_run_due_records_failed_execution_without_repeating_same_slot(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(
        RuntimeSettings(
            kb_vault_path="/vault",
            kb_scheduler_enabled=True,
            kb_scheduler_hour_local=9,
        )
    )
    fake_service = FakeKBService(fail=True)
    scheduler = KBSchedulerService(kb_service_factory=lambda: fake_service)
    now = datetime(2026, 3, 5, 15, 0, tzinfo=UTC)

    first = scheduler.run_due(now=now)
    second = scheduler.run_due(now=now)
    status = scheduler.status(now=now)

    assert first.ran is True
    assert first.success is False
    assert second.ran is False
    assert fake_service.update_calls == 1
    assert status.last_run_ok is False
    assert status.last_error_category == "backend_apply_failed"


def test_status_next_due_respects_local_timezone_hour(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AURORA_CONFIG_DIR", str(tmp_path / "config"))
    save_settings(
        RuntimeSettings(
            kb_vault_path="/vault",
            kb_scheduler_enabled=True,
            kb_scheduler_hour_local=9,
        )
    )
    scheduler = KBSchedulerService(
        kb_service_factory=lambda: FakeKBService(),
        local_timezone=ZoneInfo("America/New_York"),
    )
    now = datetime(2026, 3, 8, 11, 0, tzinfo=UTC)

    status = scheduler.status(now=now)

    assert status.next_due_at == datetime(2026, 3, 8, 13, 0, tzinfo=UTC)
    assert status.catch_up_eligible is False

