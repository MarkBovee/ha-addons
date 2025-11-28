# Battery API Add-on Specification

## Purpose

Provides entity-based control and status monitoring for SAJ Electric battery inverters via Home Assistant. Enables simple charge/discharge scheduling through HA entities without requiring NetDaemon or external automation platforms.

---

## ADDED Requirements

### Requirement: SAJ API Authentication

The add-on **SHALL** authenticate with the SAJ Electric Cloud API using the configured credentials.

#### Scenario: Successful authentication
- **WHEN** add-on starts with valid SAJ credentials
- **THEN** add-on authenticates and obtains API token
- **AND** token is stored for reuse across requests
- **AND** `sensor.ba_api_status` shows "Connected"

#### Scenario: Invalid credentials
- **WHEN** add-on starts with invalid SAJ credentials
- **THEN** authentication fails
- **AND** `sensor.ba_api_status` shows "Authentication Failed"
- **AND** error is logged with details

#### Scenario: Token refresh
- **WHEN** stored token is within 24 hours of expiry
- **THEN** add-on proactively refreshes token
- **AND** new token is stored

---

### Requirement: Battery Status Monitoring

The add-on **SHALL** poll the SAJ API for battery status and publish to Home Assistant sensors.

#### Scenario: Regular status polling
- **WHEN** poll interval elapses (default 60s)
- **THEN** add-on fetches current battery status from SAJ API
- **AND** `sensor.ba_battery_soc` is updated with current SOC percentage
- **AND** `sensor.ba_battery_mode` is updated with current user mode
- **AND** `sensor.ba_charge_direction` is updated (charging/discharging/idle)

#### Scenario: API unavailable during poll
- **WHEN** SAJ API is unreachable during status poll
- **THEN** sensors retain last known values
- **AND** `sensor.ba_api_status` shows "Disconnected"
- **AND** sensors include `unavailable_since` attribute

---

### Requirement: Entity-Based Schedule Control

The add-on **SHALL** provide MQTT entities for users to configure battery schedules.

#### Scenario: Control entities published on startup
- **WHEN** add-on starts and connects to MQTT broker
- **THEN** control entities are published via MQTT Discovery:
  - `number.ba_charge_power_w` (0-8000, default 6000)
  - `number.ba_charge_duration_min` (0-360, default 60)
  - `text.ba_charge_start_time` (HH:MM format)
  - `number.ba_discharge_power_w` (0-8000, default 6000)
  - `number.ba_discharge_duration_min` (0-360, default 60)
  - `text.ba_discharge_start_time` (HH:MM format)
  - `select.ba_schedule_type` (Charge Only/Discharge Only/Both/Clear)
  - `button.ba_apply_schedule`
- **AND** all entities have unique_id for HA UI management

#### Scenario: User sets control values
- **WHEN** user changes a control entity value in HA UI
- **THEN** add-on receives the new value via MQTT
- **AND** value is stored for next schedule application

---

### Requirement: Schedule Application

The add-on **SHALL** apply configured schedules to the SAJ inverter when triggered.

#### Scenario: Apply charge-only schedule
- **WHEN** user sets `select.ba_schedule_type` to "Charge Only"
- **AND** user presses `button.ba_apply_schedule`
- **THEN** add-on builds schedule with single charge period
- **AND** schedule is sent to SAJ API
- **AND** `sensor.ba_current_schedule` is updated with applied schedule
- **AND** `sensor.ba_last_applied` is updated with timestamp

#### Scenario: Apply discharge-only schedule
- **WHEN** user sets `select.ba_schedule_type` to "Discharge Only"
- **AND** user presses `button.ba_apply_schedule`
- **THEN** add-on builds schedule with single discharge period
- **AND** schedule is sent to SAJ API

#### Scenario: Apply charge+discharge schedule
- **WHEN** user sets `select.ba_schedule_type` to "Both"
- **AND** user presses `button.ba_apply_schedule`
- **THEN** add-on builds schedule with one charge and one discharge period
- **AND** schedule is sent to SAJ API using 1+1 pattern

#### Scenario: Clear schedule
- **WHEN** user sets `select.ba_schedule_type` to "Clear"
- **AND** user presses `button.ba_apply_schedule`
- **THEN** add-on sends empty/default schedule to SAJ API
- **AND** `sensor.ba_current_schedule` shows "No active schedule"

#### Scenario: Schedule application fails
- **WHEN** SAJ API rejects schedule application
- **THEN** `sensor.ba_api_status` shows error message
- **AND** error is logged with SAJ API response details
- **AND** `sensor.ba_current_schedule` is not updated

---

### Requirement: Dynamic Address Pattern Generation

The add-on **SHALL** dynamically generate SAJ API register addresses based on the number of charge and discharge periods.

#### Scenario: Generate pattern for 1+1 schedule
- **WHEN** user configures 1 charge period and 1 discharge period
- **THEN** add-on generates comm_address with header + 1 charge slot + 1 discharge slot
- **AND** registers used are `3647|3606|3607|3608_3608|361B|361C|361D_361D`

#### Scenario: Generate pattern for multi-period schedule
- **WHEN** user configures 2 charge periods and 3 discharge periods
- **THEN** add-on generates comm_address with header + 2 charge slots + 3 discharge slots
- **AND** each slot uses 3 consecutive Modbus registers

#### Scenario: Validate pattern limits
- **WHEN** user configures more than 3 charge or 6 discharge periods
- **THEN** add-on rejects the configuration
- **AND** error message indicates maximum limits (3 charge, 6 discharge)

#### Scenario: Reject empty schedule
- **WHEN** user configures 0 charge periods and 0 discharge periods
- **THEN** add-on rejects the configuration
- **AND** error message indicates at least 1 period required

---

### Requirement: Simulation Mode

The add-on **SHALL** support a simulation mode for testing without affecting the real inverter.

#### Scenario: Simulation mode enabled
- **WHEN** `simulation_mode` is set to `true` in configuration
- **THEN** add-on logs all API calls that would be made
- **AND** schedule applications are not sent to SAJ API
- **AND** status sensors show simulated/mock data
- **AND** `sensor.ba_api_status` shows "Simulation Mode"

---

## Acceptance Criteria

- [ ] Add-on authenticates with SAJ API and maintains token
- [ ] All control and status entities are created via MQTT Discovery
- [ ] User can configure and apply a simple charge schedule
- [ ] User can configure and apply a simple discharge schedule
- [ ] User can configure and apply a combined charge+discharge schedule
- [ ] Status sensors update every 60 seconds with live data
- [ ] Simulation mode works without affecting real inverter
- [ ] Error states are clearly communicated via entities and logs
