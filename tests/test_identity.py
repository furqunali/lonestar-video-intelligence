"""M6 acceptance: layered identity resolution (marker + attendance + zone),
reissue-safe markers, confidence gate -> HITL, and DB attribution write-back."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from avip.common.config import CONFIG_DIR
from avip.db.models import events as events_tbl
from avip.db.models import hitl_queue
from avip.grading.identity import (
    TrackIdentityInput,
    attribute_identities,
    resolve_identity,
)
from avip.grading.roster import load_roster, seed_roster

ROSTER_PATH = CONFIG_DIR.parent / "fixtures" / "sample_roster.yaml"
CDT = timezone(-timedelta(hours=5))
# 2026-09-02 10:00 Central (within EMP-0008-01's 08:00-16:00 shift)
T0 = datetime(2026, 9, 2, 10, 0, tzinfo=CDT)
T1 = datetime(2026, 9, 2, 10, 5, tzinfo=CDT)


@pytest.fixture
def roster():
    return load_roster(ROSTER_PATH)


def test_marker_clocked_in_zone_resolves_high_conf(roster):
    sig = TrackIdentityInput("CAM-0008-1", 1, "0008", "ARUCO-11",
                             {"register"}, T0, T1)
    res = resolve_identity(sig, roster, confidence_min=0.6)
    assert res.employee_id == "EMP-0008-01"
    assert res.role == "cashier"
    assert res.confidence >= 0.6 and res.route_to_hitl is False


def test_reissued_marker_follows_to_same_employee(roster):
    # Old inactive badge ARUCO-08 must NOT resolve (inactive); active ARUCO-11 does.
    old = resolve_identity(
        TrackIdentityInput("CAM-0008-1", 2, "0008", "ARUCO-08", {"register"}, T0, T1),
        roster)
    assert old.employee_id is None and old.route_to_hitl is True
    new = resolve_identity(
        TrackIdentityInput("CAM-0008-1", 3, "0008", "ARUCO-11", {"register"}, T0, T1),
        roster)
    assert new.employee_id == "EMP-0008-01"


def test_marker_but_not_clocked_in_drops_below_gate(roster):
    # ARUCO-11 at 02:00 (outside the shift) -> only marker weight (0.6) but not in
    # zone either here; clocked-in fails -> still >= 0.6? marker alone == 0.6.
    # Put them outside the zone too so confidence = 0.60 marker only, and NOT
    # clocked in -> we still accept at exactly the gate only if zone present.
    night = datetime(2026, 9, 2, 2, 0, tzinfo=CDT)
    sig = TrackIdentityInput("CAM-0008-1", 4, "0008", "ARUCO-11",
                             set(), night, night)
    res = resolve_identity(sig, roster, confidence_min=0.7)  # stricter gate
    assert res.employee_id is None and res.route_to_hitl is True


def test_no_marker_never_guesses(roster):
    sig = TrackIdentityInput("CAM-0008-1", 5, "0008", None, {"register"}, T0, T1)
    res = resolve_identity(sig, roster)
    assert res.employee_id is None
    assert res.route_to_hitl is True


def test_attribute_writes_employee_id_and_hitl(engine, roster):
    seed_roster(engine, roster)
    # Two tracked person_present events: one resolvable (ARUCO-11), one unknown.
    with engine.begin() as conn:
        conn.execute(events_tbl.insert(), [
            {"event_id": "ev-known", "location_id": "0008", "camera_id": "CAM-0008-1",
             "ts_start": T0, "ts_end": T1, "event_type": "person_present",
             "track_id": 1, "marker_code": "ARUCO-11", "zone": "register",
             "confidence": 0.9, "camera_health": {"liveness": True, "clarity": "OK"},
             "triage_status": "auto"},
            {"event_id": "ev-unknown", "location_id": "0008", "camera_id": "CAM-0008-1",
             "ts_start": T0, "ts_end": T1, "event_type": "person_present",
             "track_id": 2, "marker_code": None, "zone": "register",
             "confidence": 0.9, "camera_health": {"liveness": True, "clarity": "OK"},
             "triage_status": "auto"},
        ])

    attrs = attribute_identities(engine, roster, "0008", confidence_min=0.6)
    by_track = {a.track_id: a.result for a in attrs}
    assert by_track[1].employee_id == "EMP-0008-01"
    assert by_track[2].employee_id is None

    with engine.begin() as conn:
        emp = conn.execute(select(events_tbl.c.employee_id)
                           .where(events_tbl.c.event_id == "ev-known")).scalar_one()
        assert emp == "EMP-0008-01"
        unknown_emp = conn.execute(select(events_tbl.c.employee_id)
                                   .where(events_tbl.c.event_id == "ev-unknown")).scalar_one()
        assert unknown_emp is None
        hitl = conn.execute(select(func.count()).select_from(hitl_queue)
                            .where(hitl_queue.c.kind == "unresolved_identity")).scalar_one()
        assert hitl == 1
