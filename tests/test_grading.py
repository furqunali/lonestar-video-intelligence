"""M7 acceptance: deterministic metrics + scoring, coverage/confidence/
calibration gates, auditable scorecard, and the HARD rule that NOTHING is ever
published in the PoC."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from avip.common.config import CONFIG_DIR, load_config
from avip.db.models import events as events_tbl
from avip.db.models import grades as grades_tbl
from avip.grading.calibration import check_calibration
from avip.grading.engine import grade_employee, grade_store_day, letter_for
from avip.grading.metrics import (
    compute_metric,
    covered_seconds,
    score_for,
    zone_presence_pct,
)
from avip.grading.roster import Employee, Roster, Shift, load_roster, seed_roster

CDT = timezone(-timedelta(hours=5))
ROSTER_PATH = CONFIG_DIR.parent / "fixtures" / "sample_roster.yaml"
WORK_DATE = date(2026, 9, 2)


def _t(h, m=0):
    return datetime(2026, 9, 2, h, m, tzinfo=CDT)


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def roster():
    return load_roster(ROSTER_PATH)


# ------------------------------- metrics ----------------------------------- #
def test_covered_seconds_merges_overlap():
    # 08-10 and 09-11 -> union 08-11 = 3h, not 4h.
    secs = covered_seconds([(_t(8), _t(10)), (_t(9), _t(11))], _t(8), _t(12))
    assert secs == 3 * 3600


def test_zone_presence_pct():
    events = [{"zone": "register", "ts_start": _t(8), "ts_end": _t(14)}]
    pct = zone_presence_pct(events, "register", _t(8), _t(16))  # 6 of 8 hours
    assert pct == 75.0


def test_score_and_letter():
    assert score_for("register_attended_pct", 90, 90) == 100.0
    assert score_for("register_attended_pct", 45, 90) == 50.0
    assert score_for("sweep_interval_hours", 2, 2) == 100.0    # on target
    assert score_for("sweep_interval_hours", 4, 2) == 50.0     # twice too slow
    bands = {"A": 90, "B": 75, "C": 60}
    assert letter_for(95, bands) == "A"
    assert letter_for(80, bands) == "B"
    assert letter_for(40, bands) == "F"


# ---------------------------- calibration gate ----------------------------- #
def test_calibration_gate_is_closed_in_poc():
    assert check_calibration(None).passed is False       # no golden-set -> withhold


# ----------------------------- grade_employee ------------------------------ #
def _seed_cashier_events(engine, emp="EMP-0008-01"):
    with engine.begin() as conn:
        # healthy camera coverage across the shift
        conn.execute(events_tbl.insert().values(
            event_id="h1", location_id="0008", camera_id="CAM-0008-1",
            ts_start=_t(8), ts_end=_t(16), event_type="camera_health",
            confidence=1.0, camera_health={"liveness": True, "clarity": "OK"},
            triage_status="auto"))
        # 6h of register presence for the cashier (08-14)
        conn.execute(events_tbl.insert().values(
            event_id="z1", location_id="0008", camera_id="CAM-0008-1",
            ts_start=_t(8), ts_end=_t(14), event_type="zone_dwell",
            zone="register", track_id=1, employee_id=emp,
            confidence=0.9, camera_health={"liveness": True, "clarity": "OK"},
            triage_status="auto"))


def test_grade_employee_computes_but_withholds(config, engine, roster):
    seed_roster(engine, roster)
    _seed_cashier_events(engine)
    emp = roster.employee("EMP-0008-01")
    g = grade_employee(engine, config, roster, "0008", emp, WORK_DATE,
                       calibration_ok=False)

    # metric computed deterministically (~74% of the 8h05m shift)
    assert 70 <= g.metric_values["register_attended_pct"] <= 78
    assert g.weighted_score is not None and g.letter in {"A", "B", "C", "F"}
    assert g.gate_result["coverage_ok"] is True          # healthy coverage
    assert g.gate_result["confidence_ok"] is True
    assert g.gate_result["calibration_ok"] is False
    # HARD RULE: never published; withheld because calibration gate is closed.
    assert g.published is False
    assert g.withheld is True
    assert "z1" in g.contributing_event_ids


def test_missing_attendance_is_withheld_not_failed(config, engine):
    # A cashier with a shift but NO attendance row -> withheld, not an F.
    roster = Roster(
        work_date=WORK_DATE,
        employees=[Employee("EMP-X", "No Clock", "cashier", "red", "0008", "active")],
        shifts=[Shift("EMP-X", "0008", "register", _t(8), _t(16))],
        attendance=[],
    )
    g = grade_employee(engine, config, roster, "0008", roster.employees[0],
                       WORK_DATE, calibration_ok=True)
    assert g.gate_result.get("missing_data") is True
    assert g.letter is None                # no letter -> NOT an automatic F
    assert g.route_hitl is True
    assert g.published is False


# ----------------------------- grade_store_day ----------------------------- #
def test_grade_store_day_persists_all_unpublished(config, engine, roster):
    seed_roster(engine, roster)
    _seed_cashier_events(engine)

    card = grade_store_day(engine, config, roster, "0008", WORK_DATE)

    assert card.store_grade is not None
    assert card.store_grade.published is False
    # Every persisted grade row MUST be unpublished.
    with engine.begin() as conn:
        total = conn.execute(select(func.count()).select_from(grades_tbl)).scalar_one()
        published = conn.execute(
            select(func.count()).select_from(grades_tbl)
            .where(grades_tbl.c.published == True)  # noqa: E712
        ).scalar_one()
    assert total >= 4          # 3 rubric employees + store roll-up
    assert published == 0      # <<< nothing published, ever
