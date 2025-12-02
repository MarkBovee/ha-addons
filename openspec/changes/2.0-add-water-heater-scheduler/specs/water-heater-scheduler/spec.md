# water-heater-scheduler Specification

## Purpose
Schedule domestic hot water heating based on electricity price curves, optimizing for lowest cost while maintaining comfort and safety (legionella protection).

## ADDED Requirements

### Requirement: Price-Based Night Program Scheduling
The system SHALL schedule water heating during the lowest-priced 15-minute interval within the night window (default 00:00-06:00).

#### Scenario: Night program with cheaper night prices
- **WHEN** the current time is before 06:00
- **AND** the lowest night price (22.54 cents/kWh) is lower than the lowest day price (28.12 cents/kWh)
- **THEN** the system schedules heating at the night price window
- **AND** sets target temperature to 56°C
- **AND** updates status to "Night program planned at: HH:MM"

#### Scenario: Night program with expensive night prices
- **WHEN** the current time is before 06:00
- **AND** the lowest night price is higher than the lowest day price
- **THEN** the system schedules heating at the night price window
- **AND** sets target temperature to 52°C (reduced)

### Requirement: Price-Based Day Program Scheduling
The system SHALL schedule water heating during the lowest-priced interval in the day window (06:00-24:00) when not in night mode or legionella mode.

#### Scenario: Day program with very low price
- **WHEN** the current time is 06:00 or later
- **AND** the price level is "None" (below P20 percentile)
- **THEN** the system sets target temperature to 70°C (maximum heating)

#### Scenario: Day program with normal price
- **WHEN** the current time is 06:00 or later
- **AND** the price level is "Low", "Medium", or "High"
- **THEN** the system sets target temperature to 58°C

#### Scenario: Day program deferred due to cheaper tomorrow
- **WHEN** the current price level is above Medium
- **AND** tomorrow's night price is lower than current price
- **THEN** the system defers heating to tomorrow
- **AND** sets target temperature to idle (35°C)

### Requirement: Legionella Protection Cycle
The system SHALL run a high-temperature cycle on the configured day of week (default Saturday) to prevent legionella bacteria growth.

#### Scenario: Legionella cycle on Saturday
- **WHEN** the current day is Saturday (or configured legionella day)
- **AND** the current time is 06:00 or later
- **THEN** the system schedules a 3-hour heating cycle
- **AND** sets target temperature to 62-70°C based on price level

#### Scenario: Legionella start time optimization
- **WHEN** scheduling a legionella cycle
- **AND** the price 15 minutes before start time is lower than 15 minutes after
- **THEN** the system adjusts start time 15 minutes earlier
- **AND** logs the adjustment with price comparison

### Requirement: Away Mode Temperature Reduction
The system SHALL use reduced temperatures when away mode is active, while maintaining legionella protection.

#### Scenario: Away mode with legionella protection
- **WHEN** away mode switch is "on"
- **AND** it is legionella day (Saturday)
- **AND** current price is below 0.20 EUR/kWh
- **THEN** the system sets target temperature to 66°C

#### Scenario: Away mode with legionella protection (expensive)
- **WHEN** away mode switch is "on"
- **AND** it is legionella day
- **AND** current price is 0.20 EUR/kWh or higher
- **THEN** the system sets target temperature to 60°C

### Requirement: Bath Mode Auto-Disable
The system SHALL automatically disable bath mode when water temperature exceeds the bath threshold.

#### Scenario: Bath mode auto-disable at threshold
- **WHEN** bath mode input_boolean is "on"
- **AND** current water temperature exceeds 50°C (configurable)
- **THEN** the system turns off bath mode input_boolean
- **AND** logs the auto-disable action

### Requirement: Wait Cycle Transition Smoothing
The system SHALL use wait cycles to prevent rapid toggling between heating programs and idle state.

#### Scenario: Wait cycle countdown
- **WHEN** a heating program ends
- **AND** target temperature is above idle (35°C)
- **THEN** the system sets wait_cycles to 10 (configurable)
- **AND** decrements wait_cycles each 5-minute evaluation
- **AND** only transitions to idle when wait_cycles reaches 0

#### Scenario: Wait cycle reset on new program
- **WHEN** a new heating program starts during wait cycle countdown
- **THEN** the system resets wait_cycles to 10
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
