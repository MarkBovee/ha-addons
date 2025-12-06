## ADDED Requirements

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
