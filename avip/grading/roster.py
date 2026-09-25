"""Roster / markers / shifts / attendance reference data (spec §8, §9.5).

Loads the employee reference data the identity and grading engines need. In the
PoC this is the SAMPLE placeholder fixture (fixtures/sample_roster.yaml); the
real roster, ArUco->employee mapping, and biometric attendance export drop in
here unchanged. Also seeds the reference tables so grades stay auditable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml
from sqlalchemy.engine import Engine

from avip.db.models import attendance as attendance_tbl
from avip.db.models import employees as employees_tbl
from avip.db.models import markers as markers_tbl
from avip.db.models import shifts as shifts_tbl


@dataclass(frozen=True)
class Employee:
    employee_id: str
    name: str
    role: str
    role_colour: str
    location_id: str
    status: str = "active"


@dataclass(frozen=True)
class MarkerRow:
    marker_code: str
    employee_id: str
    active: bool
    issued_at: datetime | None = None


@dataclass(frozen=True)
class Shift:
    employee_id: str
    location_id: str
    zone: str
    start_ts: datetime
    end_ts: datetime


@dataclass(frozen=True)
class Attendance:
    employee_id: str
    location_id: str
    work_date: date
    clock_in: datetime
    clock_out: datetime


@dataclass
class Roster:
    work_date: date
    employees: list[Employee] = field(default_factory=list)
    markers: list[MarkerRow] = field(default_factory=list)
    shifts: list[Shift] = field(default_factory=list)
    attendance: list[Attendance] = field(default_factory=list)

    # ---- lookups ----
    def employee(self, employee_id: str) -> Employee | None:
        return next((e for e in self.employees if e.employee_id == employee_id), None)

    def employee_by_marker(self, marker_code: str | None) -> Employee | None:
        """Resolve an ACTIVE marker to its employee (reissue-safe)."""
        if not marker_code:
            return None
        row = next((m for m in self.markers
                    if m.marker_code == marker_code and m.active), None)
        return self.employee(row.employee_id) if row else None

    def employees_at(self, location_id: str) -> list[Employee]:
        return [e for e in self.employees
                if e.location_id == location_id and e.status == "active"]

    def shift_for(self, employee_id: str) -> Shift | None:
        return next((s for s in self.shifts if s.employee_id == employee_id), None)

    def attendance_for(self, employee_id: str) -> Attendance | None:
        return next((a for a in self.attendance
                     if a.employee_id == employee_id), None)

    def clocked_in_at(self, employee_id: str, when: datetime,
                      tz_name: str = "America/Chicago") -> bool:
        from avip.common.timeutil import ensure_store_aware
        a = self.attendance_for(employee_id)
        if not a:
            return False
        w = ensure_store_aware(when, tz_name)
        ci = ensure_store_aware(a.clock_in, tz_name)
        co = ensure_store_aware(a.clock_out, tz_name)
        return ci <= w <= co


def _dt(v) -> datetime:
    return datetime.fromisoformat(v) if isinstance(v, str) else v


def load_roster(path: Path | str) -> Roster:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Roster(
        work_date=date.fromisoformat(str(raw["work_date"])),
        employees=[Employee(**e) for e in raw.get("employees", [])],
        markers=[MarkerRow(m["marker_code"], m["employee_id"], bool(m["active"]),
                           _dt(m.get("issued_at"))) for m in raw.get("markers", [])],
        shifts=[Shift(s["employee_id"], s["location_id"], s["zone"],
                      _dt(s["start_ts"]), _dt(s["end_ts"]))
                for s in raw.get("shifts", [])],
        attendance=[Attendance(a["employee_id"], a["location_id"],
                               date.fromisoformat(str(a["work_date"])),
                               _dt(a["clock_in"]), _dt(a["clock_out"]))
                    for a in raw.get("attendance", [])],
    )


def seed_roster(engine: Engine, roster: Roster) -> None:
    """Insert the reference data into employees/markers/shifts/attendance."""
    with engine.begin() as conn:
        for e in roster.employees:
            conn.execute(employees_tbl.insert().values(
                employee_id=e.employee_id, role=e.role, role_colour=e.role_colour,
                location_id=e.location_id, status=e.status))
        for m in roster.markers:
            conn.execute(markers_tbl.insert().values(
                marker_code=m.marker_code, employee_id=m.employee_id,
                active=m.active, issued_at=m.issued_at))
        for s in roster.shifts:
            conn.execute(shifts_tbl.insert().values(
                employee_id=s.employee_id, location_id=s.location_id, zone=s.zone,
                start_ts=s.start_ts, end_ts=s.end_ts))
        for a in roster.attendance:
            conn.execute(attendance_tbl.insert().values(
                employee_id=a.employee_id, location_id=a.location_id,
                work_date=a.work_date, clock_in=a.clock_in, clock_out=a.clock_out))
