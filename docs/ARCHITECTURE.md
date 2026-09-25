# Architecture

*Lone Star — AI Video Intelligence & Operational Platform.*
Offline-first, CPU-only, store-local-time, no secrets in code. This document
describes how the system is put together, component by component.

> **Scope & safety.** Everything here operates on **exported MP4 files** (no live
> RTSP in the PoC) and on **synthetic sample data** in this public repository.
> Identity and grading are **gated** and non-biometric. No real footage, personal
> data or credentials are included.

---

## 1. Design principles

1. **Deterministic core, AI at the edges.** Detection uses a model (YOLOv8n); every
   downstream decision — zones, events, risk, grades — is deterministic, tested code.
   A model *enriches*; it never silently decides an outcome about a person.
2. **Offline & reproducible.** The pipeline and its 161 tests run with no network,
   no GPU and a local SQLite DB, so any reviewer can reproduce results.
3. **Store-local time everywhere.** All timestamps are timezone-aware
   (`America/Chicago`), normalized at ingest — no naive datetimes cross a boundary.
4. **Idempotent & self-healing.** Re-processing a clip never double-counts; corrupt
   clips are quarantined; transient failures retry with backoff.
5. **Human-in-the-loop.** Incidents are *drafted* by the system and *confirmed* by a
   person. Grades that could affect a real employee are never auto-published.
6. **Least authority.** The app reads/writes only inside one configured AI folder;
   untrusted paths/filenames are sanitized and never passed to a shell.

---

## 2. Pipeline stages

| # | Stage | Module(s) | Responsibility |
|---|-------|-----------|----------------|
| M0 | Foundation | `avip/common/` | Validated config, structured logging, time, paths, retry, security |
| M1 | Ingest | `avip/ingest/` | Discover DVR dumps, decode (PyAV), sample frames, orchestrate a run |
| M2 | Camera health | `avip/cv/health.py` | Blur / darkness / tamper (SSIM) / clock-drift checks per frame |
| M3 | Detect + track + zones | `avip/cv/detect.py`, `track.py`, `zones.py` | YOLOv8n person detection, ByteTrack IDs, polygon zone membership |
| M4 | Markers | `avip/cv/markers.py` | ArUco decode + multi-frame vote (register/badge tags) |
| M5 | Events | `avip/events/` | Canonical event schema, builder, idempotent store |
| M6 | Identity | `avip/grading/identity.py` | Non-biometric, gated resolution (never a guess) |
| M7 | Grading | `avip/grading/` | Deterministic operational grades against a rubric + calibration gate |
| — | Analytics | `avip/analytics/` | POS-exception risk scoring, multi-store rollup, heatmaps, counting |
| — | Reporting | `reporting/`, `build_consolidated.py` | Consolidated HTML director report + evidence frames |
| — | Chat | `avip/chat/` | In-report assistant ("Stella") over the events knowledge base |
| — | Notify | `avip/notify/` | Email delivery to a fixed recipient list (secrets from env only) |

### Data flow
`FreeCam MP4 → ingest.decode → sampler → cv.health → cv.detect → cv.track →
cv.zones → cv.markers → events.builder → events.store → analytics.risk →
reporting.build_consolidated → (human review) + chat`

---

## 3. Event model (the contract)

`avip/events/schema.py` defines the **canonical event** — the stable contract every
stage agrees on. Events are timezone-aware, validated (Pydantic), and written to the
store idempotently (a natural key prevents duplicates on re-runs). Because the schema
is the contract, the storage backend (SQLite ↔ PostgreSQL/TimescaleDB) and the
orchestration (batch ↔ future streaming) can change without touching producers.

## 4. Storage

- **Dev/CI:** a local **SQLite** file — zero setup, fully offline.
- **Production path:** **PostgreSQL + TimescaleDB** (time-series events) + **MinIO**
  (evidence objects), brought up via `docker-compose.yml`.
- The ORM/schema (`avip/db/`) is portable across both; Timescale DDL is additive.

## 5. Identity & grading — the gates

Identity resolution (M6) is **non-biometric** — it uses ArUco badge tags and shift
rosters, never face recognition or LPR. It returns a result **only** when the
evidence is unambiguous; otherwise it abstains (never a guess). Grading (M7) is a
**deterministic rubric** (`config/rubric.yaml`) and is guarded by a **calibration
gate**: no grade derived from placeholder/sample data may ever be published, and a
real roster + labelled golden-set must replace the sample fixtures before any grade
can affect a real person.

## 6. Security & resilience

- **Path sandbox** (`avip/common/paths.py`, `avip/security/sanitize.py`): every
  external path/filename is validated and confined to one configured AI root.
- **Tamper-evidence** (`avip/security/integrity.py`): a hash manifest of code+config
  from the reviewed commit; the pipeline can refuse to start if a file changed.
- **Quarantine**: corrupt/partial clips are isolated, never half-processed.
- **Retry/backoff** (`avip/common/retry.py`) for transient failures.
- **Backups** (`avip/security/backup.py`): scheduled DB + config snapshots.
- **Secrets**: environment/`.env` only — never in code or git (`.env` is ignored).

## 7. Run modes

`config runtime.mode`:
- **`test`** (this PC): incident alarm = beep + on-screen incident + clip.
- **`live`** (store server): beep + clip on the store LCD only — never dashboards
  or reports on the LCD. Reports/HTML always go to the shared drive for the fixed
  recipient list only.

## 8. Testing strategy

- **161 tests**, offline and deterministic, using **synthetic media** (`tests/synth.py`)
  — no real DVR dumps required.
- Coverage spans every stage: config, paths, retry, freshness, ingest, health,
  detect/track/zones, markers, events schema, identity (+ gating flag), grading,
  analytics, reporting, chat, quarantine, security, email.
- The single real-YOLO test is marked `yolo` and **self-skips** when weights/network
  are unavailable, so CI stays green offline.
- CI (`.github/workflows/tests.yml`) runs the whole suite on every push.

## 9. Roadmap — Phase 2 (deferred, pending management approval)

The architecture is intentionally ready for, but does not yet include:
- **24/7 live multi-camera RTSP** ingestion (per-frame health checks are already
  stream-agnostic and carry over unchanged).
- **Kafka** event streaming (same event schema) instead of the batch store.
- **Distributed cloud scaling** across all sites (prod already targets
  Postgres+Timescale+MinIO).

This is an extension of the current design, not a rewrite.
