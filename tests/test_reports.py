"""Tests for reports destination + fixed recipient list (Upgrade item 2)."""
from __future__ import annotations

import pytest

from avip.common.config import Recipient, Reports, load_config
from avip.notify import (
    recipient_emails,
    report_recipients,
    reports_allowed_on_lcd,
)


# --- Reports model logic ------------------------------------------------- #
def test_reports_never_on_lcd_is_rejected():
    with pytest.raises(Exception):
        Reports(on_lcd=True)


def test_active_recipients_and_emails():
    r = Reports(recipients=[
        Recipient(name="A", role="director", email="a@example.com"),
        Recipient(name="B", role="site", email=""),               # no email yet
        Recipient(name="C", role="engineer", email="c@example.com", active=False),
    ])
    assert [x.name for x in r.active_recipients()] == ["A", "B"]   # C is inactive
    assert r.recipient_emails() == ["a@example.com"]                # only active w/ email


def test_default_reports_go_to_shared_drive_not_lcd():
    r = Reports()
    assert r.destination == "shared_drive"
    assert r.on_lcd is False


# --- real config (settings.yaml) ---------------------------------------- #
def test_config_recipient_list_loads():
    cfg = load_config()
    names = [r.name for r in report_recipients(cfg)]
    # the fixed list from settings.yaml
    assert "Ahsan" in names and "Furqan Ali" in names and "Mustafa" in names
    assert len(names) >= 4


def test_config_recipient_emails_only_filled_ones():
    cfg = load_config()
    emails = recipient_emails(cfg)
    assert "furqan@example.com" in emails
    assert "mustafa@example.com" in emails
    assert all("@" in e for e in emails)          # blanks are excluded
    assert len(emails) == len(set(e.lower() for e in emails))   # de-duplicated


def test_reports_not_allowed_on_lcd():
    assert reports_allowed_on_lcd(load_config()) is False
