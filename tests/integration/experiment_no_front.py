"""pytest plugin for a targeted CI run (``-p tests.integration.experiment_no_front``):
``wait_for_human`` leaves its tab where it is, as before it brought it to the
front. With :mod:`tests.integration.experiment_click_unpainted`, the state in
which "Done" was lost. Not loaded by the suite."""

from tellurium.browser import human


async def _stays_behind(self) -> None:
    return None


human._Banner.bring_to_front = _stays_behind
