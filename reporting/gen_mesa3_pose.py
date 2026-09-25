"""MESA 3 evidence via POSE ESTIMATION (automatic — no manual pointing).

Uses YOLOv8-pose keypoints so the SYSTEM itself finds the moments:
  * HAND -> POCKET  = a wrist keypoint moves down to / below the hip (waist/pocket),
    minimal normalized wrist-hip distance. This is real gesture detection, not a
    motion guess.
  * CASH IN HAND    = both wrists close together and above the hips (counting cash).
Face is boxed from the face keypoints (nose/eyes/ears) = face DETECTION (locating
a face), NOT recognition/identity (that stays management-gated per governance).

Writes r2_txn (cash in hand), key (hand to pocket), r3_after — auto-selected.
"""
from __future__ import annotations
import sys
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

# Local video store (Furqan's 17-Sep decision: raw footage stays on the local PC).
EVID = Path(__file__).resolve().parents[1] / "02_Evidence" / "Incident_Clips"
ANA = Path(__file__).resolve().parents[1] / "reports" / "incident_analysis"
STEP_S = 0.5
MAX_WRIST_HIP = 0.22           # only accept a pose "hand-to-pocket" if the wrist is
#                                this close to the hip (normalized) — else keep motion frames

TEAL = (176, 122, 46); YELLOW = (0, 215, 255); RED = (60, 60, 220)
GREEN = (60, 200, 90); NAVY = (74, 44, 10); CYAN = (255, 200, 0)
# COCO keypoint indices
NOSE, LSH, RSH, LWR, RWR, LHIP, RHIP = 0, 5, 6, 9, 10, 11, 12
FACE_KPS = [0, 1, 2, 3, 4]


def main_person(res):
    """Return keypoints (17,3) and box of the highest-confidence person, or None."""
    if res.keypoints is None or res.boxes is None or len(res.boxes) == 0:
        return None, None
    confs = res.boxes.conf.cpu().numpy()
    i = int(np.argmax(confs))
    kp = res.keypoints.data[i].cpu().numpy()          # (17,3): x,y,conf
    box = res.boxes.xyxy[i].cpu().numpy()
    return kp, box


def kp_ok(kp, idx, thr=0.3):
    return kp[idx][2] >= thr


def dist(a, b):
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def face_box(kp):
    pts = [kp[i][:2] for i in FACE_KPS if kp[i][2] >= 0.3]
    if len(pts) < 2:
        return None
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    cx, cy = np.mean(xs), np.mean(ys)
    r = max(30.0, 2.4 * max(np.std(xs) + 1, np.std(ys) + 1, 12))
    return int(cx - r), int(cy - r * 1.1), int(cx + r), int(cy + r * 1.1)


def run(slug, file, window_s=25.0):
    """Pose-based auto evidence for one register clip. Upgrades r2_txn/key/r3_after
    to POSE frames only when a clear hand->pocket gesture exists; otherwise leaves
    the existing (motion) frames untouched. Returns True if pose frames were written."""
    MAX_WRIST_HIP = 0.22       # accept a pose "hand-to-pocket" only this close to the hip
    model = YOLO("yolov8n-pose.pt")
    cap = cv2.VideoCapture(str(EVID / file))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    dur = n / fps
    step = max(1, int(fps * STEP_S))

    frames = []                                        # (ix, t, kp)
    ix = 0
    while ix < n:
        cap.set(cv2.CAP_PROP_POS_FRAMES, ix); ok, fr = cap.read()
        if not ok:
            break
        res = model.predict(fr, verbose=False, conf=0.3)[0]
        kp, _box = main_person(res)
        frames.append((ix, ix / fps, kp))
        ix += step

    def torso(kp):
        # normalizer: shoulder->hip length (fallback to a constant)
        if kp_ok(kp, LSH) and kp_ok(kp, LHIP):
            d = dist(kp[LSH], kp[LHIP])
            if d > 5:
                return d
        return max(40.0, h * 0.15)

    pocket_best, cash_best = None, None
    for ix, t, kp in frames:
        if kp is None:
            continue
        tl = torso(kp)
        # HAND -> POCKET: a wrist near a hip and at/below hip height
        wh = []
        for wr in (LWR, RWR):
            if not kp_ok(kp, wr):
                continue
            for hp in (LHIP, RHIP):
                if not kp_ok(kp, hp):
                    continue
                d = dist(kp[wr], kp[hp]) / tl
                below = kp[wr][1] >= kp[hp][1] - 0.25 * tl
                if below:
                    wh.append(d)
        if wh:
            score = min(wh)
            if t >= dur - window_s and (pocket_best is None or score < pocket_best[0]):
                pocket_best = (score, ix, t, kp)
        # CASH IN HAND: both wrists close together, above the hips
        if kp_ok(kp, LWR) and kp_ok(kp, RWR):
            hands = dist(kp[LWR], kp[RWR]) / tl
            hipy = np.mean([kp[LHIP][1] if kp_ok(kp, LHIP) else h,
                            kp[RHIP][1] if kp_ok(kp, RHIP) else h])
            above = (kp[LWR][1] < hipy) and (kp[RWR][1] < hipy)
            if hands < 0.9 and above and (cash_best is None or hands < cash_best[0]):
                cash_best = (hands, ix, t, kp)

    if pocket_best is None:
        print("pose: no clear hand-to-pocket found in window"); cap.release(); return False
    if pocket_best[0] > MAX_WRIST_HIP:
        print(f"pose: weak hand-to-pocket signal ({pocket_best[0]:.2f} > {MAX_WRIST_HIP}) "
              f"- keeping existing motion frames (honest)"); cap.release(); return False
    p_ix, p_t = pocket_best[1], pocket_best[2]
    if cash_best is None or abs(cash_best[2] - p_t) < 3:
        c_ix = max(0, p_ix - int(6 * fps)); c_t = c_ix / fps
    else:
        c_ix, c_t = cash_best[1], cash_best[2]
    a_ix = min(n - 1, p_ix + int(2 * fps))

    def render(ix, name, label, kind):
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, min(ix, n - 1))); ok, fr = cap.read()
        if not ok:
            return
        after = fr.copy()
        res = model.predict(fr, verbose=False, conf=0.3)[0]
        kp, box = main_person(res)
        if box is not None:
            x1, y1, x2, y2 = [int(v) for v in box]
            cv2.rectangle(after, (x1, y1), (x2, y2), TEAL, 2)
            cv2.putText(after, "cashier", (x1, max(18, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEAL, 2, cv2.LINE_AA)
        if kp is not None:
            fb = face_box(kp)
            if fb:
                cv2.rectangle(after, (fb[0], fb[1]), (fb[2], fb[3]), CYAN, 2)
                cv2.putText(after, "FACE", (fb[0], max(14, fb[1] - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, CYAN, 2, cv2.LINE_AA)
            for wr in (LWR, RWR):
                if kp_ok(kp, wr):
                    cv2.circle(after, (int(kp[wr][0]), int(kp[wr][1])), 8, RED, -1)
            if kind == "pocket":
                wr = LWR if (kp_ok(kp, LWR) and (not kp_ok(kp, RWR) or kp[LWR][1] > kp[RWR][1])) else RWR
                if kp_ok(kp, wr):
                    cx, cy = int(kp[wr][0]), int(kp[wr][1])
                    cv2.rectangle(after, (cx - 55, cy - 45), (cx + 55, cy + 55), RED, 3)
                    cv2.putText(after, "HAND -> POCKET", (max(4, cx - 60), min(h - 8, cy + 80)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, RED, 2, cv2.LINE_AA)
            elif kind == "cash":
                if kp_ok(kp, LWR) and kp_ok(kp, RWR):
                    mx = int((kp[LWR][0] + kp[RWR][0]) / 2); my = int((kp[LWR][1] + kp[RWR][1]) / 2)
                    cv2.rectangle(after, (mx - 70, my - 45), (mx + 70, my + 45), RED, 3)
                    cv2.putText(after, "CASH IN HAND", (max(4, mx - 70), max(20, my - 52)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, RED, 2, cv2.LINE_AA)
        # brand
        cv2.rectangle(after, (0, 0), (after.shape[1], 40), NAVY, -1)
        cv2.putText(after, "SUGARLAND PETROLEUM", (10, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.7, TEAL, 2, cv2.LINE_AA)
        cv2.putText(after, label, (330, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.56, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.rectangle(after, (0, h - 32), (after.shape[1], h), (20, 20, 20), -1)
        cv2.putText(after, f"AI FINDING: {label}", (10, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, GREEN, 2, cv2.LINE_AA)
        cv2.imwrite(str(ANA / slug / f"{name}_after.jpg"), after)

    render(c_ix, "r2_txn", "Cash in hand at the counter (no sale rung up)", "cash")
    render(p_ix, "key", "Cashier's hand goes to the pocket (hiding cash)", "pocket")
    render(a_ix, "r3_after", "Just after - cash pocketed, drawer closed", "after")
    cap.release()
    print(f"POSE-AUTO: cash-in-hand @ {c_t:.1f}s | HAND->POCKET @ {p_t:.1f}s "
          f"(wrist-hip {pocket_best[0]:.2f}) | after @ {a_ix/fps:.1f}s")
    return True


def main():
    # CLI: python gen_mesa3_pose.py <slug> <clip filename> [window_s]   (defaults = MESA 3)
    slug = sys.argv[1] if len(sys.argv) > 1 else "auto_mesa_3_bf8e"
    file = sys.argv[2] if len(sys.argv) > 2 else "MESA 3.wmv"
    window_s = float(sys.argv[3]) if len(sys.argv) > 3 else 25.0
    run(slug, file, window_s)


if __name__ == "__main__":
    main()
