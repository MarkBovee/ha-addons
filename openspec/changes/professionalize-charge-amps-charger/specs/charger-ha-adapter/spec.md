## ADDED Requirements

### Requirement: Home Assistant Charger Device
The integration SHALL publish normalized charger data through Home Assistant entities and SHALL keep MQTT, HTTP, REST, and provider details internal to the integration.

#### Scenario: Native device discovery succeeds
- **WHEN** the adapter has a charge point identity and MQTT Discovery is available
- **THEN** Home Assistant receives one charger device with stable unique IDs, identity metadata, and normalized entities
- **AND** future HEMS can consume the entities without knowing MQTT or Charge Amps details

#### Scenario: REST fallback is used
- **WHEN** MQTT Discovery is unavailable
- **THEN** legacy REST state publication remains available
- **AND** REST-created entities are not claimed to have unique IDs or UI-managed writable semantics

### Requirement: Native Read Entity Semantics
The integration SHALL publish read-only state and measurements with correct Home Assistant entity types, units, device classes, state classes, availability, and diagnostic categories where applicable.

#### Scenario: Measured energy is available
- **WHEN** cumulative connector energy is known
- **THEN** it is published as a read-only sensor in kWh with energy metadata and suitable total-increasing semantics
- **AND** it is not represented as a writable `input_number`

#### Scenario: Measurement is unknown
- **WHEN** a power, energy, current, or voltage measurement is absent or invalid
- **THEN** its entity is unavailable or reports the defined unknown state
- **AND** the integration does not publish a fabricated zero as current measured data

#### Scenario: Offline refresh fails
- **WHEN** Charge Amps status cannot be refreshed
- **THEN** online and charging state reflect the defined unavailable/offline contract
- **AND** stale live power is not presented as current data

### Requirement: Capability-Gated Writable Entities
The integration SHALL publish native writable Home Assistant entities only for provider operations that are verified, implemented, constraint-validated, and routed through `ChargerControlService`.

#### Scenario: Current control becomes verified
- **WHEN** current control and required minimum/maximum limits are verified
- **THEN** Home Assistant may receive a `number` entity with amp unit and verified range
- **AND** `number.set_value` invokes the internal control service rather than provider API code in an HA callback

#### Scenario: Start and stop become verified
- **WHEN** start and stop capabilities are independently verified
- **THEN** Home Assistant may receive native start and stop `button` entities
- **AND** both commands use the same internal control path

#### Scenario: Capability is unsupported or unknown
- **WHEN** current control, start, stop, or connector enable/disable is unsupported or unverified
- **THEN** its writable entity is not published as available
- **AND** no fake control, invented range, or silent fallback is presented

### Requirement: Writable Command Semantics
Writable Home Assistant entities SHALL represent persistent or immediate device intent, not HEMS-specific timed orchestration.

#### Scenario: Current number is set
- **WHEN** a caller sets the verified current number to 4 A
- **THEN** the integration requests a persistent 4 A target
- **AND** it does not create a ten-minute timer or automatic restore

#### Scenario: HEMS needs timed charging
- **WHEN** HEMS needs a timed operation
- **THEN** HEMS owns timing, priority, restoration, and coordination through Home Assistant
- **AND** the adapter executes only individual supported entity/service requests

### Requirement: Truthful Availability And Diagnostics
The integration SHALL represent capability availability, provider failures, unsupported commands, constraint failures, and last control outcomes truthfully.

#### Scenario: Unsupported command is requested
- **WHEN** a Home Assistant command targets an unavailable capability
- **THEN** the entity remains unavailable or the command result reports unsupported
- **AND** no provider mutation occurs

#### Scenario: Command fails
- **WHEN** a command is rejected, times out, or fails at the provider
- **THEN** the failure is published as diagnostic state with its classification
- **AND** the requested value is not published as applied state

#### Scenario: Command succeeds
- **WHEN** a command is accepted and verified
- **THEN** normalized state is refreshed
- **AND** the outcome identifies command type, requested value, source, and result

### Requirement: Backwards-Compatible Entity Publication
The first migration phase SHALL preserve existing user-facing REST entities, MQTT entities, MQTT topics, and entity names; new normalized entities SHALL be additive.

#### Scenario: Existing consumer remains configured
- **WHEN** an automation or add-on references an existing `ca_*` entity, existing `charge_amps_*` MQTT entity, or documented compatibility topic
- **THEN** the add-on continues publishing the existing contract during phase one
- **AND** the new model does not silently rename or delete it

#### Scenario: New normalized entity is introduced
- **WHEN** a new HEMS-facing entity is added
- **THEN** it is published additively with a documented mapping to observed legacy entities
- **AND** removal or renaming requires a later explicit migration proposal and release notice

#### Scenario: Active entity appears in cleanup inventory
- **WHEN** an entity is currently published by REST or MQTT
- **THEN** it is not added to `OLD_ENTITIES` during this migration
- **AND** cleanup requires confirmed consumer analysis and a separate migration decision

### Requirement: Legacy MQTT Is Compatibility Only
The integration MAY retain existing HEMS MQTT schedule ingress temporarily, but SHALL identify it as internal legacy compatibility rather than the HEMS architecture boundary.

#### Scenario: Legacy schedule topic is used
- **WHEN** an existing installation publishes to a legacy HEMS schedule topic
- **THEN** the add-on may validate and route it through the internal schedule boundary
- **AND** the topic is not documented as the target interface for future HEMS

#### Scenario: Future HEMS integrates
- **WHEN** future HEMS controls Charge Amps
- **THEN** it uses Home Assistant entities/services
- **AND** it has no dependency on legacy MQTT topics or payloads
