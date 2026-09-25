"""Role hierarchy for the chat support system."""
from __future__ import annotations

ROLES = ("staff", "manager", "director", "admin")
_RANK = {"staff": 0, "manager": 1, "director": 2, "admin": 3}


def normalize(role: str | None) -> str:
    r = (role or "staff").strip().lower()
    return r if r in ROLES else "staff"


def rank(role: str | None) -> int:
    return _RANK.get(normalize(role), 0)


def at_least(role: str | None, required: str) -> bool:
    """True if `role` is at or above `required` in the hierarchy."""
    return rank(role) >= rank(required)
