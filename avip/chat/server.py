"""Zero-dependency chat-support server (stdlib http.server).

Serves the one-click widget at / and a small JSON REST API. Runs offline anywhere
Python runs — no FastAPI/Flask needed (swap one in for production if desired).

    python -m avip.chat.server           # then open http://localhost:8770

Endpoints:
    GET  /                      -> the widget
    POST /api/session           {user_id, role}            -> {session_id}
    POST /api/chat              {session_id, text}         -> {reply, suggestions, request}
    GET  /api/history?session_id=..                        -> [messages]
    GET  /api/pending?role=..                              -> [pending requests]
    POST /api/approve           {request_id, approver_id, role, decision, note}
    GET  /api/memory?user_id=..                            -> {memory}
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from avip.chat.store import ChatStore
from avip.chat.actions import ChatContext
from avip.chat.service import ChatService
from avip.analytics.transactions import Transaction, TransactionStore
from avip.chat.approvals import ApprovalError

ROOT = Path(__file__).resolve().parents[2]
WIDGET = Path(__file__).resolve().parent / "widget.html"
DATA = ROOT / "data"
CDT = timezone(timedelta(hours=-6))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# rich incident detail the assistant answers from (derived from verified findings)
INCIDENTS = [
    {"slug": "5nov_cash", "title": "Cash theft — Register 1 (5 Nov)", "category": "Cash theft",
     "when": "05 Nov 2024 07:09 AM", "where": "Register 1 (C3)", "cashier": "Cashier (Reg 1)",
     "amount": 0.0, "finding": "Hands in the OPEN cash drawer, bills removed — no customer, POS idle (no sale).",
     "frames": ["key"]},
    {"slug": "12nov_cash", "title": "Cash theft — Register 1 (12 Nov)", "category": "Cash theft",
     "when": "12 Nov 2024 07:13 AM", "where": "Register 1 (C3)", "cashier": "Cashier (Reg 1)",
     "amount": 0.0, "finding": "Loose cash counted at the open drawer — no customer, POS idle (no sale).",
     "frames": ["key"]},
    {"slug": "jordan_cancel", "title": "Collusion void — Jordan Lee", "category": "Collusion void",
     "when": "08 Nov 2024 05:36 PM", "where": "Register 2 (C2)", "cashier": "JORDAN LEE", "amount": 18.86,
     "finding": ("Sale CANCELLED -$18.86 (5 items: Pepsi 1L x2, Cheetos, Pistachios, Kool-Aid + $0.81 tax). "
                 "No cash collected. Cashier–customer hand contact, then the receipt dropped in the bin."),
     "frames": ["receipt", "key", "handoff", "dustbin"]},
    {"slug": "27jan_steal", "title": "Shoplifting — 27 Jan (group)", "category": "Organized shoplifting",
     "when": "27 Jan 2024 08:06 PM", "where": "Sales floor (IP Cam 16/22)", "cashier": "", "amount": 0.0,
     "finding": "4-person group: arrive (parking) → enter together → gather at cooler → grab & conceal with shielding.",
     "frames": ["entry", "entry2", "suspect", "key"]},
    {"slug": "14may_steal", "title": "Shoplifting — 14 May (group)", "category": "Organized shoplifting",
     "when": "14 May 2024 04:41 PM", "where": "Sales floor (IP Cam 15/16)", "cashier": "", "amount": 0.0,
     "finding": ">=5-person group: parking arrival → cooler drinks/case → merchandise concealed into clothing; a gloved accomplice.",
     "frames": ["entry", "suspect", "key"]},
]
_SAFE = None


def _seed_transactions(ts: TransactionStore):
    if ts.all():
        return
    ts.add_many([
        Transaction("0008-C2-3636162", "0008", "Register 2", "JORDAN LEE", 18.86,
                    "cancel", datetime(2024, 11, 8, 17, 36, tzinfo=CDT)),
        Transaction("0008-C3-05nov", "0008", "Register 1", "CASHIER (Reg 1)", 0.0,
                    "no_sale", datetime(2024, 11, 5, 7, 9, tzinfo=CDT)),
        Transaction("0008-C3-12nov", "0008", "Register 1", "CASHIER (Reg 1)", 0.0,
                    "no_sale", datetime(2024, 11, 12, 7, 13, tzinfo=CDT)),
    ])


def _export_csv(params) -> str:
    """Real, safe executor for the export_data action (runs on approval)."""
    out = ROOT / "reports" / "analytics" / "transactions_export.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = TransactionStore(DATA / "transactions.db").all()
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["tx_id", "location_id", "register", "cashier", "amount", "tx_type", "ts"])
        for r in rows:
            w.writerow([r["tx_id"], r["location_id"], r["register"], r["cashier"],
                        r["amount"], r["tx_type"], r["ts"]])
    return f"exported {len(rows)} transactions -> {out.name}"


def build_service() -> ChatService:
    DATA.mkdir(parents=True, exist_ok=True)
    ts = TransactionStore(DATA / "transactions.db"); _seed_transactions(ts)
    analytics = {}
    ajson = ROOT / "reports" / "analytics" / "analytics.json"
    if ajson.exists():
        try:
            analytics = json.loads(ajson.read_text())
        except Exception:
            analytics = {}
    report_url = r"G:\Shared drives\4. AP\lonestar-video-intelligence\01_Director_Report"
    ctx = ChatContext(transaction_store=ts, transactions=ts_transactions(ts),
                      analytics=analytics, incidents=INCIDENTS,
                      report_url=report_url, executors={"export_data": _export_csv})
    return ChatService(ChatStore(DATA / "chat.db"), ctx, now)


def ts_transactions(ts: TransactionStore):
    """Rebuild Transaction objects from the store rows for the risk engine."""
    out = []
    for r in ts.all():
        try:
            out.append(Transaction(r["tx_id"], r["location_id"], r["register"], r["cashier"],
                                   r["amount"], r["tx_type"], datetime.fromisoformat(r["ts"])))
        except Exception:
            continue
    return out


SVC = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):        # quiet
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                html = WIDGET.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers(); self.wfile.write(html); return
            if u.path == "/evidence":
                import re as _re
                slug = q.get("slug", [""])[0]; name = q.get("name", [""])[0]
                if not _re.fullmatch(r"[a-z0-9_]{1,40}", slug or "") or \
                   not _re.fullmatch(r"[a-z0-9_]{1,20}", name or ""):
                    return self._json({"error": "bad params"}, 400)   # blocks path traversal
                p = ROOT / "reports" / "incident_analysis" / slug / f"{name}_after.jpg"
                if not p.exists():
                    return self._json({"error": "not found"}, 404)
                data = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "max-age=3600")
                self.end_headers(); self.wfile.write(data); return
            if u.path == "/api/history":
                return self._json(SVC.history(q.get("session_id", [""])[0]))
            if u.path == "/api/pending":
                return self._json(SVC.pending(q.get("role", ["staff"])[0]))
            if u.path == "/api/team":
                return self._json(SVC.team_history(q.get("role", ["staff"])[0]))
            if u.path == "/api/memory":
                return self._json(SVC.memory.get(q.get("user_id", [""])[0]))
            self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def do_POST(self):
        u = urlparse(self.path); b = self._body()
        try:
            if u.path == "/api/session":
                sid = SVC.start_session(b.get("user_id", "guest"), b.get("role", "staff"))
                return self._json({"session_id": sid})
            if u.path == "/api/chat":
                return self._json(SVC.handle_message(b.get("session_id", ""), b.get("text", "")))
            if u.path == "/api/approve":
                try:
                    req = SVC.decide(b.get("request_id", ""), b.get("approver_id", "?"),
                                     b.get("role", "staff"), b.get("decision", "approve"),
                                     b.get("note", ""))
                    return self._json(req)
                except ApprovalError as e:
                    return self._json({"error": str(e)}, 400)
            self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)


def main(host="127.0.0.1", port=8770):
    global SVC
    SVC = build_service()
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"Chat support running -> http://{host}:{port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    import sys
    _host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    _port = int(sys.argv[2]) if len(sys.argv) > 2 else 8770
    main(_host, _port)
