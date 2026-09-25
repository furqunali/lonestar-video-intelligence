"""Assistant engine (Strategy pattern).

RuleEngine  — offline default: deterministic intent detection → chat answer or an
              action to run. No API key, fully testable.
LLMEngine   — optional/pluggable: uses a caller-supplied LLM for free-form answers
              while still routing recognised commands through the rule layer (so
              actions/approvals stay deterministic). Falls back to rules offline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Protocol


@dataclass
class Reply:
    text: str
    action: str | None = None
    params: dict = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)


class Engine(Protocol):
    def respond(self, text: str, memory: dict | None = None) -> Reply: ...


# intent keyword → action name (first match wins; order matters)
_INTENTS = [
    (r"\b(help|what can you|capabilit|commands?)\b", "help"),
    (r"\b(publish|shared drive|upload report)\b", "publish_shared_drive"),
    (r"\b(email|send).{0,20}(director|mustafa)\b", "email_director"),
    (r"\b(generate|rebuild|refresh|regenerate).{0,15}report\b", "generate_report"),
    (r"\b(export|download).{0,15}(data|transactions?|csv)\b", "export_data"),
    (r"\b(evidence|proof|photos?|pictures?|footage|clips?|annotat\w*)\b", "get_evidence"),
    (r"\b(summary|overview|brief|situation|status|how are things|update me)\b", "get_summary"),
    (r"\b(risk|rank|worst|priorit)\b", "get_risk_ranking"),
    (r"\b(camera|tamper|health|uptime)\b", "get_camera_health"),
    (r"\b(kpi|metric|totals?|scorecard|numbers?|stats?)\b", "get_kpis"),
    (r"\b(search|find|look ?up|transactions?|voids?|cancels?|refunds?|cashiers?)\b", "search_transaction"),
    (r"\b(incidents?|thefts?|shoplift\w*|cases?|jordan)\b", "list_incidents"),
]
_GREET = re.compile(r"\b(hi|hello|hey|salam|assalam|good (morning|afternoon|evening))\b", re.I)
_THANKS = re.compile(r"\b(thanks|thank you|shukriya|shukria)\b", re.I)
_TYPE = re.compile(r"\b(void|cancel|cancelled|refund|no[- ]?sale|return|discount)\b", re.I)
_AMOUNT = re.compile(r"(?:over|above|>=?|min(?:imum)?)\s*\$?\s*(\d{1,6}(?:\.\d{1,2})?)", re.I)
_CASHIER = re.compile(
    r"cashier\s+([A-Za-z][A-Za-z.'\- ]*?)(?:\s+(?:for|void|cancel|refund|return|over|above|with|and|please)\b|[.?!,]|$)",
    re.I)


class RuleEngine:
    """Deterministic offline engine."""

    def respond(self, text: str, memory: dict | None = None) -> Reply:
        t = (text or "").strip()
        if not t:
            return Reply("Please type a question or a command. Try 'help'.",
                         suggestions=["help", "show incidents", "risk ranking"])
        low = t.lower()
        if _GREET.search(low) and len(low) < 30:
            name = (memory or {}).get("name")
            hi = f"Hello{(' ' + name) if name else ''}! "
            return Reply(hi + "I'm the Sugarland Petroleum video-intelligence assistant. "
                         "Ask about incidents, risk, camera health, or run an action.",
                         suggestions=["show incidents", "risk ranking", "camera health", "help"])
        if _THANKS.search(low):
            return Reply("You're welcome. Anything else?",
                         suggestions=["show incidents", "risk ranking"])

        for pattern, action in _INTENTS:
            if re.search(pattern, low):
                params = self._params_for(action, t)
                return Reply(self._ack(action), action=action, params=params)

        return Reply("I didn't catch that. I can show incidents, risk ranking, camera "
                     "health, KPIs, search transactions, or (with approval) generate / "
                     "publish reports. Try 'help'.",
                     suggestions=["help", "show incidents", "risk ranking", "camera health"])

    def _params_for(self, action: str, text: str) -> dict:
        if action in ("list_incidents", "get_evidence"):
            return {"query": text}
        if action != "search_transaction":
            return {}
        p: dict = {}
        m = _CASHIER.search(text)
        if m:
            p["cashier"] = m.group(1).strip()
        mt = _TYPE.search(text)
        if mt:
            p["tx_type"] = mt.group(1)
        ma = _AMOUNT.search(text)
        if ma:
            p["min_amount"] = float(ma.group(1))
        if not p:
            p["exceptions_only"] = True
        return p

    @staticmethod
    def _ack(action: str) -> str:
        return {
            "help": "Here's what I can do:",
            "list_incidents": "Here are the loss-prevention incidents:",
            "get_summary": "Here's the current summary:",
            "get_evidence": "Evidence overview:",
            "get_risk_ranking": "POS exceptions ranked by risk:",
            "get_camera_health": "Camera-health status:",
            "get_kpis": "Key metrics:",
            "search_transaction": "Searching transactions…",
            "generate_report": "Requesting report regeneration…",
            "export_data": "Requesting a data export…",
            "email_director": "Requesting to email the Director…",
            "publish_shared_drive": "Requesting to publish to the shared drive…",
        }.get(action, "Working on it…")


class LLMEngine:
    """Pluggable LLM engine. `llm(prompt) -> str`. Recognised commands still route
    through the rule layer so actions/approvals stay deterministic."""

    def __init__(self, llm: Callable[[str], str], rules: RuleEngine | None = None):
        self.llm = llm
        self.rules = rules or RuleEngine()

    def respond(self, text: str, memory: dict | None = None) -> Reply:
        r = self.rules.respond(text, memory)
        if r.action:                       # deterministic path wins for actions
            return r
        try:
            answer = self.llm(text)
            return Reply(answer or r.text, suggestions=r.suggestions)
        except Exception:
            return r                       # offline / failure -> rule fallback
