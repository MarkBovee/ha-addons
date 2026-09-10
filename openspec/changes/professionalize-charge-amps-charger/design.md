## Context

`charge-amps-monitor` is a Home Assistant Supervisor add-on. Its current runtime combines Charge Amps Cloud communication, entity publication, price scheduling, and a legacy HEMS MQTT schedule bridge. The architecture review freezes the boundary before implementation:

```text
HEMS
  │ Home Assistant entities/services only
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
Charge Amps API/infrastructure adapter
```

Everything below Home Assistant is invisible to HEMS. In particular, HEMS does not know whether the integration uses MQTT, HTTP, REST, OCPP, a vendor SDK, or an internal database.

## Current Verified API Surface

| Operation | Method and path | Classification | Status |
| --- | --- | --- | --- |
| Authenticate | `POST /api/auth/login` | Session/auth mutation | Verified |
| Discover owned charge points | `POST /api/users/chargepoints/owned?expand=ocppConfig,topChargingLimitation` | Read | Verified |
| Read schedules | `GET /api/smartChargingSchedules/chargepoint/{charge_point_id}` | Read | Verified |
| Create/update schedule | `PUT /api/smartChargingSchedules` | Mutation | Verified |
| Delete schedule | `DELETE /api/smartChargingSchedules/{charge_point_id}/{connector_id}` | Mutation | Verified |
| Start | No verified endpoint/payload | Mutation | Unsupported until verified |
| Stop | No verified endpoint/payload | Mutation | Unsupported until verified |
| Persistent current control | No verified endpoint/payload | Mutation | Unsupported until verified |
| Connector enable/disable | No verified endpoint/payload | Mutation | Unsupported until verified |
| Provider capability/limit retrieval | Requested `topChargingLimitation` is not consumed as a verified domain contract | Read | Unknown |

Discovery currently provides charge point identity/status, connector charging state, cumulative energy, phase current/voltage, mode, OCPP status, error code, reported enabled state, and calculated power. Reported enabled state is read data; it does not prove an enable/disable command exists.

## Internal Integration Abstractions

`ChargerPort` is an internal implementation abstraction of the Charge Amps integration. It is not an interface between HEMS and Charge Amps. `ChargerControlService` is also internal to the integration. HEMS never imports, calls, or configures either abstraction directly.

The conceptual internal path is:

```text
Charge Amps HA adapter
  -> ChargerControlService
    -> ChargerPort
      -> Charge Amps infrastructure/API adapter
```

The HA adapter translates Home Assistant entity/service commands into the internal service. A future HEMS uses the same Home Assistant entities/services; it does not invoke the internal service in-process, through a local API, or through MQTT. The exact internal call graph remains an implementation detail.

## Provider-Neutral Domain

The domain uses small provider-neutral concepts rather than extending Charge Amps DTOs into public contracts:

```text
Charger
  identity: ChargerIdentity
  state: ChargerState
  measurements: ChargerMeasurements
  limits: ChargerLimits
  capabilities: ChargerCapabilities
  connectors: list[Connector]

ChargerPort (internal)
  get_state() -> Charger
  get_capabilities() -> ChargerCapabilities
  set_current(amps: float) -> CommandResult
  start() -> CommandResult
  stop() -> CommandResult
```

Normalized states may include `offline`, `available`, `preparing`, `charging`, `suspended`, `faulted`, and `unknown`, while retaining raw provider state for diagnostics. Measurements contain power, energy, voltage, and current only where measured. Limits contain minimum, maximum, connector, and phase constraints only where known and verified. Capability fields distinguish supported, unsupported, and unknown where necessary.

`set_current(4)` means a persistent request for 4 A, subject to verified capability and limits. It never means 4 A for ten minutes. Timed operation, previous-value capture, deadlines, restore policy, priority, arbitration, and coordination with battery, solar, or house load belong to orchestration above the integration.

The first implementation rejects invalid current requests deterministically. It MUST NOT silently clamp, reinterpret, or invent a provider-safe range. If a required limit is unknown, current control remains unavailable or rejects the request according to the documented safety policy.

## Capability Matrix

| Capability/data | Classification | HA consequence |
| --- | --- | --- |
| State, online, charging, measured power, energy, current, voltage | Verified when present in discovery data | Publish read-only entities when the current snapshot contains the data; otherwise unavailable |
| Schedule retrieval/create/update/delete | Verified | Keep standalone scheduler and legacy schedule ingress schedule-capable |
| Start/stop | Not verified | Do not publish start/stop buttons |
| Persistent current control | Not verified | Do not publish `number.*current` |
| Connector enable/disable mutation | Not verified | Do not publish `switch.*enabled` |
| Provider minimum/maximum current and phase limits | Unknown unless independently verified | Do not invent number range or enable current control |
| Capability diagnostic summary | Verified as an integration diagnostic concept | Publish truthfully, including unknown/unsupported reasons |

Future writable entities become eligible only after provider evidence, adapter implementation, constraint validation, command-result handling, and regression/read-back tests exist. A read-only `binary_sensor` for reported connector enabled state does not authorize a writable switch.

## Home Assistant Entity Strategy

The intended new entity names are capability-oriented and additive:

| Entity | Type | Semantics | Initial gating |
| --- | --- | --- | --- |
| `sensor.charge_amps_monitor_state` | sensor | Normalized charger state | Publish when adapter has a snapshot |
| `binary_sensor.charge_amps_monitor_online` | binary sensor | Actual connectivity/online state | Publish when state is known |
| `binary_sensor.charge_amps_monitor_charging` | binary sensor | Actual charging state | Publish when connector state is known |
| `sensor.charge_amps_monitor_power` | sensor | Measured W | Only when measured |
| `sensor.charge_amps_monitor_energy` | sensor | Cumulative kWh | Only when measured |
| `sensor.charge_amps_monitor_current` | sensor | Measured A | Only when measured |
| `sensor.charge_amps_monitor_voltage` | sensor | Measured V | Only when measured |
| `number.charge_amps_monitor_current` | number | Persistent current target | Not publishable until current operation and limits are verified |
| `switch.charge_amps_monitor_enabled` | switch | Persistent enable/disable control | Not publishable until operation is verified |
| `button.charge_amps_monitor_start` | button | Immediate start command | Not publishable until operation is verified |
| `button.charge_amps_monitor_stop` | button | Immediate stop command | Not publishable until operation is verified |
| `sensor.charge_amps_monitor_capabilities` | sensor | Capability summary and reasons | Publish truthfully as diagnostic data |
| `sensor.charge_amps_monitor_error` | sensor | Last provider/control error | Publish provider and unsupported outcomes distinctly |

Native writable entities use Home Assistant-native semantics and route to `ChargerControlService`. A failed command cannot publish the requested value as applied. REST state publication remains a compatibility fallback and must not pretend to provide UI-managed writable semantics.

## Existing Contract Inventory And Migration

Observed REST runtime IDs include:

- `input_boolean.ca_charger_charging`
- `input_number.ca_charger_total_consumption_kwh`
- `input_number.ca_charger_current_power_w`
- `sensor.ca_charger_status`
- `sensor.ca_charger_power_kw`
- `sensor.ca_charger_voltage`
- `sensor.ca_charger_current`
- `binary_sensor.ca_charger_online`
- `binary_sensor.ca_charger_connector_enabled`
- `input_text.ca_charger_name`
- `input_text.ca_charger_serial`
- `sensor.ca_charger_connector_mode`
- `sensor.ca_charger_ocpp_status`
- `sensor.ca_charger_error_code`
- `sensor.ca_charging_schedule_status`
- `sensor.ca_next_charge_start`
- `sensor.ca_next_charge_end`
- `sensor.ca_charging_schedule_error`

The current MQTT Discovery implementation derives IDs from `charge_amps`, including `binary_sensor.charge_amps_charging`, `sensor.charge_amps_total_consumption`, `sensor.charge_amps_current_power`, `sensor.charge_amps_power_kw`, `sensor.charge_amps_status`, `binary_sensor.charge_amps_online`, `binary_sensor.charge_amps_connector_enabled`, and corresponding voltage/current/diagnostic entities. Automation entities use the same MQTT prefix. README and changelog names such as `sensor.ca_schedule_status` and `sensor.charge_amps_power_kw` must be treated as documented claims until live/test HA evidence confirms their actual registry entries.

First-phase rules:

- Existing REST entities remain available.
- Existing MQTT entities and existing HEMS MQTT topics remain available.
- Existing names are not removed or renamed.
- New native entities are additive.
- Aliases are added only for confirmed consumers and have documented ownership/deprecation.
- `OLD_ENTITIES` is not expanded with currently active entities.
- Existing standalone and schedule behavior remains functional.

`battery-manager/config.yaml` references `sensor.charge_amps_monitor_charger_current_power`. Current Charge Amps source code publishes neither this REST ID nor this MQTT ID. The reference is therefore not a verified current entity and is classified as a stale or missing compatibility reference. Live HA entity-registry and automation/consumer inspection is required before deciding whether an alias is needed. No code fix is part of this change.

## Legacy MQTT HEMS Ingress

The current topics `hems/charge-amps/{connector_id}/schedule/set`, `/schedule/clear`, and `/status` may remain temporarily so existing installations are not silently broken. They are internal compatibility plumbing of the add-on. They MUST NOT be described as the HEMS integration boundary or as a future HEMS protocol.

The compatibility bridge validates and converts schedules, routes them through the internal schedule boundary, and reports actual apply/clear outcomes. It must not implement HEMS optimization, arbitration, power allocation, vendor-specific control, or a second long-term integration bus.

## Reliability Decisions

- Use explicit, sensible timeouts for every provider request, including authentication and schedule mutations.
- Use one session for provider calls and centralize request policy.
- Refresh a cached JWT within a defined expiry buffer. A token without a parseable expiry must not trigger authentication on every request; retain it until expiry/provider rejection and re-authenticate deterministically after an authentication failure.
- Distinguish authentication failure, timeout, transient provider failure, permanent provider failure, malformed response, unsupported operation, and constraint rejection.
- Use bounded retry/backoff only where operation safety and idempotency are defined, primarily for transient reads and authentication recovery. Do not blindly retry schedule mutations or commands.
- Serialize charger commands and schedule mutations where concurrent sources could conflict.
- Never report provider mutation success when no mutation occurred or verification failed.
- Add schedule read-back/regression coverage where provider semantics permit it.
- Publish unavailable/safe diagnostics without presenting stale live measurements as current.

## Migration And Rollback

Implementation proceeds through the eight phases in `proposal.md` and `tasks.md`. New writable controls start disabled because start, stop, current control, and connector enable/disable are not verified. Each capability is enabled independently only after evidence and tests pass.

Rollback is release/configuration based: disable new entities or return the adapter to read-only/legacy publication. Existing REST/MQTT entities, standalone scheduling, and legacy compatibility topics remain available during phase one.

## Non-Goals

- HEMS optimization, arbitration, priority resolution, power allocation, or multi-device planning.
- Direct HEMS access to any Charge Amps API, Python class, MQTT topic, or internal service.
- Undocumented provider endpoints or raw OCPP calls.
- Timers or automatic restoration inside `ChargerPort`.
- Immediate entity cleanup, renaming, or custom HA integration replacement.
