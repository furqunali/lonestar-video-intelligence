"""Event persistence (spec §9.4, design rules #4 & #10).

- Schema-validated: only Pydantic-valid Events are written to `events`.
- Dead-letter: raw payloads that fail validation go to `dead_letter` with the
  error — never silently dropped.
- Idempotent: writes dedupe on the deterministic event_id, so re-processing the
  same dump never double-counts.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.engine import Engine

from avip.common.logging import get_logger
from avip.common.timeutil import now_store
from avip.db.models import dead_letter, events as events_tbl
from avip.events.schema import Event

log = get_logger("events.store")


def event_to_row(ev: Event) -> dict:
    """Map an Event to an `events` table row (schema uses ts_start/ts_end)."""
    return {
        "event_id": ev.event_id,
        "schema_version": ev.schema_version,
        "location_id": ev.location_id,
        "camera_id": ev.camera_id,
        "ts_start": ev.timestamp_start,
        "ts_end": ev.timestamp_end,
        "event_type": ev.event_type,
        "track_id": ev.track_id,
        "marker_code": ev.marker_code,
        "zone": ev.zone,
        "dwell_seconds": ev.dwell_seconds,
        "confidence": ev.confidence,
        "camera_health": ev.camera_health.model_dump(),
        "employee_id": ev.employee_id,
        "evidence_uri": ev.evidence_uri,
        "triage_status": ev.triage_status,
    }


def _existing_ids(conn, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    rows = conn.execute(
        select(events_tbl.c.event_id).where(events_tbl.c.event_id.in_(ids))
    ).scalars().all()
    return set(rows)


def persist_events(engine: Engine, evs: list[Event]) -> int:
    """Insert events, skipping any whose event_id already exists (idempotent).

    Returns the number of NEW rows written.
    """
    if not evs:
        return 0
    # De-dupe within the batch too (same id can recur across overlapping clips).
    by_id: dict[str, Event] = {e.event_id: e for e in evs}
    with engine.begin() as conn:
        existing = _existing_ids(conn, list(by_id))
        new_rows = [event_to_row(e) for eid, e in by_id.items() if eid not in existing]
        if new_rows:
            conn.execute(events_tbl.insert(), new_rows)
    log.info("persisted_events", written=len(new_rows), skipped=len(by_id) - len(new_rows))
    return len(new_rows)


def dead_letter_raw(engine: Engine, raw: dict, error: str) -> None:
    with engine.begin() as conn:
        conn.execute(dead_letter.insert().values(
            raw=raw, error=error, created_at=now_store(),
        ))


def store_raw_events(engine: Engine, raw_events: list[dict]) -> tuple[int, int]:
    """Validate raw event dicts; valid -> events (idempotent), invalid -> dead_letter.

    Returns (written, dead_lettered).
    """
    valid: list[Event] = []
    dead = 0
    for raw in raw_events:
        try:
            valid.append(Event.model_validate(raw))
        except ValidationError as exc:
            dead_letter_raw(engine, raw, str(exc))
            dead += 1
            log.warning("event_dead_lettered", error=str(exc).splitlines()[0])
    written = persist_events(engine, valid)
    return written, dead
