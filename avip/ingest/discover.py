"""Discover DVR dumps for the PoC sites (spec §9.1).

Input layout on the shared drive (CLAUDE.md §2):
    incoming/<site>/<clip>.mp4        e.g. incoming/0008/reg1_2026-09-02.mp4

Only sites in config (0008/0025/0028) are processed. Every filename is
sanitized (no traversal) before use. If a clip's name contains a known
camera_id, we attach it; otherwise camera_id stays None and is resolved later.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from avip.common.config import Config
from avip.common.logging import get_logger
from avip.common.security import UnsafePathError, safe_filename

log = get_logger("ingest.discover")


@dataclass(frozen=True)
class Dump:
    """One exported video file to process."""
    location_id: str
    path: Path
    camera_id: str | None = None


def discover_dumps(input_dir: Path | str, config: Config) -> list[Dump]:
    """Return all valid-looking dumps under ``input_dir`` for known sites."""
    root = Path(input_dir)
    exts = set(config.settings.ingest.video_extensions)
    known_sites = set(config.store_ids())
    cam_ids = [c.camera_id for c in config.cameras.cameras]

    dumps: list[Dump] = []
    if not root.exists():
        log.warning("input_dir_missing", path=str(root))
        return dumps

    for site_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        site = site_dir.name
        if site not in known_sites:
            log.warning("unknown_site_skipped", site=site)
            continue
        for f in sorted(site_dir.iterdir()):
            if not f.is_file() or f.suffix.lower() not in exts:
                continue
            try:
                safe_filename(f.name)          # reject traversal / odd chars
            except UnsafePathError as exc:
                log.warning("unsafe_filename_skipped", file=str(f), error=str(exc))
                continue
            cam = next((cid for cid in cam_ids if cid in f.stem), None)
            dumps.append(Dump(location_id=site, path=f, camera_id=cam))

    log.info("discovered", count=len(dumps), input_dir=str(root))
    return dumps
