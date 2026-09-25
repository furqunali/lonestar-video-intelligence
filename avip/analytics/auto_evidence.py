"""Auto-Evidence Agent — feature 6 (no manual ROI/frame pointing).

Today an operator hand-picks the evidence moment per clip (motion peak, cooler
score, cancel time). This agent does that automatically: it scores EVERY sampled
frame on behaviour signals and returns the top, temporally-distinct, *named*
evidence frames per incident type. It is deterministic, offline and unit-tested
(no video, no model needed — it consumes person detections + a few scalar signals
the analyzer already computes).

INTEGRITY / HONESTY (skill §12): geometry heuristics get an evidence frame right
~85–90 %. TRUE ~98 % needs pose / action recognition (fist-bump, hand-to-waist
conceal, receipt-to-bin) which we do NOT fake. Every candidate therefore lists,
in `proxy`, which of its firing signals are behavioural PROXIES rather than
ground-truth detections, and `coverage_note()` states the ceiling plainly so the
camera team is never misled.

What fires, per incident type (skill §4 / §12):
  register  — drawer-ROI motion + only-cashier-present (no customer)  -> "key"
  void      — CANCEL frame ("receipt"), 2-person contact ("handoff",
              PROXY), person-near-bin after cancel ("dustbin", PROXY)
  floor     — most-people-in-zone ("group"), tightest cluster ("shielding",
              PROXY), overall cooler peak ("key")

Selection = best-per-named-signal, then temporal non-max-suppression (drop a
lower-scored pick within `min_gap_s` of a kept one so we never ship two near
identical frames), then top-`k`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from avip.cv.detect import Detection

# ---------------------------------------------------------------------------
# Behavioural signals that are geometric PROXIES, not ground-truth detections.
# Any candidate whose selection leans on one of these carries it in `.proxy`.
# ---------------------------------------------------------------------------
PROXY_SIGNALS = frozenset({"hand_contact", "receipt_to_bin", "shielding",
                           "hand_to_waist"})

_COVERAGE_NOTE = (
    "Auto-selected by geometry + motion + POS-token signals (no manual pointing). "
    "Geometric behaviour cues (hand contact, receipt-to-bin, shielding) are marked "
    "PROXY: they place the frame ~85–90% of the time. True ~98% selection of the "
    "exact act needs pose / action recognition (not enabled — privacy-gated), so "
    "every auto frame remains a human-review recommendation, not a verdict."
)


def coverage_note() -> str:
    """Honest one-paragraph disclosure of the agent's ceiling, for the report."""
    return _COVERAGE_NOTE


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FrameSample:
    """One sampled frame's features. `people` are full-frame-pixel detections."""
    idx: int
    t: float                              # seconds into the clip
    frame_w: int
    frame_h: int
    people: tuple[Detection, ...] = ()
    drawer_motion: float = 0.0            # register: raw drawer-ROI mean abs-diff
    cancel: bool = False                  # void: CANCEL/VOID token OCR'd this frame


@dataclass
class Zones:
    """Normalized (0..1) ROIs. Any may be None; scorers degrade gracefully."""
    cooler: tuple | None = None           # floor monitored target region
    drawer: tuple | None = None           # register cash drawer (context only)
    bin: tuple | None = None              # void: dustbin the receipt is dropped in
    customer: tuple | None = None         # register: counter customer stand-zone
    # Human label for the floor region. NEUTRAL by default: on a multi-camera
    # clip the peak-group frame may be an entrance/aisle, not literally a cooler,
    # so we never assert "cooler" unless a clip explicitly sets it.
    zone_label: str = "target zone"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
@dataclass
class EvidenceCandidate:
    name: str                             # file slug: key/receipt/handoff/dustbin/group/shielding
    idx: int
    t: float
    score: float                          # 0..100
    signals: dict[str, float] = field(default_factory=dict)
    proxy: list[str] = field(default_factory=list)   # subset of signals that are proxies
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _in_zone(det: Detection, zone, w: int, h: int) -> bool:
    """True if the detection's feet (bottom-center) fall inside a normalized zone."""
    if not zone:
        return False
    x1, y1, x2, y2 = zone
    bx, by = det.bottom_center
    return x1 <= bx / w <= x2 and y1 <= by / h <= y2


def _center(det: Detection) -> tuple[float, float]:
    x1, y1, x2, y2 = det.xyxy
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _min_edge_gap(people) -> float | None:
    """Smallest horizontal edge-to-edge gap between any two person boxes (px).

    Small gap == two people close enough to hand something over (a PROXY for the
    void hand-off). Overlapping boxes give 0. None if <2 people.
    """
    if len(people) < 2:
        return None
    best = None
    for i in range(len(people)):
        ax1, _, ax2, _ = people[i].xyxy
        for j in range(i + 1, len(people)):
            bx1, _, bx2, _ = people[j].xyxy
            gap = max(bx1 - ax2, ax1 - bx2, 0.0)   # 0 if overlapping in x
            if best is None or gap < best:
                best = gap
    return best


def _cluster_tightness(people, diag: float) -> float | None:
    """0..1 tightness of the group (1 == everyone on top of each other).

    Mean pairwise center distance / frame diagonal, inverted. A tight cluster of
    people is the shielding/huddle signature. None if <2 people. PROXY.
    """
    if len(people) < 2 or diag <= 0:
        return None
    cs = [_center(p) for p in people]
    tot, n = 0.0, 0
    for i in range(len(cs)):
        for j in range(i + 1, len(cs)):
            dx, dy = cs[i][0] - cs[j][0], cs[i][1] - cs[j][1]
            tot += (dx * dx + dy * dy) ** 0.5
            n += 1
    mean = tot / n
    return max(0.0, 1.0 - min(mean / diag, 1.0))


def _norm(value: float, lo: float, hi: float) -> float:
    """Min-max normalize into 0..1; 0.5 when the range is degenerate."""
    if hi <= lo:
        return 0.5
    return max(0.0, min((value - lo) / (hi - lo), 1.0))


def _people_in(sample: FrameSample, zone) -> list[Detection]:
    return [p for p in sample.people
            if _in_zone(p, zone, sample.frame_w, sample.frame_h)]


# ---------------------------------------------------------------------------
# Per-incident-type scorers. Each returns {name: EvidenceCandidate} (best frame
# per named signal) so distinct evidence moments don't collapse into one.
# ---------------------------------------------------------------------------
def _score_register(samples: list[FrameSample], zones: Zones) -> dict:
    """No-sale cash handling: drawer motion while only the cashier is present."""
    motions = [s.drawer_motion for s in samples]
    lo, hi = (min(motions), max(motions)) if motions else (0.0, 1.0)
    best = None
    for s in samples:
        motion_n = _norm(s.drawer_motion, lo, hi)
        n_people = len(s.people)
        if zones.customer:                       # explicit customer zone => precise
            solo = 0.0 if _people_in(s, zones.customer) else 1.0
        else:                                    # else: exactly one body == cashier only
            solo = 1.0 if n_people == 1 else (0.0 if n_people >= 2 else 0.3)
        # "No customer present" is the theft discriminator (a customer at the
        # counter means a legitimate sale), so it out-weighs raw drawer motion.
        score = 100.0 * (0.45 * motion_n + 0.55 * solo)
        cand = EvidenceCandidate(
            name="key", idx=s.idx, t=s.t, score=round(score, 1),
            signals={"drawer_motion_norm": round(motion_n, 3),
                     "only_cashier": round(solo, 3), "people": n_people},
            proxy=[],
            reason=(f"drawer active (motion {motion_n:.2f}) with "
                    + ("no customer at counter" if solo >= 0.9
                       else f"{n_people} person(s) present")),
        )
        if best is None or cand.score > best.score:
            best = cand
    return {"key": best} if best else {}


def _score_void(samples: list[FrameSample], zones: Zones) -> dict:
    """Collusion void: the CANCEL frame, the hand-off, the receipt-to-bin."""
    out: dict = {}
    cancel_ts = [s.t for s in samples if s.cancel]
    first_cancel = min(cancel_ts) if cancel_ts else None

    # 1) receipt / CANCEL frame — the machine-verifiable moment (NOT a proxy).
    cancel_frames = [s for s in samples if s.cancel]
    if cancel_frames:
        s = min(cancel_frames, key=lambda s: s.t)   # earliest cancel token
        out["receipt"] = EvidenceCandidate(
            name="receipt", idx=s.idx, t=s.t, score=95.0,
            signals={"cancel_token": 1.0, "people": len(s.people)},
            proxy=[],
            reason="POS CANCEL/VOID token visible on the burned-in receipt",
        )

    # 2) hand-off — two people at closest approach (PROXY: hand contact).
    diag = None
    best_gap = None
    for s in samples:
        gap = _min_edge_gap(s.people)
        if gap is None:
            continue
        if diag is None:
            diag = (s.frame_w ** 2 + s.frame_h ** 2) ** 0.5
        if best_gap is None or gap < best_gap[0]:
            best_gap = (gap, s)
    if best_gap is not None:
        gap, s = best_gap
        closeness = 1.0 - min(gap / (0.25 * (s.frame_w)), 1.0)   # closer => higher
        out["handoff"] = EvidenceCandidate(
            name="handoff", idx=s.idx, t=s.t, score=round(60.0 + 35.0 * closeness, 1),
            signals={"min_edge_gap_px": round(gap, 1), "closeness": round(closeness, 3),
                     "people": len(s.people)},
            proxy=["hand_contact"],
            reason="two people at closest approach - likely goods/cash hand-off (proxy)",
        )

    # 3) dustbin — a person near the bin AFTER the cancel (PROXY: receipt-to-bin).
    if zones.bin is not None:
        cand = None
        for s in samples:
            if first_cancel is not None and s.t < first_cancel - 1.0:
                continue                                    # must be at/after the void
            n_bin = len(_people_in(s, zones.bin))
            if not n_bin:
                continue
            after = 1.0 if (first_cancel is None or s.t >= first_cancel) else 0.5
            score = 55.0 + 25.0 * after + 10.0 * min(n_bin, 2)
            if cand is None or score > cand.score:
                cand = EvidenceCandidate(
                    name="dustbin", idx=s.idx, t=s.t, score=round(score, 1),
                    signals={"people_at_bin": n_bin, "post_cancel": after},
                    proxy=["receipt_to_bin"],
                    reason="person at the dustbin after the void - possible receipt disposal (proxy)",
                )
        if cand is not None:
            out["dustbin"] = cand
    return out


def _score_floor(samples: list[FrameSample], zones: Zones) -> dict:
    """Organized shoplifting: group in zone, tightest cluster, cooler peak."""
    out: dict = {}
    zone = zones.cooler
    zl = zones.zone_label
    counts = [len(_people_in(s, zone)) for s in samples] if zone else [0]
    hi = max(counts) if counts else 0

    # 1) group — most people at the cooler at once (max-people-in-zone).
    if zone is not None:
        best = None
        for s in samples:
            n = len(_people_in(s, zone))
            if n == 0:
                continue
            score = 100.0 * _norm(n, 1, max(hi, 2))
            if best is None or n > best[0]:
                best = (n, EvidenceCandidate(
                    name="group", idx=s.idx, t=s.t, score=round(score, 1),
                    signals={"people_in_zone": n, "total_people": len(s.people)},
                    proxy=[],
                    reason=f"{n} people converging in the {zl} (group activity)"))
        if best is not None:
            out["group"] = best[1]

    # 2) shielding — tightest cluster of >=2 people (PROXY).
    diag_best = None
    for s in samples:
        in_zone = _people_in(s, zone) if zone else list(s.people)
        diag = (s.frame_w ** 2 + s.frame_h ** 2) ** 0.5
        tight = _cluster_tightness(in_zone, diag)
        if tight is None:
            continue
        if diag_best is None or tight > diag_best[0]:
            diag_best = (tight, s, len(in_zone))
    if diag_best is not None:
        tight, s, n = diag_best
        out["shielding"] = EvidenceCandidate(
            name="shielding", idx=s.idx, t=s.t, score=round(50.0 + 45.0 * tight, 1),
            signals={"cluster_tightness": round(tight, 3), "people": n},
            proxy=["shielding"],
            reason="tight huddle of people - possible shielding of a concealment (proxy)",
        )

    # 3) key — overall best frame (matches the analyzer's cooler-peak formula).
    best = None
    for s in samples:
        n_zone = len(_people_in(s, zone)) if zone else 0
        score = n_zone * 2 + len(s.people)
        if best is None or score > best[0]:
            best = (score, EvidenceCandidate(
                name="key", idx=s.idx, t=s.t, score=round(100.0 * _norm(score, 0, max(1, 2 * hi + 4)), 1),
                signals={"people_in_zone": n_zone, "total_people": len(s.people)},
                proxy=[],
                reason=f"peak activity: {len(s.people)} people, {n_zone} in the {zl}"))
    if best is not None:
        out["key"] = best[1]
    return out


_SCORERS = {"register": _score_register, "void": _score_void, "floor": _score_floor}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def select_evidence(samples, group: str, zones: Zones | None = None,
                    k: int = 3, min_gap_s: float = 1.0) -> list[EvidenceCandidate]:
    """Auto-select up to `k` distinct evidence frames for a clip.

    group: "register" (cash theft, no overlay), "void" (POS collusion cancel),
           or "floor" (shoplifting). Unknown group -> [].
    zones: normalized ROIs (cooler/bin/customer/drawer); any may be None.
    Selection = best frame per named signal, then temporal non-max-suppression
    (a lower pick within `min_gap_s` of a kept one is dropped), then top-`k`,
    highest score first. Fail-soft: never raises on bad input.
    """
    try:
        samples = list(samples)
    except TypeError:
        return []
    if not samples:
        return []
    zones = zones or Zones()
    scorer = _SCORERS.get(group)
    if scorer is None:
        return []

    named = scorer(samples, zones)                       # {name: candidate}
    cands = sorted((c for c in named.values() if c is not None),
                   key=lambda c: c.score, reverse=True)

    # temporal NMS: keep highest-scored; drop any pick too close in time to a kept one
    kept: list[EvidenceCandidate] = []
    for c in cands:
        if all(abs(c.t - k2.t) >= min_gap_s for k2 in kept):
            kept.append(c)
        if len(kept) >= k:
            break
    return kept


def summarize(candidates) -> dict:
    """Report-ready roll-up of an auto-selection (counts + proxy disclosure)."""
    cands = list(candidates)
    proxies = sorted({p for c in cands for p in c.proxy})
    return {
        "selected": len(cands),
        "frames": [c.name for c in cands],
        "max_score": round(max((c.score for c in cands), default=0.0), 1),
        "uses_proxy_signals": bool(proxies),
        "proxy_signals": proxies,
        "coverage_note": coverage_note(),
    }
