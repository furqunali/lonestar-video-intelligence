"""Synthetic media helpers for the test-suite.

There are no real DVR dumps on the build machine, so tests generate their own
tiny MP4s and frames. This keeps the whole suite self-contained and offline.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def make_frame(w: int = 320, h: int = 240, fill: int = 120) -> np.ndarray:
    """A plain BGR frame filled with a mid-grey value (uint8)."""
    return np.full((h, w, 3), fill, dtype=np.uint8)


def make_textured_frame(w: int = 320, h: int = 240, seed: int = 0) -> np.ndarray:
    """A sharp, high-variance frame (random texture) — passes the blur check."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)


def make_person_frame(w: int = 320, h: int = 240, cx: int = 160,
                     cy: int = 160) -> np.ndarray:
    """A textured frame with a dark upright rectangle ('person') at (cx, cy)."""
    frame = make_textured_frame(w, h, seed=1)
    x0, x1 = max(0, cx - 20), min(w, cx + 20)
    y0, y1 = max(0, cy - 50), min(h, cy + 50)
    frame[y0:y1, x0:x1] = 30
    return frame


def write_mp4(path: Path, n_frames: int = 30, w: int = 320, h: int = 240,
            fps: int = 10, moving_person: bool = True) -> Path:
    """Write a short valid MP4 using PyAV. Returns the path."""
    import av

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    container = av.open(str(path), mode="w")
    stream = container.add_stream("mpeg4", rate=fps)
    stream.width, stream.height, stream.pix_fmt = w, h, "yuv420p"
    for i in range(n_frames):
        if moving_person:
            cx = int(w * (0.2 + 0.6 * i / max(1, n_frames - 1)))
            arr = make_person_frame(w, h, cx=cx, cy=h // 2)
        else:
            arr = make_textured_frame(w, h, seed=i)
        frame = av.VideoFrame.from_ndarray(arr, format="bgr24")
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():   # flush
        container.mux(packet)
    container.close()
    return path


def paste_aruco(frame: np.ndarray, marker_id: int, center: tuple[int, int],
                size: int = 60, dict_name: str = "DICT_4X4_50") -> np.ndarray:
    """Paste an ArUco marker (BGR) centered at ``center`` into ``frame``."""
    import cv2

    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dict_name))
    marker = cv2.aruco.generateImageMarker(d, marker_id, size)      # grayscale
    marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    cx, cy = center
    x0, y0 = cx - size // 2, cy - size // 2
    h, w = frame.shape[:2]
    if 0 <= x0 and 0 <= y0 and x0 + size <= w and y0 + size <= h:
        frame[y0:y0 + size, x0:x0 + size] = marker_bgr
    return frame


def make_marker_frame(w: int = 320, h: int = 240, marker_id: int = 7,
                      center: tuple[int, int] = (160, 120), size: int = 60,
                      seed: int = 2) -> np.ndarray:
    """A textured frame with one ArUco marker pasted in."""
    frame = make_textured_frame(w, h, seed=seed)
    return paste_aruco(frame, marker_id, center, size=size)


def write_corrupt_mp4(path: Path) -> Path:
    """Write bytes that look like an .mp4 but cannot be decoded."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\xde\xad\xbe\xef" * 64)
    return path
