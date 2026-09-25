"""Hardened camera-tamper / health ensemble — feature 4.

Fixes the known real-footage FALSE POSITIVE: the original tamper check compared
SSIM against the clip's OWN first frame, so over a busy 20-minute register clip
normal activity drifted SSIM below threshold and flagged TAMPER even though the
image was perfectly sharp and lit.

The fix is an ENSEMBLE that only calls TAMPER when the low-level image evidence
agrees — a real tampered camera is COVERED (few edges), DEFOCUSED (low blur),
BLINDED (luminance extreme), or shows a SUSTAINED structural change vs a STABLE
reference frame — none of which a busy-but-healthy scene exhibits (it stays sharp,
edge-rich and well-lit). This is i3's "True View" equivalent, done offline.

Additive: the original avip/cv/health.py is untouched. Provide a stable reference
frame (an empty/quiet snapshot per camera) for the strongest tamper detection;
without one, the intrinsic signals (edges/blur/luminance) still catch covered or
defocused lenses without false-flagging activity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import cv2
import numpy as np

from avip.common.config import Health
from avip.cv.health import _finite, _gray, laplacian_blur_score, solid_fraction, tamper_ssim


def edge_density(frame: np.ndarray) -> float:
    """Fraction of Canny edge pixels — a covered/defocused lens has almost none;
    a real (even busy) scene is edge-rich."""
    g = _gray(frame)
    if g.size == 0:                      # empty frame => no edges (reads as covered)
        return 0.0
    edges = cv2.Canny(g, 60, 180)
    return _finite(float(np.count_nonzero(edges)) / float(edges.size), 0.0)


def mean_luminance(frame: np.ndarray) -> float:
    g = _gray(frame)
    if g.size == 0:                      # empty frame => near-black (reads as blinded)
        return 0.0
    return _finite(float(np.mean(g)), 0.0)


# extra thresholds beyond config.Health (sensible offline defaults)
EDGE_DENSITY_MIN = 0.010      # below this = suspiciously featureless (covered/defocus)
LUM_DARK = 20.0              # near-black => blinded/covered
LUM_BRIGHT = 235.0          # near-white => glare/blinded
SUSTAIN_FRAC = 0.80         # fraction of frames that must persistently differ vs ref


@dataclass
class TamperReport:
    clarity: str                       # OK | BLUR | OCCLUDED | TAMPER
    is_tamper: bool
    blur_score: float
    edge_density: float
    solid_fraction: float
    mean_luminance: float
    sustained_change_frac: float | None  # vs stable reference, if provided
    reasons: list[str] = field(default_factory=list)


def assess_tamper(frames: Sequence[np.ndarray],
                  thresholds: Health | None = None,
                  stable_ref: np.ndarray | None = None,
                  *, edge_min: float = EDGE_DENSITY_MIN,
                  sustain_frac: float = SUSTAIN_FRAC) -> TamperReport:
    """Ensemble tamper/health assessment. Precedence: TAMPER > OCCLUDED > BLUR > OK."""
    th = thresholds or Health()
    if not frames:
        return TamperReport("OCCLUDED", False, 0.0, 0.0, 1.0, 0.0, None,
                            ["no frames (not live)"])

    blur = float(np.median([laplacian_blur_score(f) for f in frames]))
    edges = float(np.median([edge_density(f) for f in frames]))
    solid = float(np.mean([solid_fraction(f, th.solid_dark_below, th.solid_bright_above)
                           for f in frames]))
    lum = float(np.median([mean_luminance(f) for f in frames]))

    # sustained structural change vs a STABLE reference (empty-scene snapshot).
    sustained = None
    if stable_ref is not None:
        lows = 0
        for f in frames:
            try:
                if tamper_ssim(f, stable_ref) < th.tamper_ssim_min:
                    lows += 1
            except Exception:
                continue
        sustained = lows / len(frames)

    reasons: list[str] = []
    # --- real tamper conditions (each corroborated, so activity never triggers) ---
    covered = edges < edge_min and blur < th.blur_laplacian_min
    blinded = lum < LUM_DARK or lum > LUM_BRIGHT
    ref_tamper = (sustained is not None and sustained >= sustain_frac
                  and edges < edge_min)   # persistent AND structure genuinely gone
    if covered:
        reasons.append(f"lens covered/defocused (edges {edges:.3f}<{edge_min}, blur {blur:.0f})")
    if blinded:
        reasons.append(f"blinded/glare (luminance {lum:.0f})")
    if ref_tamper:
        reasons.append(f"sustained change vs reference ({sustained:.0%} of frames)")

    is_tamper = covered or blinded or ref_tamper
    is_occluded = solid > th.occlusion_solid_frac_max
    is_blurry = blur < th.blur_laplacian_min

    if is_tamper:
        clarity = "TAMPER"
    elif is_occluded:
        clarity = "OCCLUDED"; reasons.append(f"occluded (solid {solid:.2f})")
    elif is_blurry:
        clarity = "BLUR"; reasons.append(f"blurry (blur {blur:.0f}<{th.blur_laplacian_min})")
    else:
        clarity = "OK"
        # explicitly note why a busy scene is NOT tamper (this is the bug fix)
        reasons.append(f"healthy: sharp (blur {blur:.0f}), edge-rich ({edges:.3f}), lit ({lum:.0f})")

    return TamperReport(
        clarity=clarity, is_tamper=is_tamper,
        blur_score=round(blur, 2), edge_density=round(edges, 4),
        solid_fraction=round(solid, 4), mean_luminance=round(lum, 1),
        sustained_change_frac=None if sustained is None else round(sustained, 3),
        reasons=reasons,
    )
