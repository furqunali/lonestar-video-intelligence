-- Production DDL for PostgreSQL + TimescaleDB (spec §8).
-- Loaded by docker-compose into the timescaledb container on first start.
-- The offline SQLite path uses avip/db/models.py (portable) instead; the
-- create_hypertable() calls below are a Timescale-only optimisation.

CREATE TABLE IF NOT EXISTS stores    (location_id TEXT PRIMARY KEY, name TEXT, tz TEXT, hours JSONB);
CREATE TABLE IF NOT EXISTS cameras   (camera_id TEXT PRIMARY KEY, location_id TEXT, zone_map JSONB, model TEXT);
CREATE TABLE IF NOT EXISTS employees (employee_id TEXT PRIMARY KEY, role TEXT, role_colour TEXT,
                        location_id TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS markers   (marker_code TEXT PRIMARY KEY, employee_id TEXT REFERENCES employees,
                        active BOOLEAN DEFAULT TRUE, issued_at TIMESTAMPTZ);  -- reissue-safe
CREATE TABLE IF NOT EXISTS shifts    (id BIGSERIAL, employee_id TEXT, location_id TEXT, zone TEXT,
                        start_ts TIMESTAMPTZ, end_ts TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS attendance(id BIGSERIAL, employee_id TEXT, location_id TEXT, work_date DATE,
                        clock_in TIMESTAMPTZ, clock_out TIMESTAMPTZ);  -- biometric machine export

CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY, schema_version TEXT, location_id TEXT, camera_id TEXT,
  ts_start TIMESTAMPTZ NOT NULL, ts_end TIMESTAMPTZ, event_type TEXT, track_id INT,
  marker_code TEXT, zone TEXT, dwell_seconds DOUBLE PRECISION, confidence DOUBLE PRECISION,
  camera_health JSONB, employee_id TEXT, evidence_uri TEXT, triage_status TEXT);
SELECT create_hypertable('events','ts_start', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS grades (
  id BIGSERIAL, location_id TEXT, employee_id TEXT, grade_date DATE, role TEXT,
  metric_values JSONB, weighted_score DOUBLE PRECISION, letter CHAR(1),
  gate_result JSONB, rubric_version TEXT, contributing_event_ids TEXT[],
  computed_at TIMESTAMPTZ, published BOOLEAN DEFAULT FALSE);
SELECT create_hypertable('grades','computed_at', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS hitl_queue (id BIGSERIAL, kind TEXT, ref_id TEXT, severity TEXT, payload JSONB,
        status TEXT DEFAULT 'open', assigned_to TEXT, sla_due TIMESTAMPTZ, decided_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS dead_letter (id BIGSERIAL, raw JSONB, error TEXT, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS audit_log   (id BIGSERIAL, actor TEXT, action TEXT, ref_id TEXT, detail JSONB,
                          ts TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS pipeline_runs (id BIGSERIAL, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
        status TEXT, dumps_processed INT, events_written INT, errors INT, last_processed TIMESTAMPTZ);
