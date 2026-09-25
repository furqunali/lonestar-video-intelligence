"""Acceptance tests for the chat-support system: store, engine intents, approval
chain (Manager -> Director), permissions, memory, and end-to-end service flow."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from avip.chat.store import ChatStore
from avip.chat.engine import RuleEngine
from avip.chat.actions import ChatContext
from avip.chat.approvals import ApprovalEngine, ApprovalError
from avip.chat.service import ChatService
from avip.analytics.transactions import Transaction, TransactionStore

NOW = "2026-09-14T12:00:00"
def now():
    return NOW


def _ctx(tmp_path):
    txns = [
        Transaction("T1", "0008", "Register 2", "JORDAN LEE", 18.86, "cancel",
                    datetime(2024, 11, 8, 17, 36, tzinfo=timezone.utc)),
        Transaction("T2", "0008", "Register 1", "CASHIER", 0.0, "no_sale",
                    datetime(2024, 11, 5, 7, 9, tzinfo=timezone.utc)),
    ]
    ts = TransactionStore(tmp_path / "tx.db"); ts.add_many(txns)
    return ChatContext(transaction_store=ts, transactions=txns,
                       incidents=[{"slug": "jordan"}, {"slug": "5nov"}, {"slug": "12nov"}])


def _svc(tmp_path):
    return ChatService(ChatStore(tmp_path / "chat.db"), _ctx(tmp_path), now)


# ------------------------------- engine ---------------------------------- #
def test_engine_routes_intents():
    e = RuleEngine()
    assert e.respond("show me the incidents").action == "list_incidents"
    assert e.respond("what is the risk ranking").action == "get_risk_ranking"
    assert e.respond("camera health please").action == "get_camera_health"
    assert e.respond("publish the report to shared drive").action == "publish_shared_drive"
    assert e.respond("hi there").action is None            # greeting, no action


def test_engine_parses_search_params():
    r = RuleEngine().respond("search cashier JORDAN for void over 10")
    assert r.action == "search_transaction"
    assert r.params.get("cashier", "").upper().startswith("JORDAN")
    assert r.params.get("tx_type") == "void"
    assert r.params.get("min_amount") == 10.0


# ------------------------------- store ----------------------------------- #
def test_store_session_message_memory(tmp_path):
    st = ChatStore(tmp_path / "c.db")
    sid = st.create_session("u1", "staff", NOW)
    st.add_message(sid, "user", "hello", NOW)
    assert len(st.history(sid)) == 1
    st.set_memory("u1", "name", "Furqan", NOW)
    st.set_memory("u1", "name", "Furqan Ali", NOW)     # upsert
    assert st.get_memory("u1")["name"] == "Furqan Ali"


# ---------------------------- approval chain ----------------------------- #
def test_read_action_executes_immediately(tmp_path):
    svc = _svc(tmp_path)
    sid = svc.start_session("u1", "staff")
    out = svc.handle_message(sid, "show incidents")
    assert out["request"]["status"] == "executed"
    assert "incident" in out["reply"].lower()


def test_manager_director_chain(tmp_path):
    svc = _svc(tmp_path)
    sid = svc.start_session("mgr1", "manager")
    out = svc.handle_message(sid, "publish the report to the shared drive")
    req = out["request"]
    assert req["status"] == "pending_manager"
    # manager approves -> now pending director
    req = svc.decide(req["id"], "mgr1", "manager", "approve")
    assert req["status"] == "pending_director"
    # director approves -> executed
    req = svc.decide(req["id"], "dir1", "director", "approve")
    assert req["status"] == "executed"
    # outcome posted back into the original chat
    texts = " ".join(m["text"] for m in svc.history(sid))
    assert "executed" in texts.lower()


def test_deny_stops_the_chain(tmp_path):
    svc = _svc(tmp_path)
    sid = svc.start_session("mgr1", "manager")
    req = svc.handle_message(sid, "publish to shared drive")["request"]
    req = svc.decide(req["id"], "mgr1", "manager", "deny", note="not now")
    assert req["status"] == "denied"


def test_permission_blocks_low_role(tmp_path):
    svc = _svc(tmp_path)
    sid = svc.start_session("u1", "staff")
    out = svc.handle_message(sid, "generate the report")   # needs >= manager to request
    assert out["reply"].startswith("⛔")
    assert out.get("request") is None


def test_director_can_approve_manager_step(tmp_path):
    svc = _svc(tmp_path)
    sid = svc.start_session("mgr1", "manager")
    req = svc.handle_message(sid, "publish to shared drive")["request"]
    # a director (higher role) may clear the manager step, then the director step
    req = svc.decide(req["id"], "dir1", "director", "approve")
    assert req["status"] == "pending_director"
    req = svc.decide(req["id"], "dir1", "director", "approve")
    assert req["status"] == "executed"


# ------------------------------- memory ---------------------------------- #
def test_memory_learning(tmp_path):
    svc = _svc(tmp_path)
    sid = svc.start_session("u1", "staff")
    out = svc.handle_message(sid, "remember my name is Furqan")
    assert "remember" in out["reply"].lower()
    assert svc.memory.get("u1").get("name") == "Furqan"


def test_pending_visible_to_approver(tmp_path):
    svc = _svc(tmp_path)
    sid = svc.start_session("mgr1", "manager")
    svc.handle_message(sid, "publish to shared drive")
    assert len(svc.pending("manager")) == 1
    assert len(svc.pending("staff")) == 0            # staff sees none


# ------------------ everyone-can-ask: summary / evidence ----------------- #
def test_summary_and_evidence_actions(tmp_path):
    svc = _svc(tmp_path)
    sid = svc.start_session("cam1", "staff")
    out = svc.handle_message(sid, "give me a summary")
    assert out["request"]["status"] == "executed"
    assert "summary" in out["reply"].lower()
    out2 = svc.handle_message(sid, "show me the evidence")
    assert out2["request"]["action"] == "get_evidence"
    assert out2["request"]["status"] == "executed"


def test_engine_routes_summary_and_evidence():
    e = RuleEngine()
    assert e.respond("can you give me a summary").action == "get_summary"
    assert e.respond("where is the evidence footage").action == "get_evidence"


# --------------------- centralized team history -------------------------- #
def test_team_history_role_gated(tmp_path):
    svc = _svc(tmp_path)
    s1 = svc.start_session("cam1", "staff"); svc.handle_message(s1, "summary")
    s2 = svc.start_session("cam2", "staff"); svc.handle_message(s2, "risk ranking")
    # staff cannot see the centralized team history; manager+ can
    assert svc.team_history("staff") == []
    team = svc.team_history("manager")
    assert len(team) >= 2
    assert any(m.get("uid") == "cam1" for m in team) and any(m.get("uid") == "cam2" for m in team)
