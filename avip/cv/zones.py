"""Zone presence via supervision PolygonZone (spec §9.3).

Zone polygons are stored NORMALIZED (0..1) in cameras.yaml and scaled to each
frame's pixel size here, so they are resolution-independent. A person's
bottom-center anchor determines which zone they occupy.
"""
from __future__ import annotations

import numpy as np
import supervision as sv

from avip.cv.detect import Detection


def scale_polygon(norm_poly: list[list[float]], width: int, height: int) -> np.ndarray:
    pts = [[round(x * width), round(y * height)] for x, y in norm_poly]
    return np.array(pts, dtype=np.int64)


def build_zones(zones_norm: dict[str, list[list[float]]], frame_wh: tuple[int, int]
                ) -> dict[str, sv.PolygonZone]:
    w, h = frame_wh
    return {
        name: sv.PolygonZone(polygon=scale_polygon(poly, w, h))
        for name, poly in zones_norm.items()
    }


def _as_detections(det: Detection) -> sv.Detections:
    return sv.Detections(
        xyxy=np.array([det.xyxy], dtype=float),
        confidence=np.array([det.confidence], dtype=float),
        class_id=np.array([det.class_id], dtype=int),
    )


def present_zones(zones: dict[str, sv.PolygonZone], det: Detection) -> set[str]:
    """Return the set of zone names whose polygon contains this detection."""
    dets = _as_detections(det)
    present: set[str] = set()
    for name, zone in zones.items():
        mask = zone.trigger(dets)
        if bool(mask[0]):
            present.add(name)
    return present
