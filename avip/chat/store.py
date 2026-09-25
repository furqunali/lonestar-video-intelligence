"""Chat persistence — everything durably saved to SQLite (offline default).

Tables: sessions, messages, action_requests, approvals, memory. Stdlib sqlite3
(dependency-light, self-contained). Time is passed in by the caller (store-local),
never generated here, so results stay reproducible/testable.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    role       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    sender     TEXT NOT NULL,          -- user | assistant | system
    text       TEXT NOT NULL,
    meta       TEXT,                   -- json
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS action_requests (
    id         TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    action     TEXT NOT NULL,
    params     TEXT,                   -- json
    status     TEXT NOT NULL,          -- pending_manager|pending_director|approved|denied|executed|failed
    pending_roles TEXT,               -- json list of roles still required
    result     TEXT,                   -- json
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS approvals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    approver   TEXT NOT NULL,
    role       TEXT NOT NULL,
    decision   TEXT NOT NULL,          -- approve | deny
    note       TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, key)
);
CREATE INDEX IF NOT EXISTS ix_msg_sess ON messages(session_id);
CREATE INDEX IF NOT EXISTS ix_req_sess ON action_requests(session_id);
CREATE INDEX IF NOT EXISTS ix_req_status ON action_requests(status);
"""


def _j(v: Any) -> str:
    return json.dumps(v, default=str)


def _loads(v):
    if not v:
        return None
    try:
        return json.loads(v)
    except Exception:
        return v


class ChatStore:
    def __init__(self, db_path: str | Path = "data/chat.db"):
        self.db_path = str(db_path)
        p = Path(self.db_path)
        if p.parent and str(p.parent) not in ("", "."):
            p.parent.mkdir(parents=True, exist_ok=True)
        self._c = sqlite3.connect(self.db_path, check_same_thread=False)
        self._c.row_factory = sqlite3.Row
        self._c.executescript(_SCHEMA)
        self._c.commit()

    # ---- sessions ----
    def create_session(self, user_id: str, role: str, now: str) -> str:
        sid = uuid.uuid4().hex[:16]
        self._c.execute("INSERT INTO sessions VALUES (?,?,?,?)",
                        (sid, user_id, role, now))
        self._c.commit()
        return sid

    def get_session(self, session_id: str) -> dict | None:
        r = self._c.execute("SELECT * FROM sessions WHERE session_id=?",
                            (session_id,)).fetchone()
        return dict(r) if r else None

    # ---- messages ----
    def add_message(self, session_id: str, sender: str, text: str, now: str,
                    meta: dict | None = None) -> int:
        cur = self._c.execute(
            "INSERT INTO messages (session_id, sender, text, meta, created_at) "
            "VALUES (?,?,?,?,?)", (session_id, sender, text, _j(meta or {}), now))
        self._c.commit()
        return cur.lastrowid

    def history(self, session_id: str) -> list[dict]:
        rows = self._c.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["meta"] = _loads(d.get("meta"))
            out.append(d)
        return out

    def team_messages(self, limit: int = 60) -> list[dict]:
        """Centralized team conversation history — recent messages across ALL
        sessions, tagged with the user + role who owns each session."""
        rows = self._c.execute(
            "SELECT m.session_id, m.sender, m.text, m.created_at, s.user_id AS uid, "
            "s.role AS urole FROM messages m JOIN sessions s ON m.session_id=s.session_id "
            "ORDER BY m.id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ---- action requests ----
    def add_request(self, req_id: str, session_id: str, user_id: str, action: str,
                    params: dict, status: str, pending_roles: list[str], now: str) -> None:
        self._c.execute(
            "INSERT INTO action_requests (id, session_id, user_id, action, params, status, "
            "pending_roles, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (req_id, session_id, user_id, action, _j(params), status, _j(pending_roles), now))
        self._c.commit()

    def update_request(self, req_id: str, *, status: str | None = None,
                       pending_roles: list[str] | None = None,
                       result: Any = None, resolved_at: str | None = None) -> None:
        sets, params = [], []
        if status is not None:
            sets.append("status=?"); params.append(status)
        if pending_roles is not None:
            sets.append("pending_roles=?"); params.append(_j(pending_roles))
        if result is not None:
            sets.append("result=?"); params.append(_j(result))
        if resolved_at is not None:
            sets.append("resolved_at=?"); params.append(resolved_at)
        if not sets:
            return
        params.append(req_id)
        self._c.execute(f"UPDATE action_requests SET {','.join(sets)} WHERE id=?", params)
        self._c.commit()

    def get_request(self, req_id: str) -> dict | None:
        r = self._c.execute("SELECT * FROM action_requests WHERE id=?", (req_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["params"] = _loads(d.get("params")); d["result"] = _loads(d.get("result"))
        d["pending_roles"] = _loads(d.get("pending_roles")) or []
        return d

    def pending_requests(self, role: str | None = None) -> list[dict]:
        rows = self._c.execute(
            "SELECT * FROM action_requests WHERE status LIKE 'pending_%' ORDER BY created_at").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["params"] = _loads(d.get("params")); d["result"] = _loads(d.get("result"))
            d["pending_roles"] = _loads(d.get("pending_roles")) or []
            if role is None or role in d["pending_roles"]:
                out.append(d)
        return out

    # ---- approvals ----
    def add_approval(self, request_id: str, approver: str, role: str,
                     decision: str, note: str, now: str) -> None:
        self._c.execute(
            "INSERT INTO approvals (request_id, approver, role, decision, note, created_at) "
            "VALUES (?,?,?,?,?,?)", (request_id, approver, role, decision, note, now))
        self._c.commit()

    def approvals_for(self, request_id: str) -> list[dict]:
        return [dict(r) for r in self._c.execute(
            "SELECT * FROM approvals WHERE request_id=? ORDER BY id", (request_id,)).fetchall()]

    # ---- memory ----
    def set_memory(self, user_id: str, key: str, value: str, now: str) -> None:
        self._c.execute(
            "INSERT INTO memory (user_id, key, value, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (user_id, key, value, now))
        self._c.commit()

    def get_memory(self, user_id: str) -> dict[str, str]:
        rows = self._c.execute("SELECT key, value FROM memory WHERE user_id=?",
                               (user_id,)).fetchall()
        return {r["key"]: r["value"] for r in rows}

    def close(self) -> None:
        try:
            self._c.close()
        except Exception:
            pass
