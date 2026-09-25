# Changelog

All notable changes to this project are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); this is a sanitized public PoC.

## [0.1.0] — 2026-09-25

First public (sanitized, review-only) release of the offline video-intelligence PoC.

### Highlights
- **End-to-end offline pipeline** M0–M7: ingest (PyAV) → camera health → YOLOv8n
  detection + ByteTrack tracking → polygon zones → ArUco identity (gated,
  non-biometric) → canonical event store → POS-exception risk scoring → consolidated
  HTML director report + chat assistant.
- **161 automated tests**, offline & deterministic (synthetic media), green in CI.
- **Analytics**: risk matrix, multi-store rollup, camera-health-plus, heatmaps,
  transaction search; **Robbery / hold-up** incident category.
- **Safety & resilience**: idempotent event store, corrupt-clip quarantine,
  retry-with-backoff, tamper-evident integrity manifest, path sandboxing.
- **Docs**: architecture guide, sample director-report dashboard (synthetic),
  security policy.

### Engineering / release
- GitHub Actions **Tests** workflow runs the full suite on every push.
- Dockerfile (chat service) + `docker-compose.yml` for the production path
  (Postgres + TimescaleDB + MinIO). Container images are kept **private**,
  consistent with the review-only license.

### Security / sanitization
- No real footage, credentials, personal data, or production config in the repo.
- All names, stores, incidents and emails are fictitious samples.
- Published with a fresh history; secrets were never committed.
