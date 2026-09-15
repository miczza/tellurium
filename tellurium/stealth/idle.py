"""Idle simulator — micro-movements during waits.

Wired to ``Browser.launch(stealth_idle=True)``; ``Tab.wait()`` routes its
sleep through :meth:`IdleSimulator.idle` so that a wait produces the kind of
low-amplitude background mouse activity a real user generates while reading,
instead of a perfectly still cursor. Design doc 05 "Idle Simulation".
"""

import asyncio
import random


class IdleSimulator:
    def __init__(self):
        self._last_mouse_pos = (400, 300)

    async def idle(self, tab, duration: float):
        """Idle for *duration* seconds, emitting occasional micro-moves.

        Never overshoots *duration*: the trailing sleep is clamped to the
        time actually left, so ``tab.wait(0.3)`` still returns in ~0.3s.
        """
        loop = asyncio.get_running_loop()
        end_time = loop.time() + duration
        while True:
            remaining = end_time - loop.time()
            if remaining <= 0:
                return
            action = random.choices(["micro_move", "nothing"], weights=[0.3, 0.7])[0]
            if action == "micro_move":
                x, y = self._last_mouse_pos
                dx = random.gauss(0, 10)
                dy = random.gauss(0, 10)
                # Keep the cursor inside the viewport; a negative coordinate
                # would be a giveaway on its own.
                new_x = max(1.0, x + dx)
                new_y = max(1.0, y + dy)
                try:
                    await tab.mouse_move(new_x, new_y)
                except Exception:  # noqa: BLE001
                    return  # tab/browser went away mid-wait
                self._last_mouse_pos = (new_x, new_y)
            remaining = end_time - loop.time()
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining, random.uniform(0.5, 2.0)))

    def update_pos(self, x: float, y: float):
        self._last_mouse_pos = (x, y)
