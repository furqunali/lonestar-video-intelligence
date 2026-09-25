"""Report / KB freshness check (audit item 5) — runnable.

Compares the built director report (the knowledge artefact viewers see) against
the analyzer outputs it was built from. If any findings file changed after the
report was generated, the report is STALE and should be rebuilt
(`python build_consolidated.py`).

    python reporting/check_freshness.py          # exit 0 = fresh, 1 = stale

Optional: pass a max age in hours as a TTL, e.g. `... check_freshness.py 168`.
"""
from __future__ import annotations

import sys
from pathlib import Path

from avip.common.freshness import check_kb_files

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "Sugarland_Petroleum_Video_Intelligence_Director_Report.html"
ANA = ROOT / "reports" / "incident_analysis"


def main(ttl_hours: float | None = None) -> int:
    sources = [ANA / "all_findings.json", *ANA.glob("*/findings.json")]
    result = check_kb_files(REPORT, sources, ttl_hours=ttl_hours)
    tag = "FRESH" if result.fresh else "STALE"
    print(f"[{tag}] {REPORT.name}")
    print(f"  report age: {result.age_hours}h; "
          f"newest source age: {result.newest_source_age_hours}h")
    for r in result.reasons:
        print(f"  - {r}")
    if result.stale:
        print("  -> rebuild: python build_consolidated.py")
    return 0 if result.fresh else 1


if __name__ == "__main__":
    ttl = float(sys.argv[1]) if len(sys.argv) > 1 else None
    raise SystemExit(main(ttl))
