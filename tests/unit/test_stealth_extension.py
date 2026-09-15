import json
import os
import shutil

from tellurium.stealth.extension import create_stealth_extension, load_script


def test_load_script_no_params():
    content = load_script("chrome_runtime.js")
    assert "chrome" in content
    assert "runtime" in content


def test_load_script_with_params():
    content = load_script("keyboard_layout.js", {"LOCALE": "fr-FR"})
    assert "fr-FR" in content
    assert "{{LOCALE}}" not in content


def test_create_extension():
    scripts = [load_script("chrome_runtime.js")]
    ext_dir = create_stealth_extension(scripts)
    assert os.path.exists(os.path.join(ext_dir, "manifest.json"))
    assert os.path.exists(os.path.join(ext_dir, "content.js"))

    with open(os.path.join(ext_dir, "manifest.json")) as f:
        manifest = json.load(f)
    assert manifest["manifest_version"] == 3
    assert manifest["content_scripts"][0]["world"] == "MAIN"
    assert manifest["content_scripts"][0]["run_at"] == "document_start"

    with open(os.path.join(ext_dir, "content.js")) as f:
        content = f.read()
    assert "chrome" in content

    shutil.rmtree(ext_dir)


def test_create_extension_multiple_scripts():
    scripts = [
        load_script("chrome_runtime.js"),
        load_script("plugins.js"),
    ]
    ext_dir = create_stealth_extension(scripts)
    with open(os.path.join(ext_dir, "content.js")) as f:
        content = f.read()
    assert "chrome.runtime" in content or "window.chrome" in content
    assert "navigator.plugins" in content or "Plugin" in content
    shutil.rmtree(ext_dir)
