## ADDED Requirements

### Requirement: Home Assistant Boundary Is The Only HEMS Boundary
The integration SHALL expose its HEMS-facing contract only through Home Assistant entities and services, and SHALL keep provider, protocol, transport, and internal Python details below that boundary.

#### Scenario: HEMS reads charger state
- **WHEN** HEMS needs charger state or measurements
- **THEN** it reads the configured Home Assistant entities
- **AND** it does not call Charge Amps APIs, MQTT topics, add-on APIs, Python modules, databases, OCPP, or vendor protocols

#### Scenario: HEMS requests a charger operation
- **WHEN** HEMS needs a supported charger operation
- **THEN** it uses the corresponding Home Assistant entity or service
- **AND** the Charge Amps integration translates the request internally without exposing `ChargerPort` or `ChargerControlService`

### Requirement: Provider-Neutral Charger Contract
The integration SHALL represent charger identity, normalized state, measurements, limits, capabilities, schedules, and command results without Charge Amps API or Home Assistant implementation details in the internal domain contract.

#### Scenario: Consumer reads normalized state
- **WHEN** an internal integration consumer requests charger state
- **THEN** it receives normalized state, measurements, limits, capabilities, and raw diagnostic context where available
- **AND** it does not parse Charge Amps response fields

#### Scenario: Provider data is absent
- **WHEN** the provider does not supply or verify a domain value
- **THEN** the domain represents that value as unknown or unavailable
- **AND** it does not invent a value implying a safety guarantee

### Requirement: ChargerPort Is Internal
`ChargerPort` SHALL be an internal implementation abstraction of the Charge Amps integration and SHALL NOT be an interface between HEMS and Charge Amps.

#### Scenario: HA adapter uses charger port
- **WHEN** the Home Assistant adapter handles a supported control
- **THEN** it may use `ChargerControlService`, which may use `ChargerPort`
- **AND** neither abstraction is exposed as a HEMS integration contract

### Requirement: Discoverable Capabilities
The integration SHALL advertise a capability only when the corresponding provider operation is verified, implemented, and able to return a truthful result.

#### Scenario: Verified schedule capability
- **WHEN** schedule retrieval, creation/update, and deletion are verified
- **THEN** schedule capability is advertised to standalone and compatibility orchestration
- **AND** the capability includes no unverified start, stop, current, or enable operation

#### Scenario: Unverified control capability
- **WHEN** start, stop, persistent current control, connector enable/disable, or a required limit is not verified
- **THEN** the capability is unknown or unsupported
- **AND** no writable control may be enabled for it

### Requirement: Unsupported Commands Cause No Mutation
The integration SHALL reject unsupported, unknown-capability, and unsafe commands before any provider mutation.

#### Scenario: Unsupported start
- **WHEN** a caller requests `start()` without verified start capability
- **THEN** the result is a structured unsupported result
- **AND** no undocumented endpoint or provider mutation is attempted

#### Scenario: Unknown current limits
- **WHEN** a caller requests current control but required provider limits are unknown
- **THEN** the request is rejected as unsupported or unsafe according to the documented policy
- **AND** the charger is not silently clamped or mutated

### Requirement: Validated Persistent Current Control
The integration SHALL treat `set_current(amps)` as a persistent current target and SHALL implement it only after current control and all required constraints are verified.

#### Scenario: Current is within verified limits
- **WHEN** `set_current(amps)` receives a value within verified minimum and maximum limits
- **THEN** the integration sends the verified provider operation
- **AND** the result identifies whether the value was accepted and verified

#### Scenario: Current is outside verified limits
- **WHEN** the requested value is below minimum or above maximum
- **THEN** the command returns a deterministic constraint failure
- **AND** no provider mutation is attempted

#### Scenario: Invalid value is received
- **WHEN** the requested current is malformed, non-positive, or otherwise outside the defined domain
- **THEN** the command returns a validation failure
- **AND** it does not silently clamp or reinterpret the value

### Requirement: Explicit Start And Stop Semantics
The integration SHALL expose `start()` and `stop()` only when each corresponding provider operation is independently verified and capability-advertised.

#### Scenario: Verified start
- **WHEN** a caller invokes `start()` on an online charger with verified start capability
- **THEN** the adapter performs the verified start operation
- **AND** it returns a structured result whose success reflects provider execution and verification

#### Scenario: Stop is unverified
- **WHEN** stop capability is unknown or unsupported
- **THEN** `stop()` returns an unsupported result
- **AND** no provider mutation is attempted

### Requirement: Low-Level Commands Do Not Own Timers
The charger contract SHALL treat current and start/stop commands as immediate device intent and SHALL NOT create arbitrary timers or restore previous state automatically.

#### Scenario: Persistent current request
- **WHEN** a caller invokes `set_current(4)`
- **THEN** the charger is requested to use 4 A subject to validation
- **AND** no ten-minute expiry or automatic restoration is created

#### Scenario: Timed orchestration is above the integration
- **WHEN** an orchestrator needs 4 A for ten minutes
- **THEN** that orchestrator owns the deadline, previous value, and restoration policy
- **AND** it uses Home Assistant entities/services for HEMS or the internal boundary for standalone integration orchestration

### Requirement: Adapter Error And Timeout Classification
The provider adapter SHALL use explicit request timeouts and classify authentication failures, provider failures, timeouts, malformed responses, unsupported operations, and constraint violations without hiding the cause.

#### Scenario: Provider timeout
- **WHEN** a provider request exceeds its configured timeout
- **THEN** the operation returns a timeout-classified failure
- **AND** the integration does not report success or applied state

#### Scenario: Authentication failure
- **WHEN** authentication fails or the provider rejects a cached token
- **THEN** the result is authentication-classified
- **AND** the integration follows deterministic re-authentication behavior

#### Scenario: Token has no parseable expiry
- **WHEN** a cached JWT has no parseable expiry
- **THEN** the adapter does not re-authenticate on every request solely for that reason
- **AND** it re-authenticates deterministically after provider rejection or an explicit token-invalid result

### Requirement: Serialized Mutations
The integration SHALL serialize concurrent charger commands and schedule mutations where concurrent execution could cause conflicting provider state.

#### Scenario: Concurrent commands arrive
- **WHEN** two control sources issue overlapping mutations
- **THEN** the control path applies a defined serialization policy
- **AND** each result reports its actual outcome rather than optimistic requested state

### Requirement: Truthful Command Results
The integration SHALL report command success only when the provider mutation happened and the defined verification succeeded.

#### Scenario: Provider rejects mutation
- **WHEN** a provider rejects, times out, or fails a mutation
- **THEN** the command returns a failure classified with the cause
- **AND** no requested value is reported as applied

#### Scenario: Mutation succeeds
- **WHEN** a provider accepts a mutation and verification succeeds
- **THEN** the command returns success
- **AND** the next normalized state refresh can expose the observed result
