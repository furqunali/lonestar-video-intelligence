"""Scan MESA clips' TOP band for a burned-in POS receipt showing CANCELLED sales.
Reports, per clip: how many sampled frames show CANCEL, the amounts seen (with
counts), and cashier-name candidates. No fabrication — only what OCR reads.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

import cv2
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

EVID = Path(r"G:\Shared drives\4. AP\lonestar-video-intelligence\02_Evidence\Incident_Clips")

CLIPS = [
    ("auto_mesa_3_bf8e", "MESA 3.wmv"),
    ("auto_mesa_7_1_6c35", "MESA 7 (1).wmv"),
    ("auto_mesa_1_1742", "MESA 1.wmv"),
    ("auto_mesa_2_8ca6", "MESA 2.wmv"),
    ("auto_mesa_4_18cf", "Mesa 4.mp4"),
]
KEYWORDS = {"CANCELLED", "CANCEL", "SALES", "SALE", "TOTAL", "TAX", "DEBIT", "EMV",
            "NET", "CASH", "CHANGE", "CREDIT", "BALANCE", "TEND", "REFUND", "SUBTOTAL",
            "JUICE", "COCONUT", "FOCO", "MAGNUM", "WARNING", "STORE", "THANK", "YOU"}


def ocr_top(frame):
    h, w = frame.shape[:2]
    crop = frame[0:int(0.48 * h), int(0.18 * w):int(0.96 * w)]
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, (g.shape[1] * 2, g.shape[0] * 2), interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(g)
    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    out = []
    for v in (clahe, otsu, cv2.bitwise_not(otsu)):
        try:
            out.append(pytesseract.image_to_string(v, config="--psm 6").upper())
        except Exception:
            pass
    return "\n".join(out)


def scan(slug, file):
    vp = EVID / file
    if not vp.exists():
        print(f"{slug}: MISSING {vp}"); return
    cap = cv2.VideoCapture(str(vp))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    idxs = [int(i * (n - 1) / 39) for i in range(40)] if n > 40 else list(range(n))
    cancel_frames, first_s = 0, None
    amounts, names = {}, {}
    for ix in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, ix); ok, fr = cap.read()
        if not ok:
            continue
        txt = ocr_top(fr)
        if "CANCEL" in txt:
            cancel_frames += 1
            if first_s is None:
                first_s = round(ix / fps, 1)
            for line in txt.splitlines():
                if "CANCEL" in line or "TOTAL" in line:
                    for a in re.findall(r'\d{1,3}\.\d{2}', line):
                        amounts[a] = amounts.get(a, 0) + 1
        for line in txt.splitlines():
            words = [x for x in re.findall(r'\b[A-Z]{3,}\b', line) if x not in KEYWORDS]
            if len(words) >= 2:
                nm = ' '.join(words[:2])
                names[nm] = names.get(nm, 0) + 1
    cap.release()
    top_amt = sorted(amounts.items(), key=lambda kv: -kv[1])[:5]
    top_nm = sorted(names.items(), key=lambda kv: -kv[1])[:5]
    verdict = "VOID (cancel on POS)" if cancel_frames >= 3 else ("maybe" if cancel_frames else "no cancel overlay")
    print(f"\n=== {slug} ({file}) ===")
    print(f"  cancel frames: {cancel_frames}/40  first@ {first_s}s  -> {verdict}")
    print(f"  amounts: {top_amt}")
    print(f"  cashier candidates: {top_nm}")


def main():
    only = sys.argv[1:] or [c[0] for c in CLIPS]
    for slug, file in CLIPS:
        if slug in only or file in only:
            scan(slug, file)


if __name__ == "__main__":
    main()
