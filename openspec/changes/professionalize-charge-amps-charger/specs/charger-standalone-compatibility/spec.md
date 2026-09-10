## ADDED Requirements

### Requirement: Standalone Price Scheduling Remains Available
The integration SHALL preserve standalone price-based scheduling, including price sensor reads, threshold filtering, selected price levels, Charge Amps schedule period conversion, schedule writes, and schedule status publication.

#### Scenario: Standalone schedule is generated
- **WHEN** standalone mode and automation are enabled and usable price data is available
- **THEN** the add-on analyzes configured price slots and pushes a valid schedule through the internal schedule-capable boundary
- **AND** existing schedule status and source semantics remain available

#### Scenario: Price data is unavailable
- **WHEN** the configured price sensor is missing or has no usable price curve
- **THEN** no invalid provider schedule is written
- **AND** schedule status reports a visible waiting or error state

### Requirement: Standalone Operation Does Not Require HEMS
The add-on SHALL remain fully functional in standalone mode without a future HEMS service, HEMS optimization, or HEMS MQTT connection.

#### Scenario: Standalone mode runs independently
- **WHEN** operation mode is `standalone`
- **THEN** price-based scheduling and monitoring can operate without HEMS
- **AND** the charger domain remains usable for verified read operations and any future verified controls

### Requirement: Operation Modes Are Compatibility Modes
The add-on SHALL continue to accept `standalone` and `hems` operation modes while treating them as orchestration/configuration modes rather than charger-domain capabilities.

#### Scenario: HEMS mode receives a legacy schedule
- **WHEN** operation mode is `hems` and a valid existing schedule message is received through the legacy compatibility ingress
- **THEN** the message is validated and routed through the internal schedule boundary
- **AND** the add-on does not expose Charge Amps API details as the required HEMS contract

### Requirement: Truthful Legacy Schedule Results
The legacy HEMS compatibility bridge SHALL report actual schedule apply and clear outcomes and SHALL NOT claim success for a callback that did not perform the requested mutation.

#### Scenario: Schedule application fails
- **WHEN** an external schedule is syntactically valid but the provider rejects it, times out, or cannot apply it
- **THEN** the bridge publishes an error result with the failure classification
- **AND** it does not store the schedule as active

#### Scenario: Schedule clear succeeds
- **WHEN** an external clear command is received and verified schedule deletion succeeds
- **THEN** the bridge clears active schedule state
- **AND** it publishes an idle/cleared result

#### Scenario: Schedule clear fails
- **WHEN** schedule deletion fails or cannot be verified
- **THEN** the bridge retains or marks active state according to the documented recovery policy
- **AND** it publishes an error rather than a false cleared result

### Requirement: Schedule Mutation Reliability
Schedule mutations SHALL use explicit timeouts, distinguish provider failures from unsupported operations, serialize conflicting mutations, and use read-back or equivalent verification where provider semantics allow it.

#### Scenario: Schedule mutation times out
- **WHEN** an upsert or delete request exceeds its configured timeout
- **THEN** the operation reports a timeout failure
- **AND** the bridge or standalone coordinator does not claim that the schedule was applied or cleared

#### Scenario: Concurrent schedule mutations occur
- **WHEN** standalone orchestration and a legacy compatibility command overlap
- **THEN** schedule mutations follow a defined serialization policy
- **AND** the resulting status reflects the actual winning provider outcome

### Requirement: Legacy Contract Inventory And Migration
The first migration phase SHALL maintain a tested inventory of current REST entity IDs, MQTT Discovery-derived entity IDs, HEMS compatibility topics, documented names, and known downstream references before changing or removing any contract.

#### Scenario: Entity contract is proposed to change
- **WHEN** implementation proposes a rename, removal, or state-semantic change
- **THEN** referenced automations and add-ons are identified
- **AND** an additive alias, compatibility publication, or explicit migration step is provided where a real consumer requires it

#### Scenario: Battery manager reference is inspected
- **WHEN** the reference `sensor.charge_amps_monitor_charger_current_power` is evaluated
- **THEN** it is treated as unverified because current Charge Amps REST and MQTT code does not publish it
- **AND** live/test HA evidence determines whether it is stale, a documentation error, or requires a compatibility alias
- **AND** no entity is added or renamed solely by this specification review

#### Scenario: Active cleanup list is reviewed
- **WHEN** the migration reviews `OLD_ENTITIES`
- **THEN** currently active REST or MQTT entities are not added to that list
- **AND** destructive cleanup requires a later explicit migration decision

### Requirement: Regression Coverage Preserves Existing Behavior
Changes to the domain or HA adapter SHALL include regression coverage for standalone scheduling, legacy entity names, safe offline publication, schedule mutations, and legacy HEMS topic behavior.

#### Scenario: Regression suite runs
- **WHEN** a charger-domain, control-service, scheduling, or HA-adapter change is tested
- **THEN** existing standalone schedule behavior and compatibility contracts are included
- **AND** unsupported writable capabilities do not appear as available controls
