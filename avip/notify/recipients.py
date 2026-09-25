"""The FIXED report/alert recipient list + the 'never on the LCD' rule (item 2).

Only people on this list ever receive a report or alert (item 5's email agent uses
`recipient_emails`). Reports/HTML never go to the Mesa LCD — `reports_allowed_on_lcd`
is always False and is validated at config load.
"""
from __future__ import annotations

from typing import Any

from avip.common.config import Config, Recipient, get_config

# A module constant other code can assert on. Reports/HTML/dashboards must never be
# shown on the Mesa LCD — the LCD is for the incident alarm (beep + clip) only.
RECIPIENTS_NEVER_ON_LCD = True


def _cfg(config: Config | None) -> Config:
    return config if config is not None else get_config()


def report_recipients(config: Config | None = None) -> list[Recipient]:
    """The fixed, active recipient list from config."""
    return _cfg(config).settings.reports.active_recipients()


def recipient_emails(config: Config | None = None) -> list[str]:
    """Active recipients that have an email — the exact send-to list for item-5 SMTP.
    De-duplicated, order preserved. Recipients without an email are skipped."""
    seen: set[str] = set()
    out: list[str] = []
    for e in _cfg(config).settings.reports.recipient_emails():
        low = e.lower()
        if low not in seen:
            seen.add(low)
            out.append(e)
    return out


def reports_allowed_on_lcd(config: Config | None = None) -> bool:
    """Hard rule: reports/HTML are NEVER allowed on the Mesa LCD. Always False."""
    # config.on_lcd is validated to be False at load; return False defensively.
    try:
        return bool(_cfg(config).settings.reports.on_lcd)
    except Exception:
        return False
