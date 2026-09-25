"""Scheduled backup of the database + config (Upgrade item 8).

Copies the SQLite DB file and all config/*.yaml into a timestamped backup folder.
Secrets (.env) are NEVER backed up here. Fail-soft: a backup problem is logged and
returned, never raised into the pipeline. A scheduled task / cron can call
`backup_db_and_config` on a schedule.
"""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from avip.common.config import REPO_ROOT, Config, get_config

log = logging.getLogger("avip.security.backup")


@dataclass
class BackupResult:
    ok: bool = False
    dest: str = ""
    copied: list[str] = field(default_factory=list)
    reason: str = ""


def _sqlite_path(db_url: str) -> Path | None:
    """Extract the local file path from a sqlite:/// URL (None for non-sqlite)."""
    prefix = "sqlite:///"
    if not db_url.startswith(prefix):
        return None
    return (REPO_ROOT / db_url[len(prefix):]).resolve()


def backup_db_and_config(config: Config | None = None, dest: Path | None = None,
                         *, stamp: str | None = None) -> BackupResult:
    """Copy the DB + config/*.yaml into <backup_dir>/<stamp>/. `stamp` is injectable
    (Date.now is avoided in some contexts); defaults to a wall-clock timestamp."""
    res = BackupResult()
    try:
        cfg = config or get_config()
        if stamp is None:
            import datetime as _dt
            stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = Path(dest) if dest else (REPO_ROOT / cfg.settings.security.backup_dir)
        out = base / stamp
        out.mkdir(parents=True, exist_ok=True)

        # 1) database (sqlite file), if present
        dbp = _sqlite_path(cfg.settings.database.url)
        if dbp and dbp.exists():
            shutil.copy2(dbp, out / dbp.name)
            res.copied.append(dbp.name)

        # 2) config/*.yaml (NOT .env — secrets are never backed up here)
        cfg_dir = REPO_ROOT / "config"
        if cfg_dir.exists():
            cdst = out / "config"
            cdst.mkdir(exist_ok=True)
            for y in sorted(cfg_dir.glob("*.yaml")):
                shutil.copy2(y, cdst / y.name)
                res.copied.append(f"config/{y.name}")

        res.ok = True
        res.dest = str(out)
        log.info("backup ok -> %s (%d item(s))", out, len(res.copied))
        return res
    except Exception as e:                     # fail-soft
        res.ok = False
        res.reason = str(e)
        log.error("backup failed (continuing): %s", e)
        return res
