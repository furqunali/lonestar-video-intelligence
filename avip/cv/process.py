"""Clip processing: detect -> track -> zone presence/dwell => tracklets (spec §9.3).

Runs the CV chain over the sampled frames of one dump and returns per-person
Tracklets carrying, for each zone, how long the person was present (dwell) and
the frames/timestamps involved. The event builder (M5) turns these into
canonical zone_dwell / person_present / restricted_area_entry events.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

import numpy as np

from avip.cv.detect import Detection, Detector
from avip.cv.track import IoUTracker, Tracker
from avip.cv.zones import build_zones, present_zones


@dataclass
class Observation:
    frame_index: int
    ts_seconds: float
    xyxy: tuple[float, float, float, float]
    confidence: float
    zones: set[str]


@dataclass
class Tracklet:
    track_id: int
    observations: list[Observation] = field(default_factory=list)

    @property
    def ts_start(self) -> float:
        return self.observations[0].ts_seconds

    @property
    def ts_end(self) -> float:
        return self.observations[-1].ts_seconds

    @property
    def max_confidence(self) -> float:
        return max(o.confidence for o in self.observations)

    @property
    def zones_present(self) -> set[str]:
        z: set[str] = set()
        for o in self.observations:
            z |= o.zones
        return z

    def zone_dwell(self, nominal_dt: float) -> dict[str, float]:
        """Seconds of sustained presence per zone.

        For each zone, sum the gaps between consecutive present samples; a lone
        present sample counts as one nominal frame interval. Gaps larger than
        2x the sampling interval are clamped (person left and returned).
        """
        out: dict[str, float] = {}
        for zone in self.zones_present:
            ts = [o.ts_seconds for o in self.observations if zone in o.zones]
            if len(ts) == 1:
                out[zone] = nominal_dt
                continue
            total = 0.0
            for a, b in zip(ts, ts[1:]):
                total += min(b - a, 2 * nominal_dt)
            out[zone] = round(total, 3)
        return out


def _nominal_dt(frames_ts: list[float]) -> float:
    gaps = [b - a for a, b in zip(frames_ts, frames_ts[1:]) if b > a]
    return median(gaps) if gaps else 1.0


def process_clip(
    frames: list,                         # Sequence[SampledFrame] (index, ts_seconds, image)
    detector: Detector,
    zones_norm: dict[str, list[list[float]]],
    tracker: Tracker | None = None,
    frame_wh: tuple[int, int] | None = None,
) -> list[Tracklet]:
    """Detect + track + zone-tag across a clip; return aggregated tracklets."""
    tracker = tracker or IoUTracker()
    tracklets: dict[int, Tracklet] = {}
    frames_ts: list[float] = []

    for sf in frames:
        image: np.ndarray = sf.image
        frames_ts.append(sf.ts_seconds)
        if frame_wh is None:
            h, w = image.shape[:2]
            frame_wh = (w, h)
        zones = build_zones(zones_norm, frame_wh)

        detections = detector(image)
        for track_id, det in tracker.update(detections, sf.index):
            zp = present_zones(zones, det)
            tracklets.setdefault(track_id, Tracklet(track_id)).observations.append(
                Observation(sf.index, sf.ts_seconds, det.xyxy, det.confidence, zp)
            )

    return list(tracklets.values())


def nominal_dt(frames) -> float:
    """Public helper: median sampling interval (seconds) for a frame sequence."""
    return _nominal_dt([sf.ts_seconds for sf in frames])
