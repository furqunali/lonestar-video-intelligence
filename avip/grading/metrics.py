"""Deterministic, camera-visible metric functions (spec §9.6, Table 3).

These functions — never the LLM — compute every number a grade is built from.
Each is a pure function of validated events + the shift window, so a grade is
reproducible from stored events + config (design rule #2).

Only camera-measurable metrics are graded (cash/inventory are out of scope).
"""
from __future__ import annotations

from datetime import datetime

from avip.common.timeutil import ensure_store_aware


def covered_seconds(intervals: list[tuple[datetime, datetime]],
                    win_start: datetime, win_end: datetime,
                    tz_name: str = "America/Chicago") -> float:
    """Total seconds covered by the UNION of intervals, clipped to the window.

    Overlapping presence intervals are merged so a person is never double-counted.
    All datetimes are normalized to store-local first (naive == store-local).
    """
    ws = ensure_store_aware(win_start, tz_name)
    we = ensure_store_aware(win_end, tz_name)
    clipped = []
    for s, e in intervals:
        s2 = max(ensure_store_aware(s, tz_name), ws)
        e2 = min(ensure_store_aware(e, tz_name), we)
        if e2 > s2:
            clipped.append((s2, e2))
    clipped.sort()
    total = 0.0
    cur_s = cur_e = None
    for s, e in clipped:
        if cur_s is None:
            cur_s, cur_e = s, e
        elif s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += (cur_e - cur_s).total_seconds()
            cur_s, cur_e = s, e
    if cur_s is not None:
        total += (cur_e - cur_s).total_seconds()
    return total


def shift_seconds(win_start: datetime, win_end: datetime,
                  tz_name: str = "America/Chicago") -> float:
    return max(0.0, (ensure_store_aware(win_end, tz_name)
                     - ensure_store_aware(win_start, tz_name)).total_seconds())


def zone_presence_pct(events: list[dict], zone: str,
                      win_start: datetime, win_end: datetime) -> float:
    """% of the shift the person was present in ``zone`` (register/floor/post)."""
    total = shift_seconds(win_start, win_end)
    if total <= 0:
        return 0.0
    intervals = [(e["ts_start"], e["ts_end"]) for e in events
                 if e.get("zone") == zone]
    return round(100.0 * covered_seconds(intervals, win_start, win_end) / total, 2)


def sweep_interval_hours(events: list[dict], win_start: datetime,
                         win_end: datetime) -> float:
    """Average hours between housekeeping sweep passes over the shift."""
    sweeps = sorted(e["ts_start"] for e in events
                    if e.get("event_type") == "sweep_pass")
    hours = shift_seconds(win_start, win_end) / 3600.0
    if len(sweeps) < 1 or hours <= 0:
        return float("inf")            # no sweeps -> worst cadence
    return round(hours / len(sweeps), 3)


# --- metric registry: rubric metric name -> callable(events, start, end) ---
def compute_metric(metric: str, events: list[dict], zone: str,
                   win_start: datetime, win_end: datetime) -> float:
    if metric in ("register_attended_pct", "floor_presence_pct", "post_coverage_pct"):
        return zone_presence_pct(events, zone, win_start, win_end)
    if metric == "sweep_interval_hours":
        return sweep_interval_hours(events, win_start, win_end)
    raise ValueError(f"unknown metric: {metric!r}")


def score_for(metric: str, value: float, target: float) -> float:
    """Map a raw metric value to a 0..100 score against its target.

    Percent metrics: higher is better. sweep_interval_hours: lower is better.
    """
    if metric == "sweep_interval_hours":
        if value <= 0 or value == float("inf"):
            return 0.0
        return round(min(100.0, target / value * 100.0), 2)
    if target <= 0:
        return 0.0
    return round(min(100.0, value / target * 100.0), 2)
