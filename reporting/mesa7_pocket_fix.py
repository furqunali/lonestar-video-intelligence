"""MESA 7 — lock in the ACTUAL currency-to-pocket frame (human-pointed: 0:57).

Furqan verified the cashier folds a currency note into her pocket at ~57s (her
lower/waist hand). The auto pose earlier keyed on the counter hand; here we use the
human timestamp and annotate the waist hand (lower wrist) as the concealment.
"""
from __future__ import annotations
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
ANA = ROOT / "reports" / "incident_analysis"
EVID = Path(r"G:\Shared drives\4. AP\lonestar-video-intelligence\02_Evidence\Incident_Clips")
SLUG = "auto_mesa_7_1_6c35"
FILE = "MESA 7 (1).wmv"

TEAL = (176, 122, 46); RED = (60, 60, 220); GREEN = (60, 200, 90); NAVY = (74, 44, 10); CYAN = (255, 200, 0)
LWR, RWR = 9, 10
FACE_KPS = [0, 1, 2, 3, 4]
SHOTS = [
    ("key", 57.0, "Cashier folds currency note - hand to pocket (0:57)", "pocket"),
    ("r3_after", 58.0, "Currency note pushed into pocket (0:58) - no sale on POS", "pocket"),
]


def main_person(res):
    if res.keypoints is None or res.boxes is None or len(res.boxes) == 0:
        return None, None
    i = int(np.argmax(res.boxes.conf.cpu().numpy()))
    return res.keypoints.data[i].cpu().numpy(), res.boxes.xyxy[i].cpu().numpy()


def main():
    model = YOLO("yolov8n-pose.pt")
    cap = cv2.VideoCapture(str(EVID / FILE))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    for name, t, label, kind in SHOTS:
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
            pts = [kp[i][:2] for i in FACE_KPS if kp[i][2] >= 0.3]
            if len(pts) >= 2:
                cx, cy = np.mean([p[0] for p in pts]), np.mean([p[1] for p in pts])
                r = max(34.0, 2.4 * max(np.std([p[0] for p in pts]) + 1, np.std([p[1] for p in pts]) + 1, 14))
                cv2.rectangle(fr, (int(cx - r), int(cy - r * 1.1)), (int(cx + r), int(cy + r * 1.1)), CYAN, 2)
                cv2.putText(fr, "FACE", (int(cx - r), max(14, int(cy - r * 1.1) - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, CYAN, 2, cv2.LINE_AA)
            # the WAIST hand = the lower wrist (larger y) — that's the one at the pocket
            wr_pts = [(kp[wr][0], kp[wr][1]) for wr in (LWR, RWR) if kp[wr][2] >= 0.25]
            if wr_pts:
                wx, wy = max(wr_pts, key=lambda p: p[1])       # lowest in frame = at the waist
                cx, cy = int(wx), int(wy)
                cv2.circle(fr, (cx, cy), 9, RED, -1)
                if kind == "pocket":
                    cv2.rectangle(fr, (cx - 58, cy - 42), (cx + 58, cy + 52), RED, 3)
                    cv2.putText(fr, "FOLDED CURRENCY -> POCKET", (max(4, cx - 62), min(h - 8, cy + 78)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, RED, 2, cv2.LINE_AA)
        cv2.rectangle(fr, (0, 0), (w, 40), NAVY, -1)
        cv2.putText(fr, "SUGARLAND PETROLEUM", (10, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.7, TEAL, 2, cv2.LINE_AA)
        cv2.putText(fr, label, (330, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.54, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.rectangle(fr, (0, h - 32), (w, h), (20, 20, 20), -1)
        cv2.putText(fr, f"AI FINDING: {label}", (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREEN, 2, cv2.LINE_AA)
        cv2.imwrite(str(ANA / SLUG / f"{name}_after.jpg"), fr)
        print(f"{name} @ {t}s -> ok")
    cap.release()


if __name__ == "__main__":
    main()
