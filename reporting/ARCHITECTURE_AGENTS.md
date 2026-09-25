# Agentic architecture — Orchestrator + parallel domain agents + verification

Decided 14 Sep 2026 (Furqan approved). For the video-intelligence platform we use
a **hybrid**: heavy CV stays deterministic (reproducible for the blind test),
LLM agents sit at the orchestration / interpretation / verification / reporting
layer. Single agent only for trivial one-offs.

## Two layers (keep separate)
1. **Deterministic CV core** — YOLO detect, IoU track, OCR, health, heatmap, risk.
   Pure Python, reproducible (same input → same result — non-negotiable for a blind
   test). Packaged in **Docker**, scaled across stores/cameras with **Kubernetes**
   (nightly batch). LLM never does pixel detection.
2. **Agent layer** (LLM) — plan, dispatch, interpret, verify, synthesize report.

## Flow
```
                 ORCHESTRATOR (domain-expert)
     intake_clip.py → classify → dispatch → assemble → publish
        │            │              │            │
   PARALLEL ▼        ▼              ▼            ▼         (concurrent = fast)
  Register-LP     POS-Void      Floor-Shoplift   [+ Health, + Heatmap, + Counting]
   agent           agent          agent
        │  each wraps the deterministic CV core (Docker)  │
        └───────────────────┬────────────────────────────┘
                            ▼
        🔴 VERIFICATION / ADVERSARIAL agent  (INDEPENDENT — mandatory)
          • re-check every finding against the pixels/OCR
          • integrity: no hardcoding, no over-claim
          • reconcile numbers (e.g. items+tax == printed total)
          • anything that fails → HITL queue (human review, M9)
                            ▼
             SYNTHESIS agent → consolidated director HTML + shared-drive publish
```

## Why (vs single agent)
- **Speed** — N clips / N dimensions run in parallel, not sequentially.
- **Quality** — each domain agent is specialised (register vs floor vs POS).
- **Credibility** — an INDEPENDENT verification agent catches over-claims a
  single self-reviewing agent misses. This is the most important agent for the
  blind test / camera-team scrutiny.

## Caveats (be honest)
- Multi-agent = more cost/complexity; for 2–5 clips a well-structured single
  pipeline + one verification pass is enough. Full orchestration pays off at
  SCALE (many stores/cameras, audits).
- Keep CV deterministic; do not let an LLM do pixel detection (kills reproducibility).
- Do NOT add facial recognition / LPR (privacy/legal; management-gated).

## Where the code lives
- Deterministic core: `avip/cv/*`, `avip/analytics/*` (the 5 new features), `avip/pipeline.py`.
- Intake/classify: `reporting/intake_clip.py` (validated).
- Report build/publish: `build_consolidated.py` (+ `build_incident_report.py` data), `reporting/*`.
- This maps to milestones M8 (agents) / M9 (HITL + dashboard). Implement the LLM
  orchestrator with the Workflow tool when we move to scale.
```
