"""Input sanitization (spec §10.2).

Every external path/filename (DVR dumps, config values) is validated and
normalized before use. Untrusted paths are NEVER passed to the shell/ffmpeg,
and no path may escape its intended base directory (no traversal).
"""
from __future__ import annotations

import re
from pathlib import Path

# Conservative filename allow-list: letters, digits, space, dot, dash, underscore.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9 ._-]+$")


class UnsafePathError(ValueError):
    """Raised when a path escapes its base or a filename looks malicious."""


def safe_filename(name: str) -> str:
    """Validate a single path component (no separators, no traversal)."""
    if not name or name in (".", ".."):
        raise UnsafePathError(f"illegal filename: {name!r}")
    if "/" in name or "\\" in name or "\x00" in name:
        raise UnsafePathError(f"filename contains a path separator: {name!r}")
    if not _SAFE_NAME.match(name):
        raise UnsafePathError(f"filename has disallowed characters: {name!r}")
    return name


def resolve_within(base: Path | str, candidate: Path | str) -> Path:
    """Resolve ``candidate`` and guarantee it stays inside ``base``.

    Returns the resolved absolute path, or raises UnsafePathError on traversal.
    """
    base_r = Path(base).resolve()
    cand_r = (base_r / candidate).resolve() if not Path(candidate).is_absolute() \
        else Path(candidate).resolve()
    # Python 3.9+: is_relative_to
    if not cand_r.is_relative_to(base_r):
        raise UnsafePathError(f"path escapes base: {cand_r} not within {base_r}")
    return cand_r
