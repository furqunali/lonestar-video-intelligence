"""Canonical event contract (spec §7, Table 6).

Every event conforms to this Pydantic model. Validation failure => dead-letter
(handled by the event store, M5). event_id is a deterministic hash of the
identifying fields, so re-processing the same dump yields identical IDs
(idempotency, design rule #10).

NOTE: the spec calls for "Pydantic v3"; the installed runtime is Pydantic v2
(2.x). The contract is expressed in v2 syntax — semantics are identical.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

EventType = Literal[
    "person_present",
    "zone_dwell",
    "restricted_area_entry",
    "sweep_pass",
    "post_coverage",
    "camera_health",
]


class CameraHealth(BaseModel):
    liveness: bool
    clarity: Literal["OK", "BLUR", "OCCLUDED", "TAMPER"]
    blur_score: float | None = None       # Laplacian variance
    tamper_ssim: float | None = None      # SSIM vs baseline
    clock_drift_s: float | None = None    # OCR clock vs system clock


def make_event_id(
    location_id: str,
    camera_id: str,
    timestamp_start: datetime,
    event_type: str,
    track_id: int | None = None,
    zone: str | None = None,
) -> str:
    """Deterministic event id: hash(location, camera, ts_start, type, track[, zone]).

    Follows spec §7 (those five fields) and adds ``zone`` as a tiebreaker so two
    different zones on the same track at the same instant don't collide. Pure
    function of its inputs => idempotent re-runs.
    """
    key = "|".join([
        location_id,
        camera_id,
        timestamp_start.isoformat(),
        event_type,
        "" if track_id is None else str(track_id),
        zone or "",
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


class Event(BaseModel):
    event_id: str = ""                     # filled deterministically if blank
    schema_version: str = "1.0"
    location_id: str
    camera_id: str
    timestamp_start: datetime              # store-local, tz-aware (America/Chicago)
    timestamp_end: datetime
    event_type: EventType
    track_id: int | None = None
    marker_code: str | None = None
    zone: str | None = None
    dwell_seconds: float | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    camera_health: CameraHealth
    employee_id: str | None = None         # filled by identity resolution (M6)
    evidence_uri: str | None = None
    triage_status: Literal["auto", "unreviewed", "confirmed", "rejected"] = "unreviewed"

    @field_validator("timestamp_start", "timestamp_end")
    @classmethod
    def tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamps must be tz-aware (store-local)")
        return v

    @model_validator(mode="after")
    def _fill_id_and_check_order(self):
        if self.timestamp_end < self.timestamp_start:
            raise ValueError("timestamp_end must be >= timestamp_start")
        if not self.event_id:
            self.event_id = make_event_id(
                self.location_id, self.camera_id, self.timestamp_start,
                self.event_type, self.track_id, self.zone,
            )
        return self
