"""Knowledge-base / report freshness check (audit item 5).

The assistant's facts KB and the director report are DERIVED artefacts: they are
rebuilt from `all_findings.json` (+ the per-clip findings the analyzer writes).
If new footage is analysed but the KB/report is not regenerated, viewers see
stale knowledge with no warning. This module gives a deterministic staleness
signal so a rebuild can be triggered (or the report can flag itself as stale).

A KB is STALE when either:
  * any source it was built from changed AFTER the KB was generated, or
  * the KB is older than an optional time-to-live (`ttl_hours`).

Pure timestamp logic (`kb_freshness`) so it is unit-testable without files;
`check_kb_files` is the fail-soft filesystem wrapper the report/pipeline calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# small tolerance so a KB written microseconds after its source isn't "stale".
_TOLERANCE_S = 1.0


def _epoch(t) -> float | None:
    """Normalize a datetime / epoch-seconds value to epoch seconds (or None)."""
    if t is None:
        return None
    if isinstance(t, (int, float)):
        return float(t)
    if isinstance(t, datetime):
        ts = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        return ts.timestamp()
    raise TypeError(f"unsupported timestamp type: {type(t)!r}")


@dataclass
class FreshnessResult:
    fresh: bool
    stale: bool
    reasons: list[str] = field(default_factory=list)
    age_hours: float | None = None                 # how old the KB is now
    newest_source_age_hours: float | None = None   # age of the newest source

    def __bool__(self) -> bool:                    # truthy == fresh
        return self.fresh


def kb_freshness(kb_generated_at, source_mtimes, ttl_hours: float | None = None,
                 now=None) -> FreshnessResult:
    """Decide whether a KB built at `kb_generated_at` is still fresh.

    kb_generated_at: datetime or epoch-seconds the KB was built.
    source_mtimes:   iterable of source datetimes / epoch-seconds it derives from.
    ttl_hours:       optional max age before the KB is considered stale anyway.
    now:             override 'current time' (datetime/epoch) for deterministic tests.
    Fail-soft: a missing KB timestamp is reported STALE, never raised.
    """
    now_e = _epoch(now) if now is not None else datetime.now(timezone.utc).timestamp()
    kb_e = _epoch(kb_generated_at)
    if kb_e is None:
        return FreshnessResult(False, True, ["KB has no generated_at timestamp"])

    reasons: list[str] = []
    stale = False

    srcs = [e for e in (_epoch(m) for m in (source_mtimes or [])) if e is not None]
    newest = max(srcs) if srcs else None
    if newest is not None and newest > kb_e + _TOLERANCE_S:
        stale = True
        reasons.append(f"source data changed {(newest - kb_e) / 3600:.1f}h "
                       f"after the KB was built - rebuild needed")

    age_h = max(0.0, (now_e - kb_e) / 3600.0)
    if ttl_hours is not None and age_h > ttl_hours:
        stale = True
        reasons.append(f"KB age {age_h:.1f}h exceeds TTL {ttl_hours}h")

    if not stale:
        reasons.append("fresh: KB is newer than every source"
                       + (f" and within the {ttl_hours}h TTL" if ttl_hours else ""))

    return FreshnessResult(
        fresh=not stale, stale=stale, reasons=reasons,
        age_hours=round(age_h, 2),
        newest_source_age_hours=(None if newest is None
                                 else round(max(0.0, (now_e - newest) / 3600.0), 2)),
    )


def check_kb_files(kb_path, source_paths, ttl_hours: float | None = None,
                   now=None) -> FreshnessResult:
    """Filesystem wrapper: read mtimes and evaluate freshness. Never raises.

    kb_path:      the built KB / report artefact (e.g. the director HTML).
    source_paths: files it was built from (e.g. all_findings.json, per-clip JSON).
    """
    try:
        kb = Path(kb_path)
        if not kb.exists():
            return FreshnessResult(False, True, [f"KB file missing: {kb}"])
        mtimes = []
        for p in source_paths or []:
            fp = Path(p)
            if fp.exists():
                mtimes.append(fp.stat().st_mtime)
        return kb_freshness(kb.stat().st_mtime, mtimes, ttl_hours=ttl_hours, now=now)
    except Exception as exc:                        # fail-soft: report, don't crash
        return FreshnessResult(False, True, [f"freshness check error: {exc}"])
