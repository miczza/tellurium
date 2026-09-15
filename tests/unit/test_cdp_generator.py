from tellurium.cdp.generator import CDPGenerator

MINI_PROTOCOL = {
    "domains": [
        {
            "domain": "Page",
            "types": [
                {"id": "FrameId", "type": "string"},
                {
                    "id": "Frame",
                    "type": "object",
                    "properties": [
                        {"name": "id", "$ref": "FrameId"},
                        {"name": "url", "type": "string"},
                        {"name": "securityOrigin", "type": "string"},
                        {"name": "mimeType", "type": "string"},
                        {"name": "name", "type": "string", "optional": True},
                    ],
                },
            ],
            "commands": [
                {
                    "name": "navigate",
                    "parameters": [
                        {"name": "url", "type": "string"},
                        {"name": "referrer", "type": "string", "optional": True},
                    ],
                    "returns": [
                        {"name": "frameId", "$ref": "FrameId"},
                        {"name": "errorText", "type": "string", "optional": True},
                    ],
                },
                {"name": "enable", "parameters": [], "returns": []},
            ],
            "events": [
                {
                    "name": "loadEventFired",
                    "parameters": [{"name": "timestamp", "type": "number"}],
                },
            ],
        }
    ]
}


def test_module_name():
    assert CDPGenerator._module_name("Page") == "page"
    assert CDPGenerator._module_name("Input") == "input_"
    assert CDPGenerator._module_name("DOM") == "dom"


def test_generate_domain_produces_valid_python():
    gen = CDPGenerator(MINI_PROTOCOL)
    source = gen.generate_domain("Page")
    compile(source, "page.py", "exec")


def test_generated_code_contains_types():
    gen = CDPGenerator(MINI_PROTOCOL)
    source = gen.generate_domain("Page")
    assert "class FrameId(str):" in source
    assert "class Frame:" in source
    assert "url: str" in source
    assert "name: Optional[str] = None" in source


def test_generated_code_contains_commands():
    gen = CDPGenerator(MINI_PROTOCOL)
    source = gen.generate_domain("Page")
    assert "def navigate(" in source
    assert '"method": "Page.navigate"' in source
    assert "class NavigateResult:" in source
    assert "frame_id: FrameId" in source


def test_generated_code_contains_events():
    gen = CDPGenerator(MINI_PROTOCOL)
    source = gen.generate_domain("Page")
    assert "class LoadEventFired:" in source
    assert "EVENT_NAME" in source
    assert '"Page.loadEventFired"' in source


def test_generated_code_handles_no_params_command():
    gen = CDPGenerator(MINI_PROTOCOL)
    source = gen.generate_domain("Page")
    assert "def enable(" in source


def test_generate_all_bundled():
    gen = CDPGenerator(MINI_PROTOCOL)
    gen.BUNDLED_DOMAINS = ["Page"]
    result = gen.generate_all_bundled()
    assert "page" in result
    compile(result["page"], "page.py", "exec")


def test_generated_types_are_functional():
    """Execute the generated code and verify the types work."""
    gen = CDPGenerator(MINI_PROTOCOL)
    source = gen.generate_domain("Page")
    namespace = {}
    exec(source, namespace)

    # Test FrameId
    fid = namespace["FrameId"]("ABC123")
    assert fid == "ABC123"
    assert fid.to_json() == "ABC123"
    assert namespace["FrameId"].from_json("XYZ") == "XYZ"

    # Test navigate command
    cmd, result_type = namespace["navigate"]("https://example.com")
    assert cmd["method"] == "Page.navigate"
    assert cmd["params"]["url"] == "https://example.com"

    # Test NavigateResult
    nr = result_type.from_json({"frameId": "F1"})
    assert nr.frame_id == "F1"
    assert nr.error_text is None
