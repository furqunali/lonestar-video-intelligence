"""Generate analytics artifacts for the director report from the REAL incident data
using the new avip/analytics modules. Writes reports/analytics/analytics.json.

Genuine only: transactions are built from what the analysis actually found
(Jordan cancel $18.86 verified from the receipt; 5/12 Nov = no-sale cash-drawer
opens). Camera-health is measured live on each clip's sampled frames with the
hardened ensemble (proves the tamper false-positive is fixed)."""
from __future__ import annotations

import json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import cv2, numpy as np

sys.path.insert(0, r"C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence")
from avip.analytics.transactions import Transaction
from avip.analytics import risk, rollup, health_plus

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "New Videos for test"
OUT = ROOT / "reports" / "analytics"; OUT.mkdir(parents=True, exist_ok=True)
CDT = timezone(timedelta(hours=-6))  # store-local (America/Chicago, CST)

# --- transactions built from the verified incident findings (not filenames) ---
TXNS = [
    Transaction("0008-C2-3636162", "0008", "Register 2", "JORDAN LEE", 18.86,
                "cancel", datetime(2024, 11, 8, 17, 36, tzinfo=CDT),
                clip="Jordan Lee Canceled Sale By -18.86.wmv"),
    Transaction("0008-C3-05nov", "0008", "Register 1", "CASHIER (Reg 1)", 0.0,
                "no_sale", datetime(2024, 11, 5, 7, 9, tzinfo=CDT),
                clip="Cash theft By cashier 5 Nov.wmv"),
    Transaction("0008-C3-12nov", "0008", "Register 1", "CASHIER (Reg 1)", 0.0,
                "no_sale", datetime(2024, 11, 12, 7, 13, tzinfo=CDT),
                clip="Cash theft By Cashier 12 Nov.wmv"),
]

CLIPS = {
    "Cash theft By cashier 5 Nov.wmv": "Register 1 (5 Nov)",
    "Cash theft By Cashier 12 Nov.wmv": "Register 1 (12 Nov)",
    "Jordan Lee Canceled Sale By -18.86.wmv": "Register 2 (Jordan)",
    "27 Jan 2024 Stealing 1.mp4": "Sales floor (27 Jan)",
    "Stealing 14-may.mp4": "Sales floor (14 May)",
}


def sample_frames(path, n=8):
    cap = cv2.VideoCapture(str(path)); total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out = []
    for t in np.linspace(0.1, 0.9, n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * t)); ok, fr = cap.read()
        if ok: out.append(fr)
    cap.release(); return out


def main():
    # 1) risk-ranked exceptions + multi-store rollup
    findings = risk.score_transactions(TXNS)
    roll = rollup.build_rollup(TXNS)

    # 2) hardened camera-health on each clip's sampled frames (tamper fix proof)
    health = []
    for fn, label in CLIPS.items():
        p = SRC / fn
        if not p.exists():
            continue
        frames = sample_frames(p)
        rep = health_plus.assess_tamper(frames)
        health.append({"clip": label, "clarity": rep.clarity,
                       "blur": rep.blur_score, "edges": rep.edge_density,
                       "luminance": rep.mean_luminance, "tamper": rep.is_tamper,
                       "reason": rep.reasons[0] if rep.reasons else ""})
        print(f"health {label:24} -> {rep.clarity}  (blur {rep.blur_score}, edges {rep.edge_density})")

    data = {
        "risk": [{"cashier": f.cashier, "register": f.register, "location_id": f.location_id,
                  "tx_type": f.tx_type, "amount": f.amount, "score": f.score,
                  "band": risk.risk_band(f.score), "when": f.timestamp.strftime("%d %b %Y %I:%M %p"),
                  "reasons": f.reasons} for f in findings],
        "rollup": roll,
        "health": health,
    }
    (OUT / "analytics.json").write_text(json.dumps(data, indent=2, default=str))
    print("\nrisk-ranked:", [(f.cashier, f.score) for f in findings])
    print("rollup totals:", roll["totals"])
    print("wrote", OUT / "analytics.json")


if __name__ == "__main__":
    main()
