import json
import os
from tellurium.stealth.extension import load_script, create_stealth_extension


def test_load_script_no_params():
    content = load_script("webdriver.js")
    assert "navigator" in content
    assert "webdriver" in content


def test_load_script_with_params():
    content = load_script("webgl.js", {"VENDOR": "TestVendor", "RENDERER": "TestRenderer"})
    assert "TestVendor" in content
    assert "TestRenderer" in content
    assert "{{VENDOR}}" not in content


def test_create_extension():
    scripts = [load_script("webdriver.js")]
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
    assert "webdriver" in content

    # Cleanup
    import shutil
    shutil.rmtree(ext_dir)


def test_create_extension_multiple_scripts():
    scripts = [
        load_script("webdriver.js"),
        load_script("chrome_runtime.js"),
    ]
    ext_dir = create_stealth_extension(scripts)
    with open(os.path.join(ext_dir, "content.js")) as f:
        content = f.read()
    assert "webdriver" in content
    assert "chrome.runtime" in content or "chrome" in content
    import shutil
    shutil.rmtree(ext_dir)
