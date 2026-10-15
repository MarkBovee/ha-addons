## ADDED Requirements

### Requirement: Decision trace
On every schedule generation the battery manager SHALL append one JSON line to the decision trace file containing the inputs, intermediate results and published periods of that generation, and SHALL expose the last record as attributes of `sensor.battery_manager_decision`. The file SHALL be rotated at about 20 MB or 14 days. A write failure SHALL NOT prevent planning.

#### Scenario: Sell window truncated
- **WHEN** a sell window is truncated or dropped by the feasibility filter
- **THEN** the record lists its rank, decision, reason, needed and available kWh, reserve floor and projected SoC at its start

### Requirement: Projected SoC for sell windows
Sell windows SHALL be judged on the SoC projected at their start: current SoC above the reserve floor plus planned grid charge and forecast PV share ending before the window, minus earlier sell windows.

#### Scenario: Low midday SoC with PV forecast
- **WHEN** the plan is made at 36% SoC with enough remaining PV forecast to fill the battery before the evening
- **THEN** the evening sell window is kept at its full duration

### Requirement: Grid-charge margin
Grid charging in windows without a strict top-X cheapest slot, and the sell-buffer precharge, SHALL only be planned when `sell * round_trip_efficiency - charge_price >= grid_charge_min_margin`, where `sell` is the duration-weighted price of the sell windows following the charge. Without a following sell window the charge SHALL be skipped. The emergency precharge below `sell_buffer_min_soc` is exempt.

#### Scenario: Night charge below margin
- **WHEN** a spread-only night window at 0.315 is followed only by sell windows at 0.42
- **THEN** the window is skipped and the reason is logged and traced

### Requirement: Margin basis
The profit margin of sell windows SHALL be `cost_basis + min_profit_threshold`. With `margin_basis = day_min_import` the cost basis is the day's lowest import price; with `solar_export` it is the lowest export price in the planned or actually observed PV charge window (never below zero).

### Requirement: Sell hours after charging
With `discharge_after_charge_only` enabled, the top-X sell quarters of a day SHALL be chosen only from quarters at or after the end of that day's main charge window. Quarters before it SHALL NOT use the sell budget or trigger grid precharging.

#### Scenario: Morning peak
- **WHEN** a 08:00 quarter is the highest price of the day and the charge window is 11:15-16:00
- **THEN** the sell hours lie after 16:00

### Requirement: Stable charge power and publishing
The power of a charge window SHALL NOT be recomputed more than once per hour unless SoC deviates more than 5 pp from the projection or the remaining-solar forecast changes more than 25%. The schedule SHALL be sent to battery-api only when the published periods change, ignoring adaptive power steps below 100 W, with an hourly heartbeat.
