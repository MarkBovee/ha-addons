# charge-amps-monitor Specification

## Purpose
TBD - created by archiving change 2.1-add-price-aware-charging-schedules. Update Purpose after archive.
## Requirements
### Requirement: Price-Aware Charging Window Planning
The system SHALL read the configured Home Assistant price sensor (default `sensor.ep_price_import`) and, once tomorrow's price curve is available, select the cheapest contiguous block of 15-minute intervals that covers the user-defined `required_minutes_per_day` within `earliest_start_hour`/`latest_end_hour` boundaries in Home Assistant's timezone.

#### Scenario: Tomorrow price curve published
- **WHEN** the price sensor exposes a `price_curve` attribute with at least 96 future intervals for tomorrow
- **AND** automation is enabled in the add-on configuration
- **THEN** the planner computes every eligible contiguous block that meets the required duration
- **AND** chooses the block with the lowest total cost (ties resolved by earliest start)
- **AND** stores the resulting local start/end timestamps for schedule application.

#### Scenario: Price data incomplete
- **WHEN** automation is enabled but the price sensor only includes today's intervals (tomorrow missing or API returned 204)
- **THEN** the planner logs a warning, sets the status sensor to `waiting_for_prices`, and skips schedule generation until complete data is available.

### Requirement: Charge Amps Schedule Management
The system MUST create, update, and delete Charge Amps smart charging schedules via the documented `/api/smartChargingSchedules` endpoints using the selected window, connector id, and max current settings while leaving user-owned schedules untouched.

#### Scenario: Apply automation schedule
- **WHEN** a new plan differs from the stored automation metadata (different start/end or connector settings)
- **THEN** the add-on issues a PUT to `/api/smartChargingSchedules` with the computed `from`/`to` second offsets, timezone, connector id, and configured `maxCurrent`
- **AND** persists the returned `scheduleId` so subsequent comparisons can detect drift.

#### Scenario: Detect drift and reconcile hourly
- **WHEN** the hourly reconciliation detects that the automation schedule is missing, has different periods, or is marked `isSynced=false`
- **THEN** the add-on reapplies the stored plan within five minutes and updates the status sensor with `reapplied`
- **AND** emits structured logs describing the mismatch (missing schedule, changed periods, manual disable).

#### Scenario: Automation disabled by user
- **WHEN** the user toggles the automation flag to `false`
- **THEN** the add-on deletes the automation schedule via `DELETE /api/smartChargingSchedules/{chargePointId}/{connectorId}`
- **AND** stops hourly reconciliation until the toggle is re-enabled.

### Requirement: Automation Controls & Telemetry
The system SHALL expose Home Assistant helper entities for automation status, next start, next end, and last error plus a manual `charge_amps.force_schedule_refresh` service so users can trigger a recompute on demand.

#### Scenario: Publish helper sensors
- **WHEN** automation is enabled (regardless of whether a schedule is currently applied)
- **THEN** the add-on updates `sensor.ca_charging_schedule_status`, `sensor.ca_next_charge_start`, and `sensor.ca_next_charge_end` with the latest plan (ISO timestamps) every time the plan changes or reconciliation runs
- **AND** marks errors (API failure, missing data) in the status sensor attributes for visibility.

#### Scenario: Manual refresh service invoked
- **WHEN** a user calls `charge_amps.force_schedule_refresh` via Home Assistant
- **THEN** the add-on re-runs the planner immediately using the current price curve, pushes the resulting schedule if automation is enabled, and returns a success/failure payload (also logged) to the caller.

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

