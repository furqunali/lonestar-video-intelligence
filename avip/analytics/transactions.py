"""POS transaction record + transaction-indexed SQLite store (feature 5).

The incident analyzer OCRs the on-screen receipt (cancel/void, cashier, amount).
This module gives those readings a durable, searchable home — the offline
equivalent of i3's PACDM text-insertion + iSearch "search by transaction". Uses
the stdlib ``sqlite3`` so it is dependency-light and self-contained; inserts are
idempotent (INSERT OR REPLACE on tx_id) so re-processing a clip never duplicates.

Nothing here is hardcoded from a filename — a Transaction is only ever built from
what the OCR/analysis actually read.
"""
from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

# Exception types we recognise (normal "sale" is not an exception).
EXCEPTION_TYPES = ("void", "cancel", "refund", "no_sale", "discount", "return")
ALL_TYPES = EXCEPTION_TYPES + ("sale",)

_AMOUNT_RE = re.compile(r"-?\d{1,6}(?:[.,]\d{2})?")


def parse_amount(value) -> float:
    """Coerce an OCR'd amount ('−18.86', '18,86', '$18.86', 18.86) to a float.

    Returns 0.0 for anything unparseable rather than raising — a bad OCR read
    must never crash the batch (fail-soft rule)."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        # reject NaN / +-Inf (a bad numeric read) rather than propagate it.
        return abs(float(value)) if math.isfinite(value) else 0.0
    m = _AMOUNT_RE.search(str(value).replace(",", "."))
    if not m:
        return 0.0
    try:
        v = abs(float(m.group(0)))
        return v if math.isfinite(v) else 0.0
    except ValueError:
        return 0.0


def normalize_type(value: str | None) -> str:
    """Map a free-text/OCR type to a canonical type; default 'sale'."""
    t = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "cancelled": "cancel", "canceled": "cancel", "voided": "void",
        "no_sale": "no_sale", "nosale": "no_sale", "refunded": "refund",
        "returned": "return",
    }
    t = aliases.get(t, t)
    return t if t in ALL_TYPES else "sale"


@dataclass
class Transaction:
    """One POS transaction (usually an exception) read from the receipt overlay."""
    tx_id: str
    location_id: str
    register: str
    cashier: str
    amount: float
    tx_type: str
    timestamp: datetime
    clip: str | None = None
    evidence_uri: str | None = None

    def __post_init__(self):
        # sanitize on construction so downstream (risk/rollup) is always clean
        self.amount = parse_amount(self.amount)
        self.tx_type = normalize_type(self.tx_type)
        self.cashier = (self.cashier or "UNKNOWN").strip().upper() or "UNKNOWN"
        self.register = (self.register or "?").strip()
        self.location_id = (self.location_id or "?").strip()

    @property
    def is_exception(self) -> bool:
        return self.tx_type in EXCEPTION_TYPES


_SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    tx_id        TEXT PRIMARY KEY,
    location_id  TEXT NOT NULL,
    register     TEXT,
    cashier      TEXT,
    amount       REAL,
    tx_type      TEXT,
    ts           TEXT NOT NULL,
    clip         TEXT,
    evidence_uri TEXT
);
CREATE INDEX IF NOT EXISTS ix_tx_cashier ON transactions(cashier);
CREATE INDEX IF NOT EXISTS ix_tx_type    ON transactions(tx_type);
CREATE INDEX IF NOT EXISTS ix_tx_loc     ON transactions(location_id);
"""


class TransactionStore:
    """Thin idempotent SQLite store + search over POS transactions."""

    def __init__(self, db_path: str | Path = "data/transactions.db"):
        self.db_path = str(db_path)
        p = Path(self.db_path)
        if p.parent and str(p.parent) not in ("", "."):
            p.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def add(self, tx: Transaction) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO transactions "
            "(tx_id, location_id, register, cashier, amount, tx_type, ts, clip, evidence_uri) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (tx.tx_id, tx.location_id, tx.register, tx.cashier, tx.amount,
             tx.tx_type, tx.timestamp.isoformat(), tx.clip, tx.evidence_uri),
        )
        self._conn.commit()

    def add_many(self, txns: Iterable[Transaction]) -> int:
        n = 0
        for tx in txns:
            try:
                self.add(tx)
                n += 1
            except Exception:  # fail-soft: one bad record never aborts the batch
                continue
        return n

    def search(self, *, cashier: str | None = None, register: str | None = None,
               tx_type: str | None = None, location_id: str | None = None,
               min_amount: float | None = None, exceptions_only: bool = False
               ) -> list[dict]:
        """Search-by-transaction (iSearch equivalent). All filters are optional."""
        clauses, params = [], []
        if cashier:
            clauses.append("cashier = ?"); params.append(cashier.strip().upper())
        if register:
            clauses.append("register = ?"); params.append(register.strip())
        if tx_type:
            clauses.append("tx_type = ?"); params.append(normalize_type(tx_type))
        if location_id:
            clauses.append("location_id = ?"); params.append(location_id.strip())
        if min_amount is not None:
            clauses.append("amount >= ?"); params.append(float(min_amount))
        if exceptions_only:
            clauses.append("tx_type IN (%s)" % ",".join("?" * len(EXCEPTION_TYPES)))
            params.extend(EXCEPTION_TYPES)
        sql = "SELECT * FROM transactions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY ts DESC"
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def all(self) -> list[dict]:
        return [dict(r) for r in
                self._conn.execute("SELECT * FROM transactions ORDER BY ts").fetchall()]

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
