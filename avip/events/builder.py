"""Event builder (spec §9.4).

Converts CV outputs (health, tracklets, zones) into canonical, TZ-normalized,
schema-validated Events. This module grows across milestones:
  - M2: camera_health events
  - M5: person_present / zone_dwell / restricted_area_entry events + store

All timestamps are normalized to store-local (America/Chicago) here, so the
rest of the system never sees a Pakistan offset (design rule #5).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from avip.common.timeutil import to_store_local
from avip.events.schema import CameraHealth, Event
from avip.cv.process import Tracklet


def build_camera_health_event(
    location_id: str,
    camera_id: str,
    ts_start: datetime,
    ts_end: datetime,
    health: CameraHealth,
    tz_name: str = "America/Chicago",
    confidence: float = 1.0,
) -> Event:
    """Build a validated camera_health event (deterministic id, store-local ts)."""
    return Event(
        location_id=location_id,
        camera_id=camera_id,
        timestamp_start=to_store_local(ts_start, tz_name),
        timestamp_end=to_store_local(ts_end, tz_name),
        event_type="camera_health",
        confidence=confidence,
        camera_health=health,
        triage_status="auto",
    )


def _abs_ts(clip_start: datetime, seconds: float, tz_name: str) -> datetime:
    """Absolute store-local datetime for an offset (seconds) into the clip."""
    return to_store_local(clip_start + timedelta(seconds=seconds), tz_name)


def _zone_span(tracklet: Tracklet, zone: str) -> tuple[float, float]:
    ts = [o.ts_seconds for o in tracklet.observations if zone in o.zones]
    return (min(ts), max(ts)) if ts else (tracklet.ts_start, tracklet.ts_end)


def build_tracklet_events(
    location_id: str,
    camera_id: str,
    tracklet: Tracklet,
    health: CameraHealth,
    clip_start: datetime,
    *,
    nominal_dt: float,
    dwell_min_seconds: float = 1.0,
    restricted_zones: set[str] | None = None,
    marker_code: str | None = None,
    evidence_bucket: str = "evidence",
    tz_name: str = "America/Chicago",
) -> list[Event]:
    """Turn one tracklet into canonical events (person_present, zone_dwell,
    restricted_area_entry). Timestamps normalized to store-local; marker_code
    (from the M4 vote) attached; every event validated on construction.
    """
    restricted_zones = restricted_zones or set()
    events: list[Event] = []
    conf = float(tracklet.max_confidence)

    start_dt = _abs_ts(clip_start, tracklet.ts_start, tz_name)
    end_dt = _abs_ts(clip_start, tracklet.ts_end, tz_name)

    # 1) person_present — the person was on this camera for this span.
    events.append(Event(
        location_id=location_id, camera_id=camera_id,
        timestamp_start=start_dt, timestamp_end=end_dt,
        event_type="person_present", track_id=tracklet.track_id,
        marker_code=marker_code, confidence=conf, camera_health=health,
        triage_status="auto",
    ))

    # 2) zone_dwell — per zone with sufficient sustained presence.
    dwell = tracklet.zone_dwell(nominal_dt)
    for zone, secs in sorted(dwell.items()):
        if secs < dwell_min_seconds:
            continue
        z0, z1 = _zone_span(tracklet, zone)
        events.append(Event(
            location_id=location_id, camera_id=camera_id,
            timestamp_start=_abs_ts(clip_start, z0, tz_name),
            timestamp_end=_abs_ts(clip_start, z1, tz_name),
            event_type="zone_dwell", track_id=tracklet.track_id, zone=zone,
            dwell_seconds=secs, marker_code=marker_code, confidence=conf,
            camera_health=health, triage_status="auto",
        ))

        # 3) restricted_area_entry — theft/anomaly signal with an evidence clip.
        if zone in restricted_zones:
            z0_dt = _abs_ts(clip_start, z0, tz_name)
            evidence = (f"s3://{evidence_bucket}/{location_id}/{camera_id}/"
                        f"{int(z0_dt.timestamp())}.mp4")
            events.append(Event(
                location_id=location_id, camera_id=camera_id,
                timestamp_start=z0_dt,
                timestamp_end=_abs_ts(clip_start, z1, tz_name),
                event_type="restricted_area_entry", track_id=tracklet.track_id,
                zone=zone, dwell_seconds=secs, marker_code=marker_code,
                confidence=conf, camera_health=health, evidence_uri=evidence,
                triage_status="unreviewed",   # anomaly -> needs human review (HITL)
            ))

    return events
