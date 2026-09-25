"""Dedicated AI shared-drive folder helpers (Upgrade item 3).

One root (config `paths.ai_shared_root`, env `AI_SHARED_ROOT`) holds everything:

    <AI_SHARED_ROOT>/
        incoming/      (FreeCam MP4 exports, one subfolder per site: 0008, 0025, 0028)
        reports/       (generated reports + HTML)
        evidence/      (saved incident clips / key frames)

The app must ONLY read/write inside this root — never other company-drive folders.
`ensure_within_root` enforces that and also blocks path-traversal (../) on any
externally-supplied name (also serves item 8 input-sanitisation).
"""
from __future__ import annotations

from pathlib import Path

from avip.common.config import Config, get_config

INCOMING = "incoming"
REPORTS = "reports"
EVIDENCE = "evidence"


def _cfg(config: Config | None) -> Config:
    return config if config is not None else get_config()


def ai_root(config: Config | None = None) -> Path:
    """Absolute path to the dedicated AI root."""
    return Path(_cfg(config).settings.paths.ai_shared_root).resolve()


def incoming_dir(config: Config | None = None) -> Path:
    return ai_root(config) / INCOMING


def reports_dir(config: Config | None = None) -> Path:
    return ai_root(config) / REPORTS


def evidence_dir(config: Config | None = None) -> Path:
    return ai_root(config) / EVIDENCE


def site_incoming_dir(site: str, config: Config | None = None) -> Path:
    """Per-site incoming folder, e.g. <root>/incoming/0008. `site` is sanitised."""
    return ensure_within_root(incoming_dir(config) / _clean_name(site), config)


def within_root(path: str | Path, config: Config | None = None) -> bool:
    """True if `path` resolves to somewhere inside the AI root (or the root itself)."""
    root = ai_root(config)
    try:
        p = Path(path).resolve()
    except Exception:
        return False
    return p == root or root in p.parents


def ensure_within_root(path: str | Path, config: Config | None = None) -> Path:
    """Return the resolved path IF it is inside the AI root; else raise. Use this
    before any read/write so the app can never touch other company folders."""
    p = Path(path).resolve()
    if not within_root(p, config):
        raise ValueError(f"path escapes the AI shared root: {p}")
    return p


def _clean_name(name: str) -> str:
    """Reject a single path component that tries to traverse or is absolute."""
    n = str(name).strip().replace("\\", "/")
    if not n or n in (".", "..") or "/" in n or ":" in n or n.startswith("~"):
        raise ValueError(f"unsafe path component: {name!r}")
    return n


def ensure_dirs(config: Config | None = None, sites: list[str] | None = None) -> Path:
    """Create the AI root and its incoming/reports/evidence (and per-site incoming)
    subfolders if missing. Returns the root. Safe to call repeatedly (idempotent)."""
    cfg = _cfg(config)
    root = ai_root(cfg)
    root.mkdir(parents=True, exist_ok=True)
    for sub in (INCOMING, REPORTS, EVIDENCE):
        (root / sub).mkdir(parents=True, exist_ok=True)
    site_ids = sites if sites is not None else cfg.store_ids()
    for s in site_ids:
        (root / INCOMING / _clean_name(s)).mkdir(parents=True, exist_ok=True)
    return root
