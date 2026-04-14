import pytest


def pytest_addoption(parser):
    parser.addoption("--browser-mode", default="stock", choices=["stock", "patched"])


@pytest.fixture
def browser_mode(request):
    return request.config.getoption("--browser-mode")
