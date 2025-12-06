# water-heater-scheduler Specification

## Purpose
Schedule domestic hot water heating based on electricity price curves, optimizing for lowest cost while maintaining comfort and safety (legionella protection).

## ADDED Requirements

### Requirement: Smart Entity Detection
The system SHALL auto-detect compatible entities and allow manual configuration.

#### Scenario: Auto-detect price sensor
- **WHEN** `price_sensor_entity_id` is not configured
- **AND** `sensor.ep_price_import` exists (energy-prices add-on installed)
- **THEN** the system automatically uses `sensor.ep_price_import`
- **AND** logs "Auto-detected price sensor: sensor.ep_price_import"

#### Scenario: Required water heater entity
- **WHEN** `water_heater_entity_id` is not configured
- **THEN** the system logs an error and exits
- **AND** displays "water_heater_entity_id is required"

#### Scenario: Optional away/bath mode entities
- **WHEN** `away_mode_entity_id` or `bath_mode_entity_id` is not configured
- **THEN** the system disables that feature (no error)
- **AND** logs "Away mode disabled (no entity configured)"

### Requirement: Temperature Presets
The system SHALL provide preset temperature profiles for common use cases.

#### Scenario: Select comfort preset (default)
- **WHEN** `temperature_preset` is "comfort" or not specified
- **THEN** the system uses: night_preheat=56°C, night_minimal=52°C, day_preheat=58°C, day_minimal=35°C, legionella=62°C

#### Scenario: Select eco preset
- **WHEN** `temperature_preset` is "eco"
- **THEN** the system uses: night_preheat=52°C, night_minimal=48°C, day_preheat=55°C, day_minimal=35°C, legionella=60°C

#### Scenario: Select performance preset
- **WHEN** `temperature_preset` is "performance"
- **THEN** the system uses: night_preheat=60°C, night_minimal=56°C, day_preheat=60°C, day_minimal=45°C, legionella=66°C

#### Scenario: Custom temperature override
- **WHEN** `temperature_preset` is "custom"
- **THEN** the system uses values from `night_preheat_temp`, `night_minimal_temp`, `day_preheat_temp`, `day_minimal_temp`, `legionella_temp`

### Requirement: Configuration Validation
The system SHALL validate configuration on startup and warn about potential issues.

#### Scenario: Validate legionella temperature
- **WHEN** custom `legionella_temp` is below 60°C
- **THEN** the system logs warning "Legionella temp below 60°C may not be effective for sanitization"
- **AND** continues with the configured value

#### Scenario: Validate temperature ordering
- **WHEN** custom `night_preheat_temp` is less than `night_minimal_temp`
- **THEN** the system logs warning "night_preheat should be higher than night_minimal"

#### Scenario: Validate required entity exists
- **WHEN** configured `water_heater_entity_id` does not exist in Home Assistant
- **THEN** the system logs error and exits
- **AND** displays "Water heater entity not found: {entity_id}"

### Requirement: Fixed Temperature Rules
The system SHALL apply fixed temperatures for specific conditions regardless of preset.

#### Scenario: Negative or zero price
- **WHEN** the current electricity price is ≤ 0 (negative or zero)
- **THEN** the system sets target temperature to 70°C (maximum)
- **AND** logs "Free/negative price - heating to maximum"

#### Scenario: Away mode active
- **WHEN** configured away mode entity is "on"
- **THEN** the system sets target temperature to 35°C
- **AND** continues legionella protection on scheduled day

#### Scenario: Bath mode active
- **WHEN** configured bath mode entity is "on"
- **AND** current water temperature is below 58°C
- **THEN** the system sets target temperature to 58°C

### Requirement: Night Program Scheduling
The system SHALL heat water during the cheapest interval in the night window based on price comparison.

#### Scenario: Night cheaper than day - preheat
- **WHEN** the current time is within night window (default 00:00-06:00)
- **AND** lowest night price < lowest day price
- **THEN** the system sets target to preset `night_preheat` temperature
- **AND** schedules heating at the lowest night price slot

#### Scenario: Day will be cheaper - minimal heating
- **WHEN** the current time is within night window
- **AND** lowest night price ≥ lowest day price
- **THEN** the system sets target to preset `night_minimal` temperature
- **AND** heats just enough to maintain comfort until day

### Requirement: Day Program Scheduling
The system SHALL heat water during the day based on comparison with tomorrow's prices.

#### Scenario: Today cheaper than tomorrow - preheat
- **WHEN** the current time is in day window (default 06:00-24:00)
- **AND** today's price < tomorrow's price
- **THEN** the system sets target to preset `day_preheat` temperature

#### Scenario: Tomorrow will be cheaper - minimal heating
- **WHEN** the current time is in day window
- **AND** today's price ≥ tomorrow's price
- **THEN** the system sets target to preset `day_minimal` temperature

### Requirement: Legionella Protection
The system SHALL run weekly high-temperature sanitization cycle.

#### Scenario: Legionella on scheduled day
- **WHEN** the current day matches `legionella_day` (default Saturday)
- **AND** the current time is in day window
- **THEN** the system sets target to preset `legionella` temperature
- **AND** runs for `legionella_duration_hours` (default 3 hours)

#### Scenario: Legionella start time optimization
- **WHEN** scheduling legionella cycle
- **AND** price 15 minutes before is lower than 15 minutes after optimal slot
- **THEN** the system shifts start time 15 minutes earlier

### Requirement: Bath Mode Auto-Disable
The system SHALL automatically disable bath mode when target temperature is reached.

#### Scenario: Bath reaches threshold
- **WHEN** bath mode entity is "on"
- **AND** current water temperature exceeds `bath_auto_off_temp` (default 50°C)
- **THEN** the system turns off the bath mode entity
- **AND** logs "Bath mode auto-disabled at {temp}°C"

### Requirement: Cycle Gap Protection
The system SHALL prevent rapid toggling between heating programs.

#### Scenario: Minimum gap between cycles
- **WHEN** a heating program completes
- **AND** less than `min_cycle_gap_minutes` (default 50) has passed
- **THEN** the system remains at current temperature
- **AND** does not start a new program until gap is satisfied

#### Scenario: New program after gap
- **WHEN** `min_cycle_gap_minutes` has passed since last cycle ended
- **THEN** the system evaluates and starts the appropriate program

### Requirement: Output Sensors
The system SHALL create sensors for dashboard integration (no input helpers required).

#### Scenario: Create program sensor
- **WHEN** the add-on starts
- **THEN** the system creates `sensor.wh_program` showing current program (Night/Day/Legionella/Bath/Away/Idle)

#### Scenario: Create temperature sensor
- **WHEN** the add-on starts
- **THEN** the system creates `sensor.wh_target_temp` showing current target in °C

#### Scenario: Create status sensor
- **WHEN** the add-on starts
- **THEN** the system creates `sensor.wh_status` with human-readable status message

### Requirement: Price Data Integration
The system SHALL read price curves from the configured price sensor.

#### Scenario: Parse price curve
- **WHEN** the system evaluates the schedule
- **THEN** it reads `price_curve` attribute from price sensor
- **AND** parses as Dict[datetime, float] with 15-minute intervals

#### Scenario: Price sensor unavailable
- **WHEN** price sensor is unavailable or has no price_curve
- **THEN** the system logs warning and skips cycle
- **AND** retries on next evaluation interval

### Requirement: State Persistence
The system SHALL persist state to survive container restarts.

#### Scenario: Save state on change
- **WHEN** the program or target temperature changes
- **THEN** the system saves to `/data/state.json`:
  - `current_program`: active program name
  - `target_temperature`: current target in °C
  - `last_cycle_end`: ISO timestamp of last cycle completion

#### Scenario: Restore state on startup
- **WHEN** the add-on starts
- **AND** `/data/state.json` exists and is valid
- **THEN** the system restores state and logs restored values
