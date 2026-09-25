"""Analytics package (post-M7 feature layer).

Deterministic, offline, CPU-only analytics that build on the existing CV outputs
(detections, tracklets, zones) and the OCR'd POS transactions. Added to close the
feature gap vs i3International's paid modules while staying 100% on-premise:

    risk         — POS exception risk-scoring engine (Smart-ER-style risk matrix)
    counting     — line-crossing people counting + conversion rate
    heatmap      — spatial traffic / dwell heat-map overlays
    health_plus  — hardened camera-tamper / health ensemble (fixes false-positive)
    transactions — transaction-indexed SQLite store + search
    rollup       — multi-store aggregate / scorecard summary
    auto_evidence— auto-select evidence frames (no manual ROI/frame pointing)

Design rules honoured: derive from data (never hardcode), validate/sanitize inputs,
fail soft (skip a bad record, never crash the batch), pure functions where possible
so results are reproducible for the blind test.
"""
from __future__ import annotations

__all__ = [
    "risk",
    "counting",
    "heatmap",
    "health_plus",
    "transactions",
    "rollup",
    "auto_evidence",
]
