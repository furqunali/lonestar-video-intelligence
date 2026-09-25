"""Contact sheet of MESA 3's last 25 seconds so Furqan can point to the exact
hand-to-pocket frame. Each thumbnail is labelled with its timestamp; he tells me
the timestamp and I lock that exact frame in as the key evidence.
"""
from __future__ import annotations
import math
from pathlib import Path

import cv2
import numpy as np

from avip.cv.detect import YoloDetector

EVID = Path(r"G:\Shared drives\4. AP\lonestar-video-intelligence\02_Evidence\Incident_Clips")
OUT = Path(r"G:\Shared drives\4. AP\lonestar-video-intelligence\MESA3_pocket_candidates.jpg")
FILE = "MESA 3.wmv"
WINDOW_S = 25.0
STEP_S = 1.5
COLS = 4
TW = 470                                   # thumbnail width

TEAL = (176, 122, 46); YELLOW = (0, 215, 255); NAVY = (74, 44, 10)


def main():
    det = YoloDetector(conf=0.30)
    cap = cv2.VideoCapture(str(EVID / FILE))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    dur = n / fps
    t = max(0.0, dur - WINDOW_S)
    thumbs = []
    while t <= dur:
        ix = int(t * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(ix, n - 1)); ok, fr = cap.read()
        if not ok:
            break
        small = cv2.resize(fr, (960, int(960 * h / w))); sc = w / 960.0
        for d in det(small):
            x1, y1, x2, y2 = [int(v * sc) for v in d.xyxy]
            cv2.rectangle(fr, (x1, y1), (x2, y2), TEAL, 2)
        th = int(TW * h / w)
        thumb = cv2.resize(fr, (TW, th))
        cv2.rectangle(thumb, (0, 0), (TW, 26), NAVY, -1)
        cv2.putText(thumb, f"{t:0.1f}s", (8, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.6, YELLOW, 2, cv2.LINE_AA)
        thumbs.append(thumb)
        t += STEP_S
    cap.release()
    if not thumbs:
        print("no thumbs"); return
    th = thumbs[0].shape[0]
    rows = math.ceil(len(thumbs) / COLS)
    pad = 6
    sheet = np.full((rows * (th + pad) + pad, COLS * (TW + pad) + pad, 3), 30, np.uint8)
    for i, tb in enumerate(thumbs):
        r, c = divmod(i, COLS)
        y = pad + r * (th + pad); x = pad + c * (TW + pad)
        sheet[y:y + th, x:x + TW] = tb
    cv2.imwrite(str(OUT), sheet)
    print(f"contact sheet -> {OUT}  ({len(thumbs)} frames, {dur-WINDOW_S:.0f}-{dur:.0f}s)")


if __name__ == "__main__":
    main()
