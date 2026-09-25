"""Analyse the ROBBERY / hold-up clips and generate annotated evidence.

Robbery is a NEW incident category. Everything reported here is MEASURED from
pixels (YOLO person counts, camera-view/scene-cut count, activity) — the word
"robbery" is the human-review conclusion, never a machine claim, and no dollar
value is invented. Clips are read from the local blind-test folder and are NEVER
moved/committed (in-store PII).

Run:  python reporting/gen_robbery_evidence.py         (all clips)
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from avip.cv.detect import YoloDetector

ROOT = Path(__file__).resolve().parents[1]
ANA = ROOT / "reports" / "incident_analysis"
SRC = ROOT / "New Videos for test"

TEAL = (176, 122, 46); YELLOW = (0, 215, 255); RED = (60, 60, 220)
GREEN = (60, 200, 90); NAVY = (74, 44, 10)

# slug -> (filename, time_of_day, [ (frame_name, fraction, title, callout_label) ])
# fractions/titles come from a human pass over the footage; the numbers on each
# card (people, camera views) are computed below, not typed in.
ROBBERY = {
    "robbery_0427": (
        "MESA04272026 ROBBERY.wmv", "27/04/2026 ~22:23 (night)",
        [("approach", 0.12, "Suspect approaches the forecourt", "APPROACH"),
         ("counter", 0.45, "At the counter - cashier's hands up", "OVER THE COUNTER"),
         ("flee", 0.78, "Leaving through the store", "FLEEING")],
    ),
    "robbery_0916": (
        "MESA09162026 ROBBERY.mp4", "16/09/2026 ~21:41 (night)",
        [("entry", 0.20, "Two hooded suspects enter", "ENTERING"),
         ("cooler", 0.45, "At the drinks cooler", "AT THE COOLER"),
         ("key", 0.70, "Concealing / handling goods", "KEY ACT")],
    ),
    "robbery_0626": (
        "Mesa Robbery 26-June.wmv", "26 June ~03:52 (overnight)",
        [("entry", 0.20, "Suspects move to the counter", "TO THE COUNTER"),
         ("behind", 0.45, "Behind the counter - grabbing stock", "BEHIND THE COUNTER"),
         ("key", 0.70, "Taking cigarettes / vapes", "TAKING STOCK")],
    ),
}


def banner(img, title):
    h, w = img.shape[:2]
    cv2.rectangle(img, (0, 0), (w, 40), NAVY, -1)
    cv2.putText(img, "SUGARLAND PETROLEUM", (10, 27), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, TEAL, 2, cv2.LINE_AA)
    cv2.putText(img, title, (330, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.56,
                (255, 255, 255), 1, cv2.LINE_AA)


def finding_strip(img, text):
    h, w = img.shape[:2]
    cv2.rectangle(img, (0, h - 34), (w, h), (30, 40, 25), -1)
    cv2.putText(img, "AI FINDING: " + text, (10, h - 11), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, GREEN, 1, cv2.LINE_AA)


def _persons(det, frame):
    """YOLO person boxes on a width-960 copy, scaled back."""
    h, w = frame.shape[:2]
    sc = w / 960.0
    small = cv2.resize(frame, (960, int(h / sc)))
    out = []
    for d in det(small):
        x1, y1, x2, y2 = d.xyxy
        out.append((x1 * sc, y1 * sc, x2 * sc, y2 * sc, d.confidence))
    return out


def _hist(frame):
    hsv = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
    cv2.normalize(h, h)
    return h


def analyse(slug: str, det: YoloDetector) -> dict | None:
    fname, tod, frames = ROBBERY[slug]
    vp = SRC / fname
    if not vp.exists():
        print("MISSING", vp); return None
    outdir = ANA / slug; outdir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(vp))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    if n <= 0 or w == 0:
        print("unreadable", vp); cap.release(); return None
    dur = n / fps

    # --- sampled pass: max people + camera-view (scene-cut) count ---
    SAMPLES = 70
    idxs = [int(i * (n - 1) / (SAMPLES - 1)) for i in range(SAMPLES)]
    max_people = 0
    cuts = 0
    prev_h = None
    for fi in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ok, fr = cap.read()
        if not ok:
            continue
        max_people = max(max_people, len(_persons(det, fr)))
        hh = _hist(fr)
        if prev_h is not None:
            corr = cv2.compareHist(prev_h, hh, cv2.HISTCMP_CORREL)
            if corr < 0.35:                    # large change = a different camera view
                cuts += 1
        prev_h = hh
    camera_views = cuts + 1

    # --- key annotated evidence frames ---
    saved = []
    for name, frac, title, label in frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * frac))
        ok, fr = cap.read()
        if not ok:
            continue
        ppl = _persons(det, fr)
        for (x1, y1, x2, y2, c) in ppl:
            cv2.rectangle(fr, (int(x1), int(y1)), (int(x2), int(y2)), TEAL, 2)
            cv2.putText(fr, "person", (int(x1), int(y1) - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, TEAL, 1, cv2.LINE_AA)
        # NOTE: no red per-person "accusation" box here — in a robbery frame the
        # cashier (victim) and suspect both appear and the nearest-person heuristic
        # can land on the victim. We box every person (teal) and describe the moment
        # in the banner + finding strip instead — honest, no wrong finger-pointing.
        # The scene label sits top-centre, attached to the scene, not a person:
        h0, w0 = fr.shape[:2]
        (tw, _th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        lx = max(10, (w0 - tw) // 2)
        cv2.putText(fr, label, (lx, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, YELLOW, 2, cv2.LINE_AA)
        banner(fr, title)
        finding_strip(fr, f"{len(ppl)} person(s) in view - {title}")
        outp = outdir / f"{name}_after.jpg"
        cv2.imwrite(str(outp), fr, [cv2.IMWRITE_JPEG_QUALITY, 82])
        saved.append(name)
    cap.release()

    signals = {
        "slug": slug, "group": "robbery", "file": fname,
        "site": "0008 Mesa Valero", "register": "Store / front counter",
        "camera": "multi", "duration_s": round(dur, 1),
        "max_people": max_people, "scene_cuts": camera_views,
        "time_of_day": tod, "frames": saved,
    }
    (outdir / "findings.json").write_text(json.dumps(signals, indent=2))
    print(f"{slug}: {max_people} max people, {camera_views} camera view(s), "
          f"{dur:.0f}s, frames={saved}")
    return signals


def main():
    det = YoloDetector(conf=0.28)              # a touch lower: night / hooded / distant
    out = []
    for slug in ROBBERY:
        try:
            s = analyse(slug, det)
            if s:
                out.append(s)
        except Exception as e:
            import traceback
            print("ERROR", slug, e); traceback.print_exc()
    (ANA / "robbery_signals.json").write_text(json.dumps(out, indent=2))
    print("DONE robbery analysis ->", ANA / "robbery_signals.json")


if __name__ == "__main__":
    raise SystemExit(main())
