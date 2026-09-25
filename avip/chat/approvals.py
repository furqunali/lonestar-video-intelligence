"""Approval workflow — Manager -> Director sign-off before a sensitive action runs.

Flow:
  request(...) -> if the action needs no approvals, execute immediately (status
  'executed'); otherwise create a request in status 'pending_<first role>' with the
  ordered chain of required roles.
  decide(...) -> the next required approver approves (advance the chain) or denies
  (status 'denied'). When the chain is empty, the handler executes -> 'executed'
  (or 'failed' on error). Everything is persisted via ChatStore.
"""
from __future__ import annotations

import uuid

from avip.chat import roles as roles_mod
from avip.chat.actions import get_action, ChatContext, REGISTRY
from avip.chat.store import ChatStore


class ApprovalError(Exception):
    pass


class ApprovalEngine:
    def __init__(self, store: ChatStore, ctx: ChatContext, now_fn):
        """now_fn() -> ISO timestamp string (store-local); injected for reproducibility."""
        self.store = store
        self.ctx = ctx
        self._now = now_fn

    # ------------------------------------------------------------------ #
    def request(self, session_id: str, user_id: str, user_role: str,
                action_name: str, params: dict | None = None) -> dict:
        action = get_action(action_name)
        if action is None:
            raise ApprovalError(f"unknown action: {action_name}")
        if not roles_mod.at_least(user_role, action.min_role):
            raise ApprovalError(
                f"'{action_name}' requires role >= {action.min_role} (you are {user_role})")

        params = params or {}
        req_id = uuid.uuid4().hex[:16]
        chain = list(action.approvals)

        if not chain:                                   # read-only -> run now
            self.store.add_request(req_id, session_id, user_id, action_name, params,
                                   "approved", [], self._now())
            return self._execute(req_id)

        status = f"pending_{chain[0]}"
        self.store.add_request(req_id, session_id, user_id, action_name, params,
                               status, chain, self._now())
        return self.store.get_request(req_id)

    # ------------------------------------------------------------------ #
    def decide(self, req_id: str, approver_id: str, approver_role: str,
               decision: str, note: str = "") -> dict:
        req = self.store.get_request(req_id)
        if req is None:
            raise ApprovalError(f"unknown request: {req_id}")
        if not req["status"].startswith("pending_"):
            raise ApprovalError(f"request already resolved ({req['status']})")

        pending = list(req.get("pending_roles") or [])
        next_role = pending[0] if pending else None
        approver_role = roles_mod.normalize(approver_role)
        # a higher role may act for a lower one (director can approve a manager step)
        if next_role is None or not roles_mod.at_least(approver_role, next_role):
            raise ApprovalError(
                f"this step needs {next_role}; {approver_role} cannot approve it")

        decision = decision.strip().lower()
        self.store.add_approval(req_id, approver_id, approver_role, decision, note, self._now())

        if decision == "deny":
            self.store.update_request(req_id, status="denied", pending_roles=[],
                                      resolved_at=self._now())
            return self.store.get_request(req_id)

        pending.pop(0)                                   # this role approved
        if pending:
            self.store.update_request(req_id, status=f"pending_{pending[0]}",
                                      pending_roles=pending)
            return self.store.get_request(req_id)

        self.store.update_request(req_id, status="approved", pending_roles=[])
        return self._execute(req_id)

    # ------------------------------------------------------------------ #
    def _execute(self, req_id: str) -> dict:
        req = self.store.get_request(req_id)
        action = get_action(req["action"])
        try:
            result = action.handler(req.get("params") or {}, self.ctx)
            self.store.update_request(req_id, status="executed", result=result,
                                      resolved_at=self._now())
        except Exception as e:                           # fail-soft, never crash chat
            self.store.update_request(req_id, status="failed",
                                      result={"error": str(e)}, resolved_at=self._now())
        return self.store.get_request(req_id)
