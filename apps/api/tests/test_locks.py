"""Tests for KeyedLocks: one lock per key, forgotten once nobody uses it."""

import asyncio

import pytest
from api.locks import KeyedLocks


@pytest.fixture
def anyio_backend():
    """Run these asynchronous tests on asyncio only."""
    return "asyncio"


@pytest.mark.anyio
async def test_two_holders_of_the_same_key_run_one_after_the_other():
    """The second caller for a key waits until the first one has left."""
    locks = KeyedLocks()
    order: list[str] = []
    first_inside = asyncio.Event()
    let_first_leave = asyncio.Event()

    async def first() -> None:
        async with locks.hold("session-1"):
            order.append("first in")
            first_inside.set()
            await let_first_leave.wait()
            order.append("first out")

    async def second() -> None:
        await first_inside.wait()
        async with locks.hold("session-1"):
            order.append("second in")

    tasks = [asyncio.create_task(first()), asyncio.create_task(second())]
    await first_inside.wait()
    await asyncio.sleep(0.01)
    assert order == ["first in"]

    let_first_leave.set()
    await asyncio.gather(*tasks)

    assert order == ["first in", "first out", "second in"]


@pytest.mark.anyio
async def test_different_keys_do_not_wait_for_each_other():
    """A holder of one key never blocks a caller that needs another key."""
    locks = KeyedLocks()
    other_key_ran = asyncio.Event()

    # The timeout turns a deadlock (every key sharing one lock) into a failure, not a hang.
    async with asyncio.timeout(1):
        async with locks.hold("session-1"):
            async with locks.hold("session-2"):
                other_key_ran.set()

    assert other_key_ran.is_set()


@pytest.mark.anyio
async def test_a_key_is_forgotten_once_nobody_holds_or_waits_for_it():
    """The table of locks does not grow with every key ever seen."""
    locks = KeyedLocks()

    async with locks.hold("session-1"):
        assert locks.open_keys == 1

    assert locks.open_keys == 0


@pytest.mark.anyio
async def test_a_key_is_forgotten_even_when_the_body_raises():
    """An exception inside the block still releases the lock and forgets the key."""
    locks = KeyedLocks()

    with pytest.raises(RuntimeError):
        async with locks.hold("session-1"):
            raise RuntimeError("boom")

    assert locks.open_keys == 0
    async with locks.hold("session-1"):
        pass


@pytest.mark.anyio
async def test_a_cancelled_waiter_leaves_the_lock_usable_and_forgets_the_key():
    """If a caller is cancelled while waiting, the holder and the next caller are unaffected."""
    locks = KeyedLocks()
    holder_inside = asyncio.Event()
    let_holder_leave = asyncio.Event()

    async def holder() -> None:
        async with locks.hold("session-1"):
            holder_inside.set()
            await let_holder_leave.wait()

    async def waiter() -> None:
        async with locks.hold("session-1"):
            raise AssertionError("A cancelled waiter must never get the lock.")

    holder_task = asyncio.create_task(holder())
    await holder_inside.wait()
    waiter_task = asyncio.create_task(waiter())
    await asyncio.sleep(0.01)
    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    let_holder_leave.set()
    await holder_task

    assert locks.open_keys == 0
    async with locks.hold("session-1"):
        pass
