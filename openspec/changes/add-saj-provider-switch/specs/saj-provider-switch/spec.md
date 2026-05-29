## ADDED Requirements

### Requirement: Battery API provider selection
The `battery-api` add-on SHALL support a provider setting that selects either the existing SAJ cloud API backend or a Home Assistant SAJ Modbus backend.

#### Scenario: API provider stays unchanged
- **WHEN** the add-on is configured with provider `api`
- **THEN** it SHALL use the current SAJ cloud API flow for authentication, status polling, mode changes, and schedule writes

#### Scenario: Modbus provider discovers live SAJ entities through Home Assistant
- **WHEN** the add-on is configured with provider `modbus_ha`
- **THEN** it SHALL query Home Assistant for the live SAJ Modbus entities and use discovered defaults where the mapping is unambiguous

#### Scenario: Modbus provider is selected without required mapping
- **WHEN** the add-on is configured with provider `modbus_ha` and required entity mapping cannot be discovered or configured safely
- **THEN** startup SHALL fail fast or publish a clear provider diagnostic instead of silently guessing values

### Requirement: Stable MQTT contract across providers
The `battery-api` add-on SHALL preserve its existing MQTT discovery entities and schedule command topic regardless of which provider is selected.

#### Scenario: Battery Manager publishes a schedule
- **WHEN** `battery-manager` publishes a valid schedule to `battery_api/text/schedule/set`
- **THEN** the add-on SHALL accept the same payload format for both providers without requiring a `battery-manager` topic change

#### Scenario: Dashboard reads battery API status
- **WHEN** Home Assistant reads normalized `battery_api_*` entities
- **THEN** those entities SHALL exist and use the same semantic meanings for both providers

#### Scenario: Downstream scheduler needs provider slot limits
- **WHEN** a downstream scheduler reads `sensor.battery_api_api_status`
- **THEN** the entity attributes SHALL expose provider capability fields including `max_charge_periods` and `max_discharge_periods`

### Requirement: Provider diagnostics and capabilities
The `battery-api` add-on SHALL publish which provider is active and which optional capabilities are available.

#### Scenario: Modbus provider exposes optional controls
- **WHEN** the Modbus backend starts successfully
- **THEN** the add-on SHALL surface capability flags for optional controls such as export limit or passive mode without claiming unsupported features
