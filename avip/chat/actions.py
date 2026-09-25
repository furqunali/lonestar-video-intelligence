"""Typed action registry — what the assistant can DO, who may request it, and
which approvals it needs before it executes.

Read-only actions (approvals=[]) run immediately for anyone. Sensitive actions
(generate/publish/email/export) create an approval request that must be signed off
by a Manager and/or Director before it executes. Handlers read from a ChatContext
so the same registry works in tests (mock ctx) and in production (real providers).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from avip.analytics import risk as risk_mod


@dataclass
class ChatContext:
    """Data + executors the action handlers use. All optional/pluggable."""
    transaction_store: object | None = None       # avip.analytics.transactions.TransactionStore
    transactions: list = field(default_factory=list)   # list[Transaction] (for risk)
    analytics: dict = field(default_factory=dict)      # parsed reports/analytics/analytics.json
    incidents: list = field(default_factory=list)      # incident summaries
    evidence: list = field(default_factory=list)       # evidence items per incident
    report_url: str | None = None                      # shared-drive / report location
    executors: dict = field(default_factory=dict)      # name -> callable for sensitive side-effects


@dataclass
class Action:
    name: str
    description: str
    min_role: str                     # minimum role to REQUEST it
    approvals: list[str]              # ordered roles that must approve ([] = none)
    handler: Callable[[dict, ChatContext], dict]


# --------------------------- read-only handlers ---------------------------- #
def _help(params, ctx):
    return {"capabilities": [{"action": a.name, "desc": a.description,
                              "approvals": a.approvals} for a in REGISTRY.values()]}


import re as _re


def _incident_matches(inc: dict, q: str) -> bool:
    q = (q or "").lower()
    hay = " ".join(str(inc.get(k, "")) for k in
                   ("slug", "title", "category", "when", "where", "cashier", "finding")).lower()
    amt = str(inc.get("amount") or "")
    if amt and amt != "0.0" and amt in q:
        return True
    for tok in _re.findall(r"[a-z0-9.]{3,}", q):
        if tok in ("the", "and", "for", "about", "show", "give", "tell", "provide",
                   "detail", "details", "incident", "incidents", "theft", "evidence") :
            continue
        if tok in hay:
            return True
    return False


def _evidence_urls(inc: dict) -> list[str]:
    return [f"/evidence?slug={inc.get('slug')}&name={n}" for n in inc.get("frames", [])]


def _list_incidents(params, ctx):
    inc = ctx.incidents or []
    q = params.get("query") or ""
    if q:
        hits = [i for i in inc if _incident_matches(i, q)]
        if len(hits) == 1:
            d = dict(hits[0]); d["images"] = _evidence_urls(d)
            return {"detail": d}
        if hits:
            return {"count": len(hits), "incidents": hits}
    return {"count": len(inc), "incidents": inc}


def _risk_ranking(params, ctx):
    if ctx.analytics.get("risk"):
        return {"risk": ctx.analytics["risk"]}
    findings = risk_mod.score_transactions(ctx.transactions)
    return {"risk": [{"cashier": f.cashier, "register": f.register, "tx_type": f.tx_type,
                      "amount": f.amount, "score": f.score, "band": risk_mod.risk_band(f.score),
                      "reasons": f.reasons} for f in findings]}


def _camera_health(params, ctx):
    return {"health": ctx.analytics.get("health", [])}


def _kpis(params, ctx):
    roll = ctx.analytics.get("rollup", {})
    return {"kpis": roll.get("totals", {})}


def _get_evidence(params, ctx):
    q = params.get("query") or ""
    inc = ctx.incidents or []
    picked = [i for i in inc if _incident_matches(i, q)] if q else inc
    if not picked:
        picked = inc
    ev = [{"incident": i.get("title", i.get("slug")), "frames": i.get("frames", []),
           "images": _evidence_urls(i)} for i in picked]
    images = [u for e in ev for u in e["images"]]
    return {"evidence": ev, "images": images, "report_url": ctx.report_url}


def _get_summary(params, ctx):
    roll = ctx.analytics.get("rollup", {})
    risk = ctx.analytics.get("risk", [])
    if not risk and ctx.transactions:
        risk = [{"cashier": f.cashier, "score": f.score, "band": risk_mod.risk_band(f.score)}
                for f in risk_mod.score_transactions(ctx.transactions)]
    health = ctx.analytics.get("health", [])
    return {
        "incidents": len(ctx.incidents or []),
        "top_risk": (risk[0] if risk else None),
        "exceptions": roll.get("totals", {}).get("exceptions"),
        "exception_amount": roll.get("totals", {}).get("exception_amount"),
        "cameras_ok": sum(1 for h in health if h.get("clarity") == "OK"),
        "cameras_total": len(health),
        "report_url": ctx.report_url,
    }


def _search_transaction(params, ctx):
    if ctx.transaction_store is None:
        return {"error": "transaction store not available", "results": []}
    res = ctx.transaction_store.search(
        cashier=params.get("cashier"), register=params.get("register"),
        tx_type=params.get("tx_type"), min_amount=params.get("min_amount"),
        exceptions_only=bool(params.get("exceptions_only")))
    return {"results": res, "count": len(res)}


# --------------------------- sensitive handlers ---------------------------- #
def _run_executor(name: str, params, ctx, done_msg: str):
    fn = ctx.executors.get(name)
    if callable(fn):
        try:
            out = fn(params)
            return {"executed": True, "detail": out if out is not None else done_msg}
        except Exception as e:                        # fail-soft
            return {"executed": False, "error": str(e)}
    # no real executor wired -> record the intent (safe default, no side-effect)
    return {"executed": True, "detail": done_msg + " (recorded; wire an executor for the live side-effect)"}


def _generate_report(params, ctx):
    return _run_executor("generate_report", params, ctx, "Director report regenerated")


def _publish_shared_drive(params, ctx):
    return _run_executor("publish_shared_drive", params, ctx,
                         "Published to shared drive 01_Director_Report")


def _email_director(params, ctx):
    return _run_executor("email_director", params, ctx, "Summary emailed to the Director")


def _export_data(params, ctx):
    return _run_executor("export_data", params, ctx, "Transactions exported")


# ------------------------------- registry ---------------------------------- #
REGISTRY: dict[str, Action] = {a.name: a for a in [
    Action("help", "List what the assistant can do", "staff", [], _help),
    Action("list_incidents", "Show the loss-prevention incidents", "staff", [], _list_incidents),
    Action("get_summary", "Overall summary (incidents, risk, cameras)", "staff", [], _get_summary),
    Action("get_evidence", "Show evidence / where to view it", "staff", [], _get_evidence),
    Action("get_risk_ranking", "Rank POS exceptions by risk", "staff", [], _risk_ranking),
    Action("get_camera_health", "Show camera-health status", "staff", [], _camera_health),
    Action("get_kpis", "Show key metrics / totals", "staff", [], _kpis),
    Action("search_transaction", "Search POS transactions (cashier/type/amount)", "staff", [], _search_transaction),
    Action("generate_report", "Regenerate the director report", "manager", ["manager"], _generate_report),
    Action("export_data", "Export transaction data", "manager", ["manager"], _export_data),
    Action("email_director", "Email a summary to the Director", "manager", ["director"], _email_director),
    Action("publish_shared_drive", "Publish the report to the shared drive", "manager",
           ["manager", "director"], _publish_shared_drive),
]}


def get_action(name: str) -> Action | None:
    return REGISTRY.get(name)
