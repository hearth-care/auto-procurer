"""Build xsource's forward-looking items into shared fleet Signals."""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from datetime import date as Date

from clonway_cockpit.signals.horizon import compose_horizon, scan_horizon
from clonway_cockpit.signals.model import Signal

from xsource.config import Config
from xsource.store.models import Request, Supplier
from xsource.wiring import build_stores

_WORKER = "xsource"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    with contextlib.suppress(ValueError):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def _parse_date(value: str | None) -> Date | None:
    if not value:
        return None
    with contextlib.suppress(ValueError):
        return Date.fromisoformat(value)
    return None


def _add_months(day: Date, months: int) -> Date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    month_lengths = [
        31,
        29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
    return Date(year, month, min(day.day, month_lengths[month - 1]))


def _signal(
    *,
    kind: str,
    title: str,
    detail: str,
    level: str,
    urgency: str,
    dedup_key: str,
    emitted_at: datetime,
    due_at: Date | None,
    capability_key: str | None,
    focus: str | None,
    source_id: str,
) -> Signal:
    return Signal(
        worker=_WORKER,
        kind=kind,
        title=title,
        detail=detail,
        level=level,
        urgency=urgency,
        capability_key=capability_key,
        focus=focus,
        dedup_key=dedup_key,
        emitted_at=emitted_at,
        due_at=due_at,
        source_ref=source_id,
        source_id=source_id,
    )


def build_chase_quote_signals(
    requests: Sequence[Request],
    *,
    today: Date,
    now: datetime,
    chase_after_days: int = 3,
) -> tuple[Signal, ...]:
    out = []
    threshold = now.astimezone(UTC) - timedelta(days=chase_after_days)
    for request in requests:
        if request.status != "open":
            continue
        outstanding = []
        for entry in request.shortlist:
            asked_at = _parse_datetime(entry.outreach.get("asked_at"))
            if not asked_at or asked_at > threshold:
                continue
            reply_status = str(entry.reply.get("status", "")).lower()
            if reply_status in {"quoted", "declined", "no"} or entry.reply.get("quote_amount"):
                continue
            outstanding.append(entry)
        if not outstanding:
            continue
        due_at = _parse_date(str(request.constraints.get("needed_by", "")))
        out.append(
            _signal(
                kind="action.required",
                title=f"Chase quotes - {request.raw_need}",
                detail=f"{len(outstanding)} supplier reply pending after {chase_after_days} days.",
                level="warn",
                urgency="high" if due_at and due_at <= today + timedelta(days=2) else "normal",
                dedup_key=f"xsource|chase|{request.id}",
                emitted_at=now,
                due_at=due_at,
                capability_key="request.list",
                focus=request.id,
                source_id=request.id,
            )
        )
    return tuple(out)


def build_recurring_service_signals(
    suppliers: Sequence[Supplier],
    requests: Sequence[Request] | None = None,
    *,
    today: Date,
    now: datetime,
    horizon_days: int = 21,
) -> tuple[Signal, ...]:
    open_reorder_ids = {
        r.constraints.get("reorder_supplier_id")
        for r in (requests or [])
        if r.status == "open" and r.constraints.get("reorder_supplier_id")
    }
    out = []
    for supplier in suppliers:
        if not supplier.recurs_every_months or not supplier.last_used:
            continue
        if supplier.id in open_reorder_ids:
            continue
        last_used = _parse_date(supplier.last_used)
        if last_used is None:
            continue
        due_at = _add_months(last_used, supplier.recurs_every_months)
        if today <= due_at <= today + timedelta(days=horizon_days):
            out.append(
                _signal(
                    kind="deadline.approaching",
                    title=f"{supplier.name} recurring service due",
                    detail=f"{supplier.name} is due around {due_at.isoformat()}.",
                    level="warn",
                    urgency="normal",
                    dedup_key=f"xsource|recur|{supplier.id}",
                    emitted_at=now,
                    due_at=due_at,
                    capability_key="request.reorder",
                    focus=supplier.id,
                    source_id=supplier.id,
                )
            )
    return tuple(out)


def build_watcher_health_signals(
    requests: Sequence[Request],
    *,
    today: Date,
    now: datetime,
    stale_after: timedelta = timedelta(hours=2),
) -> tuple[Signal, ...]:
    live_threads = [
        entry.outreach.get("thread_id")
        for request in requests
        if request.status == "open"
        for entry in request.shortlist
        if entry.outreach.get("thread_id")
    ]
    if not live_threads:
        return ()
    last_checked = [
        parsed
        for request in requests
        if request.status == "open"
        for parsed in [_parse_datetime(request.watcher.get("last_checked_at"))]
        if parsed is not None
    ]
    if not last_checked or max(last_checked) <= now.astimezone(UTC) - stale_after:
        return (
            _signal(
                kind="anomaly.detected",
                title="xsource reply watcher stale",
                detail=f"{len(live_threads)} live outreach thread(s), watcher stale.",
                level="error",
                urgency="high",
                dedup_key="xsource|watcher",
                emitted_at=now,
                due_at=today,
                capability_key="doctor",
                focus="watcher",
                source_id="watcher",
            ),
        )
    return ()


def build_store_offline_signals(
    requests: Sequence[Request],
    *,
    today: Date,
    now: datetime,
    store_offline: bool,
) -> tuple[Signal, ...]:
    if not store_offline:
        return ()
    open_requests = [r for r in requests if r.status == "open"]
    if not open_requests:
        return ()
    return (
        _signal(
            kind="anomaly.detected",
            title="xsource GCS store offline",
            detail=(
                f"{len(open_requests)} open request(s) — new data is not persisting."
                " Check GCS credentials and open xsource cockpit (Doctor screen)."
            ),
            level="error",
            urgency="high",
            dedup_key="xsource|store_offline",
            emitted_at=now,
            due_at=today,
            capability_key="doctor",
            focus="store",
            source_id="store",
        ),
    )


@scan_horizon
def scan_xsource_horizon(*, today: Date, now: datetime) -> Sequence[Signal]:
    cfg = Config.from_env()
    with contextlib.suppress(Exception):
        suppliers, requests = build_stores(cfg)
        request_records = requests.all()
        supplier_records = suppliers.all()
        store_offline = suppliers.offline or requests.offline
        return (
            *build_chase_quote_signals(
                request_records,
                today=today,
                now=now,
                chase_after_days=cfg.chase_after_days,
            ),
            *build_recurring_service_signals(
                supplier_records, request_records, today=today, now=now
            ),
            *build_watcher_health_signals(request_records, today=today, now=now),
            *build_store_offline_signals(
                request_records,
                today=today,
                now=now,
                store_offline=store_offline,
            ),
        )
    return ()


build_xsource_signals = compose_horizon(scan_xsource_horizon)
