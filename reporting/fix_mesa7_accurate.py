"""Re-render MESA 7 evidence ACCURATELY.

The pose auto-picked a wrist-near-hip frame, but the CASH is clearly in the OTHER
(raised) hand and is NOT concealed in those frames — so "pocketed/concealed" was
inaccurate. Honest fix: put the callout on the CASH HAND (the raised wrist near the
counter) and label it truthfully as cash handled in hand at the register (no sale
rung) — the reconciliation path (POS sales log) is the exact-loss source of truth.
No fabricated concealment claim.
"""
from __future__ import annotations
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

EVID = Path(r"G:\Shared drives\4. AP\lonestar-video-intelligence\02_Evidence\Incident_Clips")
ANA = Path(__file__).resolve().parents[1] / "reports" / "incident_analysis"
SLUG = "auto_mesa_7_1_6c35"
FILE = "MESA 7 (1).wmv"

TEAL = (176, 122, 46); RED = (60, 60, 220); GREEN = (60, 200, 90); NAVY = (74, 44, 10); CYAN = (255, 200, 0)
LWR, RWR = 9, 10
FACE_KPS = [0, 1, 2, 3, 4]
# three moments where the cashier is handling cash in hand at the counter
SHOTS = [
    ("r2_txn", 27.0, "Cash in hand at the counter (no sale on POS)"),
    ("key", 50.5, "Cash handled in hand at the register - no sale rung"),
    ("r3_after", 52.5, "Cash retained in hand - verify vs POS sales log"),
]


def main_person(res):
    if res.keypoints is None or res.boxes is None or len(res.boxes) == 0:
        return None, None
    i = int(np.argmax(res.boxes.conf.cpu().numpy()))
    return res.keypoints.data[i].cpu().numpy(), res.boxes.xyxy[i].cpu().numpy()


def main():
    model = YOLO("yolov8n-pose.pt")
    cap = cv2.VideoCapture(str(EVID / FILE))
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    h = None
    for name, t, label in SHOTS:
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(int(t * fps), n - 1)); ok, fr = cap.read()
        if not ok:
            continue
        h, w = fr.shape[:2]
        res = model.predict(fr, verbose=False, conf=0.3)[0]
        kp, box = main_person(res)
        if box is not None:
            x1, y1, x2, y2 = [int(v) for v in box]
            cv2.rectangle(fr, (x1, y1), (x2, y2), TEAL, 2)
            cv2.putText(fr, "cashier", (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEAL, 2, cv2.LINE_AA)
        if kp is not None:
            # face box from face keypoints
            pts = [kp[i][:2] for i in FACE_KPS if kp[i][2] >= 0.3]
            if len(pts) >= 2:
                cx, cy = np.mean([p[0] for p in pts]), np.mean([p[1] for p in pts])
                r = max(34.0, 2.4 * max(np.std([p[0] for p in pts]) + 1, np.std([p[1] for p in pts]) + 1, 14))
                cv2.rectangle(fr, (int(cx - r), int(cy - r * 1.1)), (int(cx + r), int(cy + r * 1.1)), CYAN, 2)
                cv2.putText(fr, "FACE", (int(cx - r), max(14, int(cy - r * 1.1) - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, CYAN, 2, cv2.LINE_AA)
            # CASH HAND = the higher (smaller y) wrist that is up near the counter
            cand = [(kp[wr][1], kp[wr][0], kp[wr][2]) for wr in (LWR, RWR) if kp[wr][2] >= 0.3]
            if cand:
                cand.sort(key=lambda z: z[0])       # highest (smallest y) first
                wy, wx, _c = cand[0]
                cx, cy = int(wx), int(wy)
                cv2.rectangle(fr, (cx - 60, cy - 45), (cx + 60, cy + 45), RED, 3)
                cv2.putText(fr, "CASH IN HAND", (max(4, cx - 62), max(20, cy - 52)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.62, RED, 2, cv2.LINE_AA)
        cv2.rectangle(fr, (0, 0), (w, 40), NAVY, -1)
        cv2.putText(fr, "SUGARLAND PETROLEUM", (10, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.7, TEAL, 2, cv2.LINE_AA)
        cv2.putText(fr, label, (330, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.54, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.rectangle(fr, (0, h - 32), (w, h), (20, 20, 20), -1)
        cv2.putText(fr, f"AI FINDING (pose): {label}", (10, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, GREEN, 2, cv2.LINE_AA)
        cv2.imwrite(str(ANA / SLUG / f"{name}_after.jpg"), fr)
        print(f"{name} @ {t}s -> ok")
    cap.release()


if __name__ == "__main__":
    main()
