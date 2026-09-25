"""Acceptance tests for the Auto-Evidence Agent (feature 6).

Deterministic — synthetic FrameSamples only, no video / no model. Verifies that
each incident type auto-selects the right named moment, that temporal NMS drops
near-duplicate picks, and that behavioural proxies are honestly disclosed (never
presented as ground-truth detections)."""
from __future__ import annotations

from avip.cv.detect import Detection
from avip.analytics.auto_evidence import (
    FrameSample, Zones, select_evidence, summarize, coverage_note, PROXY_SIGNALS,
)

W, H = 1000, 600


def _person(cx, cy, w=80, h=200, conf=0.9):
    """A person box centered horizontally at cx with feet at cy (bottom-center)."""
    return Detection((cx - w / 2, cy - h, cx + w / 2, cy), conf)


def _fs(idx, t, people=(), **kw):
    return FrameSample(idx=idx, t=t, frame_w=W, frame_h=H, people=tuple(people), **kw)


# ------------------------------- register -------------------------------- #
def test_register_picks_high_motion_solo_cashier():
    samples = [
        _fs(0, 0.0, [_person(200, 550)], drawer_motion=1.0),   # solo + high motion
        _fs(1, 2.0, [_person(200, 550), _person(700, 550)], drawer_motion=1.0),  # customer present
        _fs(2, 4.0, [_person(200, 550)], drawer_motion=0.0),   # solo but no motion
    ]
    got = select_evidence(samples, "register", Zones(), k=1)
    assert len(got) == 1
    assert got[0].name == "key"
    assert got[0].idx == 0                      # solo + max motion wins
    assert got[0].signals["only_cashier"] == 1.0
    assert got[0].proxy == []                   # register signals are measured, not proxy


def test_register_customer_zone_suppresses_solo():
    zones = Zones(customer=(0.5, 0.0, 1.0, 1.0))   # right half = customer stand
    samples = [
        _fs(0, 0.0, [_person(200, 550), _person(800, 550)], drawer_motion=1.0),  # customer in zone
        _fs(1, 3.0, [_person(200, 550)], drawer_motion=0.8),                     # cashier only
    ]
    got = select_evidence(samples, "register", zones, k=1)
    assert got[0].idx == 1                       # frame with a customer is not "no-sale"


# --------------------------------- void ---------------------------------- #
def test_void_selects_cancel_handoff_and_dustbin():
    zones = Zones(bin=(0.0, 0.0, 0.2, 1.0))      # left strip = dustbin
    samples = [
        _fs(0, 0.0, [_person(400, 550), _person(470, 550)]),           # two close = handoff
        _fs(1, 5.0, [_person(400, 550)], cancel=True),                 # CANCEL frame
        _fs(2, 8.0, [_person(100, 550)]),                              # at bin, post-cancel
    ]
    got = select_evidence(samples, "void", zones, k=3)
    names = {c.name for c in got}
    assert names == {"receipt", "handoff", "dustbin"}
    receipt = next(c for c in got if c.name == "receipt")
    assert receipt.proxy == []                   # the OCR'd CANCEL is verifiable
    assert receipt.score == 95.0                 # highest-ranked
    assert got[0].name == "receipt"


def test_void_proxies_are_disclosed():
    zones = Zones(bin=(0.0, 0.0, 0.2, 1.0))
    samples = [
        _fs(0, 0.0, [_person(400, 550), _person(470, 550)]),
        _fs(1, 5.0, [_person(400, 550)], cancel=True),
        _fs(2, 8.0, [_person(100, 550)]),
    ]
    got = select_evidence(samples, "void", zones, k=3)
    handoff = next(c for c in got if c.name == "handoff")
    dustbin = next(c for c in got if c.name == "dustbin")
    assert "hand_contact" in handoff.proxy and set(handoff.proxy) <= PROXY_SIGNALS
    assert "receipt_to_bin" in dustbin.proxy and set(dustbin.proxy) <= PROXY_SIGNALS


def test_void_dustbin_requires_post_cancel():
    zones = Zones(bin=(0.0, 0.0, 0.2, 1.0))
    samples = [
        _fs(0, 0.0, [_person(100, 550)]),        # at bin but BEFORE any cancel
        _fs(1, 5.0, [_person(400, 550)], cancel=True),
    ]
    got = select_evidence(samples, "void", zones, k=3)
    assert all(c.name != "dustbin" for c in got)  # pre-cancel bin visit is ignored


# --------------------------------- floor --------------------------------- #
def test_floor_group_and_shielding():
    zones = Zones(cooler=(0.5, 0.0, 1.0, 1.0))   # right half = cooler
    # group peak and the tightest huddle occur at DIFFERENT times (realistic),
    # so temporal NMS keeps both as distinct evidence frames.
    samples = [
        _fs(0, 0.0, [_person(700, 550)]),                              # 1 at cooler
        _fs(1, 4.0, [_person(600, 550), _person(720, 550), _person(850, 550)]),  # 3 = group
        _fs(2, 8.0, [_person(690, 550), _person(710, 550)]),           # 2 tight = shielding
    ]
    got = select_evidence(samples, "floor", zones, k=3)
    names = {c.name for c in got}
    assert "group" in names and "shielding" in names
    group = next(c for c in got if c.name == "group")
    assert group.idx == 1 and group.signals["people_in_zone"] == 3
    shielding = next(c for c in got if c.name == "shielding")
    assert shielding.idx == 2 and "shielding" in shielding.proxy


# ------------------------ temporal NMS + robustness ---------------------- #
def test_temporal_nms_drops_near_duplicates():
    zones = Zones(cooler=(0.5, 0.0, 1.0, 1.0))
    # group + key + shielding all land near t=4.0 -> only the top survives min_gap
    samples = [
        _fs(0, 4.0, [_person(680, 550), _person(720, 550), _person(760, 550)]),
        _fs(1, 4.3, [_person(690, 550), _person(710, 550)]),
    ]
    got = select_evidence(samples, "floor", zones, k=3, min_gap_s=1.0)
    times = [c.t for c in got]
    # no two kept frames within 1.0s of each other
    assert all(abs(times[i] - times[j]) >= 1.0
               for i in range(len(times)) for j in range(i + 1, len(times)))


def test_empty_and_unknown_group_are_failsoft():
    assert select_evidence([], "floor", Zones()) == []
    assert select_evidence([_fs(0, 0.0)], "nonsense", Zones()) == []


def test_summarize_reports_proxy_and_note():
    zones = Zones(bin=(0.0, 0.0, 0.2, 1.0))
    samples = [
        _fs(0, 0.0, [_person(400, 550), _person(470, 550)]),
        _fs(1, 5.0, [_person(400, 550)], cancel=True),
        _fs(2, 8.0, [_person(100, 550)]),
    ]
    summary = summarize(select_evidence(samples, "void", zones, k=3))
    assert summary["selected"] == 3
    assert summary["uses_proxy_signals"] is True
    assert "hand_contact" in summary["proxy_signals"]
    assert "pose" in summary["coverage_note"].lower()
    assert coverage_note() == summary["coverage_note"]
