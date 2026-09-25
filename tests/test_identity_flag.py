"""Tests for the ArUco disable flag (Upgrade item 6).

The marker code stays in the pipeline (avip/cv/markers.py + test_markers.py still
cover it) but is OFF by default. Here we lock the flag's default + config wiring.
"""
from __future__ import annotations

from avip.common.config import Identity, load_config


def test_aruco_disabled_by_default():
    assert Identity().aruco_enabled is False


def test_config_loads_identity_flag_off():
    cfg = load_config()
    assert cfg.settings.identity.aruco_enabled is False


def test_flag_can_be_enabled_later():
    assert Identity(aruco_enabled=True).aruco_enabled is True


def test_pipeline_guards_on_the_flag():
    """The pipeline reads identity.aruco_enabled to decide whether to decode markers
    (kept, not removed). Assert the guard + the marker code both still exist."""
    import inspect

    import avip.pipeline as pipe
    src = inspect.getsource(pipe)
    assert "identity.aruco_enabled" in src           # the pipeline honours the flag
    assert "ArucoReader" in src                      # marker code NOT removed
    # markers module intact
    from avip.cv import markers
    assert hasattr(markers, "ArucoReader")
    assert hasattr(markers, "vote_marker")
