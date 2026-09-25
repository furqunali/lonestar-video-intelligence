# i3International — Feature & Reports Gap Analysis (vs our project)

Sourced from i3International's own pages/manuals (Sep 2026). i3's marketing numbers
(98% counting, >90% void detection, 87% investigation-time cut) are vendor claims,
not verified specs. cmweb (i3care.i3international.com) is a per-tenant login portal,
not publicly browsable.

## What i3 offers (relevant modules)
- **Platform:** SRX-Pro (on-prem VMS/NVR, à-la-carte licensed modules: PACDM, LPR, Heatmap, iSearch, Video Analytics); **CMS / cmweb** cloud portal (SOC 2, no-VPN remote, audit trails, multi-site); **i3Ai / i3Ai Cloud** deep-learning engine (POS/access-control API integration); **Annexxus** cameras.
- **LP / POS (asset protection):**
  - **Smart-ER** (Exception-Based Reporting) — flags POS exceptions auto-paired with the video clip: unauthorized voids/cancels, excessive discounts, refund fraud, **sweethearting**, customer-not-present till ops, scan fraud, same-day returns; **risk matrix** (amount × frequency × cashier history × time-of-day); daily cloud reports + multi-location trends.
  - **PACDM** — POS/ATM/cash-drawer text-insertion overlay + transaction search.
  - **Trajectory anomaly**, cart-pushout/walk-out, theft-ring pattern, bottom-of-basket alerts.
- **People/business analytics:** people counting (entry/exit, peaks, avg visit), conversion rate (traffic÷POS), **heat mapping + region dwell**, queue mgmt, drive-thru timer, employee engagement, BI/forecast, store scorecard.
- **Security analytics:** loitering, obstruction/blocked-exit, **True View** (camera tamper/lens), facial matching, LPR/ANPR, slip/trip/fall, alarms & intelligent search, alert center.
- **Reports:** exception (video-paired), heat-map/traffic, people-count/conversion, drive-thru, trend/forecast, multi-location scorecards, audit trails, iSearch/PACDM transaction search.

## Gap analysis (have / partial / missing)
| i3 feature | Us | Priority | Effort (our offline YOLO/OpenCV/SQLite stack) |
|---|---|---|---|
| POS void/cancel detection | ✅ (OCR) | — | done |
| Auto-pair exception ↔ clip | ✅ (director report before/after) | — | done |
| Group/shoplifting/concealment/cooler | ✅ (differentiator) | — | done |
| POS text-insertion / transaction record (PACDM) | ~ (we OCR instead of ingest) | Med | Low–Med |
| Other POS exceptions (refund/discount/return/no-sale-drawer) | ~ (drawer motion only) | **High** | Med (OCR rules + drawer-without-sale) |
| **Risk matrix (amount×freq×cashier×time)** | ❌ | **High** | Low–Med (SQL over existing tables) |
| Search-by-transaction (iSearch) | ❌ | Med | Low (index in SQLite) |
| People counting (line-crossing) | ~ (detector+tracker exist) | Med | Low (counting line) |
| Conversion rate (traffic÷POS) | ❌ | Med | Low |
| Heat mapping / dwell | ~ (zone/dwell events) | Med | Low–Med (see HEATMAP_PLAN.md) |
| Camera tamper / True View | ~ (health check, had false-pos) | **High** | Low (blur+scene-change+luminance ensemble) |
| Loitering | ~ (dwell) | Med | Low (threshold) |
| Trajectory anomaly / walk-out | ❌ | Med | Med–High |
| Multi-store trend / scorecard | ~ (per-run report) | Med | Low–Med (SQLite rollup) |
| Health/uptime monitoring | ~ (per-clip) | Med | Low (persist + summary) |
| Facial recognition | ❌ | Low | High + privacy/legal — **recommend NOT** |
| LPR/ANPR | ❌ | Low | needs plate cams — out of scope |
| Slip/trip/fall | ❌ | Low | pose est., heavy CPU |
| Cloud portal / no-VPN | ❌ by design | Low | offline = our positioning |

## TOP 5 credible features to add (best value / effort)
1. **POS exception risk-scoring engine (risk matrix).** We already OCR cashier+amount+void → add a SQL scoring pass (amount × cashier void-frequency × time-of-day) so the report RANKS incidents by risk. Mirrors i3 Smart-ER's headline. Highest value, low effort.
2. **Line-crossing people counting + conversion rate.** Add a virtual counting line to the IoU tracker; divide daily traffic by POS transactions → conversion. Turns LP tool into BI tool i3 charges extra for.
3. **Spatial heat map / dwell overlay.** Reuses existing detections (see HEATMAP_PLAN.md). Near-zero extra compute.
4. **Hardened camera-tamper / health module.** Replace the false-positive-prone TAMPER check with an ensemble (frame-diff variance + Laplacian blur + luminance drop); persist uptime. Fixes a known real-footage bug + adds i3 "True View" equivalent.
5. **Transaction-indexed search + multi-store rollup report.** Store each OCR'd transaction (time/register/cashier/amount/type/clip-offset) in SQLite → cross-store aggregate HTML (exceptions per store/cashier, trend by date). Gives i3's iSearch/PACDM + scorecard, fully offline.

## Positioning vs i3
- **We already MATCH or BEAT i3 on:** void/cancel detection, auto video-paired evidence, and group-shoplifting/concealment analysis (i3 markets "trajectory anomaly" but our concealment+collusion evidence is concrete).
- **Our angle:** 100% offline / on-prem / no per-camera license / no cloud (i3 charges per-module + cloud). Privacy-first (heatmaps anonymous; recommend NOT doing facial recognition).
- Do NOT add facial recognition or LPR (privacy/legal + hardware). Everything else is achievable on the current stack.
