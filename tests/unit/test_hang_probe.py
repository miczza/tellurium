"""The hang probe: where tellurium and Chrome were when a command got no reply."""

from __future__ import annotations

import asyncio

from tests.await_chain import awaiting, tasks_report


async def test_every_task_is_listed_with_the_awaits_it_is_suspended_in():
    gate = asyncio.Event()

    async def waiting_for_chrome():
        await gate.wait()

    async def a_command_of_the_test():
        await waiting_for_chrome()

    task = asyncio.create_task(a_command_of_the_test(), name="the-test-command")
    await asyncio.sleep(0)
    try:
        report = tasks_report()
    finally:
        gate.set()
        await task
    assert "the-test-command" in report
    block = report.split("the-test-command", 1)[1]
    assert block.index("a_command_of_the_test") < block.index("waiting_for_chrome")
    # The task that asks is not in its own report.
    assert report.startswith("1 task(s)")


async def test_the_chain_names_the_future_it_ends_on():
    future = asyncio.get_running_loop().create_future()

    async def on_a_future():
        await future

    coro = on_a_future()
    task = asyncio.ensure_future(coro)
    await asyncio.sleep(0)
    try:
        lines = awaiting(coro)
    finally:
        future.set_result(None)
        await task
    assert "on_a_future" in lines[0]
    assert "Future" in lines[-1]
