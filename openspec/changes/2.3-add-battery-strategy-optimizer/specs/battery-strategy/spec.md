# Battery Strategy Optimizer Specification (Delta)

**Version:** 2.3  
**Status:** Draft  
**Last Updated:** 2026-01-20

---

## ADDED Requirements

### Requirement: Price-Based Charging Optimization
The system **SHALL** analyze electricity price curves and identify the cheapest periods for battery charging.

#### Scenario: TopX cheapest periods identified
- **WHEN** energy-prices sensor provides 96-192 price intervals
- **THEN** system sorts prices ascending and selects bottom X intervals (where X = TopXChargeHours config)
- **AND** selected periods are used for battery charging schedule

#### Scenario: Price data unavailable
- **WHEN** energy-prices sensor is unavailable or price_curve attribute missing
- **THEN** system falls back to previous day's price curve
- **AND** warning logged: "Using yesterday's prices - energy-prices add-on unavailable"

---

### Requirement: Price-Based Discharging Optimization
The system **SHALL** analyze electricity price curves and identify the most expensive periods for battery discharging.

#### Scenario: TopX most expensive periods identified
- **WHEN** energy-prices sensor provides 96-192 price intervals
- **THEN** system sorts prices descending and selects top X intervals (where X = TopXDischargeHours config)
- **AND** selected periods are used for battery discharging schedule

#### Scenario: Insufficient expensive periods
- **WHEN** fewer expensive periods exist than TopXDischargeHours config
- **THEN** system uses all available expensive periods
- **AND** info logged: "Only N expensive periods available, using all"

---

### Requirement: Temperature-Based Discharge Duration
The system **SHALL** adjust discharge duration based on outdoor temperature to account for heating costs.

#### Scenario: Cold weather discharge (< 0°C)
- **WHEN** outdoor temperature is below 0°C
- **THEN** system sets discharge duration to 1 hour
- **AND** reasoning logged: "Temperature -5°C → 1 hour discharge (extreme cold)"

#### Scenario: Moderate weather discharge (8-16°C)
- **WHEN** outdoor temperature is between 8°C and 16°C
- **THEN** system sets discharge duration to 2 hours
- **AND** reasoning logged: "Temperature 12°C → 2 hours discharge (moderate heating)"

#### Scenario: Warm weather discharge (≥ 20°C)
- **WHEN** outdoor temperature is 20°C or higher
- **THEN** system sets discharge duration to 3 hours
- **AND** reasoning logged: "Temperature 22°C → 3 hours discharge (no heating)"

#### Scenario: Temperature sensor unavailable
- **WHEN** weather sensor unavailable or no temperature data
- **THEN** system defaults to 2 hours discharge
- **AND** warning logged: "Temperature sensor unavailable, using default 2-hour discharge"

---

### Requirement: Rank-Based Power Scaling
The system **SHALL** scale discharge power based on period rank to maximize value extraction from highest-value periods.

#### Scenario: Highest-rank period (rank 1)
- **WHEN** discharge period is rank 1 (most expensive)
- **THEN** system sets discharge power to max_discharge_power (8000W)
- **AND** schedule logged: "Rank 1 → 8000W discharge"

#### Scenario: Lower-rank periods with minimum enforcement
- **WHEN** discharge period is rank 2 or higher
- **THEN** system calculates power = max(max_discharge_power / rank, min_discharge_power)
- **AND** power is never below min_discharge_power (4000W)
- **AND** schedule logged: "Rank 2 → 4000W discharge (minimum enforced)"

---

### Requirement: State of Charge Protection
The system **SHALL** protect battery health by enforcing minimum and maximum SOC limits.

#### Scenario: Hard minimum SOC protection
- **WHEN** battery SOC drops to or below min_soc (5%)
- **THEN** system halts all discharging
- **AND** warning logged: "SOC at minimum (5%), discharge halted"

#### Scenario: Conservative SOC threshold
- **WHEN** battery SOC drops below conservative_soc (40%) during discharge
- **THEN** system reduces discharge power by 50%
- **AND** info logged: "SOC below 40%, reducing discharge to 50% power"

#### Scenario: End-of-day SOC target
- **WHEN** current time is after 20:00 and SOC below target_eod_soc (20%)
- **THEN** system avoids further discharging
- **AND** info logged: "EOD target (20%) not met, skipping discharge"

---

### Requirement: EV Charger Integration
The system **SHALL** monitor EV charger status and pause battery discharge when EV charging to avoid round-trip energy losses.

#### Scenario: EV charging during expensive period
- **WHEN** EV charger power > charging_threshold (500W)
- **AND** current period is in TopX discharge periods
- **THEN** system pauses battery discharge
- **AND** reasoning logged: "EV charging (1000W) → pausing battery discharge to avoid round-trip losses"

#### Scenario: EV idle during discharge period
- **WHEN** EV charger power ≤ charging_threshold (500W)
- **AND** current period is in TopX discharge periods
- **THEN** system allows battery discharge at scheduled power
- **AND** info logged: "EV idle → battery discharging at 8000W"

#### Scenario: EV charger sensor unavailable
- **WHEN** ev_charger.enabled is true but sensor unavailable
- **THEN** system skips EV integration checks
- **AND** warning logged: "EV charger sensor unavailable, skipping EV integration"

#### Scenario: EV integration disabled
- **WHEN** ev_charger.enabled is false
- **THEN** system skips all EV charger checks
- **AND** no EV-related logs produced

---

### Requirement: Excess Solar Opportunistic Charging
The system **SHALL** detect excess solar production and opportunistically charge the battery to prevent grid export.

#### Scenario: Excess solar detected
- **WHEN** solar_power - house_load_power > excess_solar_threshold (1000W)
- **AND** battery SOC below 100%
- **THEN** system triggers opportunistic battery charging
- **AND** info logged: "Excess solar (1500W) → opportunistic battery charge"

#### Scenario: Solar deficit
- **WHEN** solar_power - house_load_power ≤ excess_solar_threshold
- **THEN** system does not trigger opportunistic charging
- **AND** no opportunistic charge logs produced

#### Scenario: Solar sensors unavailable
- **WHEN** solar_power or house_load_power sensors unavailable
- **THEN** system skips opportunistic charging checks
- **AND** warning logged: "Solar sensors unavailable, skipping opportunistic charging"

---

### Requirement: Grid Export Prevention
The system **SHALL** monitor grid power and reduce battery discharge when grid export is detected to avoid exporting battery power at unfavorable rates.

#### Scenario: Grid export detected during discharge
- **WHEN** grid_power < -500W (negative = export)
- **AND** battery is discharging
- **THEN** system reduces discharge power by 50% or halts discharge
- **AND** warning logged: "Grid exporting (-800W) → reducing discharge to prevent battery export"

#### Scenario: Grid import during discharge
- **WHEN** grid_power ≥ 0W (importing from grid)
- **AND** battery is discharging
- **THEN** system allows discharge at scheduled power
- **AND** no grid export warnings logged

#### Scenario: Grid sensor unavailable
- **WHEN** grid_power sensor unavailable
- **THEN** system skips grid export checks
- **AND** warning logged: "Grid sensor unavailable, skipping export prevention"

---

### Requirement: Schedule Generation and Publishing
The system **SHALL** generate battery charge/discharge schedules and publish them to battery-api via MQTT.

#### Scenario: Hourly schedule generation
- **WHEN** update_interval (3600 seconds) elapses
- **THEN** system generates new charge/discharge schedule
- **AND** schedule published to MQTT topic battery_api/text/schedule/set
- **AND** info logged: "Schedule generated: 3 charge periods, 2 discharge periods"

#### Scenario: Schedule published successfully
- **WHEN** schedule published to MQTT
- **THEN** MQTT client confirms publish success
- **AND** info logged: "Schedule published to battery_api/text/schedule/set"

#### Scenario: MQTT unavailable
- **WHEN** MQTT client disconnected or publish fails
- **THEN** system logs schedule to console only (dry-run mode)
- **AND** warning logged: "MQTT unavailable, schedule logged only (not published)"
- **AND** retry connection every 60 seconds

---

### Requirement: Real-Time Monitoring
The system **SHALL** monitor battery state, grid power, solar, and EV charger every 1 minute and adjust discharge if needed.

#### Scenario: SOC drops below conservative threshold
- **WHEN** monitor_active_period runs every 60 seconds
- **AND** SOC drops below conservative_soc (40%)
- **THEN** system reduces discharge power by 50%
- **AND** info logged: "SOC at 35% → reducing discharge to 4000W"

#### Scenario: Excess solar detected during monitoring
- **WHEN** monitor_active_period detects solar surplus >1000W
- **THEN** system triggers opportunistic charging
- **AND** info logged: "Real-time: excess solar (1200W) → charging battery"

#### Scenario: EV charging detected during monitoring
- **WHEN** monitor_active_period detects EV power >500W
- **THEN** system pauses battery discharge
- **AND** reasoning logged: "Real-time: EV charging (2000W) → pausing discharge"

---

### Requirement: MQTT Discovery Entity Management
The system **SHALL** create Home Assistant entities via MQTT Discovery with proper unique_id for UI management.

#### Scenario: Discovery entities created on startup
- **WHEN** add-on starts and MQTT connected
- **THEN** system publishes discovery payloads for all entities:
  - sensor.battery_strategy_status (idle/charging/discharging)
  - sensor.battery_strategy_reasoning (text explanation of current action)
  - sensor.battery_strategy_forecast (predicted EOD SOC)
  - sensor.battery_strategy_price_ranges (TopX charge/discharge periods)
  - sensor.battery_strategy_current_action (current power/duration)
- **AND** all entities have unique_id (e.g., "battery_strategy_status")
- **AND** all entities grouped under device "Battery Strategy Optimizer"

#### Scenario: Entity state updated
- **WHEN** battery state changes (idle → charging → discharging)
- **THEN** system publishes state update to state topic
- **AND** attributes updated with reasoning, power, duration
- **AND** info logged: "Entity updated: battery_strategy_status = discharging"

---

### Requirement: Configuration Schema Validation
The system **SHALL** validate configuration on startup and reject invalid configurations with clear error messages.

#### Scenario: Valid configuration
- **WHEN** config.yaml loaded with all required fields and valid types/ranges
- **THEN** system starts successfully
- **AND** info logged: "Configuration validated successfully"

#### Scenario: Missing required field
- **WHEN** config.yaml missing required field (e.g., timing.update_interval)
- **THEN** system fails to start
- **AND** error logged: "Configuration error: missing required field 'timing.update_interval'"

#### Scenario: Invalid type
- **WHEN** config field has invalid type (e.g., max_charge_power = "abc")
- **THEN** system fails to start
- **AND** error logged: "Configuration error: 'max_charge_power' must be integer, got string"

#### Scenario: Out-of-range value
- **WHEN** config value outside valid range (e.g., min_soc = -5)
- **THEN** system fails to start
- **AND** error logged: "Configuration error: 'min_soc' must be between 0 and 100, got -5"

---

### Requirement: Graceful Shutdown
The system **SHALL** handle SIGTERM and SIGINT signals and shut down gracefully without data loss.

#### Scenario: SIGTERM received
- **WHEN** Home Assistant Supervisor sends SIGTERM signal
- **THEN** system logs "Shutdown signal received, stopping gracefully"
- **AND** current monitoring loop completes
- **AND** MQTT client disconnects cleanly
- **AND** exit code 0

#### Scenario: SIGINT received (Ctrl+C)
- **WHEN** user presses Ctrl+C during local testing
- **THEN** system logs "Interrupt signal received, stopping gracefully"
- **AND** current operation completes
- **AND** exit code 0

---

## Acceptance Criteria

- [ ] All ADDED requirements implemented and tested
- [ ] Unit tests pass with ≥85% code coverage
- [ ] Integration tests pass for all sensor modules
- [ ] End-to-end tests pass for full schedule generation + monitoring
- [ ] Dry-run validation successful for 24 hours
- [ ] Side-by-side comparison with NetDaemonApps completed (1 week)
- [ ] MQTT Discovery entities created with unique_id
- [ ] Configuration schema validation working
- [ ] Graceful shutdown on SIGTERM/SIGINT
- [ ] Documentation complete (README, CHANGELOG, config examples)
