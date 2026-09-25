"""POS exception risk-scoring engine — feature 1 (Smart-ER-style risk matrix).

Given the POS exceptions the analyzer already OCRs (void / cancel / refund /
no-sale / discount / return, with cashier + amount + time), rank them by RISK so
the director report leads with the worst offenders instead of a flat list. This
is the offline equivalent of i3 Smart-ER's headline "risk matrix" — pure,
deterministic scoring over data we already have (no new capture, no model).

Risk = weighted blend (0..100) of four normalized factors:
    severity   — how serious the exception TYPE is
    amount     — the dollar value at risk (capped/normalized)
    frequency  — is this cashier a repeat offender (their exception share)
    time       — off-hours (before open / after close / overnight) is riskier
Every score carries a human-readable reason breakdown for the reviewer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from avip.analytics.transactions import Transaction, EXCEPTION_TYPES

# Base severity per exception type (0..1). Voids/cancels & no-sale drawer opens
# are the classic sweethearting / skim signatures, so they weigh highest.
SEVERITY = {
    "void": 0.95, "cancel": 0.95, "no_sale": 0.85,
    "refund": 0.75, "return": 0.65, "discount": 0.50,
}

# Weights of the four risk factors (need not sum to 1; normalized internally).
WEIGHTS = {"severity": 0.35, "amount": 0.30, "frequency": 0.20, "time": 0.15}

# Amount at/above this is treated as "max" risk on the amount axis ($).
AMOUNT_CAP = 50.0
# Normal trading hours (store-local). Outside => higher time-risk.
OPEN_HOUR, CLOSE_HOUR = 6, 23


@dataclass
class RiskFinding:
    tx_id: str
    location_id: str
    register: str
    cashier: str
    amount: float
    tx_type: str
    timestamp: datetime
    clip: str | None
    score: float                       # 0..100
    factors: dict[str, float] = field(default_factory=dict)  # each 0..1
    reasons: list[str] = field(default_factory=list)


def _time_factor(ts: datetime) -> tuple[float, str]:
    h = ts.hour
    if OPEN_HOUR <= h < CLOSE_HOUR:
        # within hours: mild bump for very early morning (low supervision)
        return (0.25 if h < 8 else 0.1), "within trading hours"
    return 1.0, f"off-hours ({h:02d}:xx) — low supervision"


def _cashier_frequency(txns: list[Transaction]) -> dict[str, float]:
    """Each cashier's share of exceptions, normalized to the busiest offender."""
    counts: dict[str, int] = {}
    for t in txns:
        if t.is_exception:
            counts[t.cashier] = counts.get(t.cashier, 0) + 1
    if not counts:
        return {}
    mx = max(counts.values())
    return {c: (n / mx if mx else 0.0) for c, n in counts.items()}


def score_transactions(txns: list[Transaction],
                       amount_cap: float = AMOUNT_CAP,
                       weights: dict[str, float] | None = None) -> list[RiskFinding]:
    """Score every EXCEPTION transaction; return findings sorted highest-risk first.

    Fail-soft: a malformed record is skipped, never raised."""
    w = {**WEIGHTS, **(weights or {})}
    wsum = sum(w.values()) or 1.0
    freq = _cashier_frequency(txns)

    out: list[RiskFinding] = []
    for t in txns:
        try:
            if not t.is_exception:
                continue
            sev = SEVERITY.get(t.tx_type, 0.5)
            amt = min(t.amount / amount_cap, 1.0) if amount_cap > 0 else 0.0
            frq = freq.get(t.cashier, 0.0)
            tf, tf_reason = _time_factor(t.timestamp)
            factors = {"severity": sev, "amount": amt, "frequency": frq, "time": tf}
            score = 100.0 * sum(w[k] * factors[k] for k in w) / wsum

            reasons = [f"{t.tx_type.upper()} (severity {sev:.2f})",
                       f"${t.amount:.2f} at risk",
                       (f"repeat: {t.cashier} exception-rate {frq:.2f}"
                        if frq >= 0.5 else f"{t.cashier}"),
                       tf_reason]
            out.append(RiskFinding(
                tx_id=t.tx_id, location_id=t.location_id, register=t.register,
                cashier=t.cashier, amount=t.amount, tx_type=t.tx_type,
                timestamp=t.timestamp, clip=t.clip,
                score=round(score, 1), factors={k: round(v, 3) for k, v in factors.items()},
                reasons=reasons,
            ))
        except Exception:
            continue

    out.sort(key=lambda f: f.score, reverse=True)
    return out


def risk_band(score: float) -> str:
    """Map a 0..100 score to a band for the report (colour-coding)."""
    if score >= 70:
        return "CRITICAL"
    if score >= 45:
        return "HIGH"
    if score >= 25:
        return "MEDIUM"
    return "LOW"
