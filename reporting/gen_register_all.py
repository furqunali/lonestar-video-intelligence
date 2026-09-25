"""Generalized register evidence — one automatic step for EVERY register incident.

For each cash-register clip it produces ~3 auto-selected annotated frames:
  1. cash-drawer MOTION frames (counter -> key act -> just after) as a reliable base
     (works on any clip), then
  2. a POSE upgrade: if YOLOv8-pose finds a clear hand->pocket / cash-in-hand gesture,
     the key frames are replaced with the sharper pose evidence. If the gesture signal
     is weak, the motion frames are kept (honest — no over-claiming).

This is the "automatic, no manual pointing" behaviour Furqan wanted, applied to
every register clip (not just MESA 3). Run: python reporting/gen_register_all.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))                 # so `avip` imports
sys.path.insert(0, str(ROOT / "reporting"))   # so sibling gen_* modules import

from avip.cv.detect import YoloDetector       # noqa: E402
import gen_register_evidence as motion        # noqa: E402
import gen_mesa3_pose as pose                 # noqa: E402

# Cash-register incidents: slug -> (clip filename in local 02_Evidence, ROI override).
# ROI override is only needed for the two hand-curated blind-test clips (no
# calibration.json); the auto MESA clips carry their own calibration.json ROI.
CASH_CLIPS = [
    ("5nov_cash",         "Cash theft By cashier 5 Nov.wmv",  (0.44, 0.33, 0.70, 0.80)),
    ("12nov_cash",        "Cash theft By Cashier 12 Nov.wmv", (0.40, 0.30, 0.75, 0.82)),
    ("auto_mesa_1_1742",  "MESA 1.wmv",                       None),
    ("auto_mesa_2_8ca6",  "MESA 2.wmv",                       None),
    ("auto_mesa_4_18cf",  "Mesa 4.mp4",                       None),
    ("auto_mesa_7_1_6c35", "MESA 7 (1).wmv",                  None),
]


def main():
    det = YoloDetector(conf=0.30)
    for slug, fname, roi in CASH_CLIPS:
        print(f"\n=== {slug}  ({fname}) ===")
        made = motion.gen_for(slug, fname, det, roi=roi)      # reliable 3-frame base
        if made:
            try:
                upgraded = pose.run(slug, fname, window_s=999)  # search whole clip
                print("  pose upgrade:" , "applied" if upgraded else "not needed (kept motion frames)")
            except Exception as e:
                print("  pose step skipped:", e)


if __name__ == "__main__":
    main()
