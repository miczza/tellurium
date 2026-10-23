"""Tab dialog policy validation (R1, M2)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tellurium.browser.tab import Tab


def test_unknown_dialog_policy_is_rejected():
    with pytest.raises(ValueError, match="dialogs policy"):
        Tab(MagicMock(), MagicMock(), "T1", dialogs="ignore")


def test_policy_is_kept_and_defaults_to_dismiss():
    assert Tab(MagicMock(), MagicMock(), "T1")._dialogs.policy == "dismiss"
    assert Tab(MagicMock(), MagicMock(), "T1", dialogs="accept")._dialogs.policy == "accept"
