"""Auto-calibration: read a *previously-unseen* CCTV clip and, from PIXELS ONLY,
decide (a) what kind of incident camera it is and (b) where the region-of-interest
sits — with NO hardcoded per-camera ROI and NO peek at the filename.

Why this module exists
----------------------
The blind-test clips were hand-tuned (a `cash_roi` / `cooler_roi` per camera in
analyze_incidents.CLIPS). That does not survive a *different store's* camera. The
director exam may drop a clip from an unseen angle, so the system must calibrate
itself. This module is that self-calibration step.

INTEGRITY (locked, see skill §1)
--------------------------------
* Every decision is derived only from pixels + on-frame OCR. The filename and any
  human "ground truth" are never read here.
* We NEVER silently guess. Each calibration carries a 0..1 `confidence`; below a
  threshold `needs_review` is set so the report can print
  "auto-calibrated — verify ROI" instead of asserting a zone we are unsure of.
* Geometry heuristics top out ~85-90% (skill §12). We say so; `notes` records the
  evidence for a human to check.

Output plugs straight into analyze_incidents: `group` ('register'|'floor'),
`subtype` ('cash'|'void'|'shoplift'), and normalized ROIs (cash_roi / cooler_roi /
pos_band) matching the CLIPS dict keys.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

import cv2
import numpy as np

try:                                    # OCR is optional at import time
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
except Exception:                       # pragma: no cover
    pytesseract = None

from avip.cv.detect import YoloDetector, Detection

# POS overlays print these tokens; a band that OCRs several of them is a receipt.
POS_TOKENS = ("TOTAL", "CANCEL", "VOID", "CASH", "CHANGE", "SUBTOTAL",
              "SUB TOTAL", "TAX", "BALANCE", "TEND", "REFUND", "SALE", "QTY")
CONF_REVIEW = 0.62                      # below this → needs_review flag


@dataclass
class Calibration:
    group: str                          # 'register' | 'floor'
    subtype: str                        # 'cash' | 'void' | 'shoplift'
    confidence: float                   # 0..1 overall
    has_overlay: bool = False
    cash_roi: tuple | None = None       # normalized (x1,y1,x2,y2)
    cooler_roi: tuple | None = None
    pos_band: tuple | None = None
    zone_label: str = "target zone"
    frame_w: int = 0
    frame_h: int = 0
    fps: float = 0.0
    duration_s: float = 0.0
    people_avg: float = 0.0
    people_max: int = 0
    pos_score: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return self.confidence < CONF_REVIEW

    def to_dict(self) -> dict:
        d = asdict(self)
        d["needs_review"] = self.needs_review
        return d

    def as_clip(self, slug: str, file: str) -> dict:
        """Shape this calibration as an analyze_incidents.CLIPS entry."""
        clip = dict(slug=slug, file=file, group=self.group,
                    site="Auto-calibrated (unseen camera)",
                    register="Register" if self.group == "register" else "Sales floor",
                    camera="auto", has_overlay=self.has_overlay,
                    date="", start_clock="",       # unknown on an unseen camera — never faked
                    auto_calibrated=True, calib_confidence=round(self.confidence, 2),
                    calib_needs_review=self.needs_review, calib_notes=list(self.notes),
                    reported="(blind — no manual label supplied)")
        if self.group == "register":
            clip["cash_roi"] = self.cash_roi or (0.35, 0.30, 0.72, 0.82)
            if self.has_overlay and self.pos_band:
                clip["pos_band"] = self.pos_band
        else:
            clip["cooler_roi"] = self.cooler_roi or (0.50, 0.00, 1.00, 0.97)
            clip["zone_label"] = self.zone_label
            clip["date_fmt"] = "%d/%m/%Y"
        return clip


# ---------------------------------------------------------------------------
# Frame sampling
# ---------------------------------------------------------------------------
def _sample_indices(n_frames: int, k: int) -> list[int]:
    if n_frames <= 0:
        return []
    k = min(k, n_frames)
    return [int(round(i * (n_frames - 1) / max(1, k - 1))) for i in range(k)]


def _grab(cap, idx):
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, frame = cap.read()
    return frame if ok else None


# ---------------------------------------------------------------------------
# POS-overlay (receipt) detection  → the ONLY machine-verifiable-$ incident
# ---------------------------------------------------------------------------
def _ocr_tokens(img) -> int:
    """Count distinct POS tokens visible in a crop (robust to light-on-light)."""
    if pytesseract is None or img is None or img.size == 0:
        return 0
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    if g.shape[1] < 400:
        g = cv2.resize(g, (g.shape[1] * 2, g.shape[0] * 2), interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(g)
    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    hits = set()
    for variant in (clahe, otsu, cv2.bitwise_not(otsu)):
        try:
            txt = pytesseract.image_to_string(variant, config="--psm 6").upper()
        except Exception:
            continue
        for tok in POS_TOKENS:
            if tok in txt:
                hits.add(tok.replace(" ", ""))
    return len(hits)


def _detect_pos_band(frames) -> tuple[tuple | None, float]:
    """Scan candidate vertical bands for a receipt overlay.

    Returns (normalized_band, score 0..1). Receipts sit in a side band; we test
    left / right / bottom strips and keep the strongest.
    """
    if not frames:
        return None, 0.0
    h, w = frames[0].shape[:2]
    candidates = {
        "right": (0.50, 0.00, 1.00, 1.00),
        "right_narrow": (0.66, 0.00, 1.00, 1.00),
        "left": (0.00, 0.00, 0.42, 1.00),
        "bottom": (0.00, 0.55, 1.00, 1.00),
        "top": (0.25, 0.00, 0.90, 0.48),        # some registers burn the receipt at the TOP
        "top_wide": (0.00, 0.00, 1.00, 0.42),
    }
    best_band, best_tok = None, 0
    for band in candidates.values():
        x1, y1, x2, y2 = band
        px = (int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h))
        tok_total = 0
        for fr in frames[:: max(1, len(frames) // 4)]:      # ~4 probes per band
            crop = fr[px[1]:px[3], px[0]:px[2]]
            tok_total += _ocr_tokens(crop)
        if tok_total > best_tok:
            best_tok, best_band = tok_total, band
    # score: >=2 distinct POS tokens (summed over probes) is a confident overlay
    score = min(1.0, best_tok / 6.0)
    return (best_band if best_tok >= 2 else None), score


# ---------------------------------------------------------------------------
# Motion hotspot  → register cash-drawer ROI proxy
# ---------------------------------------------------------------------------
def _motion_roi(frames, grid=(6, 6)) -> tuple | None:
    """Normalized bbox of the strongest frame-to-frame motion cluster.

    The cash drawer opening / cash handling is the dominant repeated motion at a
    register with no customer traffic. PROXY — reported as such.
    """
    if len(frames) < 2:
        return None
    h, w = frames[0].shape[:2]
    gh, gw = grid
    acc = np.zeros((gh, gw), np.float64)
    prev = cv2.cvtColor(cv2.resize(frames[0], (gw * 32, gh * 32)), cv2.COLOR_BGR2GRAY)
    for fr in frames[1:]:
        cur = cv2.cvtColor(cv2.resize(fr, (gw * 32, gh * 32)), cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(cur, prev)
        for r in range(gh):
            for c in range(gw):
                acc[r, c] += float(diff[r * 32:(r + 1) * 32, c * 32:(c + 1) * 32].mean())
        prev = cur
    if acc.max() <= 0:
        return None
    # take cells above 60% of peak, bound them
    thr = acc.max() * 0.6
    rs, cs = np.where(acc >= thr)
    x1 = float(cs.min()) / gw; x2 = float(cs.max() + 1) / gw
    y1 = float(rs.min()) / gh; y2 = float(rs.max() + 1) / gh
    # keep it a plausible counter region (not the whole frame)
    if (x2 - x1) > 0.9 and (y2 - y1) > 0.9:
        return None
    return (round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2))


# ---------------------------------------------------------------------------
# Person dwell heatmap  → floor target (cooler) ROI proxy
# ---------------------------------------------------------------------------
def _dwell_roi(samples_people, w, h) -> tuple | None:
    """Bounding region of where people's feet cluster most (dwell zone).

    On a sales-floor camera the group huddles at the target shelf/cooler; the
    densest dwell zone is our monitored region. PROXY.
    """
    pts = []
    for people in samples_people:
        for d in people:
            bx, by = d.bottom_center
            pts.append((bx / w, by / h))
    if len(pts) < 3:
        return None
    pts = np.array(pts)
    # DENSITY PEAK: the shoplifting group forms the tightest cluster (a huddle),
    # while stray detections (a passer-by, the entrance) are sparse. Find the
    # densest point and bound its neighbours, so the ROI lands on the GROUP — not
    # the mid-point of everyone in the scene.
    r = 0.18
    best_i, best_n = 0, -1
    for i, p in enumerate(pts):
        n = int(np.sum(np.hypot(pts[:, 0] - p[0], pts[:, 1] - p[1]) <= r))
        if n > best_n:
            best_n, best_i = n, i
    peak = pts[best_i]
    near = pts[np.hypot(pts[:, 0] - peak[0], pts[:, 1] - peak[1]) <= r]
    x1, x2 = float(near[:, 0].min()), float(near[:, 0].max())
    y1, y2 = float(near[:, 1].min()), float(near[:, 1].max())
    x1 = max(0.0, x1 - 0.06); x2 = min(1.0, x2 + 0.06)
    y1 = max(0.0, y1 - 0.06); y2 = min(1.0, y2 + 0.06)
    if (x2 - x1) < 0.08 or (y2 - y1) < 0.08:
        return None
    return (round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2))


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def calibrate(video_path, detector: YoloDetector | None = None,
              k_frames: int = 14) -> Calibration:
    """Calibrate an unseen clip from pixels only. Never reads the filename."""
    path = Path(video_path)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(f"cannot open video: {path}")
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 15.0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    dur = n / fps if fps else 0.0

    frames, people_per = [], []
    det = detector or YoloDetector(conf=0.30)
    for idx in _sample_indices(n, k_frames):
        fr = _grab(cap, idx)
        if fr is None:
            continue
        frames.append(fr)
        small = cv2.resize(fr, (960, int(960 * h / w))) if w else fr
        sc = w / 960.0 if w else 1.0
        dets = [Detection(tuple(v * sc for v in d.xyxy), d.confidence) for d in det(small)]
        people_per.append(dets)
    cap.release()

    if not frames:
        raise RuntimeError(f"no frames read from {path}")

    people_counts = [len(p) for p in people_per]
    p_avg = float(np.mean(people_counts)) if people_counts else 0.0
    p_max = int(max(people_counts)) if people_counts else 0

    pos_band, pos_score = _detect_pos_band(frames)
    has_overlay = pos_band is not None
    notes: list[str] = []

    # ---- classify ---------------------------------------------------------
    # Signals:
    #   low-res wide + several people spread across frame  → floor shoplift
    #   POS overlay present                                → register + void
    #   otherwise counter/register with cash handling      → register cash
    low_res = (w and w <= 900) or (h and h <= 480)
    wide = (w / h) >= 1.9 if h else False
    floor_like = (low_res and p_max >= 2) or (wide and p_max >= 3)

    if has_overlay and pos_score >= 0.34:
        group, subtype = "register", "void"
        conf = 0.55 + 0.40 * pos_score            # OCR overlay is strong evidence
        notes.append(f"POS overlay OCR'd ({int(pos_score*6)} token-hits) → collusion-void camera")
    elif floor_like:
        group, subtype = "floor", "shoplift"
        # confidence grows with how clearly it's a wide, multi-person floor scene
        conf = 0.5 + 0.12 * min(p_max, 4) + (0.1 if low_res else 0) + (0.08 if wide else 0)
        notes.append(f"low-res/wide multi-person scene (max {p_max} people) → sales-floor camera")
    else:
        group, subtype = "register", "cash"
        conf = 0.5 + (0.15 if p_max >= 1 else -0.1) + (0.1 if not wide else 0)
        notes.append(f"hi-res single-counter scene (max {p_max} people, no POS overlay) → register cash camera")
    conf = float(max(0.0, min(1.0, conf)))

    # ---- propose ROI ------------------------------------------------------
    cash_roi = cooler_roi = None
    zone_label = "target zone"
    if group == "register":
        cash_roi = _motion_roi(frames)
        if cash_roi:
            notes.append(f"cash ROI from motion hotspot {cash_roi} (proxy)")
        else:
            cash_roi = (0.35, 0.30, 0.72, 0.82)
            conf = min(conf, 0.6)
            notes.append("cash ROI fallback to default counter region (low motion) — verify")
    else:
        cooler_roi = _dwell_roi(people_per, w, h)
        if cooler_roi:
            zone_label = "target shelf / cooler"
            notes.append(f"target ROI from people-dwell cluster {cooler_roi} (proxy)")
        else:
            cooler_roi = (0.50, 0.00, 1.00, 0.97)
            conf = min(conf, 0.6)
            notes.append("target ROI fallback to right-half default (sparse detections) — verify")

    cal = Calibration(
        group=group, subtype=subtype, confidence=round(conf, 3),
        has_overlay=has_overlay, cash_roi=cash_roi, cooler_roi=cooler_roi,
        pos_band=pos_band, zone_label=zone_label,
        frame_w=w, frame_h=h, fps=round(fps, 2), duration_s=round(dur, 1),
        people_avg=round(p_avg, 2), people_max=p_max, pos_score=round(pos_score, 3),
        notes=notes,
    )
    if cal.needs_review:
        cal.notes.append(f"CONFIDENCE {cal.confidence:.2f} < {CONF_REVIEW:.2f} → flagged for human ROI check")
    return cal


def _cli():
    if len(sys.argv) < 2:
        print("usage: python -m avip.analytics.auto_calibrate <video> [<video> ...]")
        return
    for vp in sys.argv[1:]:
        cal = calibrate(vp)
        print(f"\n=== {Path(vp).name} ===")
        print(json.dumps(cal.to_dict(), indent=2))


if __name__ == "__main__":
    _cli()
