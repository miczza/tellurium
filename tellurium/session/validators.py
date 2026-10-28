"""The validators of a session, combined: is it signed in?"""

from __future__ import annotations


async def combine(validators, mode: str, *, tab) -> bool:
    """Run validators sequentially with short-circuit semantics.

    - "all": first falsy or raising validator wins (returns False).
    - "any": first truthy validator wins (returns True); raises are skipped.
    Returns the final boolean outcome.
    """
    if not validators:
        return True

    if mode == "all":
        for v in validators:
            try:
                result = await v(tab)
            except Exception:  # noqa: BLE001 - user validator errors mean invalid
                return False
            if not result:
                return False
        return True

    if mode == "any":
        for v in validators:
            try:
                result = await v(tab)
            except Exception:  # noqa: BLE001 - user validator errors are skipped
                continue
            if result:
                return True
        return False

    raise ValueError(f"unknown mode: {mode!r}")
