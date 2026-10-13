"""Fixtures for the HEMS integration tests (run with pytest-homeassistant-custom-component, see docs/hems/install.md)."""
import shutil

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations, hass):
    """Load custom_components/hems from the repository, with the recorder before hass and an empty log directory.

    The test configuration directory is shared between tests, so the HEMS log files of an earlier test would
    otherwise show up in the next one."""
    log_dir = hass.config.path("hems")
    shutil.rmtree(log_dir, ignore_errors=True)
    yield
    shutil.rmtree(log_dir, ignore_errors=True)
