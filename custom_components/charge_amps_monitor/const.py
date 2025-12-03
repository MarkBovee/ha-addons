"""Constants for Charge Amps Monitor integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "charge_amps_monitor"

# Configuration keys
CONF_EMAIL: Final = "email"
CONF_PASSWORD: Final = "password"
CONF_HOST_NAME: Final = "host_name"
CONF_BASE_URL: Final = "base_url"
CONF_UPDATE_INTERVAL: Final = "update_interval"

# Defaults
DEFAULT_HOST_NAME: Final = "my.charge.space"
DEFAULT_BASE_URL: Final = "https://my.charge.space"
DEFAULT_UPDATE_INTERVAL: Final = 60  # seconds

# API Endpoints
API_AUTH_ENDPOINT: Final = "/api/auth/login"
API_CHARGE_POINTS_ENDPOINT: Final = "/api/users/chargepoints/owned"

# OCPP Status mapping
OCPP_STATUS_MAP: Final = {
    0: "Unknown",
    1: "Available",
    2: "Preparing",
    3: "Charging",
    4: "Suspended EV",
    5: "Suspended EVSE",
    6: "Finishing",
    7: "Reserved",
    8: "Unavailable",
    9: "Faulted",
}

# Charge Point Status mapping  
CHARGE_POINT_STATUS_MAP: Final = {
    0: "Unknown",
    1: "Online",
    2: "Offline",
    3: "Error",
}
