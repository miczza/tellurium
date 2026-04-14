"""Exceptions raised by tellurium.session."""


class SessionError(Exception):
    """Base class for all session-related errors."""


class SessionInvalidError(SessionError):
    """Validation failed and no login callback is registered."""


class SessionLoginFailedError(SessionError):
    """The registered login callback raised an exception."""


class SessionCorruptError(SessionError):
    """session.json is malformed and cannot be parsed."""
