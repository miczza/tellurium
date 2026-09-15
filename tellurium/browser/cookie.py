"""Cookie dataclass with JSON and Netscape format support."""

from __future__ import annotations

import json
from dataclasses import dataclass


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
        return "\t".join([self.domain, include_sub, self.path, secure, exp, self.name, self.value])

    @classmethod
    def from_netscape(cls, line: str) -> Cookie:
        parts = line.strip().split("\t")
        return cls(
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
                    if line and not line.startswith("#"):
                        cookies.append(cls.from_netscape(line))
                return cookies
        return []
