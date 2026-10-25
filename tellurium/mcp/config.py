"""How ``tellurium mcp`` runs: where it keeps sessions and downloads, and which
tools and browser options it offers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

HOME_ENV = "TELLURIUM_HOME"


def default_home() -> Path:
    """``$TELLURIUM_HOME``, else ``~/.tellurium``."""
    override = os.environ.get(HOME_ENV)
    return Path(override).expanduser() if override else Path.home() / ".tellurium"


@dataclass(frozen=True)
class ServerConfig:
    """*home* holds ``sessions/<name>`` (named sessions) and ``downloads/``.
    *allow_eval* lists the ``eval`` tool; *headed* shows the browser windows;
    *allow_local_urls* lets navigate/tab-open open ``file:``, ``chrome:`` & co."""

    home: Path
    headed: bool = False
    allow_eval: bool = True
    allow_local_urls: bool = False

    @property
    def sessions_dir(self) -> Path:
        return self.home / "sessions"

    @property
    def downloads_dir(self) -> Path:
        return self.home / "downloads"
