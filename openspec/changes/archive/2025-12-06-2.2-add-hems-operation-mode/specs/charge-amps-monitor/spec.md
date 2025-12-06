# Charge Amps Monitor Specification

## Purpose

Monitor and control Charge Amps EV chargers through the Charge Amps cloud API, with support for price-aware charging schedules in standalone mode or external orchestration via HEMS mode.

## ADDED Requirements

### Requirement: Operation Mode Selection

The system **SHALL** support two operation modes configurable via `operation_mode`:
- `standalone` (default): Internal price-based scheduling with threshold filtering
- `hems`: External schedule control via MQTT

#### Scenario: Standalone mode startup
- **WHEN** add-on starts with `operation_mode: standalone`
- **THEN** system initializes price analyzer and begins autonomous scheduling
- **AND** HEMS MQTT subscriptions are not created

#### Scenario: HEMS mode startup
- **WHEN** add-on starts with `operation_mode: hems`
- **THEN** system subscribes to HEMS schedule topics
- **AND** internal price analyzer is disabled
- **AND** system waits for external schedule commands

#### Scenario: Mode switch at runtime
- **WHEN** user changes `operation_mode` in config and restarts
- **THEN** system clears current schedule from charger
- **AND** reinitializes with new mode behavior

### Requirement: Price Threshold Filtering (Standalone Mode)

The system **SHALL** filter charging slots by `price_threshold` before selection when in standalone mode.

#### Scenario: Slots below threshold
- **WHEN** price data contains slots at €0.10, €0.15, €0.20, €0.30
- **AND** `price_threshold` is 0.25
- **THEN** only slots at €0.10, €0.15, €0.20 are eligible for selection
- **AND** slots at €0.30 are excluded

#### Scenario: No slots below threshold
- **WHEN** all available price slots exceed `price_threshold`
- **THEN** system sets status to "no_eligible_slots"
- **AND** no charging schedule is created
- **AND** `binary_sensor.ca_price_threshold_active` shows `on`

#### Scenario: Threshold ignored in HEMS mode
- **WHEN** `operation_mode` is `hems`
- **THEN** `price_threshold` config is ignored
- **AND** schedules are applied exactly as received from HEMS

### Requirement: Unique Price Level Selection (Standalone Mode)

The system **SHALL** select slots based on top X unique price levels, not individual slot count.

#### Scenario: Multiple slots at same price
- **WHEN** 4 slots exist at €0.08 and 3 slots exist at €0.10
- **AND** `top_x_charge_count` is 2
- **THEN** system selects all 7 slots (2 unique price levels)
- **AND** status shows "7 slots at 2 price levels"

#### Scenario: Fewer unique prices than requested
- **WHEN** only 5 unique price levels exist below threshold
- **AND** `top_x_charge_count` is 16
- **THEN** system selects all slots at all 5 price levels
- **AND** status shows actual count selected

### Requirement: HEMS Schedule Reception

The system **SHALL** receive and apply charging schedules via MQTT when in HEMS mode.

#### Scenario: Valid schedule received
- **WHEN** MQTT message received on `hems/charge-amps/{connector_id}/schedule/set`
- **AND** payload contains valid periods array
- **THEN** system converts periods to Charge Amps schedule format
- **AND** pushes schedule to charger via API
- **AND** sets `schedule_source` to "hems"

#### Scenario: Clear schedule command
- **WHEN** MQTT message received on `hems/charge-amps/{connector_id}/schedule/clear`
- **THEN** system deletes current schedule from charger
- **AND** sets status to "idle"

#### Scenario: Invalid schedule payload
- **WHEN** MQTT message contains malformed JSON or missing required fields
- **THEN** system logs error with details
- **AND** maintains previous schedule state
- **AND** does not crash or restart

#### Scenario: Schedule with expiration
- **WHEN** schedule payload includes `expires_at` timestamp
- **AND** current time exceeds `expires_at`
- **THEN** system automatically clears the expired schedule
- **AND** publishes status update

### Requirement: HEMS Status Publishing

The system **SHALL** publish charger status to MQTT for HEMS consumption.

#### Scenario: Status on state change
- **WHEN** charger state changes (plugged in, charging started, charging stopped)
- **THEN** system publishes to `hems/charge-amps/{connector_id}/status`
- **AND** payload includes current state, schedule info, power metrics

#### Scenario: Status includes readiness
- **WHEN** status is published
- **THEN** payload includes `ready_for_schedule` boolean
- **AND** `ready_for_schedule` is true when charger is online and can accept commands

### Requirement: Schedule Source Sensor

The system **SHALL** expose the current schedule source as a Home Assistant sensor.

#### Scenario: Standalone schedule active
- **WHEN** operating in standalone mode with active schedule
- **THEN** `sensor.ca_schedule_source` shows "standalone"

#### Scenario: HEMS schedule active
- **WHEN** operating in HEMS mode with schedule from external system
- **THEN** `sensor.ca_schedule_source` shows "hems"

#### Scenario: No schedule
- **WHEN** no schedule is currently active
- **THEN** `sensor.ca_schedule_source` shows "none"

## Acceptance Criteria

- [ ] `operation_mode` config with standalone/hems options, default standalone
- [ ] `price_threshold` config with default 0.25 EUR/kWh
- [ ] Slot selection uses unique price levels, not raw slot count
- [ ] Price threshold filters slots in standalone mode only
- [ ] HEMS mode subscribes to schedule topics and applies received schedules
- [ ] HEMS mode publishes status to designated topic
- [ ] New sensors: schedule_source, hems_last_command, price_threshold_active
- [ ] Mode switch clears schedule and reinitializes cleanly
- [ ] All existing functionality preserved when using default config
