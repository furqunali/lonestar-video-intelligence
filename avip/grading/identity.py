"""Identity resolution (spec §9.5, M6) — non-biometric, gated, never a guess.

Attributes a tracklet to an employee_id using four layered signals:
  1. ArUco marker  -> markers table -> employee_id (multi-frame vote from M4)
  2. Role colour   -> robust role even when a marker frame is unreadable
  3. Roster + biometric attendance -> who is clocked in at this store/time
  4. Zone presence -> sustained presence in the role's expected zone confirms

Signals are combined into a confidence score. If confidence is below the gate
(settings.gates.confidence_min), employee_id stays null and the tracklet is
routed to HITL — we never guess when someone's grade is at stake (design rule
#8/#9). marker_code and employee_id are separate but linked (reissue-safe).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.engine import Engine

from avip.common.logging import get_logger
from avip.common.timeutil import now_store
from avip.db.models import events as events_tbl
from avip.db.models import hitl_queue
from avip.grading.roster import Roster

log = get_logger("grading.identity")

# Confidence contributions per signal (sum capped at 1.0).
W_MARKER = 0.60      # active ArUco marker resolves to an employee
W_CLOCKED = 0.25     # that employee is clocked in (biometric attendance)
W_ZONE = 0.15        # present in the role's expected zone
W_COLOUR = 0.10      # observed badge colour matches the role's colour (bonus)


@dataclass
class TrackIdentityInput:
    camera_id: str
    track_id: int
    location_id: str
    marker_code: str | None
    zones_present: set[str]
    ts_start: datetime
    ts_end: datetime
    role_colour: str | None = None     # from badge-colour detection (future hook)


@dataclass
class IdentityResult:
    employee_id: str | None
    role: str | None
    confidence: float
    route_to_hitl: bool
    reasons: list[str] = field(default_factory=list)


def resolve_identity(
    signals: TrackIdentityInput,
    roster: Roster,
    confidence_min: float = 0.6,
) -> IdentityResult:
    """Fuse the four signals into an identity decision. Never guesses."""
    reasons: list[str] = []
    conf = 0.0
    mid = signals.ts_start + (signals.ts_end - signals.ts_start) / 2

    emp = roster.employee_by_marker(signals.marker_code)
    if emp is not None:
        conf += W_MARKER
        reasons.append(f"marker {signals.marker_code} -> {emp.employee_id}")

        if roster.clocked_in_at(emp.employee_id, mid):
            conf += W_CLOCKED
            reasons.append("clocked in (attendance)")
        else:
            reasons.append("NOT clocked in at event time")

        shift = roster.shift_for(emp.employee_id)
        if shift and shift.zone in signals.zones_present:
            conf += W_ZONE
            reasons.append(f"present in expected zone '{shift.zone}'")
        else:
            reasons.append("not seen in expected zone")

        if signals.role_colour and signals.role_colour == emp.role_colour:
            conf += W_COLOUR
            reasons.append("badge colour matches role")
    else:
        # No usable marker -> we do NOT guess from roster alone in the PoC.
        reasons.append("no active marker resolved -> cannot attribute")

    conf = round(min(conf, 1.0), 3)
    if emp is not None and conf >= confidence_min:
        return IdentityResult(emp.employee_id, emp.role, conf, False, reasons)

    reasons.append(f"confidence {conf} < gate {confidence_min} -> HITL")
    return IdentityResult(None, emp.role if emp else None, conf, True, reasons)


# --------------------------------------------------------------------------- #
#  DB attribution pass: resolve identity per (camera, track) from stored events
# --------------------------------------------------------------------------- #
@dataclass
class TrackAttribution:
    camera_id: str
    track_id: int
    result: IdentityResult


def attribute_identities(
    engine: Engine,
    roster: Roster,
    location_id: str,
    confidence_min: float = 0.6,
    tz_name: str = "America/Chicago",
) -> list[TrackAttribution]:
    """Group a store's tracked events by (camera, track), resolve identity, write
    employee_id back to the events, and route unresolved tracks to the HITL queue.
    """
    with engine.begin() as conn:
        rows = conn.execute(
            select(events_tbl.c.camera_id, events_tbl.c.track_id,
                   events_tbl.c.marker_code, events_tbl.c.zone,
                   events_tbl.c.ts_start, events_tbl.c.ts_end)
            .where(events_tbl.c.location_id == location_id)
            .where(events_tbl.c.track_id.isnot(None))
        ).mappings().all()

    groups: dict[tuple[str, int], dict] = {}
    for r in rows:
        key = (r["camera_id"], r["track_id"])
        g = groups.setdefault(key, {"marker": None, "zones": set(),
                                    "start": r["ts_start"], "end": r["ts_end"]})
        if r["marker_code"] and not g["marker"]:
            g["marker"] = r["marker_code"]
        if r["zone"]:
            g["zones"].add(r["zone"])
        g["start"] = min(g["start"], r["ts_start"])
        g["end"] = max(g["end"], r["ts_end"])

    out: list[TrackAttribution] = []
    for (camera_id, track_id), g in groups.items():
        signals = TrackIdentityInput(
            camera_id=camera_id, track_id=track_id, location_id=location_id,
            marker_code=g["marker"], zones_present=g["zones"],
            ts_start=g["start"], ts_end=g["end"],
        )
        res = resolve_identity(signals, roster, confidence_min)
        with engine.begin() as conn:
            if res.employee_id:
                conn.execute(
                    update(events_tbl)
                    .where(events_tbl.c.location_id == location_id)
                    .where(events_tbl.c.camera_id == camera_id)
                    .where(events_tbl.c.track_id == track_id)
                    .values(employee_id=res.employee_id)
                )
            else:
                conn.execute(hitl_queue.insert().values(
                    kind="unresolved_identity",
                    ref_id=f"{camera_id}:{track_id}", severity="low",
                    payload={"confidence": res.confidence, "reasons": res.reasons},
                    status="open",
                    sla_due=now_store(tz_name) + timedelta(hours=8),  # end of shift
                ))
        out.append(TrackAttribution(camera_id, track_id, res))
        log.info("identity_resolved", camera=camera_id, track=track_id,
                 employee=res.employee_id, confidence=res.confidence,
                 hitl=res.route_to_hitl)
    return out

