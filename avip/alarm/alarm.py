"""Incident alarm engine — beep + clip, split by run mode (test | live).

Design rules honoured:
  * Config-driven, no hardcoding (mode + thresholds + LCD command come from config).
  * Self-healing: every side effect (beep, open clip, LCD command) is wrapped so a
    failure is logged and the pipeline continues — the alarm can never crash a run.
  * Honest gate: fires ONLY on a real incident AND only when the incident confidence
    is >= alarm.confidence_min. A 'no incident' finding never triggers it.
  * On the Mesa LCD (LIVE mode) it shows ONLY the beep + clip — never HTML/reports.
"""
from __future__ import annotations

import logging
import os
import platform
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

log = logging.getLogger("avip.alarm")


def _safe_print(s: str) -> None:
    """Print that never crashes on a Windows cp1252 console (emoji/·/… → replaced)."""
    try:
        print(s, flush=True)
    except Exception:
        try:
            enc = sys.stdout.encoding or "utf-8"
            sys.stdout.write(s.encode(enc, "replace").decode(enc, "replace") + "\n")
            sys.stdout.flush()
        except Exception:
            pass


@dataclass
class AlarmResult:
    """What the alarm did — returned (never raised) so callers can log/test it."""
    fired: bool = False
    mode: str = "test"
    suppressed: bool = False
    reason: str = ""
    beeped: bool = False
    clip_shown: bool = False
    message: str = ""
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "fired": self.fired, "mode": self.mode, "suppressed": self.suppressed,
            "reason": self.reason, "beeped": self.beeped,
            "clip_shown": self.clip_shown, "message": self.message,
            "detail": self.detail,
        }


# --------------------------------------------------------------------------- #
#  Helpers (each fail-soft)
# --------------------------------------------------------------------------- #
def _cfg_get(alarm_cfg: Any, key: str, default):
    """Read a field from a pydantic model OR a plain dict OR fall back to default."""
    if alarm_cfg is None:
        return default
    if isinstance(alarm_cfg, Mapping):
        return alarm_cfg.get(key, default)
    return getattr(alarm_cfg, key, default)


def _incident_confidence(finding: Mapping) -> float:
    """Best available confidence for the incident. Curated/known incidents have no
    calibration score and are treated as fully confident (1.0)."""
    for k in ("alarm_confidence", "incident_confidence", "calib_confidence", "confidence"):
        v = finding.get(k) if isinstance(finding, Mapping) else None
        if isinstance(v, (int, float)):
            try:
                return max(0.0, min(1.0, float(v)))
            except Exception:
                pass
    return 1.0


def _describe(finding: Mapping) -> str:
    """One-line incident description: type · site · camera · timestamp."""
    def g(*keys, default="?"):
        for k in keys:
            v = finding.get(k)
            if v:
                return str(v)
        return default
    verdict = g("incident_verdict", "group", "category", default="incident")
    label = {"cash": "Cash theft", "void": "Cancelled-sale theft",
             "shoplift": "Group shoplifting"}.get(str(verdict).lower(), str(verdict).title())
    site = g("site", "location_id", "store")
    cam = g("camera", "register", "camera_id")
    when = g("start_clock", "date", "when", "clock", default="")
    parts = [label, f"site {site}", f"cam {cam}"]
    if when:
        parts.append(str(when))
    return "  -  ".join(parts)          # ASCII separator (Windows-console safe)


def _beep(freq: int, ms: int, repeats: int) -> bool:
    """Audible beep. winsound on Windows; terminal bell elsewhere. Never raises."""
    ok = False
    try:
        if platform.system() == "Windows":
            import winsound  # stdlib, Windows only
            for _ in range(max(1, repeats)):
                winsound.Beep(int(freq), int(ms))
                ok = True
        else:
            for _ in range(max(1, repeats)):
                sys.stdout.write("\a")
                sys.stdout.flush()
                ok = True
    except Exception as e:                     # no audio device / headless / blocked
        log.warning("alarm beep failed (continuing): %s", e)
    return ok


def _open_clip_local(clip: Path) -> bool:
    """Show the clip on THIS computer (TEST mode). Never raises."""
    try:
        if not clip or not Path(clip).exists():
            log.warning("alarm: clip not found, skipping display: %s", clip)
            return False
        if platform.system() == "Windows":
            os.startfile(str(clip))            # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(clip)])
        else:
            subprocess.Popen(["xdg-open", str(clip)])
        return True
    except Exception as e:
        log.warning("alarm: could not open clip (continuing): %s", e)
        return False


def _show_clip_lcd(clip: Path, lcd_cmd: str | None) -> bool:
    """Show the clip on the Mesa LCD (LIVE mode) ONLY — beep + clip, never HTML.

    lcd_cmd is a config string with a "{clip}" placeholder. Until it is set (LCD not
    wired yet) we log what WOULD be shown so LIVE mode is safe to run today.
    """
    try:
        if not lcd_cmd:
            log.info("alarm[LIVE]: would show clip on Mesa LCD (no lcd_player_cmd set): %s", clip)
            return False
        cmd = lcd_cmd.replace("{clip}", str(clip))
        subprocess.Popen(shlex.split(cmd))
        return True
    except Exception as e:
        log.warning("alarm[LIVE]: LCD display failed (continuing): %s", e)
        return False


# --------------------------------------------------------------------------- #
#  Public entry point
# --------------------------------------------------------------------------- #
def raise_incident_alarm(finding: Mapping, clip_path: str | Path | None,
                         *, mode: str = "test", alarm_cfg: Any = None,
                         lcd_player_cmd: str | None = None) -> AlarmResult:
    """Raise the incident alarm for one detected incident. Returns an AlarmResult;
    NEVER raises (self-healing).

    finding      : the incident finding dict (must be a real incident).
    clip_path    : path to the incident clip to show.
    mode         : 'test' (this PC) or 'live' (Mesa LCD).
    alarm_cfg    : the Alarm config model/dict (enabled, confidence_min, beep, ...).
    lcd_player_cmd: LIVE-mode command with a "{clip}" placeholder.
    """
    mode = (mode or "test").strip().lower()
    res = AlarmResult(mode=mode)
    try:
        if not isinstance(finding, Mapping):
            res.suppressed = True
            res.reason = "no finding provided"
            return res

        # Gate 1 — enabled
        if not _cfg_get(alarm_cfg, "enabled", True):
            res.suppressed = True
            res.reason = "alarm disabled in config"
            return res

        # Gate 2 — must be a real incident (never fire on a 'no incident' clip)
        if finding.get("incident_detected") is False:
            res.suppressed = True
            res.reason = "no incident — alarm suppressed"
            return res

        # Gate 3 — confidence threshold
        conf = _incident_confidence(finding)
        thr = float(_cfg_get(alarm_cfg, "confidence_min", 0.6))
        if conf < thr:
            res.suppressed = True
            res.reason = f"confidence {conf:.2f} < threshold {thr:.2f}"
            res.detail["confidence"] = conf
            return res

        msg = _describe(finding)
        res.message = msg
        res.detail["confidence"] = conf
        clip = Path(clip_path) if clip_path else None

        # Beep (both modes)
        if _cfg_get(alarm_cfg, "beep", True):
            res.beeped = _beep(int(_cfg_get(alarm_cfg, "beep_freq_hz", 880)),
                               int(_cfg_get(alarm_cfg, "beep_ms", 600)),
                               int(_cfg_get(alarm_cfg, "beep_repeats", 3)))

        # Visual: on-screen banner (TEST) or LCD (LIVE). ASCII only + safe print so a
        # Windows cmd console can never crash the alarm on an emoji/unicode char.
        banner = (f"\n{'='*64}\n  *** INCIDENT ALARM  ({mode.upper()}) ***\n"
                  f"  {msg}\n  Confidence: {conf:.0%}\n{'='*64}")
        if mode == "live":
            # Mesa LCD: ONLY beep + clip. No HTML / reports / dashboards here.
            _safe_print(banner)                # console log on the server, not the LCD
            if _cfg_get(alarm_cfg, "show_clip", True):
                res.clip_shown = _show_clip_lcd(clip, lcd_player_cmd)
        else:
            # TEST: show the incident + clip on this computer.
            _safe_print(banner)
            if _cfg_get(alarm_cfg, "show_clip", True):
                res.clip_shown = _open_clip_local(clip)

        res.fired = True
        return res
    except Exception as e:                     # absolute last-resort guard
        log.error("alarm failed hard (continuing): %s", e)
        res.suppressed = True
        res.reason = f"error: {e}"
        return res
