# Security Policy

## Scope

This repository is a **sanitized, review-only** proof-of-concept. It contains **no**
real video, credentials, personal data, or production configuration — all names,
stores and incidents are fictitious samples.

## Design safeguards

- **No secrets in code or git.** All secrets are read from the environment / `.env`
  (git-ignored); only `.env.example` (empty placeholders) is tracked.
- **Path sandboxing.** External paths and filenames are validated and confined to a
  single configured working directory; untrusted input is never passed to a shell.
- **Tamper-evidence.** A hash manifest of code + config from the reviewed commit can
  gate startup, so unreviewed changes are detected.
- **Least data.** Identity is non-biometric and gated; no facial recognition or LPR.

## Reporting a vulnerability

If you believe you have found a security issue in this code, please **do not open a
public issue**. Instead, contact the maintainer (Furqan Ali) privately via GitHub.
You will get an acknowledgement, and fixes will be handled discreetly.

## A note on use

This project is licensed **Review-Only** (see [`LICENSE`](LICENSE)). Reviewing the
code is welcome; using, deploying, or redistributing it requires the author's prior
written permission.
