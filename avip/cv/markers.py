"""ArUco ID-badge decode + multi-frame majority vote (spec §9.5, M4).

Identity is non-biometric (design rule #8): employees wear ArUco marker badges.
We decode markers per frame, attach a marker to a person when the marker's
centre falls inside that person's box, then take a majority vote across the
tracklet's frames. A marker is only assigned if it wins by at least
``vote_min_frames`` observations — never a single-frame guess.

marker_code -> employee_id resolution happens later (M6); here we only decode
and vote the marker_code.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import cv2
import numpy as np

from avip.cv.detect import Detection
from avip.cv.process import Tracklet


@dataclass(frozen=True)
class MarkerHit:
    marker_id: int
    center: tuple[float, float]


def get_aruco_dictionary(name: str = "DICT_4X4_50"):
    const = getattr(cv2.aruco, name, None)
    if const is None:
        raise ValueError(f"unknown ArUco dictionary: {name!r}")
    return cv2.aruco.getPredefinedDictionary(const)


class ArucoReader:
    """Decodes ArUco markers from frames."""

    def __init__(self, dict_name: str = "DICT_4X4_50"):
        self._dict = get_aruco_dictionary(dict_name)
        self._detector = cv2.aruco.ArucoDetector(
            self._dict, cv2.aruco.DetectorParameters()
        )

    def detect(self, frame: np.ndarray) -> list[MarkerHit]:
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self._detector.detectMarkers(gray)
        hits: list[MarkerHit] = []
        if ids is None:
            return hits
        for c, mid in zip(corners, ids.flatten()):
            pts = c.reshape(-1, 2)
            cx, cy = float(pts[:, 0].mean()), float(pts[:, 1].mean())
            hits.append(MarkerHit(int(mid), (cx, cy)))
        return hits


def marker_code_for(marker_id: int) -> str:
    """Canonical marker_code string stored on events / looked up in `markers`."""
    return f"ARUCO-{marker_id}"


def _center_in_box(center: tuple[float, float],
                   box: tuple[float, float, float, float]) -> bool:
    x, y = center
    x1, y1, x2, y2 = box
    return x1 <= x <= x2 and y1 <= y <= y2


def markers_in_frame(reader: ArucoReader, frame: np.ndarray) -> list[MarkerHit]:
    return reader.detect(frame)


def vote_marker(
    tracklet: Tracklet,
    per_frame_markers: dict[int, list[MarkerHit]],
    vote_min_frames: int = 3,
) -> str | None:
    """Majority-vote a marker_code for a tracklet across its frames.

    For each observation, any marker whose centre lies inside the person box is
    a vote for that marker id. The winner must reach ``vote_min_frames`` votes.
    """
    votes: Counter[int] = Counter()
    for obs in tracklet.observations:
        for hit in per_frame_markers.get(obs.frame_index, []):
            if _center_in_box(hit.center, obs.xyxy):
                votes[hit.marker_id] += 1
    if not votes:
        return None
    marker_id, count = votes.most_common(1)[0]
    if count < vote_min_frames:
        return None
    return marker_code_for(marker_id)


def decode_markers_for_frames(
    reader: ArucoReader, frames
) -> dict[int, list[MarkerHit]]:
    """Detect markers on each SampledFrame, keyed by its frame index."""
    return {sf.index: reader.detect(sf.image) for sf in frames}
