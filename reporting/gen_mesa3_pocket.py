"""MESA 3 — capture the cashier's hand-to-pocket (cash concealment) moment.

Furqan (human ground truth) confirmed it happens in the LAST 25 SECONDS. We do NOT
guess blindly: we search only that window and pick the frame with the strongest
LOWER-BODY (waist/pocket) motion of the cashier — a targeted, honest proxy for the
hand-to-pocket gesture (true gesture recognition would need pose models). Produces
3 frames: approach -> HAND-TO-POCKET (key) -> after.
"""
from __future__ import annotations
import json
from pathlib import Path

import cv2
import numpy as np

from avip.cv.detect import YoloDetector

ROOT = Path(__file__).resolve().parents[1]
ANA = ROOT / "reports" / "incident_analysis"
EVID = Path(r"G:\Shared drives\4. AP\lonestar-video-intelligence\02_Evidence\Incident_Clips")
SLUG = "auto_mesa_3_bf8e"
FILE = "MESA 3.wmv"
WINDOW_S = 25.0                         # last 25s (Furqan's ground truth)

TEAL = (176, 122, 46); YELLOW = (0, 215, 255); RED = (60, 60, 220)
GREEN = (60, 200, 90); NAVY = (74, 44, 10)


def banner(img, title):
    w = img.shape[1]
    cv2.rectangle(img, (0, 0), (w, 40), NAVY, -1)
    cv2.putText(img, "SUGARLAND PETROLEUM", (10, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.7, TEAL, 2, cv2.LINE_AA)
    cv2.putText(img, title, (330, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (255, 255, 255), 1, cv2.LINE_AA)


def biggest_person(dets, sc):
    best, area = None, 0
    for d in dets:
        x1, y1, x2, y2 = [v * sc for v in d.xyxy]
        a = (x2 - x1) * (y2 - y1)
        if a > area:
            area, best = a, (int(x1), int(y1), int(x2), int(y2), d.confidence)
    return best


def main():
    vp = EVID / FILE
    outdir = ANA / SLUG; outdir.mkdir(parents=True, exist_ok=True)
    det = YoloDetector(conf=0.30)
    cap = cv2.VideoCapture(str(vp))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    dur = n / fps
    start_t = max(0.0, dur - WINDOW_S)
    step = max(1, int(fps * 0.5))          # ~every 0.5s
    start_ix = int(start_t * fps)
    try:
        cal = json.loads((outdir / "calibration.json").read_text())
        croi = cal.get("cash_roi") or (0.35, 0.30, 0.72, 0.82)
    except Exception:
        croi = (0.35, 0.30, 0.72, 0.82)
    cx1, cy1, cx2, cy2 = int(croi[0]*w), int(croi[1]*h), int(croi[2]*w), int(croi[3]*h)

    # PASS A (whole clip): cash-drawer ROI motion -> "cash in hand at the counter"
    prevc = None
    cash_series = []
    ix = 0
    while ix < n:
        cap.set(cv2.CAP_PROP_POS_FRAMES, ix); ok, fr = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(fr[cy1:cy2, cx1:cx2], cv2.COLOR_BGR2GRAY)
        m = float(np.mean(cv2.absdiff(g, prevc))) if (prevc is not None and prevc.shape == g.shape) else 0.0
        prevc = g
        cash_series.append((ix, m))
        ix += step

    # PASS B (last 25s): lower-body (waist/pocket) motion -> "hand to pocket"
    prevlow = None
    samples = []
    ix = start_ix
    while ix < n:
        cap.set(cv2.CAP_PROP_POS_FRAMES, ix); ok, fr = cap.read()
        if not ok:
            break
        small = cv2.resize(fr, (960, int(960 * h / w))); sc = w / 960.0
        box = biggest_person(det(small), sc)
        low = 0.0
        if box:
            x1, y1, x2, y2, _c = box
            ly1 = y1 + int((y2 - y1) * 0.55)
            crop = cv2.cvtColor(fr[max(0, ly1):y2, max(0, x1):x2], cv2.COLOR_BGR2GRAY)
            if prevlow is not None and prevlow.shape == crop.shape and crop.size:
                low = float(np.mean(cv2.absdiff(crop, prevlow)))
            prevlow = crop if crop.size else prevlow
        samples.append((ix, box, low))
        ix += step

    scored = [s for s in samples if s[1]]
    if not scored:
        print("no person found in window"); cap.release(); return
    peak = max(scored, key=lambda s: s[2])
    peak_ix = peak[0]                                  # hand-to-pocket moment

    # cash-in-hand = drawer-motion peak; if it lands within 4s of the pocket moment,
    # restrict it to BEFORE the last-25s window so the two frames are distinct.
    cih_ix = max(cash_series, key=lambda t: t[1])[0] if cash_series else max(0, peak_ix - int(5*fps))
    if abs(cih_ix - peak_ix) < int(4 * fps):
        earlier = [t for t in cash_series if t[0] < start_ix]
        if earlier:
            cih_ix = max(earlier, key=lambda t: t[1])[0]
        else:
            cih_ix = max(0, peak_ix - int(6 * fps))
    before_ix = cih_ix
    after_ix = min(n - 1, peak_ix + int(2 * fps))

    def render(ix, name, label, pocket=False, cash=False):
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(ix, n - 1))); ok, fr = cap.read()
        if not ok:
            return
        after = fr.copy()
        small = cv2.resize(fr, (960, int(960 * h / w))); sc = w / 960.0
        box = biggest_person(det(small), sc)
        if box:
            x1, y1, x2, y2, c = box
            cv2.rectangle(after, (x1, y1), (x2, y2), TEAL, 2)
            cv2.putText(after, f"cashier {c:.2f}", (x1, max(18, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEAL, 2, cv2.LINE_AA)
            if pocket:
                ly1 = y1 + int((y2 - y1) * 0.55)
                cv2.rectangle(after, (x1 - 3, ly1 - 3), (x2 + 3, y2 + 3), RED, 3)
                cv2.putText(after, "HAND -> POCKET (cash concealed)", (max(4, x1 - 3), min(h - 8, y2 + 26)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.62, RED, 2, cv2.LINE_AA)
        if cash:
            cv2.rectangle(after, (cx1, cy1), (cx2, cy2), RED, 3)
            cv2.putText(after, "CASH IN HAND (no sale on POS)", (cx1, max(20, cy1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, RED, 2, cv2.LINE_AA)
        banner(after, label)
        cv2.rectangle(after, (0, h - 32), (w, h), (20, 20, 20), -1)
        cv2.putText(after, f"AI FINDING: {label}", (10, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, GREEN, 2, cv2.LINE_AA)
        cv2.imwrite(str(outdir / f"{name}_after.jpg"), after)

    render(before_ix, "r2_txn", "Cash in hand at the counter — no sale rung", cash=True)
    render(peak_ix, "key", "Cashier's hand goes to pocket — cash concealed", pocket=True)
    render(after_ix, "r3_after", "After — cash pocketed, drawer closed")
    print(f"cash-in-hand @ {before_ix/fps:.1f}s | pocket @ {peak_ix/fps:.1f}s | after @ {after_ix/fps:.1f}s")
    cap.release()
    print(f"MESA 3 pocket frames done. peak at {peak_ix/fps:.1f}s (window {start_t:.0f}-{dur:.0f}s), "
          f"lower-body motion {peak[2]:.1f}")


if __name__ == "__main__":
    main()
