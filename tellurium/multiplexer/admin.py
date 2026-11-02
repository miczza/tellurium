"""Admin — the multiplexer's own routes, behind the same checks as CDP.

``GET /admin/status`` answers the pool's status as JSON (proxies without
credentials, never the token); ``POST /admin/slots/<id>/restart`` replaces the
Chrome of that place (its client gets 1012) and answers 202; 409 when the
place has no Chrome (idle, launching or closing), 404 when there is no such
place. Another method on these routes is 405 with ``Allow``; any other
``/admin`` path is 404. Requests carry no body (``Content-Length: 0``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import NamedTuple

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
    """The admin routes of one multiplexer: *status* gives its status (with
    ``slots``, each with its ``id``), *restart* replaces the Chrome of a place
    and says whether there was one (:meth:`Multiplexer.restart`)."""

    def __init__(self, status: Callable[[], dict], restart: Callable[[int], bool]) -> None:
        self._status = status
        self._restart_place = restart

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
        if slot_id not in {slot["id"] for slot in self._status()["slots"]}:
            return Answer(404, f"Not found: there is no place {slot_id}", {})
        if not self._restart_place(slot_id):
            return Answer(
                409, f"Conflict: place {slot_id} has no Chrome to restart (idle or launching)", {}
            )
        body = {"id": slot_id, "restarting": True}
        return Answer(202, json.dumps(body), {}, json_body=True)


def _not_allowed(allow: str) -> Answer:
    return Answer(405, f"Method Not Allowed: use {allow}", {"Allow": allow})
