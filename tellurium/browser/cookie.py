"""Cookie dataclass with JSON and Netscape format support."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

#: Prefix curl, yt-dlp and browser extensions put on HttpOnly cookie lines.
_HTTP_ONLY_PREFIX = "#HttpOnly_"


def matches_domain(cookie_domain: str, domain: str) -> bool:
    """Whether a cookie stored for *cookie_domain* belongs to *domain*.

    Equal hosts or subdomains match (``sub.example.com`` belongs to
    ``example.com``); ``notexample.com`` does not. Leading dots are ignored.
    """
    host = cookie_domain.lstrip(".").lower()
    wanted = domain.lstrip(".").lower()
    return host == wanted or host.endswith("." + wanted)


# CookieParam fields that identify a stored cookie (Storage.setCookies).
_IDENTITY = ("name", "domain", "path", "secure", "httpOnly", "sameSite", "partitionKey")


async def read_jar(
    session: Any, domain: str | None = None, context_id: str | None = None
) -> list[Cookie]:
    """Cookies of the browser (or of *context_id*), only *domain*'s when given."""
    params = {"browserContextId": context_id} if context_id else {}
    result = await session.send("Storage.getCookies", params)
    cookies = [Cookie.from_json(c) for c in result.get("cookies", [])]
    return [c for c in cookies if domain is None or matches_domain(c.domain, domain)]


async def clear_jar(session: Any, domain: str | None = None, context_id: str | None = None) -> None:
    """Delete every cookie of the browser (or of *context_id*), or only *domain*'s.

    Runs on the browser session: ``Storage`` is there, ``Network`` is not.
    A domain's cookies are deleted by storing them again already expired.
    """
    params: dict[str, Any] = {"browserContextId": context_id} if context_id else {}
    if not domain:
        await session.send("Storage.clearCookies", params)
        return
    result = await session.send("Storage.getCookies", params)
    expired = [
        {**{k: c[k] for k in _IDENTITY if k in c}, "value": "", "expires": 1}
        for c in result.get("cookies", [])
        if matches_domain(c["domain"], domain)
    ]
    if expired:
        await session.send("Storage.setCookies", {**params, "cookies": expired})


@dataclass
class Cookie:
    name: str
    value: str
    domain: str
    path: str = "/"
    expires: float = -1
    http_only: bool = False
    secure: bool = False
    same_site: str = "Lax"

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "domain": self.domain,
            "path": self.path,
            "expires": self.expires,
            "httpOnly": self.http_only,
            "secure": self.secure,
            "sameSite": self.same_site,
        }

    @classmethod
    def from_json(cls, data: dict) -> Cookie:
        return cls(
            name=data["name"],
            value=data["value"],
            domain=data["domain"],
            path=data.get("path", "/"),
            expires=data.get("expires", -1),
            http_only=data.get("httpOnly", False),
            secure=data.get("secure", False),
            same_site=data.get("sameSite", "Lax"),
        )

    def to_netscape(self) -> str:
        include_sub = "TRUE" if self.domain.startswith(".") else "FALSE"
        secure = "TRUE" if self.secure else "FALSE"
        exp = str(int(self.expires)) if self.expires > 0 else "0"
        domain = _HTTP_ONLY_PREFIX + self.domain if self.http_only else self.domain
        return "\t".join([domain, include_sub, self.path, secure, exp, self.name, self.value])

    @classmethod
    def from_netscape(cls, line: str) -> Cookie:
        line = line.strip()
        http_only = line.startswith(_HTTP_ONLY_PREFIX)
        parts = line.removeprefix(_HTTP_ONLY_PREFIX).split("\t")
        return cls(
            http_only=http_only,
            domain=parts[0],
            path=parts[2],
            secure=parts[3] == "TRUE",
            expires=float(parts[4]) if parts[4] != "0" else -1,
            name=parts[5],
            value=parts[6] if len(parts) > 6 else "",
        )

    @classmethod
    def save_list(cls, cookies: list[Cookie], path: str, format: str = "json") -> None:
        with open(path, "w") as f:
            if format == "json":
                json.dump([c.to_json() for c in cookies], f, indent=2)
            elif format == "netscape":
                f.write("# Netscape HTTP Cookie File\n")
                for c in cookies:
                    f.write(c.to_netscape() + "\n")

    @classmethod
    def load_list(cls, path: str, format: str | None = None) -> list[Cookie]:
        if format is None:
            format = "netscape" if path.endswith(".txt") else "json"
        with open(path) as f:
            if format == "json":
                return [cls.from_json(d) for d in json.load(f)]
            elif format == "netscape":
                cookies = []
                for line in f:
                    line = line.strip()
                    if line.startswith(_HTTP_ONLY_PREFIX) or (line and not line.startswith("#")):
                        cookies.append(cls.from_netscape(line))
                return cookies
        return []
