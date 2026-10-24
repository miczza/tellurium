"""One MCP tool: its name, schema, argument whitelist and handler."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from tellurium.mcp.results import Reply, ToolError

Handler = Callable[[Any, dict[str, Any]], Awaitable[Reply]]

TARGET_ID = "targetId"
_TARGET_PARAM = {"type": "string", "description": "Tab id from session-open, tab-open or tab-list."}
_PYTHON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
}


class ToolArgumentError(ToolError):
    """The arguments do not match the tool's schema."""


def param(kind: str, description: str, *, enum: list[str] | None = None) -> dict[str, Any]:
    """A JSON-schema property of *kind* (string, integer, number, boolean)."""
    if kind not in _PYTHON_TYPES:
        raise ValueError(f"unsupported parameter type {kind!r}")
    schema: dict[str, Any] = {"type": kind, "description": description}
    if enum is not None:
        schema["enum"] = list(enum)
    return schema


@dataclass(frozen=True)
class Tool:
    """A tool the server lists. A *page* tool also takes the required ``targetId``.

    *timeout* bounds the whole call, Chrome round trips included.
    """

    name: str
    description: str
    handler: Handler
    params: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    page: bool = False
    timeout: float = 60.0

    def _properties(self) -> dict[str, Mapping[str, Any]]:
        if self.page:
            return {TARGET_ID: _TARGET_PARAM, **self.params}
        return dict(self.params)

    def _required(self) -> list[str]:
        return ([TARGET_ID] if self.page else []) + list(self.required)

    def input_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {k: dict(v) for k, v in self._properties().items()},
            "additionalProperties": False,
        }
        if self._required():
            schema["required"] = self._required()
        return schema

    def check(self, arguments: Mapping[str, Any] | None) -> dict[str, Any]:
        """The arguments if they fit the schema, else :class:`ToolArgumentError`
        naming the first problem (unknown arguments are refused, not ignored)."""
        args = dict(arguments or {})
        properties = self._properties()
        unknown = sorted(set(args) - set(properties))
        if unknown:
            allowed = ", ".join(sorted(properties)) or "none"
            raise ToolArgumentError(
                f"{self.name}: unknown argument {unknown[0]!r} (allowed: {allowed})"
            )
        for name in self._required():
            if name not in args:
                raise ToolArgumentError(f"{self.name}: missing required argument {name!r}")
        for name, value in args.items():
            _check_value(self.name, name, value, properties[name])
        return args


def _check_value(tool: str, name: str, value: Any, schema: Mapping[str, Any]) -> None:
    kind = schema["type"]
    ok = isinstance(value, _PYTHON_TYPES[kind])
    if kind != "boolean" and isinstance(value, bool):
        ok = False  # True is an int to Python, never to the schema
    if not ok:
        raise ToolArgumentError(f"{tool}: {name!r} must be {kind}, got {type(value).__name__}")
    choices = schema.get("enum")
    if choices is not None and value not in choices:
        raise ToolArgumentError(f"{tool}: {name!r} must be one of {', '.join(choices)}")
