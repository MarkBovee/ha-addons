"""Fixtures for the HEMS integration tests (run with pytest-homeassistant-custom-component, see docs/hems/install.md)."""
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """Let Home Assistant load custom_components/hems from the repository; the recorder must exist before hass."""
    yield
