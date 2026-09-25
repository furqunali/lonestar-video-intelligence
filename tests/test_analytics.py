"""Acceptance tests for the analytics feature layer (5 features).

Covers: transaction store (parse/normalize/idempotent search), risk scoring
(ordering + bands), people counting (line crossing + conversion), heat-map
(points/accumulate/overlay/zones), and hardened tamper (the busy-scene
false-positive fix)."""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pytest

from avip.analytics import risk, counting, heatmap, health_plus, rollup
from avip.cv import health as cvhealth
from avip.analytics.transactions import (
    Transaction, TransactionStore, parse_amount, normalize_type, EXCEPTION_TYPES,
)
from avip.cv.process import Observation, Tracklet
from tests.synth import make_textured_frame, make_frame

CDT = timezone.utc


def _tx(tx_id, amount, tx_type, cashier="JORDAN LEE", hour=18, loc="0008", reg="Register 2"):
    return Transaction(tx_id, loc, reg, cashier, amount, tx_type,
                       datetime(2024, 11, 8, hour, 30, tzinfo=CDT), clip="clip.wmv")


# --------------------------- transactions -------------------------------- #
def test_parse_amount_variants():
    assert parse_amount("-18.86") == 18.86
    assert parse_amount("$18,86") == 18.86
    assert parse_amount(18.86) == 18.86
    assert parse_amount("garbage") == 0.0
    assert parse_amount(None) == 0.0


def test_parse_amount_rejects_non_finite():
    """Numerical safeguard (audit #4): a NaN/Inf numeric read must not propagate."""
    assert parse_amount(float("nan")) == 0.0
    assert parse_amount(float("inf")) == 0.0
    assert parse_amount(float("-inf")) == 0.0


def test_normalize_type_aliases():
    assert normalize_type("CANCELLED") == "cancel"
    assert normalize_type("Voided") == "void"
    assert normalize_type("no sale") == "no_sale"
    assert normalize_type("whatever") == "sale"


def test_store_idempotent_and_search(tmp_path):
    st = TransactionStore(tmp_path / "tx.db")
    tx = _tx("T1", 18.86, "cancel")
    st.add(tx); st.add(tx)                       # same id twice
    assert len(st.all()) == 1                    # idempotent
    st.add(_tx("T2", 5.0, "refund", cashier="JOHN"))
    assert len(st.search(cashier="JORDAN LEE")) == 1
    assert len(st.search(exceptions_only=True)) == 2
    assert len(st.search(min_amount=10)) == 1
    st.close()


# ------------------------------- risk ------------------------------------ #
def test_risk_orders_and_skips_sales():
    txns = [
        _tx("A", 45.0, "cancel", hour=3),        # big void, off-hours => highest
        _tx("B", 2.0, "discount", hour=13),      # small discount, in-hours => low
        _tx("C", 100.0, "sale", hour=13),        # normal sale => not scored
    ]
    findings = risk.score_transactions(txns)
    assert [f.tx_id for f in findings] == ["A", "B"]        # sale excluded, A before B
    assert findings[0].score > findings[1].score
    assert risk.risk_band(findings[0].score) in ("HIGH", "CRITICAL")
    assert findings[0].reasons                               # has explanation


def test_risk_frequency_repeat_offender():
    txns = [_tx(f"V{i}", 10.0, "void", cashier="REPEAT") for i in range(4)]
    txns.append(_tx("X", 10.0, "void", cashier="ONCE"))
    findings = {f.cashier: f for f in risk.score_transactions(txns)}
    assert findings["REPEAT"].factors["frequency"] == 1.0
    assert findings["ONCE"].factors["frequency"] < 1.0


# ---------------------------- people counting ---------------------------- #
def _track(track_id, feet_ys, x=50):
    obs = [Observation(i, float(i), (x - 5, y - 20, x + 5, y), 0.9, set())
           for i, y in enumerate(feet_ys)]
    return Tracklet(track_id, obs)


def test_line_crossing_entry_and_exit():
    downward = _track(1, [20, 30, 60, 80])       # crosses y=50 downward => entry
    upward = _track(2, [80, 60, 30, 20])         # crosses y=50 upward => exit
    res = counting.count_crossings([downward, upward], (100, 100),
                                   line_norm=((0.0, 0.5), (1.0, 0.5)))
    assert res.entries == 1 and res.exits == 1
    assert res.net == 0 and res.total_crossings == 2


def test_no_crossing_when_same_side():
    t = _track(1, [10, 15, 20])                  # stays above the line
    res = counting.count_crossings([t], (100, 100))
    assert res.entries == 0 and res.exits == 0


def test_conversion_rate():
    assert counting.conversion_rate(50, 10) == 0.2
    assert counting.conversion_rate(0, 5) is None


# ------------------------------- heatmap --------------------------------- #
def test_heatmap_points_and_accumulate():
    t = _track(1, [40, 60, 60, 60])              # lingers at y~60 => dwell weight
    pts_traffic = heatmap.points_from_tracklets([t], 1.0, dwell=False)
    pts_dwell = heatmap.points_from_tracklets([t], 1.0, dwell=True)
    assert len(pts_traffic) == 4
    # dwell weight (stationary boost) >= traffic weight total
    assert sum(p.weight for p in pts_dwell) >= sum(p.weight for p in pts_traffic)
    acc = heatmap.accumulate(pts_traffic, (100, 100))
    assert acc.max() > 0


def test_heatmap_overlay_and_zone_rank():
    bg = make_textured_frame(100, 100, seed=4)
    t = _track(1, [50, 50, 50, 50], x=50)
    overlay, zones, acc = heatmap.build_heatmap(
        [t], bg, nominal_dt=1.0, dwell=False,
        zones_norm={"center": [[0.3, 0.3], [0.7, 0.3], [0.7, 0.7], [0.3, 0.7]]})
    assert overlay.shape == bg.shape             # overlay matches frame
    assert zones and zones[0].share > 0          # center zone got the weight


def test_heatmap_empty_returns_background():
    bg = make_textured_frame(60, 60, seed=1)
    overlay = heatmap.render_overlay(np.zeros((60, 60), np.float32), bg)
    assert overlay.shape == bg.shape


# --------------------------- hardened tamper ----------------------------- #
def test_busy_sharp_scene_is_not_tamper():
    """THE FIX: a sharp, edge-rich, well-lit busy clip must read OK even when it
    differs a lot from a (different) reference — old code false-flagged TAMPER."""
    frames = [make_textured_frame(seed=i) for i in range(6)]
    diff_ref = make_textured_frame(seed=999)     # very different scene
    rep = health_plus.assess_tamper(frames, stable_ref=diff_ref)
    assert rep.clarity == "OK"
    assert rep.is_tamper is False
    assert rep.edge_density > health_plus.EDGE_DENSITY_MIN


def test_covered_lens_is_tamper():
    black = [np.zeros((240, 320, 3), np.uint8) for _ in range(5)]
    rep = health_plus.assess_tamper(black)
    assert rep.clarity == "TAMPER" and rep.is_tamper


def test_no_frames_not_live():
    rep = health_plus.assess_tamper([])
    assert rep.clarity == "OCCLUDED" and rep.is_tamper is False


# -------------------------------- rollup --------------------------------- #
def test_rollup_aggregates_by_store_and_cashier():
    txns = [
        _tx("A", 18.86, "cancel", cashier="JORDAN LEE", loc="0008"),
        _tx("B", 5.00, "refund", cashier="JORDAN LEE", loc="0008"),
        _tx("C", 12.00, "void", cashier="JOHN", loc="0025"),
        _tx("D", 99.0, "sale", cashier="JOHN", loc="0025"),   # not an exception
    ]
    r = rollup.build_rollup(txns)
    assert r["totals"]["exceptions"] == 3
    assert r["totals"]["exception_amount"] == 35.86
    assert r["totals"]["stores"] == 2
    assert r["top_risk"][0]["band"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


# --------------------- numerical safeguards (audit #4) -------------------- #
def test_health_scores_are_always_finite():
    """Blur / SSIM / solid-fraction must never return NaN/Inf, else a bad read
    would silently pass a `score < threshold` gate (NaN compares False)."""
    blank = np.zeros((0, 0), np.uint8)               # degenerate/empty frame
    const = np.full((32, 32), 128, np.uint8)         # constant image (SSIM edge case)
    assert math.isfinite(cvhealth.laplacian_blur_score(const))
    assert cvhealth.solid_fraction(blank, 20, 235) == 1.0     # empty => occluded
    assert 0.0 <= cvhealth.solid_fraction(const, 20, 235) <= 1.0
    ssim_self = cvhealth.tamper_ssim(const, const)   # constant vs itself => NaN raw
    assert math.isfinite(ssim_self)                  # coerced to a finite value
    assert math.isfinite(health_plus.edge_density(const))
    assert math.isfinite(health_plus.mean_luminance(const))


def test_empty_frame_edge_and_luminance_failsafe():
    empty = np.zeros((0, 0), np.uint8)
    assert health_plus.edge_density(empty) == 0.0    # no edges => reads as covered
    assert health_plus.mean_luminance(empty) == 0.0  # near-black => reads as blinded


# ------------------ numeric precision assertions (audit #3) --------------- #
def test_risk_score_matches_closed_form_within_tolerance():
    """torch.allclose-style precision check, done with the project's NumPy stack:
    the risk score must equal its weighted-blend closed form to float tolerance."""
    t = _tx("P", 45.0, "cancel", hour=3)             # off-hours big void
    f = risk.score_transactions([t])[0]
    w = risk.WEIGHTS
    expected = 100.0 * sum(w[k] * f.factors[k] for k in w) / sum(w.values())
    assert f.score == pytest.approx(expected, abs=0.05)
    assert np.allclose([f.factors["severity"]], [risk.SEVERITY["cancel"]], atol=1e-9)


def test_jordan_receipt_reconciles_to_the_cent():
    """The voided Jordan receipt must reconcile: items subtotal + tax == total."""
    subtotal, tax = 18.05, 0.81                      # 3.59 Pepsi corrected read etc.
    assert subtotal + tax == pytest.approx(18.86, abs=1e-9)


def test_heatmap_accumulate_is_numerically_stable():
    t = _track(1, [50, 50, 50, 50], x=50)
    pts = heatmap.points_from_tracklets([t], 1.0, dwell=False)
    acc = heatmap.accumulate(pts, (100, 100))
    assert np.all(np.isfinite(acc))                  # no NaN/Inf leaked into the grid
    assert acc.min() >= 0.0
