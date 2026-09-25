"""ChatService — the orchestration layer the UI/server talks to.

Ties together the store, the engine (Strategy), the action registry, the approval
workflow and per-user memory. Every user turn is persisted; sensitive actions go
through Manager/Director approval and the outcome is posted back into the original
chat automatically.
"""
from __future__ import annotations

from avip.chat.store import ChatStore
from avip.chat.actions import ChatContext
from avip.chat.approvals import ApprovalEngine, ApprovalError
from avip.chat.engine import RuleEngine, LLMEngine, Engine
from avip.chat.memory import Memory
from avip.chat import roles as roles_mod


def _fmt_result(action: str, result: dict) -> str:
    if not isinstance(result, dict):
        return str(result)
    if result.get("error"):
        return f"⚠️ {result['error']}"
    if action == "help":
        caps = result.get("capabilities", [])
        return "I can:\n" + "\n".join(
            f" • {c['action']} — {c['desc']}" + (f"  (needs {'/'.join(c['approvals'])} approval)"
                                                 if c.get("approvals") else "")
            for c in caps)
    if action == "list_incidents":
        if result.get("detail"):
            d = result["detail"]
            lines = [f"📋 {d.get('title','Incident')} — {d.get('when','')} · {d.get('where','')}",
                     d.get("finding", "")]
            if d.get("amount"):
                lines.append(f"Amount: ${d['amount']}")
            if d.get("cashier"):
                lines.append(f"Cashier: {d['cashier']}")
            if d.get("images"):
                lines.append("(evidence pictures below)")
            return "\n".join(x for x in lines if x)
        incs = result.get("incidents", [])
        if incs and incs[0].get("title"):
            return (f"{len(incs)} matching incident(s):\n" +
                    "\n".join(f" • {i.get('title','?')} — {i.get('when','')}" for i in incs))
        return f"{result.get('count', 0)} incidents on file (cash theft, collusion void, shoplifting)."
    if action == "get_summary":
        parts = [f"{result.get('incidents','?')} incidents",
                 f"{result.get('exceptions','?')} POS exceptions (${result.get('exception_amount','?')})",
                 f"cameras {result.get('cameras_ok','?')}/{result.get('cameras_total','?')} OK"]
        tr = result.get("top_risk")
        if tr:
            parts.append(f"top risk: {tr.get('cashier','?')} ({tr.get('band','?')})")
        s = "Summary — " + " · ".join(parts) + "."
        return s + (f"\nFull report: {result['report_url']}" if result.get("report_url") else "")
    if action == "get_evidence":
        ev = result.get("evidence", [])
        head = f"{len(ev)} evidence set(s) available (BEFORE→AFTER annotated frames)."
        body = "\n".join(f" • {e.get('incident','?')}: {e.get('frames','?')} frame(s)" for e in ev[:6])
        tail = f"\nView in the report: {result['report_url']}" if result.get("report_url") else ""
        return (head + ("\n" + body if body else "") + tail)
    if action == "get_risk_ranking":
        rows = result.get("risk", [])[:5]
        return "Risk ranking:\n" + "\n".join(
            f" {i+1}. {r.get('cashier','?')} · {r.get('tx_type','?')} · "
            f"${r.get('amount',0)} · score {r.get('score','?')} ({r.get('band','?')})"
            for i, r in enumerate(rows)) if rows else "No exceptions to rank."
    if action == "get_camera_health":
        h = result.get("health", [])
        return "Camera health:\n" + "\n".join(
            f" • {x.get('clip','?')}: {x.get('clarity','?')}" for x in h) if h else "No health data."
    if action == "get_kpis":
        k = result.get("kpis", {})
        return "KPIs: " + ", ".join(f"{kk.replace('_',' ')}={vv}" for kk, vv in k.items()) if k else "No KPIs."
    if action == "search_transaction":
        n = result.get("count", 0)
        rows = result.get("results", [])[:5]
        head = f"{n} transaction(s) found." + ("" if not rows else "\n")
        return head + "\n".join(
            f" • {r.get('ts','')[:16]} {r.get('cashier','?')} {r.get('tx_type','?')} ${r.get('amount','?')}"
            for r in rows)
    # sensitive actions
    return result.get("detail") or ("Done." if result.get("executed") else str(result))


class ChatService:
    def __init__(self, store: ChatStore, ctx: ChatContext, now_fn,
                 engine: Engine | None = None, llm=None):
        self.store = store
        self.ctx = ctx
        self._now = now_fn
        self.engine = engine or (LLMEngine(llm) if llm else RuleEngine())
        self.approvals = ApprovalEngine(store, ctx, now_fn)
        self.memory = Memory(store, now_fn)

    def start_session(self, user_id: str, role: str) -> str:
        return self.store.create_session(user_id, roles_mod.normalize(role), self._now())

    def handle_message(self, session_id: str, text: str) -> dict:
        sess = self.store.get_session(session_id)
        if sess is None:
            raise ValueError(f"unknown session: {session_id}")
        user_id, role = sess["user_id"], sess["role"]
        self.store.add_message(session_id, "user", text, self._now())

        # 1) memory learning ("remember my name is ...")
        learned = self.memory.maybe_learn(user_id, text)
        if learned:
            self.store.add_message(session_id, "assistant", learned, self._now())
            return {"reply": learned, "suggestions": []}

        # 2) engine → chat answer or action
        reply = self.engine.respond(text, self.memory.get(user_id))
        request = None
        if reply.action:
            try:
                req = self.approvals.request(session_id, user_id, role, reply.action, reply.params)
                request = req
                status = req["status"]
                if status == "executed":
                    out = _fmt_result(reply.action, req.get("result") or {})
                    reply_text = f"{reply.text}\n{out}".strip()
                elif status.startswith("pending_"):
                    who = status.split("_", 1)[1]
                    reply_text = (f"🔒 Requested **{reply.action}**. This needs "
                                  f"{'/'.join(req.get('pending_roles', []))} approval — "
                                  f"currently waiting on the **{who}**. (request {req['id']})")
                else:
                    reply_text = f"Request {status}."
            except ApprovalError as e:
                reply_text = f"⛔ {e}"
        else:
            reply_text = reply.text

        images = []
        if request and isinstance(request.get("result"), dict):
            r = request["result"]
            images = list(r.get("images") or [])
            if not images and isinstance(r.get("detail"), dict):
                images = list(r["detail"].get("images") or [])
        self.store.add_message(session_id, "assistant", reply_text, self._now(),
                               meta={"action": reply.action, "images": images,
                                     "request_id": request["id"] if request else None,
                                     "status": request["status"] if request else None})
        return {"reply": reply_text, "suggestions": reply.suggestions,
                "request": request, "images": images}

    def decide(self, req_id: str, approver_id: str, role: str,
               decision: str, note: str = "") -> dict:
        req = self.approvals.decide(req_id, approver_id, role, decision, note)
        # post the outcome back into the original chat
        if req["status"] == "executed":
            msg = (f"✅ **{req['action']}** approved (final: {role}) — executed.\n"
                   f"{_fmt_result(req['action'], req.get('result') or {})}")
        elif req["status"] == "denied":
            msg = f"❌ **{req['action']}** was denied by the {role}." + (f" Note: {note}" if note else "")
        elif req["status"].startswith("pending_"):
            nxt = req["status"].split("_", 1)[1]
            msg = f"👍 {role} approved **{req['action']}** — now waiting on the **{nxt}**."
        else:
            msg = f"**{req['action']}** status: {req['status']}."
        self.store.add_message(req["session_id"], "assistant", msg, self._now(),
                               meta={"request_id": req_id, "status": req["status"]})
        return req

    def history(self, session_id: str) -> list[dict]:
        return self.store.history(session_id)

    def pending(self, role: str) -> list[dict]:
        return self.store.pending_requests(role=roles_mod.normalize(role))

    def team_history(self, role: str, limit: int = 60) -> list[dict]:
        """Centralized team conversation history. Restricted to manager+ (staff
        only see their own chat)."""
        if not roles_mod.at_least(role, "manager"):
            return []
        return self.store.team_messages(limit)
