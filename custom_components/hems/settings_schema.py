"""The HEMS settings in one place: their sections, bounds and kinds, and where each one is edited.

The Home Assistant settings form (config_flow) and the panel's settings editor (websocket `hems/settings/update`) both read this module,
so the two cannot drift apart. Pure Python: no Home Assistant imports, so the validation can be tested on its own.

Split rule (docs/hems/settings-split-plan.md): a setting about the installation or the contract stays in Home Assistant; a setting about
behaviour or planning is edited in the panel. Both are stored in the config entry's options under the same key."""
from datetime import date
from typing import Any

from .const import DEFAULT_OPTIONS

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

# The settings form, in the parts of the HEMS plan: the modules (battery, water heater, later EV) and the base components every module shares
# (prices, forecasts). Each part is a collapsible section in this order on screen; a module with an on/off switch has it as its first setting.
# The battery is open, the rest is folded away.
SECTIONS: dict[str, tuple[str, ...]] = {
    "module_battery": ("capacity_kwh", "max_power_kw", "hard_min_soc_pct", "reserve_soc_pct", "reserve_max_soc_pct", "max_soc_pct", "reserve_load_factor", "max_sell_quarters",
                       "reserve_soc_monday_pct", "reserve_soc_tuesday_pct", "reserve_soc_wednesday_pct", "reserve_soc_thursday_pct", "reserve_soc_friday_pct",
                       "reserve_soc_saturday_pct", "reserve_soc_sunday_pct", "round_trip_eff", "min_profit_margin", "hold_cost_kwh_h"),
    "module_water_heater": ("water_heater_enabled", "water_heater_energy_kwh", "water_heater_hours", "water_heater_night_energy_kwh",
                     "water_heater_legionella_energy_kwh", "water_heater_legionella_hours", "water_heater_legionella_weekday",
                     "water_heater_legionella_temp_c", "water_heater_legionella_min_c",
                     "water_heater_night_preheat_c", "water_heater_night_minimal_c", "water_heater_day_preheat_c", "water_heater_idle_c", "water_heater_low_price_c", "water_heater_negative_price_c", "water_heater_bath_c", "water_heater_away_c", "water_heater_bath_off_c", "water_heater_cycle_gap_min"),
    "module_ev": ("ev_enabled", "ev_capacity_kwh", "ev_charge_efficiency", "ev_target_required_pct", "ev_target_max_pct", "ev_max_price", "ev_solar_only",
                  "ev_min_current_a", "ev_max_current_a", "ev_min_on_minutes", "ev_min_off_minutes", "ev_deadline_monday", "ev_deadline_tuesday",
                  "ev_deadline_wednesday", "ev_deadline_thursday", "ev_deadline_friday", "ev_deadline_saturday", "ev_deadline_sunday"),
    "module_spa": ("spa_enabled", "spa_control", "spa_daily_kwh", "spa_phase", "spa_heater_kw", "spa_comfort_c", "spa_above_c", "spa_below_c", "spa_heat_rate_c_h", "spa_cool_k_h"),
    "base_prices": ("nordpool_enabled", "delivery_area", "import_vat_multiplier", "import_markup", "import_energy_tax", "export_vat_multiplier",
               "export_bonus_pct", "export_fixed_bonus", "export_energy_tax", "salderen", "salderen_until", "bonus_only_daylight", "bonus_only_positive_price"),
    "base_forecast": ("weather_enabled", "pv_gain_w_per_wm2", "pv_max_ac_w"),
    "base_grid": ("grid_limit_a", "grid_margin_a"),
    "logging": ("trace_full_plan",),
}
OPEN_SECTIONS = ("module_battery",)
NUMBERS = {"capacity_kwh": (1, 100, 0.1), "max_power_kw": (0.5, 30, 0.1), "hard_min_soc_pct": (0, 50, 1), "reserve_soc_pct": (0, 100, 1), "reserve_max_soc_pct": (0, 100, 1), "max_soc_pct": (50, 100, 1), "reserve_load_factor": (1, 3, 0.05), "max_sell_quarters": (0, 48, 1),
           **{f"reserve_soc_{day}_pct": (0, 100, 1) for day in DAYS},
           "round_trip_eff": (0.5, 1.0, 0.01), "min_profit_margin": (0, 1, 0.01), "hold_cost_kwh_h": (0, 0.05, 0.0005), "pv_gain_w_per_wm2": (0, 30, 0.1),
           "pv_max_ac_w": (0, 30000, 100), "import_vat_multiplier": (1, 2, 0.01), "import_markup": (-0.5, 0.5, 0.0001), "import_energy_tax": (0, 1, 0.00001),
           "export_vat_multiplier": (1, 2, 0.01), "export_bonus_pct": (0, 1, 0.01), "export_fixed_bonus": (-0.5, 0.5, 0.0001),
           "export_energy_tax": (0, 1, 0.00001), "water_heater_energy_kwh": (0, 15, 0.1), "water_heater_hours": (1, 6, 1),
           "water_heater_night_energy_kwh": (0, 15, 0.1), "water_heater_legionella_energy_kwh": (0, 15, 0.1), "water_heater_legionella_hours": (1, 6, 1),
           "water_heater_legionella_temp_c": (55, 75, 1), "water_heater_legionella_min_c": (50, 70, 1),
           "water_heater_night_preheat_c": (30, 75, 1), "water_heater_night_minimal_c": (30, 75, 1), "water_heater_day_preheat_c": (30, 75, 1), "water_heater_idle_c": (30, 75, 1), "water_heater_low_price_c": (30, 75, 1), "water_heater_negative_price_c": (30, 75, 1), "water_heater_bath_c": (30, 75, 1), "water_heater_away_c": (30, 75, 1), "water_heater_bath_off_c": (30, 75, 1), "water_heater_cycle_gap_min": (10, 180, 5),
           "spa_heater_kw": (0.5, 12, 0.1), "spa_daily_kwh": (0, 80, 0.5), "spa_comfort_c": (20, 40, 0.5), "spa_above_c": (0, 3, 0.5), "spa_below_c": (0, 5, 0.5),
           "spa_heat_rate_c_h": (0.2, 10, 0.1), "spa_cool_k_h": (0, 0.2, 0.005),
           "ev_capacity_kwh": (10, 200, 0.1), "ev_charge_efficiency": (0.5, 1, 0.01), "ev_target_required_pct": (0, 100, 1), "ev_target_max_pct": (0, 100, 1),
           "ev_max_price": (-1, 2, 0.01), "ev_min_current_a": (1, 32, 1), "ev_max_current_a": (6, 32, 1), "ev_min_on_minutes": (0, 120, 1),
           "ev_min_off_minutes": (0, 120, 1), "grid_limit_a": (6, 80, 1), "grid_margin_a": (0, 10, 0.5)}

# Discrete choices; the HA form shows them as a dropdown, the panel as a select.
CHOICES: dict[str, tuple[str, ...]] = {"water_heater_legionella_weekday": DAYS, "spa_phase": ("l1", "l2", "l3"), "spa_control": ("external", "climate")}
TIMES = frozenset(f"ev_deadline_{d}" for d in DAYS)        # local HH:MM or empty
DATES = frozenset({"salderen_until"})                     # ISO date or empty
TEXTS = frozenset({"delivery_area"})
# Settings that may be left empty (no deadline that day, no end date). The frontend refuses to save while a required field is empty,
# so these are optional in the form; a submitted section without one of them means the user cleared it.
EMPTYABLE = frozenset({"salderen_until", *(f"ev_deadline_{d}" for d in DAYS)})

# Edited in the panel: behaviour and planning. Everything else stays in the Home Assistant form.
PANEL_KEYS = frozenset({
    "reserve_soc_pct", "reserve_max_soc_pct", "reserve_load_factor", "max_sell_quarters", *(f"reserve_soc_{d}_pct" for d in DAYS),
    "min_profit_margin", "hold_cost_kwh_h",
    *(k for k in SECTIONS["module_water_heater"] if k != "water_heater_enabled"),
    "ev_target_required_pct", "ev_target_max_pct", "ev_max_price", "ev_solar_only", "ev_min_current_a", "ev_max_current_a",
    "ev_min_on_minutes", "ev_min_off_minutes", *TIMES,
    "spa_daily_kwh", "spa_comfort_c", "spa_above_c", "spa_below_c", "spa_heat_rate_c_h", "spa_cool_k_h",
    "trace_full_plan",
})
# The Home Assistant form: the sections without the panel settings; a section that keeps nothing is left out.
HA_SECTIONS: dict[str, tuple[str, ...]] = {name: kept for name, keys in SECTIONS.items() if (kept := tuple(k for k in keys if k not in PANEL_KEYS))}
# Shown next to the configured value in the panel, read-only (decided 3 Nov 2026): they stay configured in Home Assistant.
LEARNED_KEYS = ("round_trip_eff", "pv_gain_w_per_wm2")


def kind(key: str) -> str:
    """The input kind of one setting: number, choice, time, date, text or bool."""
    if key in NUMBERS:
        return "number"
    if key in CHOICES:
        return "choice"
    if key in TIMES:
        return "time"
    if key in DATES:
        return "date"
    return "text" if key in TEXTS else "bool"


def spec(key: str) -> dict[str, Any]:
    """One setting as the panel needs it: key, kind and, per kind, bounds or choices."""
    out: dict[str, Any] = {"key": key, "kind": kind(key)}
    if key in NUMBERS:
        out["min"], out["max"], out["step"] = NUMBERS[key]
    if key in CHOICES:
        out["options"] = list(CHOICES[key])
    return out


def panel_sections() -> list[dict[str, Any]]:
    """The panel's settings, in form order, grouped by section (only sections with a panel setting)."""
    return [{"section": name, "settings": [spec(k) for k in keys if k in PANEL_KEYS]} for name, keys in SECTIONS.items() if any(k in PANEL_KEYS for k in keys)]


def _valid_time(text: str) -> bool:
    """HH:MM on a 24-hour clock."""
    hours, sep, minutes = text.partition(":")
    return sep == ":" and hours.isdigit() and minutes.isdigit() and len(minutes) == 2 and int(hours) < 24 and int(minutes) < 60


def _valid_date(text: str) -> bool:
    """An ISO date such as 2027-01-01."""
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def coerce(key: str, value: Any) -> tuple[Any, str | None]:
    """One submitted value checked and converted to its stored type; the second item is an error text, None when valid."""
    match kind(key):
        case "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return value, "must be a number"
            low, high, _step = NUMBERS[key]
            if not low <= value <= high:
                return value, f"must be between {low:g} and {high:g}"
            # whole-number settings (hours, minutes, quarters) keep their int type: the engine counts with them
            if isinstance(DEFAULT_OPTIONS[key], int):
                return (int(value), None) if float(value).is_integer() else (value, "must be a whole number")
            return float(value), None
        case "bool":
            return (value, None) if isinstance(value, bool) else (value, "must be on or off")
        case "choice":
            return (value, None) if value in CHOICES[key] else (value, "is not one of the choices")
        case "time":
            text = str(value).strip()
            return (text, None) if not text or _valid_time(text) else (value, "must be HH:MM or empty")
        case "date":
            text = str(value).strip()
            return (text, None) if not text or _valid_date(text) else (value, "must be a date (2027-01-01) or empty")
        case _:
            return (str(value).strip(), None) if str(value).strip() else (value, "may not be empty")


def cross_errors(o: dict[str, Any]) -> dict[str, str]:
    """Rules between settings, on the merged options; the error sits on the setting a user just moved past the other one."""
    errors: dict[str, str] = {}
    if o["reserve_soc_pct"] < o["hard_min_soc_pct"]:
        errors["reserve_soc_pct"] = f"must be at least the hard minimum ({o['hard_min_soc_pct']:g} %)"
    if o["reserve_max_soc_pct"] < o["reserve_soc_pct"]:
        errors["reserve_max_soc_pct"] = "must be at least the sell floor minimum"
    if o["reserve_max_soc_pct"] > o["max_soc_pct"]:
        errors["reserve_max_soc_pct"] = f"must be at most the charge ceiling ({o['max_soc_pct']:g} %)"
    for day in DAYS:
        value = o[f"reserve_soc_{day}_pct"]
        if value and not o["hard_min_soc_pct"] <= value <= o["max_soc_pct"]:
            errors[f"reserve_soc_{day}_pct"] = "must be 0 (general minimum) or between the hard minimum and the charge ceiling"
    if o["ev_target_required_pct"] > o["ev_target_max_pct"]:
        errors["ev_target_required_pct"] = "must be at most the maximum target"
    if o["ev_min_current_a"] > o["ev_max_current_a"]:
        errors["ev_min_current_a"] = "must be at most the maximum current"
    if o["water_heater_legionella_min_c"] > o["water_heater_legionella_temp_c"]:
        errors["water_heater_legionella_min_c"] = "must be at most the legionella temperature"
    if o["water_heater_night_minimal_c"] > o["water_heater_night_preheat_c"]:
        errors["water_heater_night_minimal_c"] = "must be at most the night preheat temperature"
    return errors


def validate_panel_changes(current: dict[str, Any], changes: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Changes from the panel on top of the current options (defaults filled in).

    Returns the converted changes and the errors per key; with any error nothing may be stored. Keys outside the panel's share
    are refused, so the panel cannot change entities, modules or contract values behind the Home Assistant form."""
    errors = {key: "is not a panel setting" for key in changes if key not in PANEL_KEYS}
    converted: dict[str, Any] = {}
    for key, value in changes.items():
        if key in PANEL_KEYS:
            converted[key], error = coerce(key, value)
            if error:
                errors[key] = error
    if errors:
        return converted, errors
    return converted, {k: v for k, v in cross_errors({**current, **converted}).items() if k in converted}
