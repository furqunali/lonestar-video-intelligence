# Chat Support — AI Video-Intelligence portal

A full, offline-first support portal for the whole team (camera team, staff,
management). One-click widget → ask anything (reporting, real-time data, evidence,
analytics, summary) → the assistant answers from the platform's own data and can
**execute actions**, gated by a **Manager → Director approval** workflow. Every
message, action, approval and per-user memory is saved centrally.

## Run it (offline, zero extra install)
- Windows one-click: double-click **`run_chat.cmd`** → browser opens the widget.
- Or: `python -m avip.chat.server 127.0.0.1 8770` → open http://127.0.0.1:8770
- Docker: `docker build -f Dockerfile.chat -t slp-chat . && docker run -p 8770:8770 -v %cd%/data:/app/data slp-chat`

Everyone opens the same URL, clicks **💬 Support**, enters their name + role
(Camera team/Staff · Manager · Director) and chats.

## What anyone can ask (read-only, instant)
- **summary** / overview / status — incidents, exceptions ($), cameras OK, top risk
- **show incidents** — the loss-prevention cases
- **evidence** — where the annotated BEFORE→AFTER frames are + report link
- **risk ranking** — POS exceptions ranked (amount × cashier × time)
- **camera health** — hardened tamper/health status
- **KPIs** / metrics · **search cashier JORDAN void over 10** — transaction search

## Actions that need approval (locked → executed on sign-off)
| Action | Who can request | Approvals |
|--------|-----------------|-----------|
| generate_report | Manager+ | Manager |
| export_data | Manager+ | Manager (real CSV export) |
| email_director | Manager+ | Director |
| publish_shared_drive | Manager+ | Manager → Director |

The requester is told it's pending; Managers/Directors see a **Pending approvals**
tab with Approve/Deny; on final approval the action runs and the outcome is posted
back into the original chat.

## Centralized team history
Managers/Directors get a **Team** tab showing the whole team's recent
conversations (each message tagged with user + role). Staff see only their own.

## Persistence (everything saved)
SQLite `data/chat.db`: `sessions`, `messages`, `action_requests`, `approvals`,
`memory`. Transactions in `data/transactions.db`. Say *"remember my name is …"* and
the assistant persists it per user.

## Architecture (Strategy + pluggable LLM)
- `engine.py` — **RuleEngine** (offline default, deterministic, no API key) +
  **LLMEngine** (pluggable: pass an `llm(prompt)->str`; recognised commands still
  route through the rule layer so actions/approvals stay deterministic).
- `actions.py` — typed action registry (permission + approval chain + handlers).
- `approvals.py` — Manager→Director workflow (create → approve chain → execute).
- `service.py` — orchestration; `server.py` — stdlib HTTP + REST; `widget.html` —
  responsive one-click UI (mobile full-screen + desktop panel, light/dark).

Design: offline / on-prem, no cloud, fail-soft, everything auditable. 83 tests green
(`tests/test_chat.py`).
