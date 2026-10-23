"""new_tab waiting for an adopted page raises the builtin TimeoutError (m9)."""

import pytest

from tellurium.browser.browser import Browser


async def test_wait_adopted_raises_builtin_timeout_with_the_target():
    browser = Browser()
    with pytest.raises(TimeoutError, match="TARGET-1.*not ready"):
        await browser._wait_adopted("TARGET-1", timeout=0.01)
