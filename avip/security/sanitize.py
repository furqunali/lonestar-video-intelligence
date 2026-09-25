"""Validate/sanitise external inputs (Upgrade item 8).

Filenames, path components and OCR text are untrusted. Clean them before use so
they can never traverse the filesystem (../, absolute, drive letters) or carry
control characters into a report/DB. We never pass untrusted paths to a shell.
"""
from __future__ import annotations

import re

_UNSAFE_COMPONENT = re.compile(r"[\\/]")
_KEEP_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_component(name: str) -> str:
    """Return a SAFE single path component or raise ValueError. Rejects traversal,
    absolute paths, drive letters and separators — use for a per-site folder name."""
    n = str(name).strip().replace("\\", "/")
    if (not n or n in (".", "..") or "/" in n or ":" in n
            or n.startswith("~") or n.startswith(".")):
        raise ValueError(f"unsafe path component: {name!r}")
    return n


def sanitize_filename(name: str, *, default: str = "file", max_len: int = 120) -> str:
    """Reduce any string to a safe flat filename: strip directories, drop unusual
    characters, block traversal. Always returns a non-empty name (never a path)."""
    base = _UNSAFE_COMPONENT.split(str(name))[-1]          # last path segment only
    base = _KEEP_FILENAME.sub("_", base).strip(" ._")
    base = base or default
    if base in (".", ".."):
        base = default
    return base[:max_len]


def sanitize_text(text: str, *, max_len: int = 4000) -> str:
    """Clean OCR / external text: drop control chars (keep newlines/tabs), collapse
    nothing, cap length. Safe to embed in a report or store in the DB."""
    if text is None:
        return ""
    s = _CONTROL.sub("", str(text))
    if len(s) > max_len:
        s = s[:max_len]
    return s
