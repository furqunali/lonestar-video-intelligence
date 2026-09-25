"""Multi-object tracking (spec §9.3).

Produces stable track_ids across sampled frames so per-person dwell can be
measured. The spec names ByteTrack (via `supervision`); however, in the
installed supervision (0.30.1) `sv.ByteTrack` is deprecated (removed in 0.31)
and behaves unreliably on sparse, down-sampled batch frames. We therefore use a
small, deterministic greedy IoU tracker — the same tracklet contract, but
version-proof and fully testable offline. Swap in another Tracker impl freely.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from avip.cv.detect import Detection


def iou(a: tuple[float, float, float, float],
        b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


@dataclass
class _Track:
    track_id: int
    box: tuple[float, float, float, float]
    last_frame: int


class Tracker(Protocol):
    def update(self, detections: list[Detection], frame_index: int
               ) -> list[tuple[int, Detection]]: ...


@dataclass
class IoUTracker:
    """Greedy IoU association tracker. Deterministic given the same inputs."""
    iou_threshold: float = 0.2
    lost_buffer: int = 30
    _next_id: int = 1
    _tracks: dict[int, _Track] = field(default_factory=dict)

    def update(self, detections: list[Detection], frame_index: int
               ) -> list[tuple[int, Detection]]:
        # Drop tracks not seen for longer than the lost buffer.
        stale = [tid for tid, t in self._tracks.items()
                 if frame_index - t.last_frame > self.lost_buffer]
        for tid in stale:
            del self._tracks[tid]

        assignments: list[tuple[int, Detection]] = []
        used_tracks: set[int] = set()
        # Greedy: for each detection, take the best unused track above threshold.
        # Sort detections deterministically (by position) so ties resolve stably.
        for det in sorted(detections, key=lambda d: (d.xyxy[0], d.xyxy[1])):
            best_tid, best_iou = None, self.iou_threshold
            for tid, tr in self._tracks.items():
                if tid in used_tracks:
                    continue
                score = iou(det.xyxy, tr.box)
                if score >= best_iou:
                    best_tid, best_iou = tid, score
            if best_tid is None:
                best_tid = self._next_id
                self._next_id += 1
            self._tracks[best_tid] = _Track(best_tid, det.xyxy, frame_index)
            used_tracks.add(best_tid)
            assignments.append((best_tid, det))
        return assignments
