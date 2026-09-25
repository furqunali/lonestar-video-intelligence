"""Store-local time helpers (design rule #5).

All event timestamps are normalized to the store's local timezone
(America/Chicago) and are tz-aware. We NEVER emit +05:00 (Pakistan office)
on a US-store event.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def store_tz(tz_name: str = "America/Chicago") -> ZoneInfo:
    return ZoneInfo(tz_name)


def now_store(tz_name: str = "America/Chicago") -> datetime:
    """Current time as a tz-aware datetime in the store's local zone."""
    return datetime.now(store_tz(tz_name))


def to_store_local(dt: datetime, tz_name: str = "America/Chicago") -> datetime:
    """Normalize any datetime to store-local, tz-aware.

    Naive datetimes are assumed to already be UTC (a safe, explicit default);
    aware datetimes are converted. Result always carries the store offset.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(store_tz(tz_name))


def ensure_store_aware(dt: datetime, tz_name: str = "America/Chicago") -> datetime:
    """Make a datetime store-local and tz-aware, treating naive values as
    ALREADY store-local wall time.

    This is the correct reading for timestamps round-tripped through SQLite
    (which drops tzinfo): our events are stored in store-local time, so a naive
    "18:00" means 18:00 Central — not 18:00 UTC. Aware inputs are converted.
    """
    tz = store_tz(tz_name)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)
