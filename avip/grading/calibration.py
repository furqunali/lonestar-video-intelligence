"""Calibration gate (spec §9.6): validate the rubric against a labelled
golden-set BEFORE any grade may affect staff.

Until a real golden-set is supplied and passes within tolerance, this gate
returns False, which forces every grade to stay withheld / unpublished. This is
the structural guarantee behind the owner's requirement: "if the grading isn't
done properly, the grades are no good."
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class CalibrationResult:
    passed: bool
    reason: str
    cases: int = 0


def check_calibration(golden_path: Path | str | None = None,
                      tolerance: float = 5.0) -> CalibrationResult:
    """Return whether the rubric reproduces the golden-set within tolerance.

    In the PoC there is no real labelled golden-set, so this returns passed=False
    and NO grade is published. When `tests/golden/golden_set.yaml` is filled with
    real hand-labelled clips + expected scores, this becomes a genuine check.
    """
    if golden_path is None:
        return CalibrationResult(False, "no golden-set supplied (PoC): grades withheld")
    p = Path(golden_path)
    if not p.exists():
        return CalibrationResult(False, f"golden-set not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cases = data.get("cases") or []
    if not cases:
        return CalibrationResult(False, "golden-set is empty (placeholder): grades withheld")
    # Real check would recompute each case and compare to expected within tolerance.
    return CalibrationResult(False, "golden-set validation not yet run: grades withheld",
                            cases=len(cases))
