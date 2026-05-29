## ADDED Requirements

### Requirement: Modbus status normalization
When the Modbus backend is active, the `battery-api` add-on SHALL read SAJ Modbus data from Home Assistant and publish the same normalized battery status contract used by the API backend.

#### Scenario: Modbus telemetry is available
- **WHEN** mapped Modbus entities provide SOC, battery power, PV power, grid power, and load power
- **THEN** the add-on SHALL publish normalized `battery_api` status entities with the same sign conventions and meanings used today

### Requirement: Modbus schedule apply through TOU slots
When the Modbus backend is active, the `battery-api` add-on SHALL translate the current schedule JSON contract into Modbus time-of-use slot writes.

#### Scenario: Valid schedule is applied
- **WHEN** the add-on receives a valid schedule with charge and discharge periods
- **THEN** it SHALL convert each period into Modbus slot times, day masks, power-percent values, enable masks, and the required `AppMode` writes in a deterministic order

#### Scenario: Contract allows more slots than current provider
- **WHEN** the external schedule contract contains more periods than the active provider supports
- **THEN** the backend SHALL reject the apply with a clear provider-limit error instead of relying on a provider-specific contract payload shape

#### Scenario: Slot write verification fails
- **WHEN** one or more Modbus writes do not read back as expected
- **THEN** the add-on SHALL report schedule apply failure and SHALL NOT report the schedule as successfully applied

### Requirement: Modbus schedule clear
When the Modbus backend is active, clearing the schedule SHALL disable the relevant Modbus schedule state and restore the configured fallback mode.

#### Scenario: Empty schedule clears active slots
- **WHEN** the add-on receives an empty schedule payload
- **THEN** it SHALL clear charge and discharge enable masks and restore self-consumption or the configured fallback mode

### Requirement: Safe watts-to-percent conversion
The Modbus backend SHALL convert requested power in watts into Modbus slot values using explicit reference power configuration and safe clamping.

#### Scenario: Default inverter reference is used
- **WHEN** the Modbus backend is enabled for the current SAJ inverter and no override is configured
- **THEN** it SHALL use `8000W` as the default conversion reference

#### Scenario: Requested power exceeds Modbus bounds
- **WHEN** a schedule period requests power above the configured or supported Modbus range
- **THEN** the add-on SHALL clamp or reject the value according to configured safety rules and SHALL log what happened

#### Scenario: Conversion reference is unavailable
- **WHEN** the add-on cannot determine a safe reference power for the conversion
- **THEN** it SHALL reject the schedule apply instead of guessing a slot value

### Requirement: Mode mapping parity
The Modbus backend SHALL map the existing battery mode contract to validated Modbus app-mode behavior.

#### Scenario: Self-consumption is requested
- **WHEN** the user selects Self-consumption
- **THEN** the add-on SHALL map that request to the validated Modbus self-consumption mode

#### Scenario: Unsupported mode is requested
- **WHEN** the user selects a mode that the current Modbus device mapping does not support safely
- **THEN** the add-on SHALL reject the request and publish a clear provider diagnostic
