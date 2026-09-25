"""Line-crossing people counting + conversion rate — feature 2.

Turns the existing person tracklets into entrance/exit counts by watching each
track's feet cross a virtual line, then derives the retail conversion rate
(transactions ÷ entries). Offline equivalent of i3's people-counting + conversion
module — reuses the IoU tracker output, needs no new model.

A crossing is detected when a track's feet point moves from one side of the line
to the other (sign change of the 2-D cross product). Direction ("in" vs "out")
is the sign of that change relative to the line's orientation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from avip.cv.detect import Detection


def _feet(xyxy) -> tuple[float, float]:
    return Detection(tuple(xyxy), 1.0).bottom_center


def _side(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    """Signed side of point p relative to directed line a->b (>0 left, <0 right)."""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


@dataclass
class CountResult:
    entries: int = 0
    exits: int = 0
    line: tuple[tuple[float, float], tuple[float, float]] = ((0.0, 0.5), (1.0, 0.5))
    per_track: dict[int, str] = field(default_factory=dict)  # track_id -> "in"/"out"

    @property
    def net(self) -> int:
        return self.entries - self.exits

    @property
    def total_crossings(self) -> int:
        return self.entries + self.exits


def count_crossings(tracklets, frame_wh: tuple[int, int],
                    line_norm=((0.0, 0.5), (1.0, 0.5)),
                    inward_positive: bool = True) -> CountResult:
    """Count entries/exits from tracklets crossing a normalized line.

    line_norm: two (x, y) points in 0..1. inward_positive: if True, a crossing
    from the negative side to the positive side counts as an ENTRY.
    Fail-soft: a degenerate track/line is skipped.
    """
    w, h = frame_wh
    a = (line_norm[0][0] * w, line_norm[0][1] * h)
    b = (line_norm[1][0] * w, line_norm[1][1] * h)
    res = CountResult(line=tuple(line_norm))
    if a == b:                                   # degenerate line
        return res

    for t in tracklets:
        try:
            obs = getattr(t, "observations", [])
            if len(obs) < 2:
                continue
            sides = [_side(_feet(o.xyxy), a, b) for o in obs]
            # find the first significant sign change (ignore points on the line)
            prev = next((s for s in sides if abs(s) > 1e-6), None)
            crossed = None
            for s in sides:
                if abs(s) <= 1e-6:
                    continue
                if prev is not None and (s > 0) != (prev > 0):
                    crossed = s > 0        # True => moved to positive side
                    break
                prev = s
            if crossed is None:
                continue
            is_entry = crossed if inward_positive else not crossed
            tid = getattr(t, "track_id", -1)
            if is_entry:
                res.entries += 1
                res.per_track[tid] = "in"
            else:
                res.exits += 1
                res.per_track[tid] = "out"
        except Exception:
            continue
    return res


def conversion_rate(entries: int, transactions: int) -> float | None:
    """Transactions ÷ entries, as a 0..1 rate. None if no entries (undefined)."""
    if entries <= 0:
        return None
    return round(transactions / entries, 4)
