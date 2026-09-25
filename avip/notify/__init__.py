"""Notification targets for reports & alerts (Upgrade item 2).

Reports/HTML go to the shared drive for a FIXED recipient list ONLY, and NEVER to
the Mesa LCD. This package exposes that fixed list (item 5's email agent sends only
to it) and a hard guard that reports never target the LCD.
"""
from .email import EmailResult, EmailSettings, load_email_settings, send_report_email
from .recipients import (
    RECIPIENTS_NEVER_ON_LCD,
    recipient_emails,
    report_recipients,
    reports_allowed_on_lcd,
)

__all__ = [
    "report_recipients",
    "recipient_emails",
    "reports_allowed_on_lcd",
    "RECIPIENTS_NEVER_ON_LCD",
    "send_report_email",
    "load_email_settings",
    "EmailSettings",
    "EmailResult",
]
