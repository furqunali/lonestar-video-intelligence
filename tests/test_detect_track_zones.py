"""M3 acceptance: person detection (interface + offline detectors), IoU
tracking across frames, and PolygonZone dwell/presence per camera."""
from __future__ import annotations

import numpy as np
import pytest

from avip.cv.detect import DarkBlobDetector, Detection, ScriptedDetector
from avip.cv.process import Tracklet, nominal_dt, process_clip
from avip.cv.track import IoUTracker, iou
from avip.cv.zones import build_zones, present_zones, scale_polygon
from tests.synth import make_person_frame


class _SF:
    """Minimal SampledFrame stand-in (index, ts_seconds, image)."""
    def __init__(self, index, ts, image):
        self.index, self.ts_seconds, self.image = index, ts, image


def test_iou_basic():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert 0 < iou((0, 0, 10, 10), (5, 5, 15, 15)) < 1


def test_scale_polygon_to_pixels():
    poly = scale_polygon([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], 320, 240)
    assert poly.tolist() == [[0, 0], [320, 0], [320, 240], [0, 240]]


def test_zone_presence_inside_and_outside():
    zones_norm = {"register": [[0.3, 0.3], [0.7, 0.3], [0.7, 0.9], [0.3, 0.9]]}
    zones = build_zones(zones_norm, (320, 240))
    inside = Detection((150, 100, 170, 200), 0.9)     # bottom-center ~ (160, 200) inside
    outside = Detection((10, 10, 30, 40), 0.9)        # bottom-center ~ (20, 40) outside
    assert "register" in present_zones(zones, inside)
    assert "register" not in present_zones(zones, outside)


def test_iou_tracker_keeps_one_id_for_smooth_motion():
    tracker = IoUTracker()
    ids = set()
    for i in range(6):
        x = 100 + i * 5                                # small smooth steps -> overlap
        dets = [Detection((x, 50, x + 40, 200), 0.9)]
        for tid, _ in tracker.update(dets, i):
            ids.add(tid)
    assert ids == {1}                                  # single sustained track


def test_iou_tracker_splits_disjoint_detections():
    tracker = IoUTracker()
    out0 = tracker.update([Detection((0, 0, 20, 40), 0.9)], 0)
    out1 = tracker.update([Detection((200, 200, 220, 240), 0.9)], 1)
    assert out0[0][0] != out1[0][0]                    # no overlap -> new id


def test_scripted_detector_sequences():
    d = ScriptedDetector([[Detection((0, 0, 1, 1), 0.5)], []])
    assert len(d(np.zeros((2, 2, 3), np.uint8))) == 1
    assert d(np.zeros((2, 2, 3), np.uint8)) == []


def test_process_clip_dwell_in_register():
    # Person walks across the register zone over 6 sampled frames at 3 fps.
    w, h = 320, 240
    zones_norm = {
        "register": [[0.30, 0.35], [0.70, 0.35], [0.70, 0.95], [0.30, 0.95]],
        "entrance": [[0.72, 0.05], [0.98, 0.05], [0.98, 0.55], [0.72, 0.55]],
    }
    frames = []
    for i in range(6):
        cx = int(w * (0.35 + 0.30 * i / 5))            # stays within register x-range
        frames.append(_SF(i, i / 3.0, make_person_frame(w, h, cx=cx, cy=int(h * 0.7))))

    tracklets = process_clip(frames, DarkBlobDetector(), zones_norm, frame_wh=(w, h))
    assert len(tracklets) >= 1
    tl: Tracklet = max(tracklets, key=lambda t: len(t.observations))
    assert "register" in tl.zones_present
    dwell = tl.zone_dwell(nominal_dt(frames))
    assert dwell.get("register", 0) > 0.0
    assert tl.max_confidence > 0.0


@pytest.mark.yolo
def test_yolo_detector_smoke():
    """Real YOLOv8n path — skipped if weights can't be fetched (offline CI)."""
    from avip.cv.detect import YoloDetector
    try:
        det = YoloDetector()
        out = det(make_person_frame(320, 240))
    except Exception as exc:                            # no network / no weights
        pytest.skip(f"YOLO weights unavailable: {exc}")
    assert isinstance(out, list)                        # returns detections list
