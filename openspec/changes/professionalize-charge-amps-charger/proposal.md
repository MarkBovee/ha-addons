## Status

Implementation in progress under the phased plan. Live Home Assistant validation and staged rollout remain outstanding.

## Why

`charge-amps-monitor` currently combines Charge Amps Cloud access, response models, Home Assistant publication, price scheduling, and a legacy HEMS MQTT bridge in one runtime. It can monitor a charger, but its current contracts do not yet give future HEMS a verified, vendor-neutral capability interface.

This change defines an implementation-ready boundary while preserving standalone operation and existing integrations during migration.

## Architectural Invariant

Home Assistant entities and Home Assistant services are the only integration boundary between HEMS and Charge Amps.

```text
HEMS
  │
  │ Home Assistant entities/services ONLY
  ▼
Home Assistant
  │
  ▼
Charge Amps HA adapter
  │
  ▼
ChargerControlService
  │
  ▼
ChargerPort
  │
  ▼
Charge Amps infrastructure/API adapter
  │
  ▼
Charge Amps Cloud API
```

HEMS MUST NOT connect to MQTT, know MQTT topics or payloads, call Charge Amps APIs, call add-on-internal APIs, import Charge Amps Python modules, access add-on state or databases, know OCPP/vendor protocols, or depend on implementation-specific scheduling. MQTT, HTTP, REST, OCPP, vendor APIs, and databases remain below the Home Assistant boundary and are integration implementation details.

The existing HEMS MQTT schedule ingress may remain temporarily for backwards compatibility. It is a legacy add-on compatibility mechanism, not the target HEMS interface and not permission for HEMS to use MQTT.

## What Changes

- Freeze and characterize current REST entities, MQTT Discovery entities/topics, schedule behavior, HEMS compatibility topics, and downstream references before migration.
- Define provider-neutral charger state, measurements, limits, capabilities, schedule intent, and command-result semantics.
- Define `ChargerPort` and `ChargerControlService` explicitly as internal Charge Amps integration abstractions, never HEMS interfaces.
- Gate every writable Home Assistant entity on a verified and implemented provider operation.
- Preserve unknown capabilities, limits, and provider errors truthfully; do not invent values, silently clamp requests, or report unsuccessful mutations as successful.
- Improve API timeout, authentication, token refresh, error classification, retry, serialization, and schedule read-back requirements before implementation.
- Add native Home Assistant entities additively, while retaining existing REST and MQTT contracts in the first migration phase.
- Keep standalone price-based scheduling independent of HEMS and preserve existing schedule behavior unless a later approved proposal changes it.
- Keep the legacy HEMS MQTT ingress only as a truthful compatibility path; do not implement HEMS optimization, arbitration, priorities, or power allocation here.

## Capability Classification

### Verified and implementable

- Charge Amps authentication through `POST /api/auth/login`.
- Charge point discovery through `POST /api/users/chargepoints/owned?expand=ocppConfig,topChargingLimitation`.
- Charge point and connector status/measurement data already present in discovery responses, including online status, charging state, cumulative energy, phase current/voltage, connector mode, OCPP status, error code, and reported enabled state.
- Schedule retrieval through `GET /api/smartChargingSchedules/chargepoint/{charge_point_id}`.
- Schedule creation/update through `PUT /api/smartChargingSchedules`.
- Schedule deletion through `DELETE /api/smartChargingSchedules/{charge_point_id}/{connector_id}`.

### Not verified and therefore not implementable yet

- Direct start.
- Direct stop.
- Persistent direct charging-current control.
- Connector enable/disable mutation.
- A provider capability endpoint or verified provider limits suitable for writable current validation.

### Possible future capabilities requiring provider/API investigation

Start, stop, current control, connector enable/disable, minimum/maximum current, phase count, and any other writable operation may be added only after endpoint/payload evidence, provider behavior, error handling, and read-back tests are captured. No endpoint or limit is invented by this proposal.

## Entity Contract And Compatibility Finding

The first migration phase preserves existing runtime contracts. Current REST publication uses `ca_*` IDs such as `sensor.ca_charger_status`, `sensor.ca_charger_power_kw`, `sensor.ca_charger_current`, and `binary_sensor.ca_charger_online`. Current MQTT Discovery derives IDs from the `charge_amps` device prefix, such as `sensor.charge_amps_current_power`, `sensor.charge_amps_power_kw`, and `binary_sensor.charge_amps_charging`. README names do not fully match either runtime path.

The intended new HEMS-facing names are capability-oriented `charge_amps_monitor_*` entities, but they are additive and are not replacements for observed contracts. Compatibility aliases are allowed only after a real consumer is confirmed. `OLD_ENTITIES` MUST NOT be expanded with currently active entities.

`battery-manager` currently references `sensor.charge_amps_monitor_charger_current_power`. The Charge Amps source does not publish that ID through either its current REST path or its current MQTT Discovery path. It is therefore not a verified existing entity; it is a stale or missing compatibility reference requiring live HA/entity-registry confirmation. This change documents the finding only and does not add or rename an entity.

## Acceptance Criteria

### Architecture

- HEMS communicates with Charge Amps exclusively through Home Assistant entities and services.
- HEMS has no dependency on MQTT, Charge Amps APIs, Charge Amps Python internals, add-on databases, or vendor protocols.
- `ChargerPort` and `ChargerControlService` are documented and implemented only as internal integration abstractions.
- The legacy HEMS MQTT ingress is explicitly compatibility-only and is not the target HEMS contract.

### Capability correctness

- Only verified provider capabilities can become writable Home Assistant controls.
- Unsupported commands perform no provider mutation and return a structured unsupported result.
- Unsupported or unknown capabilities and limits are represented truthfully.
- Provider limits are not invented and requested values are not silently clamped.
- A command is not reported as successful unless the provider mutation happened and the defined verification succeeded.

### Home Assistant

- Writable controls use appropriate native Home Assistant entity types.
- State, availability, capability, and control semantics are explicitly defined.
- Entity availability reflects actual capability availability.
- Existing REST entities, MQTT entities/topics, names, and standalone behavior remain compatible during the first migration phase.

### Standalone operation

- Charge Amps Monitor remains functional without HEMS.
- Existing price-based scheduling remains independent of HEMS and retains schedule behavior.

### Reliability

- Provider failures, unsupported operations, invalid requests, timeouts, and authentication failures are distinguishable.
- Authentication and JWT refresh behavior is deterministic and does not re-authenticate on every request solely because token expiry is not parseable.
- Command serialization prevents conflicting simultaneous mutations.
- Schedule operations have regression and read-back coverage where provider semantics allow it.

## Implementation Scope And Phases

1. Contract freeze and characterization tests.
2. Charge Amps adapter reliability/error improvements.
3. Provider-neutral internal charger domain.
4. Internal `ChargerControlService`.
5. Home Assistant adapter with native entities and legacy compatibility.
6. Connect standalone scheduling to the charger boundary.
7. Make legacy HEMS ingress truthful without implementing HEMS optimization.
8. Live/test Home Assistant validation and staged rollout.

Implementation code, a future HEMS implementation, new MQTT protocols, and destructive entity migration are explicitly outside this proposal.

## Impact

- Affected specs: `charger-domain-control`, `charger-ha-adapter`, `charger-standalone-compatibility`.
- Expected implementation areas: Charge Amps API adapter, provider-neutral domain, internal control service, HA adapter, standalone scheduler, and legacy HEMS bridge.
- Implementation is intentionally limited to verified read/schedule capabilities; direct start, stop, current control, and connector enable/disable remain gated as unverified.
