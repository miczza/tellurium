"""Admin — the multiplexer's own routes, behind the same checks as CDP.

``GET /admin/status`` answers the pool's status as JSON (proxies without
credentials, never the token); ``POST /admin/slots/<id>/restart`` replaces the
Chrome of that place (its client gets 1012) and answers 202, or 404 when there
is no such place. Another method on these routes is 405 with ``Allow``; any
other ``/admin`` path is 404. Requests carry no body (``Content-Length: 0``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, NamedTuple

PREFIX = "/admin"
_STATUS = frozenset({"/admin/status", "/admin/status/"})
_RESTART = re.compile(r"/admin/slots/(\d{1,9})/restart/?")


class Answer(NamedTuple):
    """What to send back: status, body, extra headers, whether the body is JSON."""

    status: int
    body: str
    headers: dict[str, str]
    json_body: bool = False


def is_admin(path: str) -> bool:
    """Whether *path* (without its query) belongs to the admin routes."""
    return path == PREFIX or path.startswith(PREFIX + "/")


class Admin:
    """The admin routes of one multiplexer: *status* gives its status, *places*
    its places (each with ``id``, ``chrome`` and ``restart()``)."""

    def __init__(self, status: Callable[[], dict], places: Callable[[], list[Any]]) -> None:
        self._status = status
        self._places = places

    def answer(self, method: str, path: str) -> Answer:
        if path in _STATUS:
            if method != "GET":
                return _not_allowed("GET")
            return Answer(200, json.dumps(self._status(), indent=2), {}, json_body=True)
        restart = _RESTART.fullmatch(path)
        if restart is not None:
            if method != "POST":
                return _not_allowed("POST")
            return self._restart(int(restart.group(1)))
        return Answer(404, "Not found: GET /admin/status or POST /admin/slots/<id>/restart", {})

    def _restart(self, slot_id: int) -> Answer:
        for place in self._places():
            if place.id == slot_id:
                restarting = place.chrome is not None
                place.restart()
                body = {"id": slot_id, "restarting": restarting}
                return Answer(202, json.dumps(body), {}, json_body=True)
        return Answer(404, f"Not found: there is no place {slot_id}", {})


def _not_allowed(allow: str) -> Answer:
    return Answer(405, f"Method Not Allowed: use {allow}", {"Allow": allow})
