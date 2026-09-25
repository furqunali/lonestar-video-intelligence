"""Camera-health diagnostics (spec §9.2, Table 8) — the foundation layer.

Five SOP checks against config thresholds:
    1. Stream liveness   — any decodable frames?              (no frames => not live)
    2. Lens blur         — Laplacian variance < min           => BLUR
    3. Tamper / tilt     — SSIM vs baseline < min (>25% drift) => TAMPER
    4. Occlusion / glare — >max fraction of pixels solid       => OCCLUDED
    5. Clock drift       — OCR clock vs system > max seconds   => flagged

A store/zone without healthy coverage cannot be graded (this gates everything
downstream, spec §9.2). Clock-drift OCR (PaddleOCR) is optional and pluggable;
when unavailable, clock_drift_s stays None (cannot verify) rather than failing.
"""
from __future__ import annotations

from typing import Protocol, Sequence

import cv2
import numpy as np

from avip.common.config import Health
from avip.events.schema import CameraHealth


# --------------------------- individual checks ----------------------------- #
def _gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def _finite(x: float, default: float) -> float:
    """Coerce a non-finite score (NaN/Inf) to a fail-SAFE default.

    A NaN never compares True in `score < threshold`, so an un-guarded NaN would
    silently PASS a health gate (a dead/blank camera read as 'OK'). We force it
    to the worst value instead, so a bad read is always flagged, never trusted.
    """
    return x if np.isfinite(x) else default


def laplacian_blur_score(frame: np.ndarray) -> float:
    """Variance of the Laplacian — higher is sharper, lower is blurrier."""
    # non-finite => 0.0 (blurriest) so a bad read is flagged as BLUR, not OK.
    return _finite(float(cv2.Laplacian(_gray(frame), cv2.CV_64F).var()), 0.0)


def solid_fraction(frame: np.ndarray, dark_below: int, bright_above: int) -> float:
    """Fraction of pixels that are near-black or near-white (occlusion/glare)."""
    g = _gray(frame)
    if g.size == 0:                      # empty frame => treat as fully occluded
        return 1.0
    solid = np.count_nonzero((g < dark_below) | (g > bright_above))
    return _finite(float(solid) / float(g.size), 1.0)


def tamper_ssim(frame: np.ndarray, baseline: np.ndarray) -> float:
    """Structural similarity to a baseline frame (1.0 = identical)."""
    from skimage.metrics import structural_similarity as ssim

    a, b = _gray(frame), _gray(baseline)
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    # ssim of a constant/blank image is NaN => 0.0 (max drift) flags TAMPER.
    return _finite(float(ssim(a, b)), 0.0)


class ClockDriftChecker(Protocol):
    """Pluggable NVR clock-drift OCR. Returns drift in seconds, or None."""
    def __call__(self, frame: np.ndarray) -> float | None: ...


def null_clock_checker(frame: np.ndarray) -> float | None:
    """Default: no OCR available offline => drift unknown (not a failure)."""
    return None


# ------------------------------- assessment -------------------------------- #
def assess_health(
    frames: Sequence[np.ndarray],
    thresholds: Health,
    baseline: np.ndarray | None = None,
    clock_checker: ClockDriftChecker = null_clock_checker,
) -> CameraHealth:
    """Assess camera health from sampled frames + config thresholds.

    Clarity precedence (most severe first): TAMPER > OCCLUDED > BLUR > OK.
    """
    if not frames:
        return CameraHealth(liveness=False, clarity="OCCLUDED", blur_score=None,
                            tamper_ssim=None, clock_drift_s=None)

    # Median blur across frames is robust to a single bad frame.
    blur = float(np.median([laplacian_blur_score(f) for f in frames]))
    occ = float(np.mean([
        solid_fraction(f, thresholds.solid_dark_below, thresholds.solid_bright_above)
        for f in frames
    ]))
    mid = frames[len(frames) // 2]
    ssim_val = tamper_ssim(mid, baseline) if baseline is not None else None
    drift = clock_checker(mid)

    is_tamper = ssim_val is not None and ssim_val < thresholds.tamper_ssim_min
    is_occluded = occ > thresholds.occlusion_solid_frac_max
    is_blurry = blur < thresholds.blur_laplacian_min

    if is_tamper:
        clarity = "TAMPER"
    elif is_occluded:
        clarity = "OCCLUDED"
    elif is_blurry:
        clarity = "BLUR"
    else:
        clarity = "OK"

    return CameraHealth(
        liveness=True,
        clarity=clarity,
        blur_score=round(blur, 3),
        tamper_ssim=None if ssim_val is None else round(ssim_val, 4),
        clock_drift_s=drift,
    )


def is_gradeable(health: CameraHealth, thresholds: Health) -> bool:
    """Coverage gate input: healthy enough to grade the zone it covers?"""
    if not health.liveness or health.clarity != "OK":
        return False
    if (health.clock_drift_s is not None
            and abs(health.clock_drift_s) > thresholds.clock_drift_max_s):
        return False
    return True
