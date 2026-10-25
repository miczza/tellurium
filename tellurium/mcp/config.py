"""How ``tellurium mcp`` runs: where it keeps sessions and downloads, and which
tools and browser options it offers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

HOME_ENV = "TELLURIUM_HOME"
# Seconds without a tool call after which an HTTP client's sessions are closed.
DEFAULT_IDLE_TIMEOUT = 300.0
# Browsers (each a Chrome) an HTTP client, and the whole server, may run at once.
DEFAULT_SESSIONS_PER_CLIENT = 4
DEFAULT_SESSIONS = 16


def default_home() -> Path:
    """``$TELLURIUM_HOME``, else ``~/.tellurium``."""
    override = os.environ.get(HOME_ENV)
    return Path(override).expanduser() if override else Path.home() / ".tellurium"


@dataclass(frozen=True)
class HttpConfig:
    """Where ``--http`` listens (port 0: any free one); *idle_timeout* is
    the seconds without a tool call before a client's sessions are closed and
    saved (``None``: never); *max_sessions_per_client* and *max_sessions*
    cap the browsers of one client and of the server (``None``: no cap)."""

    host: str = "127.0.0.1"
    port: int = 8765
    idle_timeout: float | None = DEFAULT_IDLE_TIMEOUT
    max_sessions_per_client: int | None = DEFAULT_SESSIONS_PER_CLIENT
    max_sessions: int | None = DEFAULT_SESSIONS


@dataclass(frozen=True)
class ServerConfig:
    """*home* holds ``sessions/<name>`` (named sessions) and ``downloads/``.
    *allow_eval* lists the ``eval`` tool; *headed* shows the browser windows;
    *allow_local_urls* lets navigate/tab-open open ``file:``, ``chrome:`` & co.;
    *http* configures the HTTP transport."""

    home: Path
    headed: bool = False
    allow_eval: bool = True
    allow_local_urls: bool = False
    http: HttpConfig | None = None

    @property
    def token_path(self) -> Path:
        return self.home / "mcp-token"

    @property
    def sessions_dir(self) -> Path:
        return self.home / "sessions"

    @property
    def downloads_dir(self) -> Path:
        return self.home / "downloads"
