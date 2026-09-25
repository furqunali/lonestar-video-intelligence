"""Multi-store rollup / scorecard — feature 5b.

Aggregates POS transactions (across stores, cashiers, dates) into a summary an
Admin Director can act on — the offline equivalent of i3's multi-location
"store scorecard / trend" reports. Pure aggregation over the transaction records
+ the risk engine; returns a plain dict (render to HTML in the report layer).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from avip.analytics.transactions import Transaction, EXCEPTION_TYPES
from avip.analytics.risk import score_transactions, risk_band


def _exc_amount(txns: list[Transaction]) -> float:
    return round(sum(t.amount for t in txns if t.is_exception), 2)


def build_rollup(txns: list[Transaction], top_n: int = 10) -> dict:
    """Cross-store aggregate. Fail-soft on bad records."""
    txns = [t for t in txns if isinstance(t, Transaction)]
    exceptions = [t for t in txns if t.is_exception]

    by_store: dict[str, dict] = defaultdict(lambda: {"exceptions": 0, "amount": 0.0, "by_type": defaultdict(int)})
    by_cashier: dict[str, dict] = defaultdict(lambda: {"exceptions": 0, "amount": 0.0, "stores": set()})
    by_date: dict[str, dict] = defaultdict(lambda: {"exceptions": 0, "amount": 0.0})
    by_type: dict[str, int] = defaultdict(int)

    for t in exceptions:
        s = by_store[t.location_id]; s["exceptions"] += 1; s["amount"] += t.amount; s["by_type"][t.tx_type] += 1
        c = by_cashier[t.cashier]; c["exceptions"] += 1; c["amount"] += t.amount; c["stores"].add(t.location_id)
        try:
            d = t.timestamp.date().isoformat()
        except Exception:
            d = "unknown"
        by_date[d]["exceptions"] += 1; by_date[d]["amount"] += t.amount
        by_type[t.tx_type] += 1

    # top risk findings across everything
    findings = score_transactions(txns)
    top_risk = [{
        "tx_id": f.tx_id, "location_id": f.location_id, "register": f.register,
        "cashier": f.cashier, "tx_type": f.tx_type, "amount": f.amount,
        "score": f.score, "band": risk_band(f.score),
        "when": f.timestamp.isoformat(), "reasons": f.reasons,
    } for f in findings[:top_n]]

    def _fmt_store(k, v):
        return {"location_id": k, "exceptions": v["exceptions"],
                "amount": round(v["amount"], 2), "by_type": dict(v["by_type"])}

    def _fmt_cashier(k, v):
        return {"cashier": k, "exceptions": v["exceptions"],
                "amount": round(v["amount"], 2), "stores": sorted(v["stores"])}

    return {
        "totals": {
            "transactions": len(txns),
            "exceptions": len(exceptions),
            "exception_amount": _exc_amount(txns),
            "stores": len(by_store),
            "cashiers_flagged": len(by_cashier),
        },
        "by_store": sorted((_fmt_store(k, v) for k, v in by_store.items()),
                           key=lambda r: r["amount"], reverse=True),
        "by_cashier": sorted((_fmt_cashier(k, v) for k, v in by_cashier.items()),
                             key=lambda r: r["amount"], reverse=True),
        "by_date": dict(sorted(({k: {"exceptions": v["exceptions"], "amount": round(v["amount"], 2)}
                                 for k, v in by_date.items()}).items())),
        "by_type": dict(by_type),
        "top_risk": top_risk,
    }
