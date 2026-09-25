"""Deterministic grading engine (spec §9.6) — the defensible core.

Inputs: validated events for a store/day + roster + biometric attendance +
rubric. Output: an auditable scorecard per employee and a store roll-up. The
engine — never the LLM — computes every number.

Gates before publish:
  - coverage gate    : the employee's zone must have healthy camera coverage for
                       >= gates.coverage_min_pct of the shift (from clock-in/out)
  - confidence gate  : contributing events must be above gates.confidence_min
  - calibration gate : the rubric must pass the labelled golden-set

Missing data is NOT an automatic F — it withholds the grade and routes to HITL.
In this PoC the calibration gate is False, so NOTHING is ever published.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine

from avip.common.config import Config
from avip.common.logging import get_logger
from avip.common.timeutil import now_store
from avip.db.models import events as events_tbl
from avip.db.models import grades as grades_tbl
from avip.db.models import hitl_queue
from avip.grading.calibration import check_calibration
from avip.grading.metrics import (
    compute_metric,
    covered_seconds,
    score_for,
    shift_seconds,
)
from avip.grading.roster import Roster

log = get_logger("grading.engine")


def letter_for(score: float, bands: dict[str, float]) -> str:
    if score >= bands["A"]:
        return "A"
    if score >= bands["B"]:
        return "B"
    if score >= bands["C"]:
        return "C"
    return "F"


@dataclass
class Grade:
    location_id: str
    employee_id: str | None
    role: str
    grade_date: date
    metric_values: dict = field(default_factory=dict)
    weighted_score: float | None = None
    letter: str | None = None
    gate_result: dict = field(default_factory=dict)
    rubric_version: str = ""
    contributing_event_ids: list[str] = field(default_factory=list)
    computed_at: datetime | None = None
    published: bool = False          # ALWAYS False in the PoC
    withheld: bool = True
    route_hitl: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass
class StoreScorecard:
    location_id: str
    grade_date: date
    employee_grades: list[Grade] = field(default_factory=list)
    store_grade: Grade | None = None
    calibration_reason: str = ""


def _employee_events(engine: Engine, location_id: str, employee_id: str) -> list[dict]:
    with engine.begin() as conn:
        rows = conn.execute(
            select(events_tbl.c.event_id, events_tbl.c.event_type,
                   events_tbl.c.zone, events_tbl.c.ts_start, events_tbl.c.ts_end,
                   events_tbl.c.confidence, events_tbl.c.camera_health)
            .where(events_tbl.c.location_id == location_id)
            .where(events_tbl.c.employee_id == employee_id)
        ).mappings().all()
    return [dict(r) for r in rows]


def _healthy_coverage_pct(engine: Engine, location_id: str, zone: str,
                          win_start, win_end, tz_name: str) -> float:
    """% of the shift with healthy (clarity OK) camera coverage of the zone."""
    total = shift_seconds(win_start, win_end, tz_name)
    if total <= 0:
        return 0.0
    with engine.begin() as conn:
        rows = conn.execute(
            select(events_tbl.c.ts_start, events_tbl.c.ts_end,
                   events_tbl.c.camera_health)
            .where(events_tbl.c.location_id == location_id)
            .where(events_tbl.c.event_type == "camera_health")
        ).mappings().all()
    intervals = [(r["ts_start"], r["ts_end"]) for r in rows
                 if (r["camera_health"] or {}).get("clarity") == "OK"]
    return round(100.0 * covered_seconds(intervals, win_start, win_end, tz_name)
                 / total, 2)


def grade_employee(engine: Engine, config: Config, roster: Roster,
                   location_id: str, employee, work_date: date,
                   calibration_ok: bool) -> Grade:
    tz = config.settings.timezone
    rubric = config.rubric
    gates = config.settings.gates
    grade = Grade(location_id=location_id, employee_id=employee.employee_id,
                  role=employee.role, grade_date=work_date,
                  rubric_version=rubric.version, computed_at=now_store(tz))

    role_rubric = rubric.roles.get(employee.role)
    if role_rubric is None:
        grade.reasons.append(f"no rubric metric for role '{employee.role}'")
        grade.gate_result = {"applicable": False}
        return grade

    shift = roster.shift_for(employee.employee_id)
    att = roster.attendance_for(employee.employee_id)
    if shift is None or att is None:
        # Missing data is NOT an automatic F — withhold and route to HITL.
        grade.reasons.append("missing shift/attendance -> withheld (not an F)")
        grade.route_hitl = True
        grade.gate_result = {"missing_data": True}
        return grade

    win_start, win_end = att.clock_in, att.clock_out
    events = _employee_events(engine, location_id, employee.employee_id)

    value = compute_metric(role_rubric.metric, events, shift.zone, win_start, win_end)
    score = score_for(role_rubric.metric, value, role_rubric.target)
    contributing = [e["event_id"] for e in events if e.get("zone") == shift.zone
                    or role_rubric.metric == "sweep_interval_hours"]
    confs = [e["confidence"] for e in events if e.get("confidence") is not None]
    avg_conf = round(sum(confs) / len(confs), 3) if confs else 0.0

    coverage_pct = _healthy_coverage_pct(engine, location_id, shift.zone,
                                         win_start, win_end, tz)
    coverage_ok = coverage_pct >= gates.coverage_min_pct
    confidence_ok = avg_conf >= gates.confidence_min

    grade.metric_values = {role_rubric.metric: value, "score": score,
                           "avg_confidence": avg_conf, "coverage_pct": coverage_pct}
    grade.weighted_score = score
    grade.letter = letter_for(score, rubric.grade_bands)
    grade.contributing_event_ids = contributing
    grade.gate_result = {
        "coverage_pct": coverage_pct, "coverage_ok": coverage_ok,
        "coverage_min_pct": gates.coverage_min_pct,
        "avg_confidence": avg_conf, "confidence_ok": confidence_ok,
        "confidence_min": gates.confidence_min,
        "calibration_ok": calibration_ok,
    }

    gates_pass = coverage_ok and confidence_ok and calibration_ok
    grade.withheld = not gates_pass
    grade.published = False          # hard rule: never publish in the PoC
    if not coverage_ok:
        grade.reasons.append(f"coverage {coverage_pct}% < {gates.coverage_min_pct}%")
        grade.route_hitl = True
    if not confidence_ok:
        grade.reasons.append(f"avg confidence {avg_conf} < {gates.confidence_min}")
        grade.route_hitl = True
    if not calibration_ok:
        grade.reasons.append("calibration gate not passed -> withheld/unpublished")
    return grade


def grade_store_day(engine: Engine, config: Config, roster: Roster,
                    location_id: str, work_date: date,
                    golden_path=None) -> StoreScorecard:
    """Grade every employee at a store for a day + a store roll-up. Persists all
    grades (published=False) and enqueues withheld ones to HITL."""
    tz = config.settings.timezone
    calib = check_calibration(golden_path)
    card = StoreScorecard(location_id=location_id, grade_date=work_date,
                          calibration_reason=calib.reason)

    for emp in roster.employees_at(location_id):
        if emp.role not in config.rubric.roles:
            continue                    # manager handled via roll-up below
        g = grade_employee(engine, config, roster, location_id, emp, work_date,
                           calibration_ok=calib.passed)
        card.employee_grades.append(g)

    # Store roll-up = mean of computed employee scores (manager's "overall grade").
    scored = [g for g in card.employee_grades if g.weighted_score is not None]
    if scored:
        avg = round(sum(g.weighted_score for g in scored) / len(scored), 2)
        store_grade = Grade(
            location_id=location_id, employee_id=None, role="store",
            grade_date=work_date, weighted_score=avg,
            letter=letter_for(avg, config.rubric.grade_bands),
            rubric_version=config.rubric.version, computed_at=now_store(tz),
            metric_values={"store_score": avg, "employees_scored": len(scored)},
            gate_result={"calibration_ok": calib.passed},
            withheld=not calib.passed, published=False,
            reasons=["store roll-up"] + ([] if calib.passed else [calib.reason]),
        )
        card.store_grade = store_grade

    _persist(engine, config, card)
    log.info("store_graded", location=location_id, employees=len(card.employee_grades),
             published=False, calibration=calib.passed)
    return card


def _persist(engine: Engine, config: Config, card: StoreScorecard) -> None:
    tz = config.settings.timezone
    all_grades = list(card.employee_grades)
    if card.store_grade:
        all_grades.append(card.store_grade)
    with engine.begin() as conn:
        for g in all_grades:
            conn.execute(grades_tbl.insert().values(
                location_id=g.location_id, employee_id=g.employee_id,
                grade_date=g.grade_date, role=g.role,
                metric_values=g.metric_values, weighted_score=g.weighted_score,
                letter=g.letter, gate_result=g.gate_result,
                rubric_version=g.rubric_version,
                contributing_event_ids=g.contributing_event_ids,
                computed_at=g.computed_at, published=False,   # HARD RULE
            ))
            if g.route_hitl or g.withheld:
                conn.execute(hitl_queue.insert().values(
                    kind="grade_withheld",
                    ref_id=f"{g.location_id}:{g.employee_id or 'STORE'}",
                    severity="low",
                    payload={"role": g.role, "reasons": g.reasons,
                             "gate_result": g.gate_result},
                    status="open", sla_due=now_store(tz),
                ))
