"""Tests for the email agent (Upgrade item 5) — using a fake SMTP (no network)."""
from __future__ import annotations

import pytest

from avip.common.config import load_config
from avip.notify import EmailSettings, load_email_settings, send_report_email
from avip.notify.email import _read_env_file


class FakeSMTP:
    """Captures what would be sent instead of touching the network."""
    def __init__(self, settings=None):
        self.started_tls = False
        self.logged_in = None
        self.sent = []
        self.quit_called = False

    def starttls(self, context=None):
        self.started_tls = True

    def login(self, user, pw):
        self.logged_in = (user, pw)

    def send_message(self, msg):
        self.sent.append(msg)

    def quit(self):
        self.quit_called = True


CONFIGURED = EmailSettings(host="smtp.example.com", port=587, user="ai@example.com",
                           password="secret", sender="ai@example.com", use_tls=True)


# --- settings from env --------------------------------------------------- #
def test_load_email_settings_from_env():
    s = load_email_settings(env={
        "SMTP_HOST": "smtp.example.com", "SMTP_PORT": "465",
        "SMTP_USER": "ai@example.com", "SMTP_PASSWORD": "pw",
        "SMTP_FROM": "ai@example.com", "SMTP_USE_TLS": "false"})
    assert s.host == "smtp.example.com" and s.port == 465
    assert s.sender == "ai@example.com" and s.use_tls is False
    assert s.configured is True


def test_not_configured_is_skipped_not_crash():
    r = send_report_email("Test", "body", settings=EmailSettings(),
                          recipients=["x@example.com"])
    assert r.skipped and not r.sent
    assert "not configured" in r.reason


def test_bad_port_falls_back_to_587():
    s = load_email_settings(env={"SMTP_HOST": "h", "SMTP_FROM": "f@x", "SMTP_PORT": "abc"})
    assert s.port == 587


# --- sending (fake SMTP) ------------------------------------------------- #
def test_send_builds_and_sends(tmp_path):
    report = tmp_path / "report.html"
    report.write_text("<h1>hi</h1>", encoding="utf-8")
    fake = FakeSMTP()
    r = send_report_email("Incident report", "See attached.",
                          report_path=report, clip_link="file:///clip.mp4",
                          recipients=["a@example.com", "b@example.com"],
                          settings=CONFIGURED, smtp_factory=lambda s: fake)
    assert r.sent and not r.skipped
    assert fake.logged_in == ("ai@example.com", "secret")
    assert fake.quit_called
    msg = fake.sent[0]
    assert msg["To"] == "a@example.com, b@example.com"
    assert msg["From"] == "ai@example.com"
    assert msg["Subject"] == "Incident report"
    body = msg.get_body(preferencelist=("plain",)).get_content()
    assert "clip.mp4" in body                          # evidence clip link included
    atts = [a.get_filename() for a in msg.iter_attachments()]
    assert "report.html" in atts                       # report attached


def test_recipients_default_to_fixed_list():
    fake = FakeSMTP()
    r = send_report_email("R", "b", settings=CONFIGURED, config=load_config(),
                          smtp_factory=lambda s: fake)
    assert r.sent
    # the fixed item-2 list (only entries with an email)
    assert "furqan@example.com" in r.recipients
    assert "mustafa@example.com" in r.recipients


def test_no_recipients_is_skipped():
    r = send_report_email("R", "b", settings=CONFIGURED, recipients=[],
                          smtp_factory=lambda s: FakeSMTP())
    assert r.skipped and "no recipients" in r.reason


def test_send_failure_is_soft():
    def boom(settings):
        raise RuntimeError("smtp down")
    r = send_report_email("R", "b", settings=CONFIGURED,
                          recipients=["a@example.com"], smtp_factory=boom)
    assert not r.sent and not r.skipped
    assert "send failed" in r.reason                   # logged + returned, never raised


# --- .env reader --------------------------------------------------------- #
def test_env_file_reader(tmp_path):
    p = tmp_path / ".env"
    p.write_text('# comment\nSMTP_HOST=smtp.example.com\nSMTP_FROM="ai@example.com"\n\n',
                 encoding="utf-8")
    d = _read_env_file(p)
    assert d["SMTP_HOST"] == "smtp.example.com"
    assert d["SMTP_FROM"] == "ai@example.com"            # quotes stripped
