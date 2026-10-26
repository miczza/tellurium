"""Exceptions raised by tellurium.session."""


class SessionError(Exception):
    """Base class for all session-related errors."""


class SessionInvalidError(SessionError):
    """Validation failed and no login callback is registered."""


class SessionLoginFailedError(SessionError):
    """The registered login callback raised an exception."""


class SessionCorruptError(SessionError):
    """session.json is malformed and cannot be parsed."""


class SessionBusyError(SessionError):
    """The session is open in another process (or by another Session here).

    ``pid`` is the holder's process id, ``None`` if it could not be read.
    """

    def __init__(self, path: str, pid: int | None) -> None:
        holder = f"process {pid}" if pid else "another process"
        super().__init__(
            f"session at {path} is already open by {holder}: close it there, "
            "or open another session"
        )
        self.path = path
        self.pid = pid
