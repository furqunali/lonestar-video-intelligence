"""Tests for corrupt/failed-clip quarantine (Upgrade item 7)."""
from __future__ import annotations

import run_incoming as ri


def test_quarantine_moves_clip_with_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(ri, "QUARANTINE", tmp_path / "quarantine")
    monkeypatch.setattr(ri, "status", lambda *a, **k: None)     # isolate (no STATUS.txt)

    clip = tmp_path / "corrupt.wmv"
    clip.write_bytes(b"not a real video")

    dest = ri.quarantine_clip(clip, "analysis error / corrupt")
    assert dest is not None
    assert dest.exists()                        # moved into quarantine
    assert not clip.exists()                    # removed from incoming (won't re-loop)
    assert dest.parent == (tmp_path / "quarantine")
    sidecar = dest.with_suffix(dest.suffix + ".reason.txt")
    assert sidecar.exists()
    assert "corrupt" in sidecar.read_text(encoding="utf-8")


def test_quarantine_last_resort_unlink(tmp_path, monkeypatch):
    """If the move itself fails, the clip is still removed so it can't re-loop forever."""
    monkeypatch.setattr(ri, "QUARANTINE", tmp_path / "q")
    monkeypatch.setattr(ri, "status", lambda *a, **k: None)

    clip = tmp_path / "bad.wmv"
    clip.write_bytes(b"x")

    def boom(*a, **k):
        raise OSError("move failed")
    monkeypatch.setattr(ri.shutil, "move", boom)

    dest = ri.quarantine_clip(clip, "reason")
    assert dest is None
    assert not clip.exists()                    # last-resort unlink happened
