"""A test's side task (the "person" who signs in) fails where it can be read."""

import asyncio

import pytest

from tests.side_task import side_task


async def test_a_failed_side_task_is_noted_on_the_failure_of_the_test():
    async def person():
        raise AssertionError("no banner button appeared")

    with pytest.raises(RuntimeError) as caught:
        async with side_task(person()):
            await asyncio.sleep(0.05)
            raise RuntimeError("nobody signed in within 60 s")
    notes = "\n".join(caught.value.__notes__)
    assert "no banner button appeared" in notes
    assert "AssertionError" in notes


async def test_a_side_task_still_running_tells_where_it_waits():
    async def waiting_for_the_launch():
        await asyncio.sleep(3600)

    async def person():
        await waiting_for_the_launch()

    with pytest.raises(RuntimeError) as caught:
        async with side_task(person()) as task:
            await asyncio.sleep(0.05)
            raise RuntimeError("nobody signed in within 60 s")
    assert task.cancelled()
    notes = "\n".join(caught.value.__notes__)
    assert "still running" in notes
    assert "waiting_for_the_launch" in notes


async def test_a_side_task_the_body_awaited_is_not_noted_twice():
    async def person():
        raise AssertionError("no launch #2")

    with pytest.raises(AssertionError) as caught:
        async with side_task(person()) as task:
            await task
    assert not getattr(caught.value, "__notes__", [])


async def test_a_side_task_failing_after_a_clean_body_fails_the_test():
    async def person():
        raise AssertionError("late")

    with pytest.raises(AssertionError, match="late"):
        async with side_task(person()):
            await asyncio.sleep(0.05)


async def test_a_clean_side_task_is_quiet():
    async def person():
        return 1

    async with side_task(person()) as task:
        await task
    assert task.result() == 1
