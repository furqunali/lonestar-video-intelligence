"""M4 acceptance: ArUco decode + multi-frame majority vote -> marker_code."""
from __future__ import annotations

from avip.cv.detect import Detection, ScriptedDetector
from avip.cv.markers import (
    ArucoReader,
    decode_markers_for_frames,
    marker_code_for,
    vote_marker,
)
from avip.cv.process import process_clip
from tests.synth import make_marker_frame, make_textured_frame


class _SF:
    def __init__(self, index, ts, image):
        self.index, self.ts_seconds, self.image = index, ts, image


def test_decode_single_marker():
    reader = ArucoReader("DICT_4X4_50")
    frame = make_marker_frame(marker_id=12, center=(160, 120), size=70)
    hits = reader.detect(frame)
    ids = {h.marker_id for h in hits}
    assert 12 in ids


def test_no_marker_returns_empty():
    reader = ArucoReader("DICT_4X4_50")
    assert reader.detect(make_textured_frame(seed=42)) == []


def test_marker_code_format():
    assert marker_code_for(7) == "ARUCO-7"


def test_vote_assigns_marker_when_enough_frames():
    reader = ArucoReader("DICT_4X4_50")
    w, h = 320, 240
    # 5 frames: marker 9 near the top of a fixed person box in all of them.
    frames, boxes = [], []
    for i in range(5):
        frames.append(_SF(i, i / 3.0, make_marker_frame(
            w, h, marker_id=9, center=(160, 90), size=64, seed=i)))
        boxes.append([Detection((120.0, 60.0, 200.0, 220.0), 0.9)])  # box holds marker

    per_frame = decode_markers_for_frames(reader, frames)
    tracklets = process_clip(frames, ScriptedDetector(boxes),
                             zones_norm={}, frame_wh=(w, h))
    assert len(tracklets) == 1
    code = vote_marker(tracklets[0], per_frame, vote_min_frames=3)
    assert code == "ARUCO-9"


def test_vote_returns_none_below_threshold():
    reader = ArucoReader("DICT_4X4_50")
    w, h = 320, 240
    # Marker visible in only 1 of 4 frames -> below the 3-frame threshold.
    frames, boxes = [], []
    for i in range(4):
        if i == 0:
            img = make_marker_frame(w, h, marker_id=5, center=(160, 90), size=64, seed=i)
        else:
            img = make_textured_frame(w, h, seed=100 + i)
        frames.append(_SF(i, i / 3.0, img))
        boxes.append([Detection((120.0, 60.0, 200.0, 220.0), 0.9)])

    per_frame = decode_markers_for_frames(reader, frames)
    tracklets = process_clip(frames, ScriptedDetector(boxes),
                             zones_norm={}, frame_wh=(w, h))
    code = vote_marker(tracklets[0], per_frame, vote_min_frames=3)
    assert code is None


def test_marker_outside_box_not_counted():
    reader = ArucoReader("DICT_4X4_50")
    w, h = 320, 240
    frames, boxes = [], []
    for i in range(4):
        # marker at far right, but the person box is on the left -> no votes
        frames.append(_SF(i, i / 3.0, make_marker_frame(
            w, h, marker_id=3, center=(280, 90), size=48, seed=i)))
        boxes.append([Detection((10.0, 60.0, 90.0, 220.0), 0.9)])
    per_frame = decode_markers_for_frames(reader, frames)
    tracklets = process_clip(frames, ScriptedDetector(boxes),
                             zones_norm={}, frame_wh=(w, h))
    assert vote_marker(tracklets[0], per_frame, vote_min_frames=3) is None
