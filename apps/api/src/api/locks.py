"""A set of locks, one per key, that forgets a key once nobody uses it any more.

Two requests that need the same thing must not do the same slow work twice. Asking the next
question for one session, or extracting the skills of one preparation, are such jobs: while one
request does it, an identical request should wait and then reuse the result.

These locks live in the memory of one server process, so they only help when the API runs as a single process (`--workers 1`).
The session store protects the data itself across processes; these locks only avoid wasted model calls.
"""

import asyncio
from collections.abc import Hashable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncGenerator


@dataclass
class _Entry:
    """One key's lock, and how many callers hold it or are waiting for it."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class KeyedLocks:
    """Hand out one `asyncio.Lock` per key, for example per session id.

    Use it as ``async with locks.hold(session_id): ...``. Callers with the same key run one
    after the other; callers with different keys never wait for each other. A key is removed
    from the table when its last user leaves, so the table does not grow without limit.
    """

    def __init__(self) -> None:
        """Start with no keys."""
        self._entries: dict[Hashable, _Entry] = {}

    @property
    def open_keys(self) -> int:
        """How many keys are held or waited for right now. Zero when the locks are idle."""
        return len(self._entries)

    @asynccontextmanager
    async def hold(self, key: Hashable) -> AsyncGenerator[None]:
        """Wait for the key's lock, run the block while holding it, then release it.

        The lock is released, and the key forgotten if nobody else wants it, even when the
        block raises or the waiting caller is cancelled.
        """
        entry = self._entries.get(key)
        if entry is None:
            entry = self._entries[key] = _Entry()
        entry.users += 1
        try:
            async with entry.lock:
                yield
        finally:
            entry.users -= 1
            if entry.users == 0:
                del self._entries[key]
