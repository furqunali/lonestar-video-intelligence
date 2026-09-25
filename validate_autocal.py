"""Blind-validate auto-calibration against the 5 hand-tuned clips.

Proof-of-capability for the director exam: run auto_calibrate on each clip WITHOUT
telling it the type or the ROI, then score it against the hand-tuned ground truth
(analyze_incidents.CLIPS). If it recovers type + ROI on clips it never saw
configured, it will handle a different store's unseen camera too.

Run:  python validate_autocal.py
"""
from __future__ import annotations
import json
from pathlib import Path

from analyze_incidents import CLIPS, SRC
from avip.analytics.auto_calibrate import calibrate
from avip.cv.detect import YoloDetector

OUT = Path("reports") / "auto_calibration_validation.json"


def truth_subtype(clip: dict) -> str:
    if clip["group"] == "floor":
        return "shoplift"
    return "void" if clip.get("has_overlay") else "cash"


def _inter(a, b) -> float:
    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
    iw = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0.0, min(ay2, by2) - max(ay1, by1))
    return iw * ih


def iou(a, b) -> float:
    if not a or not b:
        return 0.0
    inter = _inter(a, b)
    ua = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def containment(pred, truth) -> float:
    """Fraction of the PREDICTED ROI that lies inside the TRUE zone.

    Fairer than IoU when the auto proposal is a tight, precise sub-region of a
    broad hand-tuned box: a focused proposal fully inside the true zone scores 1.0.
    """
    if not pred or not truth:
        return 0.0
    pa = (pred[2]-pred[0])*(pred[3]-pred[1])
    return _inter(pred, truth) / pa if pa > 0 else 0.0


def center_in(pred, truth) -> bool:
    if not pred or not truth:
        return False
    cx, cy = (pred[0]+pred[2])/2, (pred[1]+pred[3])/2
    return truth[0] <= cx <= truth[2] and truth[1] <= cy <= truth[3]


def main():
    det = YoloDetector(conf=0.30)          # one shared model
    rows, ok_type, ok_roi = [], 0, 0
    for clip in CLIPS:
        vp = SRC / clip["file"]
        t_group, t_sub = clip["group"], truth_subtype(clip)
        cal = calibrate(vp, detector=det)
        gt_roi = clip.get("cash_roi") if t_group == "register" else clip.get("cooler_roi")
        pr_roi = cal.cash_roi if cal.group == "register" else cal.cooler_roi
        roi_iou = round(iou(gt_roi, pr_roi), 3)
        cont = round(containment(pr_roi, gt_roi), 3)
        cin = center_in(pr_roi, gt_roi)
        type_ok = bool(cal.group == t_group and cal.subtype == t_sub)
        # ROI "lands right" = its centre is inside the true zone AND most of it is
        # contained in the true zone (a precise proposal inside a broad box passes).
        roi_ok = bool(cin and cont >= 0.5)
        ok_type += int(type_ok); ok_roi += int(roi_ok)
        rows.append(dict(
            clip=clip["file"], truth=f"{t_group}/{t_sub}",
            predicted=f"{cal.group}/{cal.subtype}", type_ok=type_ok,
            confidence=cal.confidence, needs_review=bool(cal.needs_review),
            has_overlay=f"{cal.has_overlay} (truth {bool(clip.get('has_overlay'))})",
            roi_iou=roi_iou, roi_containment=cont, roi_center_in_zone=bool(cin),
            roi_ok=roi_ok, people_max=cal.people_max, pos_score=cal.pos_score,
            notes=cal.notes,
        ))
        flag = "OK " if (type_ok and roi_ok) else ("T? " if not type_ok else "R? ")
        print(f"{flag}{clip['file'][:34]:34s} truth={t_group}/{t_sub:8s} "
              f"pred={cal.group}/{cal.subtype:8s} conf={cal.confidence:.2f} "
              f"center_in={'Y' if cin else 'n'} contain={cont:.2f} iou={roi_iou:.2f}")

    n = len(CLIPS)
    print(f"\nTYPE accuracy: {ok_type}/{n}   ROI lands-in-zone: {ok_roi}/{n}")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(dict(
        type_accuracy=f"{ok_type}/{n}", roi_lands_in_zone=f"{ok_roi}/{n}", rows=rows,
    ), indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    print("scorecard ->", OUT)


if __name__ == "__main__":
    main()
