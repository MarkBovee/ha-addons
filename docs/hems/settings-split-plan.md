# Settings split: basic setup in HA, planning in the dashboard

Status: built on branch fix/hems-settings-save (2026-11-03): phases 1-4 done; the panel editor is not yet checked on the live server.

## Problem

The HA settings form (`config_flow.py`, `SECTIONS`) now has 75 fields in 8 sections. HA's options form only offers plain number boxes,
text fields and switches. Fields that belong together, such as seven separate `ev_deadline_<day>` text boxes or 13 water-heater
temperatures, cannot be shown as one week grid or one temperature ladder. The form also has no validation that spans fields
(min below max, sell floor below the charge ceiling). One field the frontend thinks is "missing" blocks the whole save; that was the bug
fixed today. The panel already has a Settings view, but it only reads the settings and describes them in words
(`settingsInWords`, `hems/settings`).

## Split rule

A setting stays in HA when it describes **the installation or the contract**: it rarely changes and you need it before the first plan.
A setting moves to the dashboard when it describes **behaviour or planning**: you tune it, it gains from a visual editor, and you want to see what it does to the plan.

| Stays in HA (Configure) | To the dashboard |
| --- | --- |
| Battery: capacity, max power, hard minimum, charge ceiling (`max_soc_pct`), round-trip efficiency | Sell floor min/max, load factor, min profit margin, hold cost |
| Module on/off: water heater, EV, spa | Water heater: energy, hours, legionella day/temp, all temperature levels, cycle gap |
| Prices: delivery area, VAT, markup, energy tax, bonuses, net metering + end date | EV: targets, max price, solar-only, currents, on/off times, **week grid of deadlines** |
| Forecast: weather on/off, PV max AC, PV gain | Spa: comfort temperature, band, heat rate, cooling |
| Grid: limit and margin (A) | Logging: full plan trace |
| Nord Pool on/off | |

That leaves about 25 fields in HA and about 50 in the dashboard.

## Design

1. **One settings registry** (`settings_schema.py`): per key it holds the type, bounds, step, default, section, unit, a short help text and `where` (`ha` or `panel`).
   `DEFAULT_OPTIONS`, `SECTIONS`, `NUMBERS` and `EMPTYABLE` are derived from it, so the HA form and the dashboard cannot drift apart.
2. **Storage stays as it is**: every setting stays in `entry.options` under the same key. No migration is needed, and existing installs keep their values.
3. **Write path**: a new admin-only websocket command `hems/settings/update` that takes `{key: value}`. It validates each value against the registry, then
   checks the cross-field rules (`hard_min ≤ reserve_min ≤ reserve_max ≤ max_soc`, EV required ≤ max, legionella min ≤ temp). It writes with
   `async_update_entry` and returns field errors the panel can show next to the input. It writes HEMS options only; it does not touch devices
   (the write lock in `const.WRITE_UNLOCKED` stays the only device gate).
4. **Apply without a full reload where safe**: planning keys only change `EngineSettings`, so the coordinator rebuilds the settings and replans
   at once. A key that changes entities or modules still reloads the entry.
5. **Panel UI** (Settings view, per module): sliders with the value shown for SoC limits, a SoC bar with floor, sell band and ceiling,
   a 7-day deadline grid for the EV, a temperature ladder for the water heater, and "what this changes" text from `settingsInWords`.
   It saves per section, with dirty state and an undo of the last save.
   Learned values (decided 2026-11-03): PV gain and round-trip efficiency stay configured in HA, and the panel shows the learned value
   next to the configured one (source: the `learned` event, for example round_trip_eff 0.86 learned vs 0.82 configured, from 195.9 kWh charged).
   The panel only shows them; it does not edit them.
6. **HA form** keeps only the `ha` keys plus one line: "Planning settings are in the HEMS panel". `flatten_sections` keeps merging on top of stored
   options, so panel keys survive a save of the HA form.

## Phases

1. Registry plus derived constants, no behaviour change (tests: the form lists the same fields; defaults are equal).
2. `hems/settings/update` with validation and cross-field rules (tests: a good save, a field error, a cross-field error, a non-admin is refused).
3. Panel editor for the battery and EV (the largest gain), then the water heater and spa.
4. Drop the `panel` keys from the HA form, add the hint line, and update the changelog and README (no breaking change: same keys, same values).

## Decisions

- 2026-11-03: a panel change applies at once (hot apply, step 4 of the design); only keys that change entities or modules reload the entry.
- 2026-11-03: PV gain and round-trip efficiency stay in HA; the panel shows their learned values (see step 5).
