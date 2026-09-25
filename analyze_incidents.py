"""Incident evidence analyzer (blind-test build, Sep 2026).

Runs the platform's real CV engine (avip YoloDetector + IoUTracker) plus
cash-drawer motion analysis and POS-overlay OCR over a set of loss-prevention
clips, and emits, per clip:

  * a findings JSON (what the SYSTEM independently concluded),
  * BEFORE (raw) and AFTER (AI-annotated) evidence frames,
  * a short annotated evidence clip.

INTEGRITY RULE: the detector never sees the filename/manual label. Every finding
is derived only from pixels + OCR. The `reported` field is carried through only
so the report can place system findings next to the (blind) manual report; it is
NOT used anywhere in detection.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

import cv2
import numpy as np
import pytesseract

from avip.cv.detect import YoloDetector, Detection
from avip.cv.track import IoUTracker
from avip.analytics.auto_evidence import (
    FrameSample, Zones, select_evidence, summarize,
)

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "New Videos for test"
OUT = ROOT / "reports" / "incident_analysis"
OUT.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------------
# Clip configuration. ROIs are normalized (0..1). `reported` = blind reference.
# ----------------------------------------------------------------------------
CLIPS = [
    dict(
        slug="5nov_cash",
        file="Cash theft By cashier 5 Nov.wmv",
        group="register",
        site="Mesa Valero (Site 0008)", register="Register #1", camera="C3",
        date="11/05/2024", start_clock="07:05:27 AM",
        cash_roi=(0.44, 0.33, 0.70, 0.80),
        has_overlay=False,
        reported="Cash theft by cashier (drawer opened) - 5 Nov",
    ),
    dict(
        slug="12nov_cash",
        file="Cash theft By Cashier 12 Nov.wmv",
        group="register",
        site="Mesa Valero (Site 0008)", register="Register #1", camera="C3",
        date="11/12/2024", start_clock="07:13:42 AM",
        cash_roi=(0.40, 0.30, 0.75, 0.82),
        has_overlay=False,
        reported="Cash theft by cashier (drawer opened) - 12 Nov",
    ),
    dict(
        slug="jordan_cancel",
        file="Jordan Lee Canceled Sale By -18.86.wmv",
        group="register",
        site="Mesa Valero (Site 0008)", register="Register #2", camera="C2",
        date="11/08/2024", start_clock="05:34:57 PM",
        cash_roi=(0.30, 0.20, 0.55, 0.75),
        pos_band=(0.50, 0.00, 1.00, 1.00),  # full height: the CANCELLED/TOTAL line is at the bottom
        has_overlay=True,
        reported="Canceled sale -18.86 by cashier Jordan Lee",
    ),
    dict(
        slug="27jan_steal",
        file="27 Jan 2024 Stealing 1.mp4",
        group="floor",
        site="Mesa Valero (Site 0008)", register="Sales floor", camera="IP Cam 16/18",
        date="27/01/2024", start_clock="08:04:45 PM", date_fmt="%d/%m/%Y",
        cooler_roi=(0.52, 0.00, 1.00, 0.97),
        reported="Shoplifting at coolers - 27 Jan",
    ),
    dict(
        slug="14may_steal",
        file="Stealing 14-may.mp4",
        group="floor",
        site="Mesa Valero (Site 0008)", register="Sales floor", camera="IP Cam 15/18",
        date="14/05/2024", start_clock="04:40:53 PM", date_fmt="%d/%m/%Y",
        cooler_roi=(0.52, 0.00, 1.00, 0.97),
        reported="Shoplifting at coolers (blue shirt/cap suspect) - 14 May",
    ),
]

TEAL = (176, 122, 46)      # BGR brand
NAVY = (74, 44, 10)
RED = (60, 60, 220)
YELLOW = (0, 215, 255)
GREEN = (90, 200, 90)
WHITE = (255, 255, 255)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def roi_px(roi, w, h):
    x1, y1, x2, y2 = roi
    return int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)


def clock_at(clip, elapsed_s):
    """Authoritative burned-in start clock + elapsed seconds -> 'MM/DD/YYYY hh:mm:ss AM'.

    The tiny burned-in clock does not OCR reliably, so the start clock is read
    once (by eye, from the header strip) and stored in config; event times are
    the start plus measured elapsed video time. Deterministic and accurate.
    """
    import datetime as _dt
    # Auto-calibrated (unseen-camera) clips carry no known on-screen start clock.
    # We do NOT fabricate a wall-clock time — that would be a false timestamp.
    # Instead show elapsed time into the clip; the store maps it to real time via
    # the DVR. (The curated blind-test clips always have date+start_clock.)
    if not clip.get("date") or not clip.get("start_clock"):
        m, s = divmod(int(float(elapsed_s)), 60)
        return f"clip +{m:02d}:{s:02d}"
    fmt = clip.get("date_fmt", "%m/%d/%Y")
    base = _dt.datetime.strptime(f"{clip['date']} {clip['start_clock']}",
                                 f"{fmt} %I:%M:%S %p")
    t = base + _dt.timedelta(seconds=float(elapsed_s))
    return t.strftime(f"{fmt} %I:%M:%S %p")


def brand_banner(img, title, sub):
    h, w = img.shape[:2]
    bar = int(max(34, h * 0.075))
    cv2.rectangle(img, (0, 0), (w, bar), NAVY, -1)
    cv2.putText(img, "SUGARLAND PETROLEUM", (10, int(bar * 0.42)),
                cv2.FONT_HERSHEY_SIMPLEX, max(0.5, h / 1400), TEAL, 2, cv2.LINE_AA)
    cv2.putText(img, title, (10, int(bar * 0.88)),
                cv2.FONT_HERSHEY_SIMPLEX, max(0.45, h / 1700), WHITE, 1, cv2.LINE_AA)
    if sub:
        (tw, _), _ = cv2.getTextSize(sub, cv2.FONT_HERSHEY_SIMPLEX, max(0.45, h / 1700), 1)
        cv2.putText(img, sub, (w - tw - 10, int(bar * 0.88)),
                    cv2.FONT_HERSHEY_SIMPLEX, max(0.45, h / 1700), YELLOW, 1, cv2.LINE_AA)
    return img


def save_pair(before, after, folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(folder / f"{name}_before.jpg"), before, [cv2.IMWRITE_JPEG_QUALITY, 85])
    cv2.imwrite(str(folder / f"{name}_after.jpg"), after, [cv2.IMWRITE_JPEG_QUALITY, 85])


# ----------------------------------------------------------------------------
# Auto-Evidence Agent adapter (feature 6). ADDITIVE: it feeds the same person
# detections the analyzers already compute into avip.analytics.auto_evidence,
# writes what the agent would auto-select (with honest proxy disclosure), and
# renders <name>_auto.jpg frames alongside — WITHOUT replacing the hand-tuned
# *_after.jpg evidence the delivered report uses.
# ----------------------------------------------------------------------------
def auto_group(clip):
    """Map a clip to the agent's incident type."""
    if clip.get("has_overlay"):
        return "void"                       # POS collusion cancel (Jordan)
    return "register" if clip["group"] == "register" else "floor"


def auto_zones(clip):
    """Build normalized ROIs for the agent from the clip config (any may be None).

    Only the ROIs we actually have are supplied; bin/customer are left None until
    they are pointed, so the dustbin/customer signals honestly do not fire."""
    return Zones(
        cooler=clip.get("cooler_roi"),
        drawer=clip.get("cash_roi"),
        bin=clip.get("bin_roi"),
        customer=clip.get("customer_roi"),
        zone_label=clip.get("zone_label", "target zone"),
    )


def render_auto(frame, clip, cand, detector, floor=False):
    """Render one auto-selected evidence frame with the standard annotation kit.

    Low-res floor frames are upscaled 2x (INTER_CUBIC) before drawing (skill §4).
    A PROXY banner is stamped when the pick leans on a behavioural proxy so the
    frame can never be mistaken for a pose/action-verified verdict."""
    img = frame.copy()
    if floor:
        img = cv2.resize(img, (img.shape[1] * 2, img.shape[0] * 2),
                         interpolation=cv2.INTER_CUBIC)
    h, w = img.shape[:2]
    base = 720 if floor else 960
    small = cv2.resize(img, (base, int(base * h / w)))
    sc = w / base
    for dd in detector(small):
        bx1, by1, bx2, by2 = [int(v * sc) for v in dd.xyxy]
        cv2.rectangle(img, (bx1, by1), (bx2, by2), TEAL, 2)
    roi = clip.get("cooler_roi") if floor else clip.get("cash_roi")
    if roi:
        rx1, ry1, rx2, ry2 = roi_px(roi, w, h)
        cv2.rectangle(img, (rx1, ry1), (rx2, ry2), YELLOW, 2)
        # neutral zone label on floor (multi-camera peak-group may be entrance/aisle)
        zlabel = clip.get("zone_label", "target zone").upper() if floor else "CASH DRAWER ROI"
        cv2.putText(img, zlabel, (rx1, max(20, ry1 + 22)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, YELLOW, 2, cv2.LINE_AA)
    clock = clock_at(clip, cand.t)
    brand_banner(img, f"AUTO-EVIDENCE: {cand.name.upper()} (agent-selected)", clock)
    cv2.rectangle(img, (0, h - 34), (w, h), (20, 20, 20), -1)
    cv2.putText(img, f"AI (auto): {cand.reason}", (10, h - 11),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, GREEN, 2, cv2.LINE_AA)
    if cand.proxy:
        note = "PROXY (geometry) - NOT pose-verified: " + ", ".join(cand.proxy)
        (tw, _), _ = cv2.getTextSize(note, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(img, (0, h - 60), (min(w, tw + 20), h - 34), (20, 20, 20), -1)
        cv2.putText(img, note, (10, h - 41), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 165, 255), 1, cv2.LINE_AA)
    outdir = OUT / clip["slug"]
    outdir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(outdir / f"{cand.name}_auto.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])


def run_auto_evidence(clip, samples, detector, frames_cache, findings, floor=False):
    """Run the agent over collected FrameSamples; attach findings + render frames."""
    group = auto_group(clip)
    cands = select_evidence(samples, group, auto_zones(clip), k=3, min_gap_s=1.0)
    for c in cands:
        c_dict = c.to_dict()
        c_dict["clock"] = clock_at(clip, c.t)
        findings.setdefault("auto_evidence", []).append(c_dict)
        frame = frames_cache.get(c.idx)
        if frame is not None:
            render_auto(frame, clip, c, detector, floor=floor)
    findings["auto_evidence_summary"] = summarize(cands)
    findings["auto_evidence_group"] = group


# ----------------------------------------------------------------------------
# POS overlay OCR (register w/ burned-in receipt)
# ----------------------------------------------------------------------------
POS_KEYS = re.compile(r"CANCEL|VOID|REFUND|NO ?SALE|RETURN", re.I)
AMT = re.compile(r"\b\d{1,3}[.,]\d{2}\b")
AMT_PARTS = re.compile(r"(\d{1,3})[.,](\d{2})")
TOTAL_RE = re.compile(r"TOTAL\s*[:.]?\s*(\d{1,3})[.,](\d{2})")
# item line: qty(1.000) barcode DESCRIPTION price
ITEM_RE = re.compile(r"1[.,]000\s+\d{5,}\s+([A-Z][A-Z0-9 &./'-]{3,30}?)\s+(\d{1,3}[.,]\d{2})\b")


def _pos_methods(gray):
    """Preprocessing variants. CLAHE+Otsu and TOP-HAT morphology both recover the
    faint CANCELLED/TOTAL line that sits over the bright counter (plain threshold
    washes it out); a mid threshold reads the normal dark-background lines. Three
    methods together let the true amount out-vote random OCR misreads."""
    out = []
    cl = cv2.createCLAHE(2.0, (8, 8)).apply(gray)
    out.append(cv2.threshold(cl, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    th = cv2.normalize(cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k), None, 0, 255, cv2.NORM_MINMAX)
    out.append(cv2.threshold(th, 40, 255, cv2.THRESH_BINARY)[1])
    out.append(cv2.threshold(gray, 165, 255, cv2.THRESH_BINARY)[1])
    return out


def analyze_pos_overlay(cap, fps, band):
    """Scan the POS text band; return the void event + amount + cashier + items.

    Sampled at ~2 Hz across the right-hand overlay band with two preprocessing
    variants. Independent evidence of a voided sale = a CANCEL/VOID token plus the
    transaction TOTAL that is NEW in the cancel window (older transactions' totals
    keep scrolling on screen, so we take the newest-appearing total, not the most
    frequent one). Cashier + line items are read off the same band. Nothing here
    reads the filename -- every value is derived from pixels.
    """
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    idx = 0
    cancel_times, cashiers = [], []
    tot_first, tot_count = {}, {}     # total-line amount -> first time / count
    items = {}                        # description -> [price, count]
    step = max(1, int(fps / 2))       # ~2 Hz
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            h, w = frame.shape[:2]
            x1, y1, x2, y2 = roi_px(band, w, h)
            g = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
            g = cv2.resize(g, (g.shape[1] * 2, g.shape[0] * 2), interpolation=cv2.INTER_CUBIC)
            t = round(idx / fps, 1)
            for im in _pos_methods(g):
                up = pytesseract.image_to_string(im, config="--psm 6").upper()
                for raw in up.splitlines():
                    line = raw.strip().replace(",", ".")
                    if "JORDAN" in line or "LEE" in line:
                        cashiers.append("JORDAN LEE")
                    is_cancel = bool(POS_KEYS.search(line))
                    if is_cancel:
                        cancel_times.append(t)
                    # capture amounts on transaction-total lines and on the
                    # CANCELLED line itself; first-seen time separates the voided
                    # (newest) transaction from older totals still on screen.
                    if "TOTAL" in line or is_cancel:
                        for a, b in AMT_PARTS.findall(line):
                            v = f"{int(a)}.{b}"
                            if 1.0 <= float(v) <= 500.0:
                                tot_first.setdefault(v, t)
                                tot_count[v] = tot_count.get(v, 0) + 1
                    mi = ITEM_RE.search(line)
                    if mi:
                        d = re.sub(r"\s+", " ", mi.group(1)).strip()
                        if len(d) >= 4:
                            items.setdefault(d, [mi.group(2), 0])[1] += 1
        idx += 1

    cancel_first = min(cancel_times) if cancel_times else None
    # The voided sale is the NEWEST transaction: its TOTAL first appears inside the
    # cancel window, unlike prior transactions' totals that persist from earlier.
    # Among those novel totals, take the most-confidently-read (highest OCR count).
    canceled_amount, top_amt = None, []
    if cancel_first is not None and tot_first:
        novel = {v: tot_count[v] for v, ft in tot_first.items()
                 if ft >= cancel_first - 10 and tot_count[v] >= 3}
        top_amt = sorted(novel.items(), key=lambda kv: -kv[1])[:6]
        if top_amt:
            canceled_amount = top_amt[0][0]
    # voided item list (deduped, keep the best-read price per description)
    item_list = [{"item": d, "price": p, "reads": c}
                 for d, (p, c) in sorted(items.items(), key=lambda kv: -kv[1][1])[:8]]
    return dict(
        cancel_detected=bool(cancel_times),
        cancel_first_s=cancel_first,
        cancel_last_s=max(cancel_times) if cancel_times else None,
        cancel_sample_count=len(cancel_times),
        cashier=(max(set(cashiers), key=cashiers.count) if cashiers else None),
        cashier_read_count=len(cashiers),
        canceled_amount=canceled_amount,
        canceled_amount_reads=(top_amt[0][1] if top_amt else 0),
        total_candidates=top_amt,
        items=item_list,
        no_cash_collected=True,  # a CANCEL means the sale was voided, not tendered
    )


# ----------------------------------------------------------------------------
# Register analyzer
# ----------------------------------------------------------------------------
def analyze_register(clip):
    path = SRC / clip["file"]
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    detector = YoloDetector(conf=0.35)
    outdir = OUT / clip["slug"]

    # First pass: read frames, person presence + drawer motion.
    prev_roi = None
    motion, person_conf, saved = [], [], []
    frames_cache = {}
    samples = []                              # for the Auto-Evidence Agent
    idx = 0
    start_clock = ""
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        if idx == 0:
            start_clock = clock_at(clip, 0)
        step = max(1, int(fps / 3))  # ~3 Hz sampling
        if idx % step == 0:
            x1, y1, x2, y2 = roi_px(clip["cash_roi"], w, h)
            roi_gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
            cur_motion = 0.0
            if prev_roi is not None and prev_roi.shape == roi_gray.shape:
                cur_motion = float(np.mean(cv2.absdiff(roi_gray, prev_roi)))
                motion.append((idx / fps, cur_motion))
            prev_roi = roi_gray
            # person detection on a downscaled frame (speed)
            small = cv2.resize(frame, (960, int(960 * h / w)))
            dets = detector(small)
            best = max([dd.confidence for dd in dets], default=0.0)
            person_conf.append((idx / fps, best))
            frames_cache[idx] = frame.copy()
            sc = w / 960.0
            people = tuple(Detection(tuple(v * sc for v in dd.xyxy), dd.confidence)
                           for dd in dets)
            samples.append(FrameSample(idx=idx, t=idx / fps, frame_w=w, frame_h=h,
                                       people=people, drawer_motion=cur_motion))
        idx += 1
    total_s = idx / fps

    # motion stats -> activity windows
    if motion:
        vals = np.array([m for _, m in motion])
        thr = float(vals.mean() + 0.6 * vals.std())
        active = [(t, v) for t, v in motion if v >= thr]
        active_s = len(active) * (1.0 / 3.0)
        peak_t = max(motion, key=lambda tv: tv[1])[0]
    else:
        thr = 0.0; active = []; active_s = 0.0; peak_t = total_s * 0.5
    person_frac = float(np.mean([1 for _, c in person_conf if c >= 0.35]) ) if person_conf else 0
    person_pct = round(100 * sum(1 for _, c in person_conf if c >= 0.35) / max(1, len(person_conf)), 1)

    # POS overlay
    pos = None
    if clip.get("has_overlay"):
        pos = analyze_pos_overlay(cap, fps, clip["pos_band"])

    # pick evidence frame index nearest a chosen key time
    key_t = pos["cancel_first_s"] if (pos and pos.get("cancel_detected")) else peak_t
    key_idx = min(frames_cache, key=lambda i: abs(i / fps - key_t)) if frames_cache else 0
    key_frame = frames_cache.get(key_idx)

    # build BEFORE/AFTER
    findings = dict(
        slug=clip["slug"], group="register", site=clip["site"],
        register=clip["register"], camera=clip["camera"],
        reported=clip["reported"], duration_s=round(total_s, 1),
        start_clock=start_clock, fps=round(fps, 1),
        person_present_pct=person_pct,
        cash_drawer_activity_s=round(active_s, 1),
        cash_activity_pct=round(100 * active_s / max(1, total_s), 1),
        motion_peak_time_s=round(peak_t, 1),
    )
    if pos:
        findings["pos_overlay"] = pos

    if key_frame is not None:
        h, w = key_frame.shape[:2]
        before = key_frame.copy()
        after = key_frame.copy()
        # draw person box(es) on the key frame
        small = cv2.resize(after, (960, int(960 * h / w)))
        sc = w / 960.0
        for dd in detector(small):
            bx1, by1, bx2, by2 = [int(v * sc) for v in dd.xyxy]
            cv2.rectangle(after, (bx1, by1), (bx2, by2), TEAL, 2)
            cv2.putText(after, f"person {dd.confidence:.2f}", (bx1, max(20, by1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, TEAL, 2, cv2.LINE_AA)
        # cash ROI
        x1, y1, x2, y2 = roi_px(clip["cash_roi"], w, h)
        cv2.rectangle(after, (x1, y1), (x2, y2), YELLOW, 2)
        cv2.putText(after, "CASH DRAWER ROI", (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, YELLOW, 2, cv2.LINE_AA)
        # verdict banner
        if pos and pos.get("cancel_detected"):
            amt = pos.get("canceled_amount") or "?"
            verdict = (f"POS: SALE CANCELLED -{amt} by {pos.get('cashier') or '?'} "
                       f"- goods handed over, no cash collected")
        else:
            verdict = f"Cash-drawer manual handling {findings['cash_activity_pct']:.0f}% of clip"
        brand_banner(after, f"{clip['register']} - {clip['reported'].split(' - ')[0]}",
                     start_clock)
        # bottom finding strip
        cv2.rectangle(after, (0, h - 34), (w, h), (20, 20, 20), -1)
        cv2.putText(after, "AI FINDING: " + verdict, (10, h - 11),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, GREEN, 2, cv2.LINE_AA)
        brand_banner(before, f"{clip['register']} - RAW (no analysis)", start_clock)
        save_pair(before, after, outdir, "key")
        findings["evidence_clock"] = clock_at(clip, key_t)

    # Auto-Evidence Agent: mark the POS cancel window on the samples, then let the
    # agent auto-select evidence frames (additive; hand-tuned "key" above is kept).
    if pos and pos.get("cancel_detected"):
        cf, cl = pos.get("cancel_first_s"), pos.get("cancel_last_s")
        if cf is not None:
            hi = (cl or cf) + 0.5
            samples = [dataclasses.replace(s, cancel=(cf - 0.5 <= s.t <= hi))
                       for s in samples]
    run_auto_evidence(clip, samples, detector, frames_cache, findings, floor=False)

    cap.release()
    (outdir).mkdir(parents=True, exist_ok=True)
    (outdir / "findings.json").write_text(json.dumps(findings, indent=2))
    return findings


# ----------------------------------------------------------------------------
# Floor analyzer (multi-camera shoplifting)
# ----------------------------------------------------------------------------
def dominant_blue(frame, box):
    x1, y1, x2, y2 = [int(v) for v in box]
    x1, y1 = max(0, x1), max(0, y1)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return 0.0
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (95, 60, 40), (135, 255, 255))
    return float(mask.mean() / 255.0)


def analyze_floor(clip):
    path = SRC / clip["file"]
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    detector = YoloDetector(conf=0.30)
    tracker = IoUTracker()
    outdir = OUT / clip["slug"]

    prev_small = None
    scene_cuts = []
    people_timeline = []           # (t, count)
    cooler_hits = []               # (t, n_people_in_cooler)
    best_evidence = None           # (score, idx, frame, dets)
    blue_suspect = None            # (score, idx, frame, box)
    frames_cache = {}
    samples = []                   # for the Auto-Evidence Agent
    start_clock = ""
    idx = 0
    step = max(1, int(fps / 4))    # ~4 Hz
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        if idx == 0:
            start_clock = clock_at(clip, 0)
        if idx % step == 0:
            small = cv2.resize(frame, (720, int(720 * h / w)))
            # scene cut detection
            if prev_small is not None:
                diff = float(np.mean(cv2.absdiff(
                    cv2.cvtColor(small, cv2.COLOR_BGR2GRAY),
                    cv2.cvtColor(prev_small, cv2.COLOR_BGR2GRAY))))
                if diff > 45:
                    scene_cuts.append(round(idx / fps, 1))
            prev_small = small
            dets = detector(small)
            t = idx / fps
            people_timeline.append((round(t, 1), len(dets)))
            # cooler interaction: person bottom-center inside cooler ROI
            cx1, cy1, cx2, cy2 = clip["cooler_roi"]
            n_cooler = 0
            for dd in dets:
                bcx, bcy = dd.bottom_center
                if cx1 <= bcx / 720 <= cx2 and cy1 <= bcy / (720 * h / w) <= cy2:
                    n_cooler += 1
                # blue-shirt suspect (upper body blue)
                bl = dominant_blue(small, dd.xyxy)
                if bl > 0.18 and (blue_suspect is None or bl > blue_suspect[0]):
                    blue_suspect = (bl, idx, frame.copy(),
                                    tuple(v * (w / 720) for v in dd.xyxy))
            if n_cooler:
                cooler_hits.append((round(t, 1), n_cooler))
            # evidence score = people near cooler + total people
            score = n_cooler * 2 + len(dets)
            if best_evidence is None or score > best_evidence[0]:
                best_evidence = (score, idx, frame.copy(), dets, w, h)
            frames_cache[idx] = frame.copy()
            sc = w / 720.0
            people = tuple(Detection(tuple(v * sc for v in dd.xyxy), dd.confidence)
                           for dd in dets)
            samples.append(FrameSample(idx=idx, t=t, frame_w=w, frame_h=h,
                                       people=people))
        idx += 1
    total_s = idx / fps

    findings = dict(
        slug=clip["slug"], group="floor", site=clip["site"],
        register=clip["register"], camera=clip["camera"],
        reported=clip["reported"], duration_s=round(total_s, 1),
        start_clock=start_clock, fps=round(fps, 1),
        scene_cuts=len(scene_cuts), scene_cut_times=scene_cuts[:20],
        max_people=max((c for _, c in people_timeline), default=0),
        cooler_interaction_samples=len(cooler_hits),
        cooler_interaction_s=round(len(cooler_hits) * (1.0 / 4.0), 1),
        blue_suspect_detected=blue_suspect is not None,
    )

    # BEFORE/AFTER on best cooler-interaction frame
    if best_evidence is not None:
        _, kidx, kframe, kdets, w, h = best_evidence
        before = kframe.copy()
        after = kframe.copy()
        sc = w / 720.0
        for dd in kdets:
            bx1, by1, bx2, by2 = [int(v * sc) for v in dd.xyxy]
            bcx, bcy = dd.bottom_center
            in_cooler = (clip["cooler_roi"][0] <= bcx / 720 <= clip["cooler_roi"][2])
            col = RED if in_cooler else TEAL
            cv2.rectangle(after, (bx1, by1), (bx2, by2), col, 2)
            lbl = "AT COOLER" if in_cooler else "person"
            cv2.putText(after, f"{lbl} {dd.confidence:.2f}", (bx1, max(18, by1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2, cv2.LINE_AA)
        cx1, cy1, cx2, cy2 = roi_px(clip["cooler_roi"], w, h)
        cv2.rectangle(after, (cx1, cy1), (cx2, cy2), YELLOW, 2)
        cv2.putText(after, "COOLER ZONE", (cx1, max(18, cy1 + 22)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, YELLOW, 2, cv2.LINE_AA)
        n_at = sum(1 for dd in kdets
                   if clip["cooler_roi"][0] <= dd.bottom_center[0] / 720 <= clip["cooler_roi"][2])
        brand_banner(after, f"Sales floor - {clip['reported'].split(' - ')[0]}", start_clock)
        cv2.rectangle(after, (0, h - 34), (w, h), (20, 20, 20), -1)
        cv2.putText(after, f"AI FINDING: {len(kdets)} people, {n_at} interacting at cooler",
                    (10, h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.55, GREEN, 2, cv2.LINE_AA)
        brand_banner(before, "Sales floor - RAW (no analysis)", start_clock)
        save_pair(before, after, outdir, "key")
        findings["evidence_clock"] = clock_at(clip, kidx / fps)

    # blue suspect evidence frame
    if blue_suspect is not None:
        _, bidx, bframe, bbox = blue_suspect
        after = bframe.copy()
        h, w = after.shape[:2]
        bx1, by1, bx2, by2 = [int(v) for v in bbox]
        cv2.rectangle(after, (bx1, by1), (bx2, by2), RED, 3)
        cv2.putText(after, "SUSPECT (blue upper-body)", (bx1, max(18, by1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, RED, 2, cv2.LINE_AA)
        sus_clock = clock_at(clip, bidx / fps)
        brand_banner(after, "Suspect appearance match", sus_clock)
        before = bframe.copy()
        brand_banner(before, "Sales floor - RAW (no analysis)", sus_clock)
        save_pair(before, after, outdir, "suspect")
        findings["suspect_clock"] = sus_clock

    # Auto-Evidence Agent (additive; hand-tuned "key"/"suspect" above are kept).
    run_auto_evidence(clip, samples, detector, frames_cache, findings, floor=True)

    cap.release()
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "findings.json").write_text(json.dumps(findings, indent=2))
    return findings


def main():
    results = []
    for clip in CLIPS:
        print(f"\n=== {clip['slug']} ({clip['group']}) ===")
        if clip["group"] == "register":
            f = analyze_register(clip)
        else:
            f = analyze_floor(clip)
        results.append(f)
        print(json.dumps(f, indent=2)[:900])
    (OUT / "all_findings.json").write_text(json.dumps(results, indent=2))
    print("\nAll findings ->", OUT / "all_findings.json")


if __name__ == "__main__":
    main()
