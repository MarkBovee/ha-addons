"""Constants and defaults of the HEMS integration (dry-run planner)."""
from datetime import timedelta

DOMAIN = "hems"
PLATFORMS = ["sensor"]

# Entity roles chosen in the config flow (HEMS only ever sees these Home Assistant entities).
CONF_SOC = "soc_entity"
CONF_BATTERY_POWER = "battery_power_entity"
CONF_BATTERY_POSITIVE_DISCHARGING = "battery_power_positive_is_discharging"
CONF_PV = "pv_entity"
CONF_GRID = "grid_entity"                      # + import / - export
CONF_INVERTER = "inverter_output_entity"       # optional: AC output of the inverter, a better house-load source
CONF_EV = "ev_power_entity"                    # optional: subtracted from the house load
CONF_PRICE_CURVE = "price_curve_entity"        # sensor with a `price_curve` attribute: [{start, end, price}]

# Settings (options flow) and their defaults. Price components mirror the energy-prices add-on.
DEFAULT_OPTIONS = {
    "capacity_kwh": 25.0,
    "max_power_kw": 8.0,
    "hard_min_soc_pct": 5.0,
    "reserve_soc_pct": 30.0,
    "round_trip_eff": 0.82,
    "wear_cost": 0.10,
    "pv_gain_w_per_wm2": 0.0,                  # 0 = calibrate from recorded PV against the weather data
    "pv_max_ac_w": 8000.0,
    "weather_enabled": True,
    "import_vat_multiplier": 1.21,
    "import_markup": 0.02,
    "import_energy_tax": 0.11085,
    "export_vat_multiplier": 1.21,
    "export_bonus_pct": 0.10,
    "export_fixed_bonus": 0.02,
    "export_energy_tax": 0.11085,
    "salderen": True,
    "bonus_only_daylight": True,
    "bonus_only_positive_price": True,
}

HISTORY_DAYS = 7
HISTORY_REFRESH = timedelta(hours=1)
WEATHER_REFRESH = timedelta(minutes=30)
WEATHER_MAX_AGE = timedelta(hours=6)           # beyond this the forecast is dropped, not trusted
TRACE_DIR = "hems"
TRACE_FILE = "decision_trace.jsonl"
