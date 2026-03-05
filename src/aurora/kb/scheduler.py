from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, tzinfo
from typing import Callable, Literal

from aurora.kb.scheduler_state import (
    KBSchedulerState,
    SchedulerRunReason,
    load_kb_scheduler_state,
    save_kb_scheduler_state,
)
from aurora.kb.service import KBService, KBServiceError
from aurora.runtime.settings import RuntimeSettings, load_settings, save_settings

SchedulerIdleReason = Literal["disabled", "not_due"]


@dataclass(frozen=True)
class KBSchedulerStatus:
    enabled: bool
    local_hour: int
    timezone_name: str
    next_due_at: datetime | None
    catch_up_eligible: bool
    last_planned_slot_at: datetime | None
    last_run_started_at: datetime | None
    last_run_completed_at: datetime | None
    last_run_ok: bool | None
    last_run_reason: SchedulerRunReason | None
    last_error_category: str | None


@dataclass(frozen=True)
class KBSchedulerRunResult:
    ran: bool
    reason: SchedulerRunReason | SchedulerIdleReason
    success: bool | None
    slot_at: datetime | None
    error_category: str | None = None


class KBSchedulerService:
    """Scheduler lifecycle and due execution engine for daily KB updates."""

    def __init__(
        self,
        *,
        kb_service_factory: Callable[[], KBService] = KBService,
        load_settings_fn: Callable[[], RuntimeSettings] = load_settings,
        save_settings_fn: Callable[[RuntimeSettings], RuntimeSettings] = save_settings,
        load_state_fn: Callable[[], KBSchedulerState] = load_kb_scheduler_state,
        save_state_fn: Callable[[KBSchedulerState], KBSchedulerState] = save_kb_scheduler_state,
        local_timezone: tzinfo | None = None,
    ) -> None:
        self._kb_service_factory = kb_service_factory
        self._load_settings = load_settings_fn
        self._save_settings = save_settings_fn
        self._load_state = load_state_fn
        self._save_state = save_state_fn
        self._local_timezone = local_timezone

    def enable(self, *, hour_local: int | None = None, now: datetime | None = None) -> KBSchedulerStatus:
        now_utc = _normalize_utc(now)
        settings = self._load_settings()
        effective_hour = settings.kb_scheduler_hour_local if hour_local is None else hour_local

        updated_settings = self._save_settings(
            settings.model_copy(
                update={
                    "kb_scheduler_enabled": True,
                    "kb_scheduler_hour_local": effective_hour,
                }
            )
        )

        state = self._load_state()
        baseline_slot = self._latest_slot_at_or_before(now_utc=now_utc, hour_local=effective_hour)
        state_last_slot = _parse_optional_utc(state.last_planned_slot_utc)
        if state_last_slot is None or baseline_slot > state_last_slot:
            self._save_state(
                KBSchedulerState(
                    last_planned_slot_utc=_format_utc(baseline_slot),
                    last_run_started_at_utc=state.last_run_started_at_utc,
                    last_run_completed_at_utc=state.last_run_completed_at_utc,
                    last_run_ok=state.last_run_ok,
                    last_run_reason=state.last_run_reason,
                    last_error_category=state.last_error_category,
                )
            )

        return self._build_status(
            settings=updated_settings,
            state=self._load_state(),
            now_utc=now_utc,
        )

    def disable(self, *, now: datetime | None = None) -> KBSchedulerStatus:
        now_utc = _normalize_utc(now)
        settings = self._load_settings()
        updated_settings = self._save_settings(
            settings.model_copy(
                update={
                    "kb_scheduler_enabled": False,
                }
            )
        )
        return self._build_status(
            settings=updated_settings,
            state=self._load_state(),
            now_utc=now_utc,
        )

    def status(self, *, now: datetime | None = None) -> KBSchedulerStatus:
        return self._build_status(
            settings=self._load_settings(),
            state=self._load_state(),
            now_utc=_normalize_utc(now),
        )

    def run_due(self, *, now: datetime | None = None) -> KBSchedulerRunResult:
        now_utc = _normalize_utc(now)
        settings = self._load_settings()
        state = self._load_state()
        due_slot = self._compute_due_slot(settings=settings, state=state, now_utc=now_utc)

        if not settings.kb_scheduler_enabled:
            return KBSchedulerRunResult(
                ran=False,
                reason="disabled",
                success=None,
                slot_at=None,
            )

        if due_slot is None:
            return KBSchedulerRunResult(
                ran=False,
                reason="not_due",
                success=None,
                slot_at=None,
            )

        reason: SchedulerRunReason = "scheduled" if due_slot == now_utc else "catch_up"
        state_update = {
            "last_planned_slot_utc": _format_utc(due_slot),
            "last_run_started_at_utc": _format_utc(now_utc),
            "last_run_completed_at_utc": _format_utc(now_utc),
            "last_run_reason": reason,
        }

        try:
            self._kb_service_factory().run_update()
        except KBServiceError as error:
            self._save_state(
                state_from_update(
                    state=state,
                    update=state_update
                    | {
                        "last_run_ok": False,
                        "last_error_category": error.category,
                    },
                )
            )
            return KBSchedulerRunResult(
                ran=True,
                reason=reason,
                success=False,
                slot_at=due_slot,
                error_category=error.category,
            )

        self._save_state(
            state_from_update(
                state=state,
                update=state_update
                | {
                    "last_run_ok": True,
                    "last_error_category": None,
                },
            )
        )
        return KBSchedulerRunResult(
            ran=True,
            reason=reason,
            success=True,
            slot_at=due_slot,
        )

    def _build_status(
        self,
        *,
        settings: RuntimeSettings,
        state: KBSchedulerState,
        now_utc: datetime,
    ) -> KBSchedulerStatus:
        due_slot = self._compute_due_slot(settings=settings, state=state, now_utc=now_utc)
        latest_slot = self._latest_slot_at_or_before(now_utc=now_utc, hour_local=settings.kb_scheduler_hour_local)
        next_due_at = None
        catch_up_eligible = False

        if settings.kb_scheduler_enabled:
            if due_slot is not None:
                next_due_at = due_slot
                catch_up_eligible = due_slot < now_utc
            else:
                next_due_at = self._next_slot_after(
                    now_utc=now_utc,
                    hour_local=settings.kb_scheduler_hour_local,
                )

        local_tz = self._resolve_local_timezone(now_utc)
        return KBSchedulerStatus(
            enabled=settings.kb_scheduler_enabled,
            local_hour=settings.kb_scheduler_hour_local,
            timezone_name=getattr(local_tz, "key", str(local_tz)),
            next_due_at=next_due_at,
            catch_up_eligible=catch_up_eligible,
            last_planned_slot_at=_parse_optional_utc(state.last_planned_slot_utc),
            last_run_started_at=_parse_optional_utc(state.last_run_started_at_utc),
            last_run_completed_at=_parse_optional_utc(state.last_run_completed_at_utc),
            last_run_ok=state.last_run_ok,
            last_run_reason=state.last_run_reason,
            last_error_category=state.last_error_category,
        )

    def _compute_due_slot(
        self,
        *,
        settings: RuntimeSettings,
        state: KBSchedulerState,
        now_utc: datetime,
    ) -> datetime | None:
        if not settings.kb_scheduler_enabled:
            return None

        local_tz = self._resolve_local_timezone(now_utc)
        now_local = now_utc.astimezone(local_tz)
        today_slot_local = datetime.combine(
            now_local.date(),
            time(settings.kb_scheduler_hour_local, 0),
            tzinfo=local_tz,
        )
        today_slot_utc = today_slot_local.astimezone(UTC)
        latest_slot = self._latest_slot_at_or_before(
            now_utc=now_utc,
            hour_local=settings.kb_scheduler_hour_local,
        )
        state_last_slot = _parse_optional_utc(state.last_planned_slot_utc)

        if state_last_slot is None and now_local < today_slot_local:
            return None
        if state_last_slot is None:
            return latest_slot
        if latest_slot > state_last_slot:
            return latest_slot
        if latest_slot == today_slot_utc and now_utc == today_slot_utc:
            return latest_slot
        return None

    def _latest_slot_at_or_before(self, *, now_utc: datetime, hour_local: int) -> datetime:
        local_tz = self._resolve_local_timezone(now_utc)
        now_local = now_utc.astimezone(local_tz)
        slot_local = datetime.combine(now_local.date(), time(hour_local, 0), tzinfo=local_tz)
        if now_local < slot_local:
            slot_local = slot_local - timedelta(days=1)
        return slot_local.astimezone(UTC)

    def _next_slot_after(self, *, now_utc: datetime, hour_local: int) -> datetime:
        local_tz = self._resolve_local_timezone(now_utc)
        now_local = now_utc.astimezone(local_tz)
        slot_today_local = datetime.combine(now_local.date(), time(hour_local, 0), tzinfo=local_tz)
        if now_local < slot_today_local:
            return slot_today_local.astimezone(UTC)
        slot_next_day_local = datetime.combine(
            now_local.date() + timedelta(days=1),
            time(hour_local, 0),
            tzinfo=local_tz,
        )
        return slot_next_day_local.astimezone(UTC)

    def _resolve_local_timezone(self, now_utc: datetime) -> tzinfo:
        if self._local_timezone is not None:
            return self._local_timezone
        return now_utc.astimezone().tzinfo or UTC


def state_from_update(*, state: KBSchedulerState, update: dict[str, object]) -> KBSchedulerState:
    return KBSchedulerState(
        last_planned_slot_utc=_pick(update, "last_planned_slot_utc", state.last_planned_slot_utc),
        last_run_started_at_utc=_pick(update, "last_run_started_at_utc", state.last_run_started_at_utc),
        last_run_completed_at_utc=_pick(
            update,
            "last_run_completed_at_utc",
            state.last_run_completed_at_utc,
        ),
        last_run_ok=_pick(update, "last_run_ok", state.last_run_ok),
        last_run_reason=_pick(update, "last_run_reason", state.last_run_reason),
        last_error_category=_pick(update, "last_error_category", state.last_error_category),
    )


def _pick(update: dict[str, object], key: str, fallback: object) -> object:
    return update[key] if key in update else fallback


def _normalize_utc(now: datetime | None) -> datetime:
    current = now or datetime.now(tz=UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _parse_optional_utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "KBSchedulerRunResult",
    "KBSchedulerService",
    "KBSchedulerStatus",
]
