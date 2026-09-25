"""M5 acceptance: TZ-normalized, schema-validated events from tracklets;
invalid payloads dead-lettered; idempotent persistence."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from avip.cv.process import Observation, Tracklet
from avip.db.models import dead_letter, events as events_tbl
from avip.events.builder import build_tracklet_events
from avip.events.schema import CameraHealth, Event, make_event_id
from avip.events.store import persist_events, store_raw_events

HEALTH = CameraHealth(liveness=True, clarity="OK", blur_score=250.0)
CLIP_START = datetime(2026, 9, 2, 23, 0, tzinfo=timezone.utc)   # -> 18:00 CDT


def _tracklet_in(zones_per_obs) -> Tracklet:
    tl = Tracklet(track_id=1)
    for i, zones in enumerate(zones_per_obs):
        tl.observations.append(
            Observation(i, i * (1 / 3), (120.0, 60.0, 200.0, 220.0), 0.9, set(zones))
        )
    return tl


# ------------------------------- schema ------------------------------------ #
def test_event_id_is_deterministic():
    a = make_event_id("0008", "CAM-0008-1", CLIP_START, "person_present", 1, "register")
    b = make_event_id("0008", "CAM-0008-1", CLIP_START, "person_present", 1, "register")
    assert a == b and len(a) == 32


def test_event_rejects_naive_timestamp():
    import pytest
    with pytest.raises(Exception):
        Event(location_id="0008", camera_id="CAM-0008-1",
              timestamp_start=datetime(2026, 9, 2, 18, 0),   # naive!
              timestamp_end=datetime(2026, 9, 2, 18, 1),
              event_type="person_present", confidence=0.9, camera_health=HEALTH)


# ------------------------------- builder ----------------------------------- #
def test_build_tracklet_events_types_and_tz():
    tl = _tracklet_in([{"register"}, {"register"}, {"register", "restricted"},
                       {"register", "restricted"}])
    evs = build_tracklet_events(
        "0028", "CAM-0028-1", tl, HEALTH, CLIP_START,
        nominal_dt=1 / 3, dwell_min_seconds=0.3,
        restricted_zones={"restricted"}, marker_code="ARUCO-9",
    )
    kinds = [e.event_type for e in evs]
    assert "person_present" in kinds
    assert "zone_dwell" in kinds
    assert "restricted_area_entry" in kinds
    for e in evs:
        # store-local Central offset, never Pakistan (+05:00)
        assert e.timestamp_start.utcoffset().total_seconds() == -5 * 3600
        assert e.marker_code == "ARUCO-9"
    entry = next(e for e in evs if e.event_type == "restricted_area_entry")
    assert entry.evidence_uri.startswith("s3://evidence/0028/CAM-0028-1/")
    assert entry.triage_status == "unreviewed"       # anomaly -> HITL


def test_dwell_below_min_is_dropped():
    tl = _tracklet_in([{"register"}])                # single sample => dwell = nominal_dt
    evs = build_tracklet_events(
        "0008", "CAM-0008-1", tl, HEALTH, CLIP_START,
        nominal_dt=1 / 3, dwell_min_seconds=5.0,     # high threshold
    )
    assert [e.event_type for e in evs] == ["person_present"]   # no zone_dwell


# -------------------------------- store ------------------------------------ #
def test_persist_is_idempotent(engine):
    tl = _tracklet_in([{"register"}, {"register"}, {"register"}])
    evs = build_tracklet_events("0008", "CAM-0008-1", tl, HEALTH, CLIP_START,
                                nominal_dt=1 / 3, dwell_min_seconds=0.3)
    n1 = persist_events(engine, evs)
    n2 = persist_events(engine, evs)              # same events again
    assert n1 == len(evs) and n1 > 0
    assert n2 == 0                                # nothing new -> no double count
    with engine.begin() as conn:
        total = conn.execute(select(func.count()).select_from(events_tbl)).scalar_one()
    assert total == n1


def test_invalid_payload_goes_to_dead_letter(engine):
    good = Event(
        location_id="0008", camera_id="CAM-0008-1",
        timestamp_start=datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc),
        timestamp_end=datetime(2026, 9, 2, 18, 1, tzinfo=timezone.utc),
        event_type="person_present", confidence=0.9, camera_health=HEALTH,
    ).model_dump(mode="json")

    bad = dict(good)
    bad["timestamp_start"] = "2026-09-02T18:00:00"     # naive -> validation fails
    bad["event_id"] = ""

    written, dead = store_raw_events(engine, [good, bad])
    assert written == 1
    assert dead == 1
    with engine.begin() as conn:
        dl = conn.execute(select(func.count()).select_from(dead_letter)).scalar_one()
    assert dl == 1
