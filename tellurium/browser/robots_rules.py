"""robots.txt rules as RFC 9309 reads them: groups, patterns, longest match.

Pure parsing and matching, no I/O: the download and the cache are in ``robots.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_BYTES = 500 * 1024  # RFC 9309 §2.5: parse at least the first 500 KiB

PRODUCT_TOKEN = re.compile(r"[A-Za-z_-]+")  # RFC 9309 §2.2.1
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")
_STARS = re.compile(r"\*{2,}")


_Pattern = tuple[tuple[str, ...], bool]  # the literal runs between ``*``, anchored


def _compile(pattern: str) -> _Pattern:
    """*pattern* (``*`` any run, ``$`` at the end the end) cut at its ``*``,
    a run of them counted once."""
    anchored = pattern.endswith("$")
    return tuple(_STARS.sub("*", pattern[:-1] if anchored else pattern).split("*")), anchored


def _matches(pattern: _Pattern, path: str) -> bool:
    """Whether *pattern* matches the start of *path*: each run found forward
    from where the previous one ended, the leftmost (no backtracking)."""
    runs, anchored = pattern
    if not path.startswith(runs[0]):
        return False
    if len(runs) == 1:
        return not anchored or len(path) == len(runs[0])
    pos = len(runs[0])
    for run in runs[1:-1]:
        if (found := path.find(run, pos)) < 0:
            return False
        pos = found + len(run)
    if anchored:
        return path.endswith(runs[-1]) and len(path) - len(runs[-1]) >= pos
    return path.find(runs[-1], pos) >= 0


@dataclass(frozen=True)
class RobotsRules:
    """The rules of one group: ``(pattern, allow)`` pairs, patterns normalised."""

    rules: tuple[tuple[str, bool], ...]
    # Longest pattern (as written) first, allow first on a tie: the first match decides.
    _order: tuple[tuple[bool, _Pattern], ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        ranked = sorted(self.rules, key=lambda rule: (-len(rule[0]), not rule[1]))
        object.__setattr__(self, "_order", tuple((a, _compile(p)) for p, a in ranked))

    def allows(self, target: str) -> bool:
        """Whether *target* (path and query) may be crawled: the longest matching
        pattern decides, ``allow`` on a tie; ``/robots.txt`` always may."""
        path = _normalise(target or "/")
        if path == "/robots.txt":
            return True
        return next((allow for allow, pattern in self._order if _matches(pattern, path)), True)


ALLOW_ALL = RobotsRules(())
DISALLOW_ALL = RobotsRules((("/", False),))


def parse(text: str, agent: str = "*") -> RobotsRules:
    """The rules of *text* (its first 500 KiB) for the product token *agent*: the
    groups naming it, merged, else the ``*`` groups, else none (everything allowed)."""
    wanted = agent.lower()
    if len(text) > MAX_BYTES // 4:  # maybe over the limit once encoded
        raw = text.encode("utf-8", errors="replace")
        if len(raw) > MAX_BYTES:  # the last line may be cut: dropped
            text = raw[:MAX_BYTES].decode("utf-8", errors="ignore").rpartition("\n")[0]
    groups: dict[str, list[tuple[str, bool]]] = {}
    current: list[list[tuple[str, bool]]] = []
    in_rules = False
    for line in text.lstrip("\ufeff").splitlines():
        key, sep, value = line.split("#", 1)[0].partition(":")
        if not sep:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if in_rules:
                current, in_rules = [], False
            token = "*" if value.startswith("*") else _product_token(value)
            if token:
                current.append(groups.setdefault(token, []))
        elif key in ("allow", "disallow"):
            in_rules = True
            if value:  # an empty disallow forbids nothing
                for rules in current:
                    rules.append((_normalise(value), key == "allow"))
    chosen = groups.get(wanted) if wanted != "*" else None
    if chosen is None:
        chosen = groups.get("*", [])
    return RobotsRules(tuple(chosen))


def outcome(status: int | None, body: bytes, agent: str) -> RobotsRules:
    """RFC 9309 §2.3.1: 2xx → its rules; 4xx → everything allowed; anything else
    (5xx, no answer) → everything disallowed."""
    if status is not None and 200 <= status < 300:
        return parse(body[: MAX_BYTES + 1].decode("utf-8", errors="replace"), agent)
    if status is not None and 400 <= status < 500:
        return ALLOW_ALL
    return DISALLOW_ALL


def _product_token(value: str) -> str:
    match = PRODUCT_TOKEN.match(value)
    return match.group(0).lower() if match else ""


def _normalise(path: str) -> str:
    """RFC 9309 §2.2.2: octets outside US-ASCII percent-encoded, escapes of
    unreserved characters decoded, the others kept (hex in upper case)."""

    def unescape(m: re.Match) -> str:
        char = chr(int(m.group(1), 16))
        return char if char in _UNRESERVED else f"%{m.group(1).upper()}"

    encoded = "".join(c if ord(c) < 128 else "".join(f"%{b:02X}" for b in c.encode()) for c in path)
    return _ESCAPE.sub(unescape, encoded)
