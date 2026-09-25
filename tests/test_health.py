"""M2 acceptance: the 5 SOP camera-health checks vs thresholds, and emission
of a validated camera_health event."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from avip.common.config import Health
from avip.cv.health import (
    assess_health,
    is_gradeable,
    laplacian_blur_score,
    solid_fraction,
    tamper_ssim,
)
from avip.events.builder import build_camera_health_event
from tests.synth import make_frame, make_textured_frame

TH = Health()  # default thresholds (== config defaults)


def test_blur_score_orders_sharp_vs_flat():
    sharp = make_textured_frame(seed=3)
    flat = make_frame(fill=120)
    assert laplacian_blur_score(sharp) > laplacian_blur_score(flat)


def test_solid_fraction_detects_black_frame():
    black = np.zeros((240, 320, 3), dtype=np.uint8)
    textured = make_textured_frame(seed=5)
    assert solid_fraction(black, TH.solid_dark_below, TH.solid_bright_above) > 0.85
    assert solid_fraction(textured, TH.solid_dark_below, TH.solid_bright_above) < 0.85


def test_ssim_identical_is_one_and_shifted_is_lower():
    base = make_textured_frame(seed=7)
    assert tamper_ssim(base, base) > 0.99
    other = make_textured_frame(seed=8)
    assert tamper_ssim(other, base) < 0.75          # different scene => tamper-level drift


def test_assess_ok_on_textured_frames():
    frames = [make_textured_frame(seed=i) for i in range(5)]
    base = frames[len(frames) // 2]
    h = assess_health(frames, TH, baseline=base)
    assert h.liveness is True
    assert h.clarity == "OK"
    assert is_gradeable(h, TH) is True


def test_assess_blur_on_flat_frames():
    frames = [make_frame(fill=120) for _ in range(5)]
    h = assess_health(frames, TH)
    assert h.clarity == "BLUR"
    assert is_gradeable(h, TH) is False


def test_assess_occluded_on_dark_frames():
    frames = [np.zeros((240, 320, 3), dtype=np.uint8) for _ in range(5)]
    h = assess_health(frames, TH)
    assert h.clarity == "OCCLUDED"


def test_assess_tamper_when_scene_changes():
    frames = [make_textured_frame(seed=10) for _ in range(5)]
    baseline = make_textured_frame(seed=999)         # a different baseline scene
    h = assess_health(frames, TH, baseline=baseline)
    assert h.clarity == "TAMPER"


def test_liveness_false_on_no_frames():
    h = assess_health([], TH)
    assert h.liveness is False
    assert is_gradeable(h, TH) is False


def test_clock_drift_gate():
    frames = [make_textured_frame(seed=i) for i in range(5)]
    base = frames[2]
    h = assess_health(frames, TH, baseline=base, clock_checker=lambda f: 12.0)
    assert h.clock_drift_s == 12.0
    assert is_gradeable(h, TH) is False              # > 5s drift => not gradeable


def test_emits_valid_camera_health_event():
    frames = [make_textured_frame(seed=i) for i in range(5)]
    h = assess_health(frames, TH, baseline=frames[2])
    t0 = datetime(2026, 9, 2, 23, 30, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 2, 23, 31, tzinfo=timezone.utc)
    ev = build_camera_health_event("0008", "CAM-0008-1", t0, t1, h)
    assert ev.event_type == "camera_health"
    assert ev.event_id and len(ev.event_id) == 32
    # normalized to store-local (CDT = -05:00), not Pakistan (+05:00)
    assert ev.timestamp_start.utcoffset().total_seconds() == -5 * 3600
    assert ev.camera_health.clarity == "OK"
