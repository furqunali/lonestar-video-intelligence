"""Tests for retry-with-backoff (Upgrade item 7). Sleep is injected so tests are instant."""
from __future__ import annotations

import pytest

from avip.common.retry import retry_call, with_retry


def _recorder():
    slept: list[float] = []
    return slept, (lambda d: slept.append(d))


def test_succeeds_first_try_no_sleep():
    slept, sleep = _recorder()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    assert retry_call(fn, sleep=sleep) == "ok"
    assert calls["n"] == 1
    assert slept == []


def test_retries_then_succeeds():
    slept, sleep = _recorder()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    assert retry_call(fn, attempts=5, base_delay=1.0, backoff=2.0, sleep=sleep) == "ok"
    assert calls["n"] == 3
    assert slept == [1.0, 2.0]                 # backoff: 1.0, then 2.0


def test_raises_last_after_all_attempts():
    slept, sleep = _recorder()

    def fn():
        raise RuntimeError("still down")

    with pytest.raises(RuntimeError, match="still down"):
        retry_call(fn, attempts=3, base_delay=0.5, sleep=sleep)
    assert len(slept) == 2                      # slept between the 3 attempts


def test_only_listed_exceptions_are_retried():
    slept, sleep = _recorder()

    def fn():
        raise KeyError("not retried")

    with pytest.raises(KeyError):
        retry_call(fn, attempts=3, exceptions=(ValueError,), sleep=sleep)
    assert slept == []                          # KeyError not in list -> no retry


def test_max_delay_caps_backoff():
    slept, sleep = _recorder()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 4:
            raise ValueError("x")
        return 1

    retry_call(fn, attempts=6, base_delay=10.0, backoff=10.0, max_delay=15.0, sleep=sleep)
    assert slept == [10.0, 15.0, 15.0]          # 10, then capped at 15


def test_with_retry_decorator():
    slept, sleep = _recorder()
    calls = {"n": 0}

    @with_retry(attempts=3, base_delay=0.1, sleep=sleep)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise OSError("blip")
        return "done"

    assert flaky() == "done"
    assert calls["n"] == 2
