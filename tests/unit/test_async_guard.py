"""The guard that fails a hung async test before pytest-timeout ends the run."""

from __future__ import annotations

import asyncio

import pytest

from tests.async_guard import guard_seconds, guarded


async def test_a_hung_test_fails_with_a_timeout_naming_the_guard():
    async def hung():
        await asyncio.Event().wait()

    with pytest.raises(TimeoutError, match="pytest-timeout"):
        await guarded(hung, 0.1)()


async def test_the_test_own_timeout_passes_through():
    async def own():
        raise TimeoutError("mine")

    with pytest.raises(TimeoutError, match="mine"):
        await guarded(own, 5)()


async def test_arguments_and_result_pass_through():
    async def add(a, b=0):
        return a + b

    assert await guarded(add, 5)(1, b=2) == 3


def test_the_guard_comes_before_pytest_timeout():
    assert guard_seconds(120) == 105
    assert guard_seconds(None) is None and guard_seconds(0) is None and guard_seconds(10) is None


async def test_a_test_that_swallows_the_cancellation_still_fails():
    async def stubborn():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        return "late"

    with pytest.raises(TimeoutError, match="pytest-timeout"):
        await guarded(stubborn, 0.1)()


async def test_the_time_spent_in_setup_counts():
    import time

    async def slow():
        await asyncio.sleep(5)

    with pytest.raises(TimeoutError, match="pytest-timeout"):
        await asyncio.wait_for(guarded(slow, 1.0, lambda: time.monotonic() - 0.95)(), 0.5)
