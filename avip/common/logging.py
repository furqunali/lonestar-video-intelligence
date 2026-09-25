"""Structured logging (structlog) with run_id / event_id binding.

Observability rule (spec §10.5): structlog everywhere, carrying run_id and
event_id so a single dump's journey through the pipeline is traceable.
"""
from __future__ import annotations

import logging
import sys

import structlog

_CONFIGURED = False


def configure(level: str = "INFO") -> None:
    """Configure structlog once. Human-readable console output for the PoC."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(format="%(message)s", stream=sys.stderr,
                        level=getattr(logging, level.upper(), logging.INFO))
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None, **bind):
    """Return a bound structlog logger. Pass run_id=... etc. to bind context."""
    configure()
    log = structlog.get_logger(name)
    return log.bind(**bind) if bind else log
