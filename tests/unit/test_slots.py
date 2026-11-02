"""Slots: a cap shared by every loop and thread, handed out first come, first
served, with no polling; cancellation never loses a slot."""

from __future__ import annotations

import asyncio
import gc
import threading
import time

import pytest

from tellurium.session.slots import Slots


async def _until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.001)


def _wait(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached")
        time.sleep(0.001)


async def _enter(slots: Slots, name: str, order: list[str], hold: float = 0.0) -> None:
    async with slots.slot():
        order.append(name)
        await asyncio.sleep(hold)


async def test_free_slot_is_taken_at_once():
    slots = Slots(2)
    async with slots.slot(), slots.slot():
        assert slots.held == 2 and slots.waiting == 0
    assert slots.held == 0


async def test_waiters_enter_in_arrival_order():
    slots = Slots(1)
    order: list[str] = []
    gate = asyncio.Event()

    async def holder():
        async with slots.slot():
            await gate.wait()

    first = asyncio.create_task(holder())
    await _until(lambda: slots.held == 1)
    tasks = []
    for name in ("a", "b", "c"):
        tasks.append(asyncio.create_task(_enter(slots, name, order)))
        await _until(lambda: slots.waiting == len(tasks))
    gate.set()
    await asyncio.gather(first, *tasks)
    assert order == ["a", "b", "c"]
    assert slots.held == 0 and slots.waiting == 0


async def test_who_releases_and_asks_again_waits_its_turn():
    slots = Slots(1)
    order: list[str] = []
    gate = asyncio.Event()

    async def greedy():
        async with slots.slot():
            await gate.wait()
        await _enter(slots, "greedy-again", order)  # no await in between

    first = asyncio.create_task(greedy())
    await _until(lambda: slots.held == 1)
    other = asyncio.create_task(_enter(slots, "other", order))
    await _until(lambda: slots.waiting == 1)
    gate.set()
    await asyncio.gather(first, other)
    assert order == ["other", "greedy-again"]


def test_fifo_across_threads_with_their_own_loops():
    slots = Slots(1)
    order: list[str] = []
    errors: list[BaseException] = []

    def run(name: str) -> None:
        try:
            asyncio.run(_enter(slots, name, order))
        except BaseException as exc:  # noqa: BLE001 - reported by the test
            errors.append(exc)

    async def main():
        async with slots.slot():
            threads = []
            for name in ("t1", "t2", "t3"):
                thread = threading.Thread(target=run, args=(name,))
                thread.start()
                threads.append(thread)
                await _until(lambda: slots.waiting == len(threads))
        return threads

    threads = asyncio.run(main())
    for thread in threads:
        thread.join(5)
    assert not errors
    assert order == ["t1", "t2", "t3"]
    assert slots.held == 0 and slots.waiting == 0


def test_cap_holds_across_threads():
    slots = Slots(2)
    lock = threading.Lock()
    inside = [0]
    peak = [0]

    async def worker():
        for _ in range(20):
            async with slots.slot():
                with lock:
                    inside[0] += 1
                    peak[0] = max(peak[0], inside[0])
                await asyncio.sleep(0.001)
                with lock:
                    inside[0] -= 1

    threads = [threading.Thread(target=asyncio.run, args=(worker(),)) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert peak[0] == 2
    assert slots.held == 0 and slots.waiting == 0


async def test_cancelled_while_waiting_leaves_the_queue():
    slots = Slots(1)
    order: list[str] = []
    gate = asyncio.Event()

    async def holder():
        async with slots.slot():
            await gate.wait()

    first = asyncio.create_task(holder())
    await _until(lambda: slots.held == 1)
    gone = asyncio.create_task(_enter(slots, "gone", order))
    await _until(lambda: slots.waiting == 1)
    kept = asyncio.create_task(_enter(slots, "kept", order))
    await _until(lambda: slots.waiting == 2)
    gone.cancel()
    with pytest.raises(asyncio.CancelledError):
        await gone
    assert slots.waiting == 1
    gate.set()
    await asyncio.gather(first, kept)
    assert order == ["kept"]
    assert slots.held == 0 and slots.waiting == 0


@pytest.mark.parametrize("woken", [False, True])
async def test_cancelled_after_the_slot_was_given_passes_it_on(woken):
    """The slot is given, then the waiter is cancelled before it resumes
    (before or after its future is resolved): the next one gets the slot."""
    slots = Slots(1)
    order: list[str] = []
    held = slots.slot()
    await held.__aenter__()
    unlucky = asyncio.create_task(_enter(slots, "unlucky", order))
    await _until(lambda: slots.waiting == 1)
    nxt = asyncio.create_task(_enter(slots, "next", order))
    await _until(lambda: slots.waiting == 2)

    await held.__aexit__(None, None, None)  # gives the slot to `unlucky`, no suspension
    assert slots.waiting == 1 and slots.held == 1
    if woken:
        await asyncio.sleep(0)  # its future resolved, its step not yet run
    unlucky.cancel()
    with pytest.raises(asyncio.CancelledError):
        await unlucky
    await asyncio.wait_for(nxt, 1)
    assert order == ["next"]
    assert slots.held == 0 and slots.waiting == 0


async def test_cancelling_timeout_around_the_wait():
    slots = Slots(1)
    async with slots.slot():
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.05):
                async with slots.slot():
                    pytest.fail("entered a taken slot")
        assert slots.held == 1 and slots.waiting == 0
    assert slots.held == 0


async def test_timeout_while_waiting_takes_nothing_and_keeps_the_order():
    slots = Slots(1)
    order: list[str] = []
    held = slots.slot()
    await held.__aenter__()
    first = asyncio.create_task(_enter(slots, "first", order))
    await _until(lambda: slots.waiting == 1)
    with pytest.raises(TimeoutError, match="0.05"):
        async with slots.slot(timeout=0.05):
            pytest.fail("entered a taken slot")
    assert slots.held == 1 and slots.waiting == 1
    last = asyncio.create_task(_enter(slots, "last", order))
    await _until(lambda: slots.waiting == 2)
    await held.__aexit__(None, None, None)
    await asyncio.wait_for(asyncio.gather(first, last), 1)
    assert order == ["first", "last"]
    assert slots.held == 0 and slots.waiting == 0


@pytest.mark.parametrize("given_first", [True, False])
async def test_timeout_in_the_same_round_as_the_slot_loses_nothing(given_first):
    """The deadline passes while the slot is being handed over: the waiter
    either keeps it or passes it on, never both, never neither."""
    slots = Slots(1)
    order: list[str] = []
    held = slots.slot()
    await held.__aenter__()

    async def timed():
        async with slots.slot(timeout=0.05):
            order.append("timed")

    waiter = asyncio.create_task(timed())
    await _until(lambda: slots.waiting == 1)
    nxt = asyncio.create_task(_enter(slots, "next", order))
    await _until(lambda: slots.waiting == 2)
    time.sleep(0.08)  # the loop is blocked: the deadline is due with the next round
    if given_first:
        await held.__aexit__(None, None, None)  # wake-up queued before the due timer
        await asyncio.sleep(0)
    else:
        await asyncio.sleep(0)
        await held.__aexit__(None, None, None)
    results = await asyncio.wait_for(asyncio.gather(waiter, nxt, return_exceptions=True), 1)
    assert results[1] is None
    assert results[0] is None or isinstance(results[0], TimeoutError)
    assert order == (["timed", "next"] if results[0] is None else ["next"])
    assert slots.held == 0 and slots.waiting == 0


async def test_timeout_does_not_limit_the_block():
    slots = Slots(1)
    async with slots.slot(timeout=0.01):
        await asyncio.sleep(0.05)
    held = slots.slot()
    await held.__aenter__()
    stayed = []

    async def long_block():
        async with slots.slot(timeout=0.5):
            await asyncio.sleep(0.6)
            stayed.append(True)

    task = asyncio.create_task(long_block())
    await _until(lambda: slots.waiting == 1)
    await held.__aexit__(None, None, None)
    await asyncio.wait_for(task, 2)
    assert stayed == [True]
    assert slots.held == 0 and slots.waiting == 0


async def test_timeout_with_a_free_slot_enters_at_once():
    slots = Slots(1)
    async with slots.slot(timeout=0):
        assert slots.held == 1


async def test_waiter_of_a_closed_loop_is_skipped():
    """A loop closed with a waiter still queued cannot take the slot: the
    next one gets it, and the abandoned waiter gives nothing back later."""
    slots = Slots(1)
    order: list[str] = []
    held = slots.slot()
    await held.__aenter__()

    def strand() -> None:
        other = asyncio.new_event_loop()
        other.create_task(_enter(slots, "stranded", order))
        other.run_until_complete(asyncio.sleep(0.01))
        other.close()

    await asyncio.to_thread(strand)
    assert slots.waiting == 1
    after = asyncio.create_task(_enter(slots, "after", order))
    await _until(lambda: slots.waiting == 2)
    await held.__aexit__(None, None, None)
    await asyncio.wait_for(after, 1)
    gc.collect()  # the stranded task goes: its wait must not give a slot back
    assert order == ["after"]
    assert slots.held == 0 and slots.waiting == 0


async def test_three_opens_in_a_loop_each_get_a_turn_quickly():
    """The backlog case: max 1, three tasks taking a slot for 50 ms in a
    loop. With polling the one that released took it again and a waiter
    could wait over a second; first come, first served gives turns in order."""
    slots = Slots(1)
    start = time.monotonic()
    first_entry: dict[str, float] = {}
    turns: list[str] = []

    async def opener(name: str):
        for _ in range(3):
            async with slots.slot():
                first_entry.setdefault(name, time.monotonic() - start)
                turns.append(name)
                await asyncio.sleep(0.05)

    await asyncio.gather(*(opener(name) for name in ("a", "b", "c")))
    assert max(first_entry.values()) < 0.2
    assert turns == ["a", "b", "c"] * 3
    assert slots.held == 0
