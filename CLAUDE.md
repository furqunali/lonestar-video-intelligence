# CLAUDE.md — Master Operating Brief (Claude Code)

**Project:** Lone Star — AI Video Intelligence & Operational Platform
**Repo:** https://github.com/furqunali/lonestar-video-intelligence (private)
**Owner:** Furqan Ali — Senior AI Engineer, SLP Operations

You are building this platform. Work **autonomously, milestone by milestone**, reading
the documents in this repo. The human will give only short instructions.

---

## 1. Source of truth (read these first, in order)
1. **This file (`CLAUDE.md`)** — how to operate + the environment reality below.
2. **`docs/BUILD_SPEC.docx`** — full architecture, schemas, components, milestones (M0–M10), tests.
3. **`docs/DATA_REQUEST_FORM.docx`** — real values: sites, cameras, timezone.

> Where the spec and this file differ on **GPU** or **RTSP**, **this file wins.**

---

## 2. Machines & folders (Windows)
| Purpose | Location |
|---|---|
| **Code** (this git repo, where you build) | `C:\Users\Rauf\Desktop\SLP Projects All\lonestar-video-intelligence` |
| **Input video** (FreeCam MP4 exports, per site) | `G:\Shared drives\4. AP\lonestar-video-intelligence\incoming` |
| **Output reports** (team reads these) | `G:\Shared drives\4. AP\lonestar-video-intelligence\reports` |

- **Code stays on `C:` and in Git. Data stays on `G:` (the shared drive).**
  Because data lives outside the repo folder, it is never committed — keep it that way.
- In config YAML, write Windows paths with **forward slashes**, e.g.
  `G:/Shared drives/4. AP/lonestar-video-intelligence/incoming`.

---

## 3. Environment — read carefully (this changes what you build)
- **Normal PC, NO GPU.** Use the small model **`yolov8n` on CPU**. Do **not** require CUDA.
  This is fine: we process exported clips in an **overnight batch**, not in real time.
- **Video source: i3 International SRX-Pro DVRs, exported as MP4 via "FreeCam".**
  **There is NO RTSP stream.** Ingestion reads **MP4 files from the `incoming` folder**
  (one subfolder per site, e.g. `incoming\0008\`). Do **not** build RTSP/live streaming.
- **No DVR passwords are needed in the app** for the PoC — the camera team exports the
  MP4s manually; you only read files. Never put credentials in code or config.
- Store-local timezone is **America/Chicago (Central)**.
- Sites in scope: **0008 (Mesa Valero), 0025 (Polo Club), 0028 (Woodridge)** — 6 register cameras.

---

## 4. Golden rules (always)
1. Build in **milestone order M0 → M10** (spec §12). After each milestone, run its
   **acceptance tests** (spec §13). Move on only when tests pass.
2. **Agents never compute grades.** Grades come only from deterministic Python; the LLM
   only writes the report text from numbers already computed.
3. **Never commit secrets or data.** `.env`, `data/`, and any `*.mp4` are git-ignored.
4. **Config-driven:** cameras, zones, rubric, role→colour live in `config/*.yaml`.
5. **Idempotent:** re-running the same MP4 must not create duplicate events or grades.
6. **Store-local time:** all event timestamps in America/Chicago (never Pakistan +05:00).
7. Commit after each passing milestone with a clear message (e.g. `M3: detection + tracking + zones`).

---

## 5. The work loop (do this yourself — no need to ask between steps)
```
plan  ->  write code  ->  run it  ->  read the output yourself  ->  fix
      ->  run the milestone tests  ->  commit  ->  next milestone
```
The **tests are your success signal.** Keep looping until they pass.

---

## 6. Stop and ask the human ONLY when:
- A design decision the spec does not cover.
- An error you have tried to fix 2–3 different ways and still cannot resolve.
- Anything that would publish **real employee grades** or touch **real store credentials**.

Otherwise: keep going on your own.

---

## 7. First task
1. **M0** — scaffold the repo; bring up services with **docker-compose**
   (PostgreSQL+TimescaleDB, MinIO, FastAPI, Prefect). If Docker isn't available on this
   PC, set up a local Python env with a Postgres/SQLite fallback and say so.
2. Create the `config/*.yaml` files (cameras, rubric, roles, settings) with the folder
   paths from §2 and thresholds from the spec.
3. **M1 → M5** — ingest MP4 → camera health → detection/tracking → zones → events,
   using sample MP4s in `incoming\0008\` from **site 0008 first**.
4. After **M5**, stop and give a **short plain-language summary** of what works before
   starting grading (M6–M7), which needs the employee / roster / attendance data.

Keep everything simple and readable. Prefer clear code over clever code.
