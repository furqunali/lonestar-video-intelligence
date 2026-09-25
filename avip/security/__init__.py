"""Security & tamper protection (Upgrade item 8).

  * integrity  — hash key code/config vs a known-good manifest; refuse to run if a
                 file was tampered.
  * sanitize   — validate/clean external inputs (filenames, path components, OCR text)
                 so untrusted data can never traverse the filesystem or reach a shell.
  * backup     — scheduled copy of the DB + config (never secrets) to a backup folder.
"""
from .backup import backup_db_and_config
from .integrity import (
    IntegrityError,
    IntegrityResult,
    check_or_raise,
    compute_manifest,
    verify,
    write_manifest,
)
from .sanitize import sanitize_component, sanitize_filename, sanitize_text

__all__ = [
    "compute_manifest", "write_manifest", "verify", "check_or_raise",
    "IntegrityResult", "IntegrityError",
    "sanitize_component", "sanitize_filename", "sanitize_text",
    "backup_db_and_config",
]
