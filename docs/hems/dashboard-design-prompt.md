# Prompt for Claude Design: the HEMS dashboard in Home Assistant

Paste everything below the line into Claude Design. It is written in English because that is the language of the system's entity names and documentation; the dashboard text itself is Dutch (see section 3).

---

## 0. What I ask of you

Design the dashboard for **HEMS**, a home energy management system that runs inside my Home Assistant. I want an interface that is a graphic masterpiece and, at the same time, the clearest possible answer to the questions "what is my house doing with energy right now, what will it do next, and why?".

**I am not prescribing any design.** Everything below describes what the system is, what it knows, what it will do and what I want to be able to see and do. Choosing the visual language, the layout, the information hierarchy, the chart forms, the interaction patterns, the colour system, the typography, the motion and the way controls are presented is **your job**. Research what the best energy, smart-home, trading and operations interfaces do today (consumer energy apps, home battery and EV apps, grid and trading dashboards, flight-deck and industrial control-room displays, data-journalism charts) and decide for yourself what fits this system. Show me the references you drew on, explain your reasoning, and then go beyond them. Challenge anything in this brief that you think makes a worse interface.

Please deliver:
1. A short research summary: what you looked at, what you learned, what you chose and what you rejected, and why.
2. The design concept: structure of the dashboard (screens, navigation, the relationship between overview and detail), the visual system, and the key components with their states (normal, empty, loading, stale data, fault, disabled, "dry-run", future "live").
3. Concrete visual designs of the main screens, for phone, tablet and a large wall or desk display.
4. A specification precise enough that it can be built in Home Assistant: for every element, which entity or attribute feeds it (use the names in section 6), how it updates, and what it does when the data is missing or old.
5. Where Home Assistant's built-in dashboard capabilities (see section 3) cannot deliver the design, say so, and propose the smallest extension that would (for example a custom card, extra helper entities, or extra attributes on HEMS entities). I can change HEMS itself, so tell me which data you wish it published.

Ask me questions where my answers would change the design. Do not ask me for things you can research.

## 1. What HEMS is

HEMS is a modular energy planner. Once every quarter of an hour it looks at the electricity prices, the weather and solar forecast, the expected consumption of the house, and the state of the battery, the car and the hot-water boiler, and it computes **one plan for the whole house** over the next 24 to 48 hours. It explains every decision in words and numbers.

Principles that must be visible in the interface:
- **Explainability is the product.** Every action has a reason, a price comparison and an alternative that was rejected. The dashboard should make "why is it doing this?" a first-class, always-reachable question, not a log file.
- **Modules propose, the engine decides.** Each module (battery, water heater, EV) only proposes what it wants; the engine makes the single house plan and a per-device executor decides what may really be sent. The dashboard should show this chain.
- **Honest about uncertainty.** Forecasts (PV, house load) are estimates and are wrong by a known amount; prices for tomorrow are not known until early afternoon; sensor data can be stale. The interface must show confidence and data age, not pretend certainty.
- **Home Assistant is the only integration boundary.** HEMS reads Home Assistant entities and (later) calls Home Assistant services. It knows no brand, protocol or vendor.
- **Dry-run today, live tomorrow.** At this moment HEMS plans but controls nothing. In the coming weeks one module at a time will be allowed to act. The dashboard must make the difference between "this is what HEMS would do" and "this is what HEMS is doing" unmistakable, and must be designed so that the same screens work in both situations.

## 2. The household and the hardware (context, not a design input)

- Dutch house, dynamic electricity contract (Zonneplan, Nord Pool day-ahead prices, quarter-hour resolution, prices in EUR/kWh including VAT and energy tax). The salderingsregeling (netting) ends on 1 January 2027, after which the export price drops (no energy-tax refund); the system already models this by date.
- Grid connection **3 x 25 A** (the limit is per phase). Smart meter (DSMR) with per-phase current and power.
- Solar: roughly 5 kW peak (inverter 8 kW). Home battery: **25 kWh, up to 8 kW**, SAJ inverter. Round-trip efficiency about 0.82; wear cost is part of the economics.
- Electric car: Kia EV4 (81.4 kWh), charged by a 22 kW three-phase charger that the system may later set to 6 to 16 A per phase.
- Hot water: heat pump with a domestic hot water tank (Vaillant), planned in cheap hours, with a weekly legionella protection run at 62 degrees on a chosen weekday.
- Local time zone Europe/Amsterdam; all clock times shown are local; planning runs on a UTC quarter grid. Currency EUR.

## 3. The technical platform

**Home Assistant** 2026.10.4 (Home Assistant OS), UI language Dutch. HEMS is a custom integration (domain `hems`, device "HEMS") with ~26 entities. It is an ordinary integration: data reaches the dashboard only through entity states and attributes.

**Dashboards.** Lovelace dashboards in storage mode (UI-editable, saved as JSON). There are currently two: the default "Overview" (a sections-style view) and "Battery Management" (to be replaced). Home Assistant supports multiple dashboards, views, sections, badges, conditional visibility, and per-user or per-device layouts. The dashboard can also be shown full-screen without sidebar and header.

**Custom cards already installed (through HACS):** apexcharts-card, mushroom, button-card, card-mod, kiosk-mode, power-flow-card-plus, simple-swipe-card, clock-weather-card, mini-media-player, Helios. A theme add-on is installed. You are free to use any of these, to propose others (they must be installable via HACS or as a local module), or to propose a purpose-built custom card. Prefer approaches that survive Home Assistant updates.

**Constraints of the platform you must design within:**
- A dashboard cannot edit the integration's settings directly. HEMS settings live in the integration's options dialog ("Configure"), which opens as a Home Assistant modal. The dashboard can show settings, link to that dialog, and call services/toggle entities. Of all HEMS controls, only one entity is writable today (`switch.hems_ev_force_charge`). I can add switch, number, select and button entities to HEMS for the controls you want on the dashboard (module on/off, module mode, master switch, priorities); say which.
- Updates are not continuous. The plan is recomputed every quarter hour (a few seconds past the boundary), the battery executor re-checks on every battery SoC update, Home Assistant restarts occasionally (HEMS recovers within a minute and reports `no_soc` briefly). Some attributes are large series (up to 96 to 192 quarters) and are not stored in the history database; the history database keeps the states and the small attributes.
- Entity ids are stable and in English in every language (`sensor.hems_battery_action`); state labels and settings texts are translated to Dutch.
- Sign conventions: battery power **+ charging, - discharging** (AC side); grid **+ import, - export**; PV and house load are always >= 0.
- All times in attributes are local ISO times unless noted (the price_curve attribute is UTC).
- Data is local to my installation; the design must not rely on external web services at display time.

## 4. How HEMS works: the flow

**Inputs (Home Assistant entities and one weather source):**
state of charge and power of the battery, PV power, grid power at the meter, optional inverter output, car state of charge / plug / charging / problem, charger current per phase, grid meter current per phase, the recorder's long-term statistics for the consumption history (seven days), Nord Pool day-ahead prices (fetched by HEMS itself; tomorrow's prices appear around 13:15), and an Open-Meteo weather and irradiance forecast.

**Base components, shared by all modules (switchable settings, not devices):**
- Prices: market price converted to a consumer import price and export price per quarter, with the solar bonus rules and the end of netting.
- Forecasts: PV production per quarter (from irradiance, calibrated against my recorded PV) and base house load per quarter (median profile of the same local hour over the last seven days, with the planned boiler and car energy added at the hours they are planned).
- Grid connection: the 25 A per phase limit and the safety margin; the meter currents per phase.

**Modules (each can be switched on or off, and each only proposes):**
1. Battery. Chooses charge, discharge or idle per quarter from one economic objective over the whole horizon: charge when energy is cheap, sell or self-use when it is dear, keep what is worth more later, never below the reserve, only when a cycle earns more than a configured margin after round-trip loss. Produces: the action now, the power setpoint, the full plan, the charge/discharge windows, the "sell windows" (stretches of the price curve where selling pays) and the expected saving.
2. Water heater (boiler). Plans the daily heating run in the cheapest hour(s) of the night and the day part, a longer weekly legionella run, and puts that energy into the load forecast so the battery plans around it. Today it only plans; a separate add-on still does the heating.
3. EV. One planner with three priced terms: required energy (target state of charge before the next deadline of a weekly schedule, to the cheapest quarters before it), extra energy (up to a higher target, only in quarters under a price threshold) and PV surplus (surplus costs its export price, so charging on sun falls out of the prices). Plus an override "force charge". Produces: status, a quarter-by-quarter plan with current per phase, the setpoint that would be sent after hysteresis and after the grid headroom check.
4. Future modules: flexible loads, heat pump / space heating, and so on. The dashboard structure should make room for more modules without a redesign.

**Engine and executor.** The engine builds the house plan: modules' loads go into the load forecast, the battery plans around them, the grid connection limit caps grid charging per quarter. A per-phase load balancer checks the live meter currents against 25 A minus the margin and can throttle the car (and, later, other loads) by priority. An executor re-checks the plan against live data right before anything would be sent, and the system reports when it overrides the plan and why.

**Outputs today:** sensors and attributes only (dry-run). **Outputs planned:** per module one of three modes (dry-run, advisory, auto), a master switch that returns everything to dry-run, a priority order for loads, and hold/hysteresis settings; in "auto" HEMS will write to the inverter (time-of-use slots), the charger (current limit) and, later, the boiler.

**A decision cycle in words:** at each quarter boundary HEMS reads the inputs; if the battery state of charge is missing or old it reports why and plans nothing; otherwise it builds the price series (market first), the load and PV forecasts, the boiler and EV plans, plans the battery, runs the safety checks, writes one decision record with the reasons, and publishes the sensors.

## 5. Modules, settings, and switching on and off

Every module has an on/off setting; modules are listed in the order of the settings dialog. Values shown are today's defaults or current values; ranges are the allowed ranges.

**Module: battery** (always on)
- Usable capacity 25 kWh (1 to 100). Maximum charge/discharge power 8 kW (0.5 to 30). Hard minimum state of charge 5 % (0 to 50). Reserve state of charge 30 % (0 to 100). Round-trip efficiency 0.82 (0.5 to 1). Minimum profit margin: currently 0.08 EUR per discharged kWh, net of losses (0 to 1). Waiting cost 0.002 EUR per stored kWh per hour (0 to 0.05).

**Module: water heater** (on/off; currently on)
- Energy of a normal heating run 1.9 kWh (0 to 15), length 1 hour (1 to 6), energy of an optional night run 0 kWh (0 = none), legionella run energy 2.6 kWh, legionella length 3 hours, legionella weekday Saturday.

**Module: EV** (on/off; currently on, dry-run)
- Battery capacity 81.4 kWh; charging efficiency 0.90; required target state of charge 80 % at every deadline; maximum target 100 % (only through cheap quarters); price threshold for the extra energy 0.20 EUR/kWh (effective price, surplus counts at the export price); "solar only" (extra energy only where PV surplus covers the minimum current); minimum current 6 A, maximum 16 A per phase; minimum minutes on and off (10 each); seven optional deadlines, one per weekday, as local times (Monday and Thursday 07:30 today; empty = no deadline that day). Override: a switch "force charge" that plans the required energy as early and as hard as allowed, ends by itself when the car leaves or the target is reached, and is off after any restart on purpose.

**Base: prices**
- Nord Pool on/off, delivery area NL, import VAT multiplier 1.21, import markup 0.02, import energy tax 0.11085, export VAT multiplier 1.21, export bonus percentage 0.10, fixed export bonus 0.02, export energy tax 0.11085, netting on/off, netting ends on 2027-01-01, bonus only in daylight, bonus only for a positive price.

**Base: forecasts and solar**
- Weather on/off, PV gain (0 = calibrate automatically against recorded PV), PV peak AC power 5000 W. The PV sensor can be one entity or several (sum).

**Base: grid connection**
- Limit per phase 25 A, margin 1 A.

**Logging**
- Log the full plan every cycle (about 1 MB per day), on/off.

**Entity roles the owner assigns once** (shown for completeness): battery SoC and power, PV, grid power, optional inverter output, price curve fallback (now removed), EV power, car plugged / charging / problem / state of charge, charger current limit number (only its maximum is read), charger current per phase L1 to L3, meter current per phase L1 to L3, meter feed-in power per phase L1 to L3, extra PV sensors.

**Planned per-module controls (do not exist yet; design for them):** mode (dry-run / advisory / auto), priority in the load balancer, minimum that is always allowed, hold and hysteresis times, a global "HEMS may control" master switch with a clear armed/disarmed state, and confirmations for every state change that moves hardware.

## 6. What HEMS publishes today (entity catalogue)

All under the device "HEMS". Entity ids are fixed English; states of enum sensors are translated.

**Battery and plan**
- `sensor.hems_battery_action`: charge / discharge / idle for the current quarter. Attributes: the whole decision trace, notably `reason` (a sentence), `compare` (sell, buy and keep values in EUR per stored kWh and the best later opportunities), `segments` (the plan as runs), `windows`, `soc_pct`, `power_w`, `import_price`, `export_price`, `horizon_slots`, `status`.
- `sensor.hems_battery_setpoint` (W, + charge): what the executor would send now. Attributes `planned_w`, `power_w`, `overridden`, `reason`, `soc_pct`.
- `sensor.hems_executor`: as_planned, at_floor, limited_floor, at_full, limited_full, no_soc, stale_soc, expired, no_plan.
- `sensor.hems_plan`: the plan as one Dutch sentence ("Laden 10:45-13:15 - Ontladen 15:45-18:15 - ..."). Attributes: `markdown` (the plan as a table), `windows` (per window kwh, power, average price, SoC from/to, expected PV and load), `slots` (the next 12 hours per quarter: start, action, power_w, soc_kwh, reason), `quarters`.
- `sensor.hems_charge_window`, `sensor.hems_discharge_window` (timestamps = start of the first window; attributes with end, kWh, power, average price, SoC at both ends, PV and load inside the window).
- `sensor.hems_sell_window`: start of the next sell window; attribute `windows` per window with peak price, thresholds, status (planned, partial, no_stock, kept_for_later, unsold), sold kWh and the charge moments it comes from.
- `sensor.hems_expected_saving` (EUR over the horizon).
- `sensor.hems_status`: ok, no_soc, stale_soc, no_prices, no_price_for_now; attributes price source, weather age, history hours.
- `binary_sensor.hems_tomorrow_prices_available`.

**Prices**
- `sensor.hems_import_price`, `sensor.hems_export_price` (EUR/kWh, current quarter). Attributes `curve` (local ISO start + price, from now on) and `price_curve` (the whole local day and later, UTC start, end, price; this is the format of the old price sensor).
- `sensor.hems_price_average_today`, `_price_min_today`, `_price_max_today`, `sensor.hems_max_profit_today` (EUR/kWh).

**Forecast**
- `sensor.hems_pv_forecast_next_hour` and `_24h` (kWh; attribute `forecast` per quarter), `sensor.hems_load_forecast_next_hour` (kWh excluding the car; attribute `forecast`), `sensor.hems_irradiance_forecast` (W/m2) and `sensor.hems_temperature_forecast` (degrees C), each with per-quarter `forecast`.

**Boiler**
- `sensor.hems_water_heater_plan`: start of the next planned run; attribute `windows` (kind night / heating / legionella, start, end, expected kWh, average price).

**EV**
- `sensor.hems_ev_status`: off, not_plugged, no_soc, problem, idle, planned, deadline_at_risk, forced.
- `sensor.hems_ev_plan`: start of the first planned charge quarter. Attributes `status`, `reason`, `deadline`, `required_kwh`, `optional_kwh`, `planned_kwh`, `shortfall_kwh`, `quarters` (start, current_a, kwh, price_eur_kwh, surplus_kwh, tier = deadline / cheap / forced).
- `sensor.hems_ev_setpoint` (A per phase): what would be sent after hysteresis and the grid check. Attributes `planned_a`, `code` (as_planned, hold_min_on, hold_min_off, limited_by_grid, below_minimum, or the no-plan status), `reason`, `allowed_a` (what the live meter leaves for the car).
- `switch.hems_ev_force_charge` (writable).

**Related entities from the rest of the house that the dashboard may use** (they belong to other systems and are named here so you can combine them):
- Battery and inverter telemetry: `sensor.battery_api_battery_soc`, `_battery_power`, `_pv_power`, `_grid_power`, `_load_power`; the inverter's own sensors (`sensor.saj_*`, ~200).
- Grid meter: `sensor.power_usage` (W, + import, - export), `sensor.electricity_meter_current_phase_l1..l3`, `..._power_consumption_phase_l1..l3`, `..._power_production_phase_l1..l3`, voltage per phase.
- Charger: `sensor.ocpp_hub_ed13009a_power`, `_status`, `_current_l1..l3`, `_energy`, `_current_session`, `_last_session`, `binary_sensor.ocpp_hub_ed13009a_plugged_in`, `_car_charging`, `_problem`, `number.ocpp_hub_ed13009a_charge_limit`, mirror status to the vendor backend.
- Car: `sensor.ev4_ev_battery_level`, range, charging power, scheduled departure times.
- Boiler: the water heater entity, the water-heater add-on's `sensor.wh_heating_plan`, `sensor.wh_last_legionella`, `input_text.heating_schedule_status`.
- Weather: `weather.buienradar`, forecast.solar production sensors.
- During the transition (to be removed later): the old battery-manager sensors (`sensor.battery_manager_*`: current action, mode, status, schedule, decision, reasoning) and the old price add-on sensors.

## 7. What I want to see and do

Treat these as jobs the interface must do well, not as a screen list. Organise them however is best.

**Right now**
- What is the house doing with energy this second: PV, house, battery, grid, car, boiler, with direction and size; am I importing or exporting, and at what price right now compared with today.
- What HEMS wants the battery to do this quarter and why, in one sentence, with the deciding numbers (sell value, buy cost, keep value) available one tap deeper.
- Whether the executor changed the plan (limited by floor, full, stale data) and why.
- Health at a glance: is HEMS running, is the data fresh, is the price source market data, is tomorrow's price published, what build is running, did it recover after a restart.

**The plan**
- The next 24 to 48 hours on one time axis: import and export price per quarter, battery state of charge trajectory, the charge, discharge and idle blocks, the sell windows, PV forecast and house-load forecast, the boiler and EV runs, and "now". Comparing price against what the plan does must be effortless.
- For any quarter I touch: the action, the power, the reasons, the alternatives that were rejected, the forecast values behind it.
- The difference between the plan I saw an hour ago and the plan now (the plan shifts; show why).
- Money: expected saving over the horizon, today's realised result versus doing nothing, and the running total; later the same for the car and the boiler.

**Prices**
- Today and tomorrow (once published) as a landscape: cheap and dear periods, average, minimum, maximum, the best selling hours and the cheapest charging block, the maximum profit of a cycle, import against export, the effect of the netting end date.

**Solar and load**
- Forecast against actual for PV and for house load, the calibration, the error over the last days (the forecast bias is something I track), and the surplus (PV minus load) that the car and battery compete for.

**Battery**
- State of charge, power, reserve and hard floor, energy in stock and what it was bought at, cycles, the next sale and the next charge, the sell windows and their status, and an honest "why nothing happens" when the plan idles.

**Car**
- Plugged, state of charge, charging power and current per phase, deadline schedule (the weekly one, and the next deadline), what must be charged by when, the planned charge quarters with their effective price and the part covered by solar, the setpoint and why it is what it is, the grid headroom per phase, deadline at risk warnings, the force-charge override with its end condition, session history.

**Boiler**
- Tank temperature, program, the next planned run, the legionella status (last run, days ago, due date), and today's price window.

**Grid connection**
- Per phase current against the 25 A limit and margin, who uses what (house, car, battery grid-charging, boiler), headroom, and what the load balancer throttled and why.

**Control and settings**
- Switch modules on and off, see each module's current settings in plain words, jump to change them, and see which entities are assigned to which role. Show clearly what a change affects.
- The future master switch and per-module modes (dry-run, advisory, auto) with a safe, deliberate interaction for arming anything that moves hardware, and an obvious way to disarm everything at once.
- The EV override.
- Notifications I would want: deadline at risk, data stale, legionella overdue, a plan that could not be executed.

**Transition view (temporary but important):** while HEMS is in dry-run next to the old battery manager, I want to compare what each would do or did on the same day (actions, energy sold, price obtained, cash), with the cases where they disagree called out.

**History and learning:** what HEMS did yesterday and last week, the decisions that turned out right or wrong, forecast accuracy, and an explanation of any day's result.

## 8. Quality bar and guardrails

- The result should feel like a distinctive, crafted product, not a default Home Assistant card grid; but beauty must never cost truthfulness. Charts must be honest about scale, uncertainty and missing data.
- Works on a phone in one hand, on a tablet, and on a large display that can run unattended all day; readable at a glance from a distance and rich when I lean in. Light and dark appearance both considered. Accessibility (contrast, colour-blind safe encodings, touch targets, reduced motion) is part of the design.
- Every number has a unit and a time; every state has an empty, loading, stale and fault appearance; every control that can move hardware has a confirmation and a visible armed state.
- Text in the dashboard is Dutch, entity names stay English. Dates and times are local (24-hour clock), decimals with a comma in text, prices with four decimals where precision matters.
- Performance: it must stay smooth with 192-quarter series and a handful of live entities updating every few seconds, and must not poll anything outside Home Assistant.
- No secrets or credentials appear in the design; no part of the design may require a service outside my network.
- It has to be buildable and maintainable by me with Claude Code in Home Assistant: prefer structures that are described in YAML/JSON, versionable in a git repository, and robust to entity changes.

Start with the research summary and your questions, then show me the concept.
