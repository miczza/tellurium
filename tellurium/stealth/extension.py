"""Generate a Chrome extension for stealth script injection."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent / "scripts"


def load_script(name: str, params: dict | None = None) -> str:
    """Load a JS script, replacing {{PARAM}} placeholders."""
    content = (SCRIPTS_DIR / name).read_text()
    if params:
        for key, value in params.items():
            content = content.replace(f"{{{{{key}}}}}", str(value))
    return content


def create_stealth_extension(scripts: list[str], matches: list[str] | None = None) -> str:
    """Create a temp directory with a Chrome extension. Returns the path."""
    if matches is None:
        matches = ["<all_urls>"]

    ext_dir = tempfile.mkdtemp(prefix="tellurium_ext_")

    manifest = {
        "manifest_version": 3,
        "name": "Tellurium",
        "version": "1.0",
        "content_scripts": [{
            "matches": matches,
            "js": ["content.js"],
            "run_at": "document_start",
            "all_frames": True,
            "world": "MAIN",
        }],
    }

    with open(os.path.join(ext_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f)

    content = "\n".join(scripts)
    with open(os.path.join(ext_dir, "content.js"), "w") as f:
        f.write(content)

    return ext_dir
