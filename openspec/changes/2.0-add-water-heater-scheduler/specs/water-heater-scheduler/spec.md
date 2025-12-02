# water-heater-scheduler Specification

## Purpose
Schedule domestic hot water heating based on electricity price curves, optimizing for lowest cost while maintaining comfort and safety (legionella protection).

## ADDED Requirements

### Requirement: User-Configurable Entity Selection
The system SHALL allow users to select target entities via the add-on configuration UI.

#### Scenario: Configure water heater entity
- **WHEN** the user sets `water_heater_entity_id` to `water_heater.my_heat_pump`
- **THEN** the system controls that specific water heater entity
- **AND** reads current temperature from its attributes
- **AND** sets operation mode and target temperature via HA services

#### Scenario: Configure price sensor entity
- **WHEN** the user sets `price_sensor_entity_id` to `sensor.ep_price_import`
- **THEN** the system reads price curves from that sensor's attributes
- **AND** uses the `price_curve` and `price_level` attributes for scheduling decisions

#### Scenario: Configure auxiliary entities
- **WHEN** the user configures `away_mode_entity_id`, `bath_mode_entity_id`, and `status_text_entity_id`
- **THEN** the system uses those entities for away mode detection, bath mode control, and status display

### Requirement: User-Configurable Temperature Settings
The system SHALL allow users to configure all temperature thresholds via the add-on configuration UI.

#### Scenario: Custom night program temperature
- **WHEN** the user sets `temp_night_program` to 54
- **AND** night prices are cheaper than day prices
- **THEN** the system uses 54°C as the night program target (instead of default 56°C)

#### Scenario: Custom idle temperature
- **WHEN** the user sets `temp_idle` to 40
- **THEN** the system uses 40°C as the idle/standby temperature (instead of default 35°C)

#### Scenario: Custom bath threshold
- **WHEN** the user sets `temp_bath_threshold` to 55
- **AND** bath mode is enabled
- **AND** current water temperature exceeds 55°C
- **THEN** the system auto-disables bath mode

### Requirement: User-Configurable Schedule Settings
The system SHALL allow users to configure scheduling parameters via the add-on configuration UI.

#### Scenario: Custom night window
- **WHEN** the user sets `night_window_start` to "23:00" and `night_window_end` to "07:00"
- **THEN** the system uses 23:00-07:00 as the night price window (instead of default 00:00-06:00)

#### Scenario: Custom legionella day
- **WHEN** the user sets `legionella_day_of_week` to "Sunday"
- **THEN** the system runs legionella protection on Sundays (instead of default Saturday)

#### Scenario: Custom evaluation interval
- **WHEN** the user sets `schedule_interval_minutes` to 10
- **THEN** the system evaluates the schedule every 10 minutes (instead of default 5)

### Requirement: Price-Based Night Program Scheduling
The system SHALL schedule water heating during the lowest-priced 15-minute interval within the configured night window.

#### Scenario: Night program with cheaper night prices
- **WHEN** the current time is within the night window
- **AND** the lowest night price is lower than the lowest day price
- **THEN** the system schedules heating at the night price window
- **AND** sets target temperature to configured `temp_night_program` (default 56°C)
- **AND** updates status to "Night program planned at: HH:MM"

#### Scenario: Night program with expensive night prices
- **WHEN** the current time is within the night window
- **AND** the lowest night price is higher than the lowest day price
- **THEN** the system schedules heating at the night price window
- **AND** sets target temperature to configured `temp_night_program_low` (default 52°C)

### Requirement: Price-Based Day Program Scheduling
The system SHALL schedule water heating during the lowest-priced interval in the day window when not in night mode or legionella mode.

#### Scenario: Day program with very low price
- **WHEN** the current time is outside the night window
- **AND** the price level is "None" (below P20 percentile)
- **THEN** the system sets target temperature to configured `temp_day_program_max` (default 70°C)

#### Scenario: Day program with normal price
- **WHEN** the current time is outside the night window
- **AND** the price level is "Low", "Medium", or "High"
- **THEN** the system sets target temperature to configured `temp_day_program` (default 58°C)

#### Scenario: Day program deferred due to cheaper tomorrow
- **WHEN** `next_day_price_check` is enabled (default true)
- **AND** the current price level is above Medium
- **AND** tomorrow's night price is lower than current price
- **THEN** the system defers heating to tomorrow
- **AND** sets target temperature to configured `temp_idle` (default 35°C)

### Requirement: Legionella Protection Cycle
The system SHALL run a high-temperature cycle on the configured day of week to prevent legionella bacteria growth.

#### Scenario: Legionella cycle on configured day
- **WHEN** the current day matches configured `legionella_day_of_week` (default Saturday)
- **AND** the current time is outside the night window
- **THEN** the system schedules a heating cycle for configured `legionella_duration_hours` (default 3)
- **AND** sets target temperature to configured `temp_legionella` or `temp_legionella_max` based on price level

#### Scenario: Legionella start time optimization
- **WHEN** scheduling a legionella cycle
- **AND** the price 15 minutes before start time is lower than 15 minutes after
- **THEN** the system adjusts start time 15 minutes earlier
- **AND** logs the adjustment with price comparison

### Requirement: Away Mode Temperature Reduction
The system SHALL use reduced temperatures when away mode is active, while maintaining legionella protection.

#### Scenario: Away mode with legionella protection (cheap price)
- **WHEN** configured away mode entity is "on"
- **AND** it is legionella day
- **AND** current price is below configured `cheap_price_threshold` (default 0.20 EUR/kWh)
- **THEN** the system sets target temperature to configured `temp_away_legionella_cheap` (default 66°C)

#### Scenario: Away mode with legionella protection (expensive price)
- **WHEN** configured away mode entity is "on"
- **AND** it is legionella day
- **AND** current price is at or above configured `cheap_price_threshold`
- **THEN** the system sets target temperature to configured `temp_away_legionella` (default 60°C)

### Requirement: Bath Mode Auto-Disable
The system SHALL automatically disable bath mode when water temperature exceeds the configured bath threshold.

#### Scenario: Bath mode auto-disable at threshold
- **WHEN** configured bath mode entity is "on"
- **AND** current water temperature exceeds configured `temp_bath_threshold` (default 50°C)
- **THEN** the system turns off the bath mode entity
- **AND** logs the auto-disable action

### Requirement: Wait Cycle Transition Smoothing
The system SHALL use wait cycles to prevent rapid toggling between heating programs and idle state.

#### Scenario: Wait cycle countdown
- **WHEN** a heating program ends
- **AND** target temperature is above configured `temp_idle`
- **THEN** the system sets wait_cycles to configured `wait_cycles_limit` (default 10)
- **AND** decrements wait_cycles each evaluation interval
- **AND** only transitions to idle when wait_cycles reaches 0

#### Scenario: Wait cycle reset on new program
- **WHEN** a new heating program starts during wait cycle countdown
- **THEN** the system resets wait_cycles to configured `wait_cycles_limit`
- **AND** applies the new program's target temperature

### Requirement: Status Entity Updates
The system SHALL update Home Assistant entities with current schedule status for dashboard display.

#### Scenario: Status during active heating
- **WHEN** a heating program is active
- **THEN** the system updates `input_text.heating_schedule_status` with "{Program} program from: HH:MM to: HH:MM"
- **AND** creates/updates `sensor.wh_program_type` with current program name
- **AND** creates/updates `sensor.wh_target_temp` with target temperature

#### Scenario: Status during idle with planned program
- **WHEN** no program is currently active
- **AND** a program is scheduled for later today
- **THEN** the system updates status to "{Program} program planned at: HH:MM"

### Requirement: Price Data Integration
The system SHALL read price curves from the energy-prices add-on sensor attributes.

#### Scenario: Successful price data read
- **WHEN** the system evaluates the schedule
- **THEN** it reads `sensor.ep_price_import` state and attributes
- **AND** parses `price_curve` attribute as Dict[datetime, float]
- **AND** uses `price_level` attribute for temperature decisions

#### Scenario: Price sensor unavailable
- **WHEN** `sensor.ep_price_import` is unavailable or has no price_curve
- **THEN** the system logs a warning
- **AND** skips the current evaluation cycle
- **AND** retries on the next 5-minute interval

### Requirement: State Persistence Across Restarts
The system SHALL persist scheduling state to survive container restarts.

#### Scenario: State saved on shutdown
- **WHEN** the add-on receives shutdown signal
- **THEN** the system saves `heater_on`, `target_temperature`, `wait_cycles` to `/data/state.json`

#### Scenario: State restored on startup
- **WHEN** the add-on starts
- **AND** `/data/state.json` exists and is valid
- **THEN** the system restores `heater_on`, `target_temperature`, `wait_cycles`
- **AND** logs the restored state values
