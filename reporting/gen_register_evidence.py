"""Generate 3-4 annotated evidence frames per auto-calibrated REGISTER incident,
so each incident card has a proper slideshow (not a single frame).

Frames (chronological): register overview -> counter activity -> KEY cash-drawer
act (motion peak) -> immediately after. Every frame is derived from pixels
(YOLO persons + cash-drawer ROI + motion peak) and branded. No fabricated values.
"""
from __future__ import annotations
import json
from pathlib import Path

import cv2
import numpy as np

from avip.cv.detect import YoloDetector

ROOT = Path(__file__).resolve().parents[1]
ANA = ROOT / "reports" / "incident_analysis"
# Local video store (Furqan's 17-Sep decision: raw footage stays on the local PC).
EVID = ROOT / "02_Evidence" / "Incident_Clips"

TEAL = (176, 122, 46); YELLOW = (0, 215, 255); RED = (60, 60, 220)
GREEN = (60, 200, 90); NAVY = (74, 44, 10)

# slug -> source clip filename (in the evidence store)
CLIPS = {
    "auto_mesa_1_1742": "MESA 1.wmv",
    "auto_mesa_2_8ca6": "MESA 2.wmv",
    "auto_mesa_3_bf8e": "MESA 3.wmv",
}


def banner(img, title):
    h, w = img.shape[:2]
    cv2.rectangle(img, (0, 0), (w, 40), NAVY, -1)
    cv2.putText(img, "SUGARLAND PETROLEUM", (10, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.7, TEAL, 2, cv2.LINE_AA)
    cv2.putText(img, title, (330, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 1, cv2.LINE_AA)


def gen_for(slug: str, fname: str, det: YoloDetector, roi=None):
    vp = EVID / fname
    if not vp.exists():
        print("MISSING", vp); return 0
    outdir = ANA / slug; outdir.mkdir(parents=True, exist_ok=True)
    try:
        cal = json.loads((outdir / "calibration.json").read_text())
    except Exception:
        cal = {}
    roi = roi or cal.get("cash_roi") or (0.35, 0.30, 0.72, 0.82)
    cap = cv2.VideoCapture(str(vp))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if n <= 0 or w == 0:
        print("unreadable", vp); cap.release(); return 0
    rx1, ry1, rx2, ry2 = int(roi[0]*w), int(roi[1]*h), int(roi[2]*w), int(roi[3]*h)

    # locate the cash-drawer motion peak
    idxs = [int(i*(n-1)/39) for i in range(40)] if n > 40 else list(range(n))
    prev, motion = None, []
    for ix in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, ix); ok, fr = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(fr[ry1:ry2, rx1:rx2], cv2.COLOR_BGR2GRAY)
        m = float(np.mean(cv2.absdiff(g, prev))) if (prev is not None and prev.shape == g.shape) else 0.0
        prev = g; motion.append((ix, m))
    peak = max(motion, key=lambda t: t[1])[0] if motion else n // 2

    # 3 ACCURATE frames anchored on the actual incident (the cash-drawer motion
    # peak): just-before (approach) -> the key act -> just-after (cash handled).
    gap = int(2 * fps)
    before = max(0, peak - gap)
    if before == peak:
        before = max(0, peak - int(fps))
    after_ix = min(n - 1, peak + gap)
    if after_ix == peak:
        after_ix = min(n - 1, peak + int(fps))
    picks = [
        ("r2_txn", before, "At the counter (no customer, no sale)"),
        ("key", peak, "Cash taken from the open drawer"),
        ("r3_after", after_ix, "Just after - cash in hand"),
    ]
    made = 0
    for name, ix, label in picks:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(ix, n - 1))); ok, fr = cap.read()
        if not ok:
            continue
        after = fr.copy()
        small = cv2.resize(fr, (960, int(960 * h / w))); sc = w / 960.0
        for d in det(small):
            x1, y1, x2, y2 = [int(v * sc) for v in d.xyxy]
            cv2.rectangle(after, (x1, y1), (x2, y2), TEAL, 2)
            cv2.putText(after, f"person {d.confidence:.2f}", (x1, max(18, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEAL, 2, cv2.LINE_AA)
        cv2.rectangle(after, (rx1, ry1), (rx2, ry2), YELLOW, 2)
        cv2.putText(after, "CASH DRAWER", (rx1, max(20, ry1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, YELLOW, 2, cv2.LINE_AA)
        if name == "key":
            cv2.rectangle(after, (rx1 - 5, ry1 - 5), (rx2 + 5, ry2 + 5), RED, 3)
            cv2.putText(after, "KEY ACT", (rx1, min(h - 6, ry2 + 26)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, RED, 2, cv2.LINE_AA)
        banner(after, label)
        cv2.rectangle(after, (0, h - 32), (w, h), (20, 20, 20), -1)
        cv2.putText(after, f"AI FINDING: {label}", (10, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, GREEN, 2, cv2.LINE_AA)
        cv2.imwrite(str(outdir / f"{name}_after.jpg"), after)
        made += 1
    cap.release()
    print(f"{slug} -> {made} frames")
    return made


def main():
    det = YoloDetector(conf=0.30)
    for slug, fname in CLIPS.items():
        gen_for(slug, fname, det)


if __name__ == "__main__":
    main()
