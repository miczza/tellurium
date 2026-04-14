#!/usr/bin/env python3
"""Generate CDP domain bindings from protocol.json."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tellurium.cdp.generator import CDPGenerator

DOMAINS_DIR = Path(__file__).parent.parent / "tellurium" / "cdp" / "domains"


def main():
    protocol_path = Path(__file__).parent.parent / "tellurium" / "cdp" / "protocol.json"
    if not protocol_path.exists():
        print(f"Error: {protocol_path} not found", file=sys.stderr)
        sys.exit(1)
    with open(protocol_path) as f:
        protocol = json.load(f)
    gen = CDPGenerator(protocol)
    modules = gen.generate_all_bundled()
    DOMAINS_DIR.mkdir(parents=True, exist_ok=True)
    init_path = DOMAINS_DIR / "__init__.py"
    init_path.write_text('"""Auto-generated CDP domain bindings."""\n')
    for module_name, source in modules.items():
        path = DOMAINS_DIR / f"{module_name}.py"
        path.write_text(source)
        print(f"Generated: {path}")
    print(f"\n{len(modules)} domains generated.")


if __name__ == "__main__":
    main()
