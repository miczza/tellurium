"""The values of a session's metadata: what JSON can hold, so session.json
can always be written and read back."""

from __future__ import annotations

import math
from typing import Any


def check(value: Any) -> None:
    """Raise TypeError if value (or any nested element) is not JSON-serializable."""
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(
                f"metadata float values must be finite (got {value!r}); "
                "NaN and Infinity are not valid JSON"
            )
        return
    if isinstance(value, list):
        for v in value:
            check(v)
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(f"metadata dict keys must be str, got {type(k).__name__}")
            check(v)
        return
    raise TypeError(
        f"metadata values must be JSON-serializable "
        f"(str, int, float, bool, None, list, dict); got {type(value).__name__}"
    )
