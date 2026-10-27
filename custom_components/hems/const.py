"""Constants and defaults of the HEMS integration (dry-run planner)."""
from datetime import timedelta

DOMAIN = "hems"
PLATFORMS = ["sensor", "binary_sensor", "switch", "select"]

# Entity roles chosen in the config flow (HEMS only ever sees these Home Assistant entities).
CONF_SOC = "soc_entity"
CONF_BATTERY_POWER = "battery_power_entity"
CONF_BATTERY_POSITIVE_DISCHARGING = "battery_power_positive_is_discharging"
CONF_PV = "pv_entity"
CONF_GRID = "grid_entity"                      # + import / - export
CONF_INVERTER = "inverter_output_entity"       # optional: AC output of the inverter, a better house-load source
CONF_EV = "ev_power_entity"                    # optional: subtracted from the house load
CONF_PRICE_CURVE = "price_curve_entity"        # optional: sensor with a `price_curve` attribute [{start, end, price}]; fallback and cross-check

# Optional roles of the EV module, the grid and the solar component. Like the roles above they are Home Assistant entities picked by the
# owner (reconfigure step); HEMS knows no charger brand, only that these carry the plug, the charge, the car's SoC and the currents.
CONF_EV_PLUGGED = "ev_plugged_entity"          # binary_sensor: a car is connected to the socket
CONF_EV_CHARGING = "ev_charging_entity"        # binary_sensor: the car is charging
CONF_EV_PROBLEM = "ev_problem_entity"          # binary_sensor: the socket reports a problem
CONF_EV_SOC = "ev_soc_entity"                  # sensor: the car's state of charge (%)
CONF_EV_LIMIT = "ev_limit_entity"              # number (A): only its `max` attribute is read, as the charger's ceiling
CONF_EV_CURRENTS = ("ev_current_l1_entity", "ev_current_l2_entity", "ev_current_l3_entity")           # the charger's current per phase (A)
CONF_METER_CURRENTS = ("meter_current_l1_entity", "meter_current_l2_entity", "meter_current_l3_entity")  # the grid meter's current per phase (A, no sign)
CONF_METER_EXPORTS = ("meter_export_l1_entity", "meter_export_l2_entity", "meter_export_l3_entity")      # the meter's feed-in power per phase: above 0 = exporting on that phase
CONF_PV_EXTRA = "pv_extra_entities"            # more PV power sensors, added to `pv_entity` (several arrays or inverters)

# Optional roles for the dashboard only (read, never planned on): the water heater or its tank temperature, when the last legionella
# run happened, and the action sensor of the battery manager HEMS replaces (for the transition comparison).
CONF_WATER_HEATER = "water_heater_entity"
CONF_LEGIONELLA_LAST = "legionella_last_entity"
CONF_COMPARE_ACTION = "compare_action_entity"
LEGIONELLA_OVERDUE = timedelta(days=8)        # the run is weekly; a day of slack before the alert

# Settings (options flow) and their defaults. Price components mirror the energy-prices add-on.
DEFAULT_OPTIONS = {
    "capacity_kwh": 25.0,
    "max_power_kw": 8.0,
    "hard_min_soc_pct": 5.0,
    "reserve_soc_pct": 30.0,
    "round_trip_eff": 0.82,
    "min_profit_margin": 0.10,
    "hold_cost_kwh_h": 0.002,                  # EUR per kWh per hour of waiting; 0 = off (charge as early as equal prices allow)
    "pv_gain_w_per_wm2": 0.0,                  # 0 = calibrate from recorded PV against the weather data
    "pv_max_ac_w": 5000.0,
    "weather_enabled": True,
    "water_heater_enabled": False,             # the water heater module: plans the daily heating run for the load forecast (the heating itself is not controlled)
    "water_heater_energy_kwh": 1.9,
    "water_heater_hours": 1,
    "water_heater_night_energy_kwh": 0.0,       # 0 = the day part carries the heating, no night run
    "water_heater_legionella_energy_kwh": 2.6,
    "water_heater_legionella_hours": 3,
    "water_heater_legionella_weekday": "saturday",
    "ev_enabled": False,                       # the EV module: plans the charge of the car (dry-run, nothing is written to the charger)
    "ev_capacity_kwh": 81.4,
    "ev_charge_efficiency": 0.90,              # grid kWh to battery kWh; to be measured with charger kWh against the SoC jump
    "ev_target_required_pct": 80.0,            # reached by every deadline
    "ev_target_max_pct": 100.0,                # reached only through quarters under the price threshold
    "ev_max_price": 0.20,                      # EUR/kWh, effective price (PV surplus counts at the export price)
    "ev_solar_only": False,
    "ev_min_current_a": 6.0,
    "ev_max_current_a": 16.0,
    "ev_min_on_minutes": 10.0,
    "ev_min_off_minutes": 10.0,
    "ev_deadline_monday": "07:30", "ev_deadline_tuesday": "", "ev_deadline_wednesday": "", "ev_deadline_thursday": "07:30",
    "ev_deadline_friday": "", "ev_deadline_saturday": "", "ev_deadline_sunday": "",       # local HH:MM, empty = no deadline that day
    "grid_limit_a": 25.0,                      # the connection's limit per phase (3x25 A)
    "grid_margin_a": 1.0,                      # kept free below it
    "trace_full_plan": True,                   # also log every planned quarter each cycle (about 1 MB per day)
    "nordpool_enabled": True,                  # HEMS fetches day-ahead prices itself
    "delivery_area": "NL",
    "import_vat_multiplier": 1.21,
    "import_markup": 0.02,
    "import_energy_tax": 0.11085,
    "export_vat_multiplier": 1.21,
    "export_bonus_pct": 0.10,
    "export_fixed_bonus": 0.02,
    "export_energy_tax": 0.11085,
    "salderen": True,
    "salderen_until": "2027-01-01",           # first local day without netting (the law ends it on 1 Jan 2027); empty = only the switch decides
    "bonus_only_daylight": True,
    "bonus_only_positive_price": True,
}

HISTORY_DAYS = 7
HISTORY_REFRESH = timedelta(hours=1)
WEATHER_REFRESH = timedelta(minutes=30)
WEATHER_MAX_AGE = timedelta(hours=6)           # beyond this the forecast is dropped, not trusted
RETRY_STATUSES = frozenset({"no_soc", "stale_soc", "no_prices"})   # inputs that usually appear within a minute after a restart
RETRY_DELAY = timedelta(seconds=60)
EXECUTION_NOTICE_W = 100               # a limited command that moves less than this between SoC updates is not worth a new state
TRACE_DIR = "hems"
TRACE_FILE = "decision_trace.jsonl"      # one line per cycle: inputs, the comparison behind the action, plan segments
PLANS_FILE = "plans.jsonl"                 # one line per cycle: every planned quarter with the inputs it came from
EVENTS_FILE = "events.jsonl"               # fetches, status changes, action changes, settings changes
BUILD_FILE = "BUILD"                  # written by hems/deploy.py: the commit this code was deployed from
STORE_VERSION = 1
SAMPLE_SECONDS = 10                      # live power is integrated into energy per quarter at this interval
