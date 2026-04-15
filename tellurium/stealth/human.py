"""Human simulation algorithms: Wind Mouse, Sigma-Lognormal velocity, HumanTyping, HumanScroll, ActionTimer."""
import math
import random


# ---------------------------------------------------------------------------
# Wind Mouse
# ---------------------------------------------------------------------------

def wind_mouse(
    start_x: float, start_y: float,
    dest_x: float, dest_y: float,
    G_0: float = 9.0, W_0: float = 3.0,
    M_0: float = 15.0, D_0: float = 12.0,
) -> list[tuple[int, int]]:
    """Generate mouse trajectory using Wind Mouse algorithm.
    Returns list of (x, y) intermediate coordinates.
    """
    start = (int(round(start_x)), int(round(start_y)))
    points = [start]
    sqrt3 = math.sqrt(3)
    sqrt5 = math.sqrt(5)
    cx, cy = start_x, start_y
    vx = vy = wx = wy = 0.0
    max_vel = M_0

    while True:
        dist = math.hypot(dest_x - cx, dest_y - cy)
        if dist < 1:
            break
        w_mag = min(W_0, dist)
        if dist >= D_0:
            wx = wx / sqrt3 + (2 * random.random() - 1) * w_mag / sqrt5
            wy = wy / sqrt3 + (2 * random.random() - 1) * w_mag / sqrt5
        else:
            wx /= sqrt3
            wy /= sqrt3
            if max_vel < 3:
                max_vel = random.random() * 3 + 3
            else:
                max_vel /= sqrt5

        vx += wx + G_0 * (dest_x - cx) / dist
        vy += wy + G_0 * (dest_y - cy) / dist
        v_mag = math.hypot(vx, vy)
        if v_mag > max_vel:
            v_clip = max_vel / 2 + random.random() * max_vel / 2
            vx = (vx / v_mag) * v_clip
            vy = (vy / v_mag) * v_clip

        cx += vx
        cy += vy
        px, py = int(round(cx)), int(round(cy))
        if not points or (px, py) != points[-1]:
            points.append((px, py))

    dest = (int(round(dest_x)), int(round(dest_y)))
    if not points or points[-1] != dest:
        points.append(dest)
    return points


# ---------------------------------------------------------------------------
# Sigma-Lognormal velocity profile
# ---------------------------------------------------------------------------

def lognormal_pdf(t: float, mu: float, sigma: float) -> float:
    if t <= 0:
        return 0.0
    return (1.0 / (sigma * math.sqrt(2 * math.pi) * t)) * math.exp(
        -(math.log(t) - mu) ** 2 / (2 * sigma ** 2)
    )


def lognormal_speed_profile(
    num_points: int,
    mu: float = -0.5,
    sigma: float = 0.4,
    correction_ratio: float = 0.15,
    mu2: float = 0.8,
    sigma2: float = 0.3,
) -> list[float]:
    """Normalized cumulative positions [0, 1] along path."""
    t_values = [0.01 + i * 2.99 / (num_points - 1) for i in range(num_points)]
    speed = []
    for t in t_values:
        s = lognormal_pdf(t, mu, sigma)
        if correction_ratio > 0:
            s += correction_ratio * lognormal_pdf(t, mu2, sigma2)
        speed.append(s)
    cumulative = []
    total = 0.0
    for s in speed:
        total += s
        cumulative.append(total)
    for i in range(len(cumulative)):
        cumulative[i] /= total
    return cumulative


def apply_lognormal_velocity(
    path: list[tuple[int, int]],
    mu: float = -0.5,
    sigma: float = 0.4,
    base_interval_ms: float = 8.3,
) -> list[tuple[int, int, float]]:
    """Re-parametrize a Wind Mouse path with Sigma-Lognormal velocity.
    Returns [(x, y, timestamp_ms), ...].
    """
    if len(path) < 2:
        return [(path[0][0], path[0][1], 0.0)] if path else []

    # Compute arc lengths
    arc = [0.0]
    for i in range(1, len(path)):
        dx = path[i][0] - path[i - 1][0]
        dy = path[i][1] - path[i - 1][1]
        arc.append(arc[-1] + math.hypot(dx, dy))
    total_len = arc[-1]
    if total_len < 1:
        return [(path[0][0], path[0][1], 0.0)]
    arc_norm = [a / total_len for a in arc]

    n_out = max(len(path), int(total_len / 2))
    target_s = lognormal_speed_profile(n_out, mu, sigma)

    result = []
    t_ms = 0.0
    prev = (None, None)
    path_x = [p[0] for p in path]
    path_y = [p[1] for p in path]

    for s in target_s:
        idx = 0
        for j in range(len(arc_norm) - 1):
            if arc_norm[j + 1] >= s:
                idx = j
                break
        else:
            idx = len(arc_norm) - 2
        seg_len = arc_norm[idx + 1] - arc_norm[idx]
        frac = (s - arc_norm[idx]) / seg_len if seg_len > 0 else 0
        nx = path_x[idx] + frac * (path_x[idx + 1] - path_x[idx])
        ny = path_y[idx] + frac * (path_y[idx + 1] - path_y[idx])
        px, py = int(round(nx)), int(round(ny))
        if (px, py) != prev:
            result.append((px, py, t_ms))
            prev = (px, py)
        t_ms += base_interval_ms + random.gauss(0, 1.5)
    return result


# ---------------------------------------------------------------------------
# Mouse profiles
# ---------------------------------------------------------------------------

MOUSE_PROFILES = {
    "careful": {"wind": {"G_0": 7, "W_0": 1.5, "M_0": 10, "D_0": 15}, "mu": -0.3, "sigma": 0.5},
    "normal":  {"wind": {"G_0": 9, "W_0": 3,   "M_0": 15, "D_0": 12}, "mu": -0.5, "sigma": 0.4},
    "hasty":   {"wind": {"G_0": 12, "W_0": 5,  "M_0": 25, "D_0": 8},  "mu": -0.8, "sigma": 0.3},
}


# ---------------------------------------------------------------------------
# HumanTyping
# ---------------------------------------------------------------------------

FINGER_MAP = {
    'q': ('L', 0), 'a': ('L', 0), 'z': ('L', 0),
    'w': ('L', 1), 's': ('L', 1), 'x': ('L', 1),
    'e': ('L', 2), 'd': ('L', 2), 'c': ('L', 2),
    'r': ('L', 3), 'f': ('L', 3), 'v': ('L', 3),
    't': ('L', 3), 'g': ('L', 3), 'b': ('L', 3),
    'y': ('R', 3), 'h': ('R', 3), 'n': ('R', 3),
    'u': ('R', 3), 'j': ('R', 3), 'm': ('R', 3),
    'i': ('R', 2), 'k': ('R', 2), ',': ('R', 2),
    'o': ('R', 1), 'l': ('R', 1), '.': ('R', 1),
    'p': ('R', 0), ';': ('R', 0), '/': ('R', 0),
    ' ': ('R', 4),
}


class HumanTyping:
    def __init__(self, wpm: float = 52):
        self._base_iki = 60_000 / (wpm * 5)  # ms per character

    def get_events(self, text: str) -> list[dict]:
        events = []
        prev_char = None
        for i, char in enumerate(text):
            iki = self._compute_iki(prev_char, char) if i > 0 else random.gauss(300, 80)
            dwell = self._compute_dwell(char)
            events.append({"type": "rawKeyDown", "key": char, "delay_ms": iki})
            events.append({"type": "char", "key": char, "delay_ms": random.uniform(1, 5)})
            events.append({"type": "keyUp", "key": char, "delay_ms": dwell})
            prev_char = char
        return events

    def _compute_iki(self, prev: str, curr: str) -> float:
        base = self._base_iki
        if prev == ' ':
            base *= random.uniform(1.3, 2.0)
        elif prev in '.!?,;:':
            base *= random.uniform(2.0, 4.0)
        prev_info = FINGER_MAP.get(prev.lower())
        curr_info = FINGER_MAP.get(curr.lower())
        if prev_info and curr_info:
            if prev_info[0] != curr_info[0]:  # alternate hands
                base *= 0.85
            elif prev_info[1] == curr_info[1]:  # same finger
                base *= 1.30
        iki = random.gauss(base, base * 0.25)
        if random.random() < 0.02:  # micro-pause
            iki += random.uniform(300, 1200)
        return max(30, iki)

    def _compute_dwell(self, char: str) -> float:
        base = random.gauss(116, 24)
        if char == ' ':
            base *= 1.15
        return max(40, base)


def apply_key_rollover(
    events: list[dict], *, threshold_ms: float = 80.0
) -> list[dict]:
    """Overlap keyDown[N+1] before keyUp[N] when flight time is short.

    Simulates real fast-typist key rollover (40-70% of typists exhibit this
    above ~70 WPM). Per-char rawKeyDown -> char -> keyUp order is preserved;
    only the keyUp is pushed after the next char's rawKeyDown when IKI is
    below threshold_ms.

    Input shape: flat list of {type, key, delay_ms} triples, three per char:
    [rawKeyDown, char, keyUp, rawKeyDown, char, keyUp, ...].
    Returns a new list; input is not mutated.
    """
    if len(events) < 6:
        return list(events)

    out: list[dict] = []
    i = 0
    while i < len(events):
        if i + 5 < len(events):
            this_down, this_char, this_up = events[i], events[i + 1], events[i + 2]
            next_down = events[i + 3]
            if (
                this_up["type"] == "keyUp"
                and next_down["type"] == "rawKeyDown"
                and next_down["delay_ms"] < threshold_ms
            ):
                # Swap: emit down, char, next_down, up; continue from i+4 so
                # the next iteration handles events[i+4] (next char's `char`)
                # and events[i+5] (next char's `keyUp`).
                out.extend([this_down, this_char, next_down, this_up])
                i += 4
                continue
        out.append(events[i])
        i += 1
    return out


# ---------------------------------------------------------------------------
# HumanScroll
# ---------------------------------------------------------------------------

class HumanScroll:
    async def scroll_by(self, session, delta_y: float,
                        mouse_x: float = 400, mouse_y: float = 300):
        import asyncio
        if abs(delta_y) < 10:
            return
        direction = 1 if delta_y > 0 else -1
        remaining = abs(delta_y)
        notch_count = 0
        while remaining > 20:
            notch_delta = min(remaining, 100 + random.gauss(0, 15))
            remaining -= notch_delta
            mx = mouse_x + random.gauss(0, 3)
            my = mouse_y + random.gauss(0, 3)
            await session.send("Input.dispatchMouseEvent", {
                "type": "mouseWheel", "x": mx, "y": my,
                "deltaX": 0, "deltaY": direction * notch_delta,
            })
            total_notches = int(abs(delta_y) / 100) + 1
            t = notch_count / max(1, total_notches - 1)
            if t < 0.2:
                delay = random.uniform(80, 150)
            elif t > 0.8:
                delay = random.uniform(100, 200)
            else:
                delay = random.uniform(30, 80)
            await asyncio.sleep(delay / 1000)
            notch_count += 1


# ---------------------------------------------------------------------------
# ActionTimer
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402  (placed after class definitions for readability)

ACTION_TRANSITION_DELAYS = {
    ("scroll", "click"): (200, 500),
    ("click", "type"): (150, 400),
    ("type", "click"): (100, 300),
    ("navigate", "click"): (500, 1500),
    ("navigate", "type"): (400, 1200),
}


class ActionTimer:
    def __init__(self):
        self._last_action_type: str | None = None

    async def delay_between(self, next_action: str):
        if self._last_action_type:
            key = (self._last_action_type, next_action)
            if key in ACTION_TRANSITION_DELAYS:
                min_ms, max_ms = ACTION_TRANSITION_DELAYS[key]
                await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)
        self._last_action_type = next_action
