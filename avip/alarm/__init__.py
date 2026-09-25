"""Incident alarm (Upgrade item 1).

Raises an audible + visual alarm when a real incident is detected ABOVE the
confidence threshold. Config-driven run mode:
  - TEST (Furqan's PC): beep + on-screen incident banner + open the clip here.
  - LIVE (Mesa server): beep + clip on the Mesa LCD ONLY — never reports/HTML.

Self-healing: any failure (no audio device, missing player, bad path) is caught
and logged; the alarm NEVER raises into the pipeline.
"""
from .alarm import AlarmResult, raise_incident_alarm

__all__ = ["AlarmResult", "raise_incident_alarm"]
