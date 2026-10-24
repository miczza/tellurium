"""CDP code generator — produces typed Python modules from Chrome DevTools Protocol JSON."""

from __future__ import annotations

import re
from typing import Any

# Python builtins / keywords that need a trailing underscore when used as module names
_PYTHON_RESERVED = frozenset(
    {
        "False",
        "None",
        "True",
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "input",
        "is",
        "lambda",
        "nonlocal",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "try",
        "while",
        "with",
        "yield",
        # also shadow builtins that would clash
        "type",
        "id",
        "list",
        "dict",
        "set",
        "object",
    }
)


def _to_snake(name: str) -> str:
    """Convert camelCase / PascalCase to snake_case."""
    # Insert underscore before uppercase letters that follow lowercase letters or digits
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    # Handle sequences of uppercase letters (e.g. "DOMNode" -> "DOM_Node")
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    return s.lower()


def _to_pascal(name: str) -> str:
    """Convert camelCase to PascalCase."""
    if name:
        return name[0].upper() + name[1:]
    return name


class CDPGenerator:
    """Generates typed Python source code from a CDP protocol.json dict."""

    BUNDLED_DOMAINS = [
        "Target",
        "Browser",
        "Page",
        "Network",
        "DOM",
        "Runtime",
        "Input",
        "Fetch",
        "Storage",
        "Emulation",
        "Log",
        "Accessibility",
    ]

    # CDP primitive type -> Python type annotation
    _PRIMITIVE_MAP: dict[str, str] = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "object": "T_JSON_DICT",
        "any": "Any",
    }

    def __init__(self, protocol: dict[str, Any]) -> None:
        self._protocol = protocol
        # Build domain lookup: domain_name -> domain dict
        self._domains: dict[str, dict[str, Any]] = {
            d["domain"]: d for d in protocol.get("domains", [])
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_domain(self, domain_name: str) -> str:
        """Return complete Python source for one CDP domain."""
        domain = self._domains[domain_name]
        lines: list[str] = []

        # Module header
        lines.append(f'"""Auto-generated CDP bindings for the {domain_name} domain."""')
        lines.append("")
        lines.append("from __future__ import annotations")
        lines.append("")
        lines.append("from dataclasses import dataclass, field")
        lines.append("from typing import Any, Optional")
        lines.append("")
        lines.append("from tellurium.cdp.types import T_JSON_DICT")
        lines.append("")
        lines.append("")

        # Types
        for type_def in domain.get("types", []):
            lines.extend(self._generate_type(domain_name, type_def))
            lines.append("")
            lines.append("")

        # Commands
        for cmd in domain.get("commands", []):
            lines.extend(self._generate_command(domain_name, cmd))
            lines.append("")
            lines.append("")

        # Events
        for event in domain.get("events", []):
            lines.extend(self._generate_event(domain_name, event))
            lines.append("")
            lines.append("")

        return "\n".join(lines)

    def generate_all_bundled(self) -> dict[str, str]:
        """Generate source for all bundled domains. Returns {module_name: source}."""
        result: dict[str, str] = {}
        for domain_name in self.BUNDLED_DOMAINS:
            if domain_name in self._domains:
                module = self._module_name(domain_name)
                result[module] = self.generate_domain(domain_name)
        return result

    # ------------------------------------------------------------------
    # Type generation
    # ------------------------------------------------------------------

    def _generate_type(self, domain: str, type_def: dict[str, Any]) -> list[str]:
        """Generate source lines for a CDP type definition."""
        type_id = type_def["id"]
        base_type = type_def.get("type", "object")

        if base_type == "string" and "enum" not in type_def:
            return self._generate_string_alias(type_id)
        elif base_type == "object":
            return self._generate_dataclass_type(domain, type_id, type_def.get("properties", []))
        else:
            # Numeric aliases and enums: simple subclass
            python_base = self._PRIMITIVE_MAP.get(base_type, "Any")
            lines = [
                f"class {type_id}({python_base}):",
                '    """CDP type alias."""',
                "",
                f"    def to_json(self) -> {python_base}:",
                f"        return {python_base}(self)",
                "",
                "    @classmethod",
                f"    def from_json(cls, val: {python_base}) -> {type_id}:",
                "        return cls(val)",
            ]
            return lines

    def _generate_string_alias(self, type_id: str) -> list[str]:
        """Generate a string subclass type alias."""
        return [
            f"class {type_id}(str):",
            '    """CDP string type alias."""',
            "",
            "    def to_json(self) -> str:",
            "        return str(self)",
            "",
            "    @classmethod",
            f"    def from_json(cls, val: str) -> {type_id}:",
            "        return cls(val)",
        ]

    def _generate_dataclass_type(
        self, domain: str, type_id: str, properties: list[dict[str, Any]]
    ) -> list[str]:
        """Generate a @dataclass for a CDP object type."""
        required = [p for p in properties if not p.get("optional")]
        optional = [p for p in properties if p.get("optional")]

        lines = ["@dataclass", f"class {type_id}:"]

        # Required fields
        for prop in required:
            py_type = self._resolve_type(domain, prop)
            snake = _to_snake(prop["name"])
            lines.append(f"    {snake}: {py_type}")

        # Optional fields
        for prop in optional:
            py_type = self._resolve_type(domain, prop)
            snake = _to_snake(prop["name"])
            lines.append(f"    {snake}: Optional[{py_type}] = None")

        if not required and not optional:
            lines.append("    pass")

        # to_json
        lines.append("")
        lines.append("    def to_json(self) -> T_JSON_DICT:")
        lines.append("        d: T_JSON_DICT = {}")
        for prop in required:
            snake = _to_snake(prop["name"])
            lines.append(
                "        d[{!r}] = {}".format(
                    prop["name"], self._serialize_field(domain, prop, snake)
                )
            )
        for prop in optional:
            snake = _to_snake(prop["name"])
            lines.append(f"        if self.{snake} is not None:")
            lines.append(
                "            d[{!r}] = {}".format(
                    prop["name"], self._serialize_field(domain, prop, f"self.{snake}")
                )
            )
        lines.append("        return d")

        # from_json classmethod
        lines.append("")
        lines.append("    @classmethod")
        lines.append(f"    def from_json(cls, data: T_JSON_DICT) -> {type_id}:")
        args: list[str] = []
        for prop in required:
            snake = _to_snake(prop["name"])
            expr = self._deserialize_field(domain, prop, "data[{!r}]".format(prop["name"]))
            args.append(f"            {snake}={expr}")
        for prop in optional:
            snake = _to_snake(prop["name"])
            expr = self._deserialize_field(domain, prop, "data.get({!r})".format(prop["name"]))
            # Wrap optional in a conditional to keep None semantics
            args.append(
                "            {}={} if {!r} in data else None".format(
                    snake,
                    self._deserialize_field(domain, prop, "data[{!r}]".format(prop["name"])),
                    prop["name"],
                )
            )
        if args:
            lines.append("        return cls(")
            lines.extend([a + "," for a in args])
            lines.append("        )")
        else:
            lines.append("        return cls()")
        return lines

    # ------------------------------------------------------------------
    # Command generation
    # ------------------------------------------------------------------

    def _generate_command(self, domain: str, cmd: dict[str, Any]) -> list[str]:
        """Generate a command function + optional result dataclass."""
        cmd_name = cmd["name"]
        snake_name = _to_snake(cmd_name)
        params = cmd.get("parameters") or []
        returns = cmd.get("returns") or []

        result_class = f"{_to_pascal(cmd_name)}Result"
        has_result = bool(returns)

        lines: list[str] = []

        # Result dataclass (defined before the function so it can be referenced)
        if has_result:
            lines.extend(self._generate_result_dataclass(domain, result_class, returns))
            lines.append("")
            lines.append("")

        # Function signature
        required_params = [p for p in params if not p.get("optional")]
        optional_params = [p for p in params if p.get("optional")]

        sig_parts = [""]  # always include self-less functions here
        for p in required_params:
            py_type = self._resolve_type(domain, p)
            sig_parts.append("{}: {}".format(_to_snake(p["name"]), py_type))
        for p in optional_params:
            py_type = self._resolve_type(domain, p)
            sig_parts.append("{}: Optional[{}] = None".format(_to_snake(p["name"]), py_type))

        # Return type annotation
        if has_result:
            pass
        else:
            pass

        sig = ", ".join(sig_parts[1:])  # drop leading empty
        lines.append(
            "def {}({}) -> tuple[T_JSON_DICT, {}]:".format(
                snake_name,
                sig,
                f"type[{result_class}]" if has_result else "None",
            )
        )

        # Build params dict
        lines.append("    params: T_JSON_DICT = {}")
        for p in required_params:
            snake = _to_snake(p["name"])
            lines.append(
                "    params[{!r}] = {}".format(p["name"], self._serialize_field(domain, p, snake))
            )
        for p in optional_params:
            snake = _to_snake(p["name"])
            lines.append(f"    if {snake} is not None:")
            lines.append(
                "        params[{!r}] = {}".format(
                    p["name"], self._serialize_field(domain, p, snake)
                )
            )

        lines.append(
            f'    cmd: T_JSON_DICT = {{"method": "{domain}.{cmd_name}", "params": params}}'
        )
        if has_result:
            lines.append(f"    return cmd, {result_class}")
        else:
            lines.append("    return cmd, None")
        return lines

    def _generate_result_dataclass(
        self, domain: str, class_name: str, returns: list[dict[str, Any]]
    ) -> list[str]:
        """Generate a result @dataclass for a command."""
        required = [r for r in returns if not r.get("optional")]
        optional = [r for r in returns if r.get("optional")]

        lines = ["@dataclass", f"class {class_name}:"]

        for prop in required:
            py_type = self._resolve_type(domain, prop)
            snake = _to_snake(prop["name"])
            lines.append(f"    {snake}: {py_type}")

        for prop in optional:
            py_type = self._resolve_type(domain, prop)
            snake = _to_snake(prop["name"])
            lines.append(f"    {snake}: Optional[{py_type}] = None")

        if not required and not optional:
            lines.append("    pass")

        # from_json classmethod
        lines.append("")
        lines.append("    @classmethod")
        lines.append(f"    def from_json(cls, data: T_JSON_DICT) -> {class_name}:")
        args: list[str] = []
        for prop in required:
            snake = _to_snake(prop["name"])
            expr = self._deserialize_field(domain, prop, "data[{!r}]".format(prop["name"]))
            args.append(f"            {snake}={expr}")
        for prop in optional:
            snake = _to_snake(prop["name"])
            args.append(
                "            {}={} if {!r} in data else None".format(
                    snake,
                    self._deserialize_field(domain, prop, "data[{!r}]".format(prop["name"])),
                    prop["name"],
                )
            )
        if args:
            lines.append("        return cls(")
            lines.extend([a + "," for a in args])
            lines.append("        )")
        else:
            lines.append("        return cls()")
        return lines

    # ------------------------------------------------------------------
    # Event generation
    # ------------------------------------------------------------------

    def _generate_event(self, domain: str, event: dict[str, Any]) -> list[str]:
        """Generate an event @dataclass."""
        event_name = event["name"]
        class_name = _to_pascal(event_name)
        params = event.get("parameters") or []

        required = [p for p in params if not p.get("optional")]
        optional = [p for p in params if p.get("optional")]

        lines = ["@dataclass", f"class {class_name}:"]
        lines.append(
            f'    EVENT_NAME: str = field(init=False, repr=False, default="{domain}.{event_name}")'
        )

        for prop in required:
            py_type = self._resolve_type(domain, prop)
            snake = _to_snake(prop["name"])
            lines.append(f"    {snake}: {py_type}")

        for prop in optional:
            py_type = self._resolve_type(domain, prop)
            snake = _to_snake(prop["name"])
            lines.append(f"    {snake}: Optional[{py_type}] = None")

        # from_json classmethod
        lines.append("")
        lines.append("    @classmethod")
        lines.append(f"    def from_json(cls, data: T_JSON_DICT) -> {class_name}:")
        args: list[str] = []
        for prop in required:
            snake = _to_snake(prop["name"])
            expr = self._deserialize_field(domain, prop, "data[{!r}]".format(prop["name"]))
            args.append(f"            {snake}={expr}")
        for prop in optional:
            snake = _to_snake(prop["name"])
            args.append(
                "            {}={} if {!r} in data else None".format(
                    snake,
                    self._deserialize_field(domain, prop, "data[{!r}]".format(prop["name"])),
                    prop["name"],
                )
            )
        if args:
            lines.append("        return cls(")
            lines.extend([a + "," for a in args])
            lines.append("        )")
        else:
            lines.append("        return cls()")
        return lines

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _module_name(domain: str) -> str:
        """Convert a domain name to a Python module name.

        Examples:
            Page  -> page
            Input -> input_   (shadows built-in)
            DOM   -> dom
        """
        name = domain.lower()
        if name in _PYTHON_RESERVED:
            name = name + "_"
        return name

    @staticmethod
    def _to_snake(name: str) -> str:
        return _to_snake(name)

    def _resolve_type(self, domain: str, prop: dict[str, Any]) -> str:
        """Map a CDP property/parameter definition to a Python type annotation string."""
        if "$ref" in prop:
            ref = prop["$ref"]
            # If the ref contains a dot it references another domain
            if "." in ref:
                # e.g. "Network.Headers" — keep as-is for now (cross-domain refs
                # are fine as string annotations thanks to `from __future__ import annotations`)
                return ref.split(".")[-1]
            return ref

        cdp_type = prop.get("type", "any")

        if cdp_type == "array":
            items = prop.get("items", {})
            if "$ref" in items:
                item_type = items["$ref"].split(".")[-1]
            else:
                item_type = self._PRIMITIVE_MAP.get(items.get("type", "any"), "Any")
            return f"list[{item_type}]"

        return self._PRIMITIVE_MAP.get(cdp_type, "Any")

    def _serialize_field(self, domain: str, prop: dict[str, Any], var: str) -> str:
        """Return Python expression that serialises `var` (a field value) to JSON-safe form."""
        if "$ref" in prop:
            # String aliases and dataclasses both have .to_json()
            return f"{var}.to_json()"

        cdp_type = prop.get("type", "any")

        if cdp_type == "array":
            items = prop.get("items", {})
            if "$ref" in items:
                return f"[i.to_json() for i in {var}]"
            # Primitive arrays pass through
            return f"list({var})"

        # Primitives pass through as-is
        return var

    def _deserialize_field(self, domain: str, prop: dict[str, Any], expr: str) -> str:
        """Return Python expression that deserialises `expr` (a raw JSON value)."""
        if "$ref" in prop:
            ref = prop["$ref"]
            class_name = ref.split(".")[-1]
            return f"{class_name}.from_json({expr})"

        cdp_type = prop.get("type", "any")

        if cdp_type == "array":
            items = prop.get("items", {})
            if "$ref" in items:
                item_class = items["$ref"].split(".")[-1]
                return f"[{item_class}.from_json(i) for i in {expr}]"
            # Primitive arrays
            item_py = self._PRIMITIVE_MAP.get(items.get("type", "any"), "Any")
            if item_py in ("str", "int", "float", "bool"):
                return f"[{item_py}(i) for i in {expr}]"
            return f"list({expr})"

        # Cast primitives explicitly for safety
        py_type = self._PRIMITIVE_MAP.get(cdp_type, "Any")
        if py_type in ("str", "int", "float", "bool"):
            return f"{py_type}({expr})"

        return expr
