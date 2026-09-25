"""Tests for the dedicated AI shared-drive folder helpers (Upgrade item 3)."""
from __future__ import annotations

from pathlib import Path

import pytest

from avip.common import paths as P
from avip.common.config import load_config


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    """A config whose AI root is an isolated temp folder."""
    monkeypatch.setenv("AI_SHARED_ROOT", str(tmp_path / "ai"))
    return load_config()


def test_root_and_subdirs_derived(cfg, tmp_path):
    root = P.ai_root(cfg)
    assert root == (tmp_path / "ai").resolve()
    assert P.incoming_dir(cfg) == root / "incoming"
    assert P.reports_dir(cfg) == root / "reports"
    assert P.evidence_dir(cfg) == root / "evidence"


def test_ensure_dirs_creates_structure(cfg):
    root = P.ensure_dirs(cfg)
    assert (root / "incoming").is_dir()
    assert (root / "reports").is_dir()
    assert (root / "evidence").is_dir()
    # per-site incoming from the store list (0008 / 0025 / 0028)
    for site in ("0008", "0025", "0028"):
        assert (root / "incoming" / site).is_dir()


def test_site_incoming_dir(cfg):
    d = P.site_incoming_dir("0008", cfg)
    assert d == P.incoming_dir(cfg) / "0008"


def test_within_root_true_for_inside(cfg):
    assert P.within_root(P.incoming_dir(cfg) / "0008" / "clip.mp4", cfg)
    assert P.within_root(P.ai_root(cfg), cfg)          # the root itself


def test_within_root_false_for_outside(cfg, tmp_path):
    assert not P.within_root(tmp_path / "somewhere_else" / "x.mp4", cfg)
    assert not P.within_root("C:/Windows/system32", cfg)


def test_ensure_within_root_rejects_outside(cfg, tmp_path):
    inside = P.ensure_within_root(P.reports_dir(cfg) / "r.html", cfg)
    assert isinstance(inside, Path)
    with pytest.raises(ValueError):
        P.ensure_within_root(tmp_path / "outside.txt", cfg)


def test_site_name_rejects_traversal(cfg):
    for bad in ("..", "../evil", "a/b", "C:/x", "~root"):
        with pytest.raises(ValueError):
            P.site_incoming_dir(bad, cfg)


def test_default_root_is_local_path():
    """With no env override, the default root is the local data/ai_shared path."""
    import os
    os.environ.pop("AI_SHARED_ROOT", None)
    cfg = load_config()
    assert cfg.settings.paths.ai_shared_root == "data/ai_shared"
