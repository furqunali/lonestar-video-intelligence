"""Email agent for reports & alerts (Upgrade item 5).

Sends a report (or incident alert) by SMTP using a GENERIC company example.com AI
account shared across projects. Rules honoured:
  * Every SMTP value — host / port / username / from-address / password — comes from
    the environment (.env) ONLY. Nothing is hardcoded here or in settings.yaml/git.
  * The from-address is a single value (SMTP_FROM) so it can be set later with no
    code change.
  * Sends ONLY to the fixed recipient list (item 2, avip.notify.recipient_emails).
  * Attaches the report (or includes a link); for an incident, includes the evidence
    clip link.
  * Fail-soft: if email is not configured or the send fails, it logs and returns —
    it NEVER raises into the pipeline.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Callable

from avip.common.config import REPO_ROOT, Config
from avip.notify.recipients import recipient_emails

log = logging.getLogger("avip.notify.email")

# Env var names (values live in .env only — see .env.example).
ENV = {
    "host": "SMTP_HOST",
    "port": "SMTP_PORT",
    "user": "SMTP_USER",
    "password": "SMTP_PASSWORD",
    "sender": "SMTP_FROM",
    "use_tls": "SMTP_USE_TLS",
}


def _read_env_file(path: Path) -> dict[str, str]:
    """Minimal .env reader (KEY=VALUE, # comments). No dependency; never raises."""
    out: dict[str, str] = {}
    try:
        if not path.exists():
            return out
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception as e:
        log.warning("could not read .env (%s): %s", path, e)
    return out


@dataclass
class EmailSettings:
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    sender: str = ""
    use_tls: bool = True

    @property
    def configured(self) -> bool:
        """Enough to attempt a send: a host and a from-address at minimum."""
        return bool(self.host and self.sender)


@dataclass
class EmailResult:
    sent: bool = False
    skipped: bool = False
    reason: str = ""
    recipients: list[str] = field(default_factory=list)
    subject: str = ""

    def as_dict(self) -> dict:
        return {"sent": self.sent, "skipped": self.skipped, "reason": self.reason,
                "recipients": list(self.recipients), "subject": self.subject}


def load_email_settings(env: dict | None = None, dotenv_path: Path | None = None) -> EmailSettings:
    """Build EmailSettings from the environment (.env merged in, but never overriding
    an already-set process env var). Secrets stay in env/.env — never in code."""
    import os

    merged: dict[str, str] = {}
    merged.update(_read_env_file(dotenv_path or (REPO_ROOT / ".env")))
    merged.update({k: v for k, v in (env if env is not None else os.environ).items()})

    def g(key: str, default: str = "") -> str:
        return str(merged.get(ENV[key], default) or default)

    port_raw = g("port", "587")
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = 587
    use_tls = g("use_tls", "true").lower() not in ("0", "false", "no", "off")
    return EmailSettings(host=g("host"), port=port, user=g("user"),
                         password=g("password"), sender=g("sender"), use_tls=use_tls)


def _build_message(settings: EmailSettings, subject: str, body: str,
                   recipients: list[str], report_path: Path | None,
                   report_link: str | None, clip_link: str | None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    lines = [body or ""]
    if report_link:
        lines += ["", f"Report: {report_link}"]
    if clip_link:
        lines += ["", f"Evidence clip: {clip_link}"]
    msg.set_content("\n".join(lines).strip() or "(no content)")
    # Attach the report file if a real path was given.
    if report_path:
        try:
            p = Path(report_path)
            if p.exists() and p.is_file():
                data = p.read_bytes()
                sub = "html" if p.suffix.lower() in (".html", ".htm") else "octet-stream"
                maintype = "text" if sub == "html" else "application"
                msg.add_attachment(data, maintype=maintype, subtype=sub, filename=p.name)
        except Exception as e:
            log.warning("could not attach report %s: %s", report_path, e)
    return msg


def send_report_email(subject: str, body: str = "", *,
                      report_path: str | Path | None = None,
                      report_link: str | None = None,
                      clip_link: str | None = None,
                      recipients: list[str] | None = None,
                      settings: EmailSettings | None = None,
                      config: Config | None = None,
                      smtp_factory: Callable[[EmailSettings], "smtplib.SMTP"] | None = None
                      ) -> EmailResult:
    """Send a report/alert email. Returns an EmailResult; NEVER raises (fail-soft).

    recipients defaults to the FIXED item-2 list. smtp_factory is injectable for tests.
    """
    res = EmailResult(subject=subject)
    try:
        settings = settings or load_email_settings()
        if recipients is None:
            recipients = recipient_emails(config)
        res.recipients = list(recipients)

        if not settings.configured:
            res.skipped = True
            res.reason = "email not configured (SMTP_HOST / SMTP_FROM missing in .env)"
            log.info("email skipped: %s", res.reason)
            return res
        if not recipients:
            res.skipped = True
            res.reason = "no recipients with an email in the fixed list"
            log.info("email skipped: %s", res.reason)
            return res

        msg = _build_message(settings, subject, body, recipients,
                             Path(report_path) if report_path else None,
                             report_link, clip_link)

        smtp = (smtp_factory(settings) if smtp_factory
                else _default_smtp(settings))
        try:
            if settings.use_tls and hasattr(smtp, "starttls"):
                try:
                    smtp.starttls(context=ssl.create_default_context())
                except Exception:
                    pass                       # server may already be implicit-TLS
            if settings.user and settings.password:
                smtp.login(settings.user, settings.password)
            smtp.send_message(msg)
        finally:
            try:
                smtp.quit()
            except Exception:
                pass

        res.sent = True
        log.info("report email sent to %d recipient(s)", len(recipients))
        return res
    except Exception as e:                     # fail-soft — never crash the pipeline
        res.sent = False
        res.reason = f"send failed: {e}"
        log.error("email send failed (continuing): %s", e)
        return res


def _default_smtp(settings: EmailSettings) -> "smtplib.SMTP":
    if settings.port == 465:
        return smtplib.SMTP_SSL(settings.host, settings.port,
                                context=ssl.create_default_context(), timeout=20)
    return smtplib.SMTP(settings.host, settings.port, timeout=20)
