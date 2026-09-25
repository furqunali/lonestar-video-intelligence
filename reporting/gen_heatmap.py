"""Generate traffic + dwell heat-map overlays for the floor clips using the real
detection+tracking pipeline. Saves PNGs into reports/analytics/ and records the
distinct-person count per clip. Offline, deterministic."""
from __future__ import annotations

import sys, json
from dataclasses import dataclass
from pathlib import Path

import cv2, numpy as np

sys.path.insert(0, r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence")
from avip.cv.detect import YoloDetector
from avip.cv.track import IoUTracker
from avip.cv.process import process_clip, nominal_dt
from avip.analytics import heatmap

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "New Videos for test"
OUT = ROOT / "reports" / "analytics"; OUT.mkdir(parents=True, exist_ok=True)

FLOOR = [("27 Jan 2024 Stealing 1.mp4", "27jan", "Sales floor — 27 Jan"),
         ("Stealing 14-may.mp4", "14may", "Sales floor — 14 May")]


@dataclass
class SF:
    index: int
    ts_seconds: float
    image: np.ndarray


def sample(path, fps_target=1.5):
    cap = cv2.VideoCapture(str(path)); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); step = max(1, int(fps / fps_target))
    frames, i = [], 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        if i % step == 0:
            frames.append(SF(i, i / fps, fr))
        i += 1
    cap.release(); return frames


def main():
    results = {}
    for fn, slug, label in FLOOR:
        p = SRC / fn
        if not p.exists():
            print("missing", fn); continue
        frames = sample(p)
        if not frames:
            continue
        h, w = frames[0].image.shape[:2]
        tracklets = process_clip(frames, YoloDetector(conf=0.30), {},
                                 tracker=IoUTracker(), frame_wh=(w, h))
        dt = nominal_dt(frames)
        # clean background = a mid frame, upscaled 2x + light unsharp so the store
        # scene reads crisp under the heat (counters the low-res softness)
        bg = cv2.resize(frames[len(frames) // 2].image, (w * 2, h * 2),
                        interpolation=cv2.INTER_CUBIC)
        bg = cv2.addWeighted(bg, 1.5, cv2.GaussianBlur(bg, (0, 0), 3), -0.5, 0)
        # scale feet points to the 2x background
        for kind, dwell in (("traffic", False), ("dwell", True)):
            pts = heatmap.points_from_tracklets(tracklets, dt, dwell=dwell)
            for pt in pts:
                pt.x *= 2; pt.y *= 2
            acc = heatmap.accumulate(pts, bg.shape[:2])
            # tighter blur + gamma/floor => crisp hotspots, clean frame elsewhere
            # (removes the faint colour-shadow wash), stronger for dwell
            overlay = heatmap.render_overlay(
                acc, bg, sigma=22, alpha=0.7, gamma=1.5, floor=0.10)
            # brand banner
            cv2.rectangle(overlay, (0, 0), (overlay.shape[1], 46), (74, 44, 10), -1)
            cv2.putText(overlay, "SUGARLAND PETROLEUM  -  HEAT MAP",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (176, 122, 46), 2, cv2.LINE_AA)
            cv2.putText(overlay, f"{label}  ({kind})", (overlay.shape[1] - 430, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 215, 255), 1, cv2.LINE_AA)
            cv2.imwrite(str(OUT / f"heat_{slug}_{kind}.jpg"), overlay,
                        [cv2.IMWRITE_JPEG_QUALITY, 88])
        results[slug] = {"label": label, "distinct_persons": len(tracklets),
                         "samples": len(frames)}
        print(f"{label}: {len(tracklets)} distinct persons over {len(frames)} samples")

    (OUT / "heatmap.json").write_text(json.dumps(results, indent=2))
    print("wrote heat maps ->", OUT)


if __name__ == "__main__":
    main()
