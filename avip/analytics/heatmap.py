"""Spatial traffic / dwell heat-maps — feature 3.

Accumulates person FEET points (the correct floor anchor) from the existing
tracklets into a 2-D density grid, blurs, colour-maps and blends over a clean
camera frame. Two flavours: traffic (footfall) and dwell (weighted by time, with
a boost for near-stationary samples — queues, displays). Plus per-zone ranking
using the same camera zone polygons. OpenCV + numpy only, offline, no new model.

Heat-maps are inherently ANONYMOUS (aggregate foot positions, no identity) — a
genuine privacy advantage worth stating in the report.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from avip.cv.detect import Detection


@dataclass
class HeatPoint:
    frame_index: int
    x: float
    y: float
    weight: float = 1.0
    stationary: bool = False


def points_from_tracklets(tracklets, nominal_dt: float = 1.0, *, dwell: bool = False,
                          motion_thresh: float = 12.0) -> list[HeatPoint]:
    """Extract feet points from tracklets.

    dwell=False -> traffic (weight 1 per sample).
    dwell=True  -> weight by nominal_dt seconds, x2 when the track is near-stationary
                   between consecutive samples (that is what 'dwelling' means)."""
    pts: list[HeatPoint] = []
    for t in tracklets:
        obs = getattr(t, "observations", [])
        prev = None
        for o in obs:
            try:
                fx, fy = Detection(tuple(o.xyxy), 1.0).bottom_center
            except Exception:
                continue
            stationary = False
            if prev is not None:
                d = ((fx - prev[0]) ** 2 + (fy - prev[1]) ** 2) ** 0.5
                stationary = d < motion_thresh
            prev = (fx, fy)
            if dwell:
                weight = float(nominal_dt) * (2.0 if stationary else 1.0)
            else:
                weight = 1.0
            pts.append(HeatPoint(getattr(o, "frame_index", 0), fx, fy, weight, stationary))
    return pts


def accumulate(points, shape_hw: tuple[int, int]) -> np.ndarray:
    """Stamp weighted feet points into a float32 accumulator (H, W)."""
    h, w = shape_hw
    acc = np.zeros((h, w), dtype=np.float32)
    for p in points:
        x, y = int(round(p.x)), int(round(p.y))
        if 0 <= x < w and 0 <= y < h:
            acc[y, x] += float(getattr(p, "weight", 1.0))
    return acc


def render_overlay(acc: np.ndarray, background: np.ndarray, *, sigma: float = 25.0,
                   alpha: float = 0.5, colormap: int = cv2.COLORMAP_TURBO,
                   mask_cold: bool = True, shared_max: float | None = None,
                   gamma: float = 1.0, floor: float = 0.0) -> np.ndarray:
    """Blur -> normalize -> colormap -> blend a heat accumulator onto a frame.

    shared_max: normalize against this instead of the per-image max — REQUIRED when
    comparing two overlays side-by-side (e.g. rush vs normal) so intensities match.
    gamma>1 steepens the alpha so only true hotspots colour (>1 = crisper).
    floor: normalized values below this contribute NO colour (removes the faint
    'colour shadow' wash over low-traffic areas — leaves the clean frame there).
    """
    if background is None or background.size == 0:
        raise ValueError("background frame required for heat overlay")
    bg = background if background.ndim == 3 else cv2.cvtColor(background, cv2.COLOR_GRAY2BGR)
    if acc.shape[:2] != bg.shape[:2]:
        acc = cv2.resize(acc, (bg.shape[1], bg.shape[0]))
    if float(acc.max()) <= 0.0:
        return bg.copy()                                  # nothing to show

    blurred = cv2.GaussianBlur(acc, (0, 0), sigmaX=sigma, sigmaY=sigma)
    mx = float(shared_max) if shared_max else float(blurred.max())
    mx = mx if mx > 0 else 1.0
    norm = np.clip(blurred / mx * 255.0, 0, 255).astype(np.uint8)
    colored = cv2.applyColorMap(norm, colormap)

    if mask_cold:
        m = norm.astype(np.float32) / 255.0
        if floor > 0.0:
            m = np.where(m < floor, 0.0, m)              # drop faint shadows
        if gamma != 1.0:
            m = np.power(m, gamma)                        # hotspots pop, low fades
        m = m[..., None]
        return (bg * (1 - alpha * m) + colored * (alpha * m)).astype(np.uint8)
    return cv2.addWeighted(bg, 1 - alpha, colored, alpha, 0)


@dataclass
class ZoneHeat:
    zone: str
    weight: float
    share: float               # fraction of total accumulated weight


def rank_zones(acc: np.ndarray, zones_norm: dict[str, list[list[float]]]) -> list[ZoneHeat]:
    """Sum the accumulator inside each normalized zone polygon; rank by share."""
    h, w = acc.shape[:2]
    total = float(acc.sum()) or 1.0
    out: list[ZoneHeat] = []
    for name, poly in (zones_norm or {}).items():
        try:
            pts = np.array([[int(x * w), int(y * h)] for x, y in poly], dtype=np.int32)
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.fillPoly(mask, [pts], 255)
            wgt = float(acc[mask > 0].sum())
            out.append(ZoneHeat(name, round(wgt, 2), round(wgt / total, 4)))
        except Exception:
            continue
    out.sort(key=lambda z: z.weight, reverse=True)
    return out


def build_heatmap(tracklets, background: np.ndarray, *, nominal_dt: float = 1.0,
                  dwell: bool = False, zones_norm=None, **render_kw):
    """One-call convenience: tracklets -> (overlay image, ranked zones, accumulator)."""
    pts = points_from_tracklets(tracklets, nominal_dt, dwell=dwell)
    acc = accumulate(pts, background.shape[:2])
    overlay = render_overlay(acc, background, **render_kw)
    zones = rank_zones(acc, zones_norm) if zones_norm else []
    return overlay, zones, acc
