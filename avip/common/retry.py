"""Retry-with-backoff for transient failures (Upgrade item 7 — self-healing).

Deterministic and dependency-free. Wrap a transient operation (video decode, DB
write, object storage, email, model call) so a temporary blip is retried with
exponential backoff instead of failing the run. `sleep` is injectable so tests run
instantly. This is self-HEALING, not self-evolving — it only re-attempts the same
call; it never rewrites behaviour.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Iterable, TypeVar

log = logging.getLogger("avip.retry")

T = TypeVar("T")


def retry_call(fn: Callable[[], T], *,
               attempts: int = 3,
               base_delay: float = 0.5,
               backoff: float = 2.0,
               max_delay: float = 30.0,
               exceptions: Iterable[type[BaseException]] = (Exception,),
               sleep: Callable[[float], None] = time.sleep,
               on_retry: Callable[[int, BaseException, float], None] | None = None,
               label: str = "operation") -> T:
    """Call `fn` up to `attempts` times, backing off between tries.

    Raises the LAST exception if every attempt fails (the caller decides whether that
    is fatal or fail-soft). `attempts` is total tries (>=1). Delays: base_delay,
    base_delay*backoff, ... capped at max_delay.
    """
    attempts = max(1, int(attempts))
    exc_types = tuple(exceptions)
    last: BaseException | None = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except exc_types as e:                 # noqa: PERF203 — retry loop
            last = e
            if i >= attempts:
                log.error("%s failed after %d attempt(s): %s", label, attempts, e)
                raise
            delay = min(max_delay, base_delay * (backoff ** (i - 1)))
            log.warning("%s failed (attempt %d/%d): %s — retrying in %.2fs",
                        label, i, attempts, e, delay)
            if on_retry is not None:
                try:
                    on_retry(i, e, delay)
                except Exception:              # a bad callback must not break retry
                    pass
            if delay > 0:
                sleep(delay)
    # Unreachable (loop either returns or raises), but keeps type-checkers happy:
    assert last is not None
    raise last


def with_retry(*, attempts: int = 3, base_delay: float = 0.5, backoff: float = 2.0,
               exceptions: Iterable[type[BaseException]] = (Exception,),
               sleep: Callable[[float], None] = time.sleep, label: str | None = None):
    """Decorator form of :func:`retry_call`."""
    def deco(fn):
        def wrapper(*args, **kwargs):
            return retry_call(lambda: fn(*args, **kwargs), attempts=attempts,
                              base_delay=base_delay, backoff=backoff,
                              exceptions=exceptions, sleep=sleep,
                              label=label or getattr(fn, "__name__", "operation"))
        wrapper.__name__ = getattr(fn, "__name__", "wrapper")
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return deco
