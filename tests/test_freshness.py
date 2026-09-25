"""Tests for the KB / report freshness check (audit item 5)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from avip.common.freshness import kb_freshness, check_kb_files, FreshnessResult

BASE = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def test_fresh_when_kb_newer_than_all_sources():
    r = kb_freshness(BASE, [BASE - timedelta(hours=1), BASE - timedelta(minutes=5)],
                     now=BASE + timedelta(minutes=1))
    assert r.fresh and not r.stale and bool(r) is True


def test_stale_when_a_source_changed_after_build():
    r = kb_freshness(BASE, [BASE + timedelta(hours=2)], now=BASE + timedelta(hours=3))
    assert r.stale and not r.fresh
    assert any("rebuild needed" in x for x in r.reasons)


def test_stale_when_ttl_exceeded():
    r = kb_freshness(BASE, [BASE - timedelta(hours=1)], ttl_hours=24,
                     now=BASE + timedelta(hours=30))
    assert r.stale
    assert any("TTL" in x for x in r.reasons)
    assert r.age_hours == 30.0


def test_missing_timestamp_is_stale_failsoft():
    r = kb_freshness(None, [BASE])
    assert r.stale and not r.fresh


def test_epoch_seconds_inputs_accepted():
    kb = BASE.timestamp()
    r = kb_freshness(kb, [kb - 3600], now=kb + 60)
    assert r.fresh


def test_check_kb_files_missing_kb(tmp_path):
    r = check_kb_files(tmp_path / "nope.html", [], now=BASE)
    assert r.stale and "missing" in r.reasons[0].lower()


def test_check_kb_files_detects_newer_source(tmp_path):
    kb = tmp_path / "report.html"
    src = tmp_path / "all_findings.json"
    kb.write_text("kb")
    src.write_text("data")
    # make the source clearly newer than the KB artefact
    import os
    kb_time = 1_000_000.0
    os.utime(kb, (kb_time, kb_time))
    os.utime(src, (kb_time + 3600, kb_time + 3600))
    r = check_kb_files(kb, [src])
    assert r.stale
