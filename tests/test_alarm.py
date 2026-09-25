"""Tests for the incident alarm (Upgrade item 1).

Beep and clip-display side effects are monkeypatched so the suite never makes a
sound or opens a window. We assert the GATING (incident-only, confidence),
mode routing (test vs live), and self-healing (never raises).
"""
from __future__ import annotations

import pytest

from avip.alarm import alarm            # the submodule holding _beep / _open_clip_local
from avip.alarm import raise_incident_alarm
from avip.common.config import Alarm, Runtime


@pytest.fixture(autouse=True)
def _no_side_effects(monkeypatch):
    """Replace the real beep / clip openers with recorders."""
    calls = {"beep": 0, "local": [], "lcd": []}

    def fake_beep(freq, ms, repeats):
        calls["beep"] += 1
        return True

    def fake_local(clip):
        calls["local"].append(str(clip))
        return True

    def fake_lcd(clip, cmd):
        calls["lcd"].append((str(clip), cmd))
        return bool(cmd)

    monkeypatch.setattr(alarm, "_beep", fake_beep)
    monkeypatch.setattr(alarm, "_open_clip_local", fake_local)
    monkeypatch.setattr(alarm, "_show_clip_lcd", fake_lcd)
    return calls


def _incident(**over):
    f = {"slug": "auto_x", "incident_detected": True, "incident_verdict": "cash",
         "site": "0008", "camera": "C3", "start_clock": "07:09:44",
         "calib_confidence": 0.9}
    f.update(over)
    return f


# --- gating -------------------------------------------------------------- #
def test_fires_on_real_incident_test_mode(_no_side_effects):
    r = raise_incident_alarm(_incident(), "clip.wmv", mode="test", alarm_cfg=Alarm())
    assert r.fired and not r.suppressed
    assert r.mode == "test"
    assert r.beeped
    assert _no_side_effects["beep"] == 1
    assert _no_side_effects["local"] == ["clip.wmv"]
    assert not _no_side_effects["lcd"]          # no LCD in test mode
    assert "Cash theft" in r.message and "0008" in r.message


def test_suppressed_when_no_incident(_no_side_effects):
    r = raise_incident_alarm(_incident(incident_detected=False), "clip.wmv",
                             alarm_cfg=Alarm())
    assert not r.fired and r.suppressed
    assert "no incident" in r.reason.lower()
    assert _no_side_effects["beep"] == 0        # never beeps on a normal clip


def test_suppressed_below_confidence(_no_side_effects):
    cfg = Alarm(confidence_min=0.8)
    r = raise_incident_alarm(_incident(calib_confidence=0.5), "clip.wmv", alarm_cfg=cfg)
    assert not r.fired and r.suppressed
    assert "confidence" in r.reason.lower()
    assert _no_side_effects["beep"] == 0


def test_suppressed_when_disabled(_no_side_effects):
    r = raise_incident_alarm(_incident(), "clip.wmv", alarm_cfg=Alarm(enabled=False))
    assert not r.fired and r.suppressed
    assert _no_side_effects["beep"] == 0


def test_curated_incident_has_full_confidence(_no_side_effects):
    """A curated incident with no calibration score is treated as confident (fires)."""
    f = _incident()
    f.pop("calib_confidence")
    r = raise_incident_alarm(f, "clip.wmv", alarm_cfg=Alarm())
    assert r.fired
    assert r.detail["confidence"] == 1.0


# --- mode routing -------------------------------------------------------- #
def test_live_mode_uses_lcd_only(_no_side_effects):
    r = raise_incident_alarm(_incident(), "clip.wmv", mode="live", alarm_cfg=Alarm(),
                             lcd_player_cmd='play "{clip}"')
    assert r.fired and r.mode == "live"
    assert _no_side_effects["lcd"] == [("clip.wmv", 'play "{clip}"')]
    assert not _no_side_effects["local"]        # never opens on this PC in live mode
    assert r.clip_shown


def test_live_mode_without_lcd_cmd_is_safe(_no_side_effects):
    """LIVE with no LCD command still beeps and never raises (logs only)."""
    r = raise_incident_alarm(_incident(), "clip.wmv", mode="live", alarm_cfg=Alarm())
    assert r.fired and r.beeped
    assert r.clip_shown is False


# --- self-healing -------------------------------------------------------- #
def test_never_raises_on_bad_finding(_no_side_effects):
    r = raise_incident_alarm(None, None, alarm_cfg=Alarm())
    assert not r.fired and r.suppressed


def test_beep_can_be_turned_off(_no_side_effects):
    r = raise_incident_alarm(_incident(), "clip.wmv", alarm_cfg=Alarm(beep=False))
    assert r.fired and not r.beeped
    assert _no_side_effects["beep"] == 0


def test_dict_alarm_cfg_also_works(_no_side_effects):
    """alarm_cfg may be a plain dict (not only the pydantic model)."""
    r = raise_incident_alarm(_incident(), "clip.wmv",
                             alarm_cfg={"enabled": True, "confidence_min": 0.6,
                                        "beep": True, "show_clip": True})
    assert r.fired


# --- config model -------------------------------------------------------- #
def test_runtime_rejects_bad_mode():
    with pytest.raises(Exception):
        Runtime(mode="banana")


def test_runtime_defaults_to_test():
    assert Runtime().mode == "test"
    assert Runtime(mode="LIVE").mode == "live"   # normalised lower-case
