"""Per-user persistent memory for the chat assistant (backed by ChatStore)."""
from __future__ import annotations

import re

from avip.chat.store import ChatStore

_REMEMBER = re.compile(r"\bremember\s+(?:that\s+)?(?:my\s+)?([a-z ]{2,20})\s+is\s+(.+)", re.I)


class Memory:
    def __init__(self, store: ChatStore, now_fn):
        self.store = store
        self._now = now_fn

    def get(self, user_id: str) -> dict[str, str]:
        return self.store.get_memory(user_id)

    def set(self, user_id: str, key: str, value: str) -> None:
        self.store.set_memory(user_id, key.strip().lower(), value.strip(), self._now())

    def maybe_learn(self, user_id: str, text: str) -> str | None:
        """If the user said 'remember my X is Y', persist it. Returns a confirmation."""
        m = _REMEMBER.search(text or "")
        if not m:
            return None
        key, value = m.group(1).strip().lower(), m.group(2).strip().rstrip(".")
        self.set(user_id, key, value)
        return f"Got it — I'll remember your {key} is {value}."
