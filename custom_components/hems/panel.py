"""The HEMS panel in the Home Assistant sidebar: one web component served from frontend/, versioned with the integration.

The same file also defines Lovelace cards (hems-timeline-card, hems-verdict-card), loaded on every dashboard as an extra
module, so parts of the panel can be placed on other dashboards too."""
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

URL_BASE = "/hems_static"
PANEL_URL = "hems"
MODULE = "hems-panel.js"
FRONTEND_DIR = Path(__file__).parent / "frontend"


def _version() -> str:
    """Cache buster: the file's modification time, so a deploy is picked up without a version bump and an unchanged file stays cached."""
    try:
        return str(int((FRONTEND_DIR / MODULE).stat().st_mtime))
    except OSError:
        return "0"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Serve frontend/ once per run, load the cards everywhere, and add the sidebar entry.

    Without the frontend (a headless test instance) there is no sidebar to add to; the sensors work regardless."""
    if "frontend" not in hass.config.components:
        return
    data = hass.data.setdefault(DOMAIN, {})
    version = await hass.async_add_executor_job(_version)
    if not data.get("static_registered"):
        await hass.http.async_register_static_paths([StaticPathConfig(URL_BASE, str(FRONTEND_DIR), cache_headers=False)])
        frontend.add_extra_js_url(hass, f"{URL_BASE}/{MODULE}?v={version}")
        data["static_registered"] = True
    if PANEL_URL not in hass.data.get(frontend.DATA_PANELS, {}):
        await panel_custom.async_register_panel(hass, webcomponent_name="hems-panel", frontend_url_path=PANEL_URL, sidebar_title="HEMS",
                                                sidebar_icon="mdi:home-lightning-bolt", module_url=f"{URL_BASE}/{MODULE}?v={version}",
                                                require_admin=False, config={})


def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar entry (the static files stay served until the restart; that is harmless)."""
    if "frontend" not in hass.config.components:
        return
    frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
