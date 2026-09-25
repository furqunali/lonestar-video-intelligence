"""Tests for security & tamper protection (Upgrade item 8)."""
from __future__ import annotations

import pytest

from avip.common.config import load_config
from avip.security import (
    IntegrityError,
    backup_db_and_config,
    check_or_raise,
    compute_manifest,
    sanitize_component,
    sanitize_filename,
    sanitize_text,
    verify,
    write_manifest,
)
from avip.security.backup import _sqlite_path


# --- integrity ----------------------------------------------------------- #
def _tree(root):
    (root / "a.py").write_text("print(1)\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "b.yaml").write_text("x: 1\n", encoding="utf-8")
    return ["a.py", "sub/b.yaml"]


def test_manifest_verify_ok(tmp_path):
    files = _tree(tmp_path)
    m = compute_manifest(tmp_path, files)
    mpath = write_manifest(m, tmp_path / "manifest.json")
    res = verify(tmp_path, mpath)
    assert res.ok and not res.changed and not res.missing


def test_verify_detects_tamper(tmp_path):
    files = _tree(tmp_path)
    mpath = write_manifest(compute_manifest(tmp_path, files), tmp_path / "m.json")
    (tmp_path / "a.py").write_text("print(2)  # tampered\n", encoding="utf-8")
    res = verify(tmp_path, mpath)
    assert not res.ok
    assert "a.py" in res.changed


def test_verify_detects_missing(tmp_path):
    files = _tree(tmp_path)
    mpath = write_manifest(compute_manifest(tmp_path, files), tmp_path / "m.json")
    (tmp_path / "sub" / "b.yaml").unlink()
    res = verify(tmp_path, mpath)
    assert not res.ok
    assert "sub/b.yaml" in res.missing


def test_check_or_raise_noop_when_disabled():
    cfg = load_config()                          # integrity_check is false in settings
    assert check_or_raise(cfg).ok is True


def test_check_or_raise_refuses_without_manifest():
    cfg = load_config()
    cfg.settings.security.integrity_check = True
    cfg.settings.security.manifest_path = "security/does_not_exist_xyz.json"
    alerts = []
    with pytest.raises(IntegrityError):
        check_or_raise(cfg, alert=alerts.append)
    assert alerts                                # an alert was raised


# --- sanitize ------------------------------------------------------------ #
def test_sanitize_component_rejects_traversal():
    for bad in ("..", "../x", "a/b", "C:/x", "~root", ".hidden", ""):
        with pytest.raises(ValueError):
            sanitize_component(bad)
    assert sanitize_component("0008") == "0008"


def test_sanitize_filename_flattens_and_cleans():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename(r"C:\evil\clip .wmv") == "clip .wmv"
    assert sanitize_filename("") == "file"
    assert sanitize_filename("a" * 300).__len__() == 120


def test_sanitize_text_strips_control_chars():
    assert sanitize_text("hi\x00\x07 there\n") == "hi there\n"
    assert len(sanitize_text("x" * 5000, max_len=100)) == 100
    assert sanitize_text(None) == ""


# --- backup -------------------------------------------------------------- #
def test_sqlite_path_parsing():
    assert _sqlite_path("postgresql://x") is None
    p = _sqlite_path("sqlite:///data/avip.db")
    assert p is not None and p.name == "avip.db"


def test_backup_copies_config(tmp_path):
    res = backup_db_and_config(dest=tmp_path, stamp="TEST")
    assert res.ok
    # config/*.yaml were copied
    assert any(c.startswith("config/") for c in res.copied)
    assert (tmp_path / "TEST" / "config").is_dir()
