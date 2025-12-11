# HEMS Add-on Specification (Delta)

## ADDED Requirements

### Requirement: Price-Driven Battery Scheduling
The system SHALL generate a rolling 15-minute battery schedule using the Range-Based strategy driven by the Home Assistant sensor `sensor.energy_prices_electricity_import_price` without external fallbacks.

#### Scenario: Schedule from current price
- **WHEN** the add-on starts or the current price changes
- **THEN** the add-on computes the current price range (load/adaptive/discharge) and builds a minimal schedule of charge + discharge periods covering the day
- **AND** it persists the schedule via the `battery-api` add-on

### Requirement: Adaptive Discharge Control
The system SHALL adjust discharge power every minute using the 1-minute average consumption sensor to match grid load while respecting inverter limits and SOC thresholds.

#### Scenario: Adaptive adjustment
- **WHEN** an active discharge period is running
- **AND** the 1-minute average power usage indicates import above the configured threshold
- **THEN** the add-on increases discharge power (capped by max inverter power and SOC rules)
- **AND** changes of less than 100W are ignored to avoid churn

### Requirement: Opportunistic Solar (Optional)
When enabled, the system SHALL allow opportunistic solar charging during discharge periods when excess solar export is detected.

#### Scenario: Excess solar detected
- **WHEN** sun is up and grid export is below -1000W during a discharge period scheduled at 0W
- **AND** state of charge is below 99%
- **THEN** the add-on regenerates the schedule to permit charging from solar without creating new charge windows

### Requirement: Status & Observability
The system SHALL expose status entities (input_text/input_number or MQTT discovery) for next charge/discharge windows, current price/range, and adaptive power.

#### Scenario: Status refresh
- **WHEN** a schedule is applied or a monitoring adjustment occurs
- **THEN** the add-on updates status entities within 15 minutes to reflect current state
