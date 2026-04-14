"""Idle simulator — micro-movements during waits."""
import asyncio
import random


class IdleSimulator:
    def __init__(self):
        self._last_mouse_pos = (400, 300)

    async def idle(self, tab, duration: float):
        end_time = asyncio.get_event_loop().time() + duration
        while asyncio.get_event_loop().time() < end_time:
            action = random.choices(["micro_move", "nothing"], weights=[0.3, 0.7])[0]
            if action == "micro_move":
                x, y = self._last_mouse_pos
                dx = random.gauss(0, 10)
                dy = random.gauss(0, 10)
                new_x, new_y = x + dx, y + dy
                await tab.mouse_move(new_x, new_y)
                self._last_mouse_pos = (new_x, new_y)
            await asyncio.sleep(random.uniform(0.5, 2.0))

    def update_pos(self, x: float, y: float):
        self._last_mouse_pos = (x, y)
