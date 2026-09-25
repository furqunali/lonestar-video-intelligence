"""Update MESA 3 to an accurate COLLUSION VOID.

OCR confirmed a CANCELLED overlay (3/40 frames). The exact line OCRs poorly, so
the amount and cashier are HUMAN-VERIFIED from the clearly-legible on-frame POS
receipt (same policy as the Jordan clip): CANCELLED -$15.39 (TOTAL 15.39), cashier
ALEX MORGAN, no cash collected. Updates the finding to void and re-renders
the key frame highlighting the POS cancel band.
"""
from __future__ import annotations
import json
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
ANA = ROOT / "reports" / "incident_analysis"
ALLF = ANA / "all_findings.json"
EVID = Path(r"G:\Shared drives\4. AP\lonestar-video-intelligence\02_Evidence\Incident_Clips")
SLUG = "auto_mesa_3_bf8e"
FILE = "MESA 3.wmv"
AMOUNT = "15.39"
CASHIER = "ALEX MORGAN"
CANCEL_FIRST_S = 13.8
CANCEL_COUNT = 3
FRAME_T = 51.0                       # a frame where the full CANCELLED overlay is legible

TEAL = (176, 122, 46); RED = (60, 60, 220); GREEN = (60, 200, 90); NAVY = (74, 44, 10); CYAN = (255, 200, 0)


def update_finding():
    data = json.loads(ALLF.read_text())
    for f in data:
        if f["slug"] == SLUG:
            f["has_overlay"] = True
            f["pos_overlay"] = {
                "cancel_detected": True,
                "canceled_amount": AMOUNT,
                "cashier": CASHIER,
                "cancel_first_s": CANCEL_FIRST_S,
                "cancel_sample_count": CANCEL_COUNT,
                "note": "amount & cashier human-verified from the on-frame POS receipt (OCR of the line is unreliable); also a smaller CANCELLED -1.34 is visible",
            }
            f["incident_verdict"] = "void"
            break
    ALLF.write_text(json.dumps(data, indent=2))
    print("finding updated -> void", AMOUNT, CASHIER)


def render_cancel():
    model = YOLO("yolov8n-pose.pt")
    cap = cv2.VideoCapture(str(EVID / FILE))
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.set(cv2.CAP_PROP_POS_FRAMES, min(int(FRAME_T * fps), n - 1))
    ok, fr = cap.read()
    cap.release()
    if not ok:
        print("could not read frame"); return
    h, w = fr.shape[:2]
    res = model.predict(fr, verbose=False, conf=0.3)[0]
    if res.boxes is not None and len(res.boxes):
        i = int(np.argmax(res.boxes.conf.cpu().numpy()))
        x1, y1, x2, y2 = [int(v) for v in res.boxes.xyxy[i].cpu().numpy()]
        cv2.rectangle(fr, (x1, y1), (x2, y2), TEAL, 2)
        cv2.putText(fr, "cashier", (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEAL, 2, cv2.LINE_AA)
        kp = res.keypoints.data[i].cpu().numpy() if res.keypoints is not None else None
        if kp is not None:
            pts = [kp[j][:2] for j in (0, 1, 2, 3, 4) if kp[j][2] >= 0.3]
            if len(pts) >= 2:
                cx, cy = np.mean([p[0] for p in pts]), np.mean([p[1] for p in pts])
                r = max(34.0, 2.4 * max(np.std([p[0] for p in pts]) + 1, np.std([p[1] for p in pts]) + 1, 14))
                cv2.rectangle(fr, (int(cx - r), int(cy - r * 1.1)), (int(cx + r), int(cy + r * 1.1)), CYAN, 2)
                cv2.putText(fr, "FACE", (int(cx - r), max(14, int(cy - r * 1.1) - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, CYAN, 2, cv2.LINE_AA)
    # highlight the POS cancel band (top-centre where the receipt is burned in)
    bx1, by1, bx2, by2 = int(0.30 * w), int(0.06 * h), int(0.74 * w), int(0.44 * h)
    cv2.rectangle(fr, (bx1, by1), (bx2, by2), RED, 3)
    cv2.putText(fr, f"POS: CANCELLED -${AMOUNT}", (bx1, max(20, by1 - 26)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, RED, 2, cv2.LINE_AA)
    cv2.putText(fr, f"cashier {CASHIER} - no cash collected", (bx1, max(20, by1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, RED, 2, cv2.LINE_AA)
    # brand + finding strip
    cv2.rectangle(fr, (0, 0), (w, 40), NAVY, -1)
    cv2.putText(fr, "SUGARLAND PETROLEUM", (10, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.7, TEAL, 2, cv2.LINE_AA)
    label = f"Cancelled sale voided - CANCELLED -${AMOUNT}, cashier {CASHIER}"
    cv2.putText(fr, label, (330, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.rectangle(fr, (0, h - 32), (w, h), (20, 20, 20), -1)
    cv2.putText(fr, f"AI FINDING: VOID/CANCELLED sale -${AMOUNT}, no cash collected (POS overlay)",
                (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREEN, 2, cv2.LINE_AA)
    cv2.imwrite(str(ANA / SLUG / "receipt_after.jpg"), fr)
    print("receipt_after.jpg (cancel highlight) written")


if __name__ == "__main__":
    update_finding()
    render_cancel()
