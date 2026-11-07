"""pytest plugin for a targeted CI run (``-p tests.integration.experiment_click_unpainted``):
the banner probe clicks without first waiting for the page's next frame, as
the tests did when "Done" was lost. Not loaded by the suite."""

from tests.integration import banner_probe

banner_probe.WAIT_FOR_FRAME = False
