"""Portable database schema (SQLAlchemy Core).

One table definition set that works on BOTH the offline SQLite default and the
production PostgreSQL + TimescaleDB stack. JSONB/array columns use SQLAlchemy's
portable JSON type; the Timescale ``create_hypertable`` calls in schema.sql are
a production-only optimisation and are not required for correctness.

Schema mirrors spec §8 (Database Schema DDL).
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine, make_url

metadata = MetaData()

stores = Table(
    "stores", metadata,
    Column("location_id", String, primary_key=True),
    Column("name", Text),
    Column("tz", Text),
    Column("hours", JSON),
)

cameras = Table(
    "cameras", metadata,
    Column("camera_id", String, primary_key=True),
    Column("location_id", String),
    Column("zone_map", JSON),
    Column("model", Text),
)

employees = Table(
    "employees", metadata,
    Column("employee_id", String, primary_key=True),
    Column("role", Text),
    Column("role_colour", Text),
    Column("location_id", Text),
    Column("status", Text),
)

markers = Table(
    "markers", metadata,
    Column("marker_code", String, primary_key=True),
    Column("employee_id", String),
    Column("active", Boolean, default=True),
    Column("issued_at", DateTime(timezone=True)),
)

shifts = Table(
    "shifts", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("employee_id", String),
    Column("location_id", String),
    Column("zone", Text),
    Column("start_ts", DateTime(timezone=True)),
    Column("end_ts", DateTime(timezone=True)),
)

attendance = Table(
    "attendance", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("employee_id", String),
    Column("location_id", String),
    Column("work_date", DateTime(timezone=True)),
    Column("clock_in", DateTime(timezone=True)),
    Column("clock_out", DateTime(timezone=True)),
)

events = Table(
    "events", metadata,
    Column("event_id", String, primary_key=True),   # deterministic hash => idempotent
    Column("schema_version", Text),
    Column("location_id", String),
    Column("camera_id", String),
    Column("ts_start", DateTime(timezone=True), nullable=False),
    Column("ts_end", DateTime(timezone=True)),
    Column("event_type", Text),
    Column("track_id", Integer),
    Column("marker_code", Text),
    Column("zone", Text),
    Column("dwell_seconds", Float),
    Column("confidence", Float),
    Column("camera_health", JSON),
    Column("employee_id", Text),
    Column("evidence_uri", Text),
    Column("triage_status", Text),
)

grades = Table(
    "grades", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("location_id", String),
    Column("employee_id", String),
    Column("grade_date", DateTime(timezone=True)),
    Column("role", Text),
    Column("metric_values", JSON),
    Column("weighted_score", Float),
    Column("letter", String),
    Column("gate_result", JSON),
    Column("rubric_version", Text),
    Column("contributing_event_ids", JSON),   # TEXT[] on Postgres; JSON is portable
    Column("computed_at", DateTime(timezone=True)),
    Column("published", Boolean, default=False),
)

hitl_queue = Table(
    "hitl_queue", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("kind", Text),
    Column("ref_id", Text),
    Column("severity", Text),
    Column("payload", JSON),
    Column("status", Text, default="open"),
    Column("assigned_to", Text),
    Column("sla_due", DateTime(timezone=True)),
    Column("decided_at", DateTime(timezone=True)),
)

dead_letter = Table(
    "dead_letter", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("raw", JSON),
    Column("error", Text),
    Column("created_at", DateTime(timezone=True)),
)

audit_log = Table(
    "audit_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("actor", Text),
    Column("action", Text),
    Column("ref_id", Text),
    Column("detail", JSON),
    Column("ts", DateTime(timezone=True)),
)

pipeline_runs = Table(
    "pipeline_runs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("status", Text),
    Column("dumps_processed", Integer, default=0),
    Column("events_written", Integer, default=0),
    Column("errors", Integer, default=0),
    Column("last_processed", DateTime(timezone=True)),
)


def make_engine(url: str) -> Engine:
    """Create an Engine. For a sqlite file URL, ensure the parent dir exists."""
    u = make_url(url)
    if u.get_backend_name() == "sqlite" and u.database and u.database != ":memory:":
        Path(u.database).resolve().parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, future=True)


def init_db(engine: Engine) -> None:
    """Create all tables if absent (offline SQLite path / first run)."""
    metadata.create_all(engine)
