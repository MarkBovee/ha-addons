## 1. Contract Freeze And Characterization Tests

- [ ] 1.1 Record current REST entity IDs, MQTT Discovery-derived IDs, unique IDs, device metadata, HEMS compatibility topics, and downstream references from source, documentation, and live/test HA evidence.
- [x] 1.2 Add characterization tests for current authentication, discovery, schedule retrieval/upsert/delete payloads, safe offline publication, and current legacy entity names.
- [x] 1.3 Resolve documented-versus-runtime entity mismatches before enabling new entities, aliases, or cleanup behavior.
- [ ] 1.4 Investigate `battery-manager` reference `sensor.charge_amps_monitor_charger_current_power` against live/test HA registry and consumers; document whether alias is required without changing it in this phase.
- [x] 1.5 Add fixture strategy for representative Charge Amps responses without credentials or secret live payloads.

## 2. Charge Amps Adapter Reliability And Error Improvements

- [x] 2.1 Extract typed errors for authentication, timeout, transient/permanent provider failure, malformed response, unsupported operation, and constraint failure.
- [x] 2.2 Keep all Charge Amps requests on the existing session and centralize sensible timeout and bounded safe-read retry/backoff policy.
- [x] 2.3 Preserve JWT refresh behavior and test valid expiry, expiry buffer, missing/unparseable expiry, failed re-authentication, and deterministic token lifecycle logging without per-request re-authentication.
- [x] 2.4 Keep verified read and schedule operations unchanged while recording endpoint and payload evidence for each mutation.
- [x] 2.5 Add schedule read-back or equivalent verification where supported; never blindly retry non-idempotent writes.

## 3. Provider-Neutral Internal Charger Domain

- [x] 3.1 Add provider-neutral models for identity, normalized state, measurements, limits, capabilities, command results, and schedule intent.
- [x] 3.2 Map existing `ChargePoint` and `Connector` DTOs to normalized state while preserving raw diagnostic context.
- [x] 3.3 Define `ChargerPort` as an internal integration abstraction and detect capabilities only from verified provider operations.
- [x] 3.4 Keep start, stop, current control, connector enable/disable, unknown limits, and unknown phase count unsupported or unknown until evidence exists.
- [x] 3.5 Validate current requests deterministically for online state, fault state, enabled state, known minimum/maximum, connector limits, and phase constraints.
- [x] 3.6 Reject unsupported, unsafe, and unknown-limit requests without provider mutation; never silently clamp.
- [x] 3.7 Keep `set_current`, `start`, and `stop` immediate and timer-free; test that timed restore belongs to higher-level orchestration.

## 4. Internal ChargerControlService

- [x] 4.1 Add `ChargerControlService` as the internal single command path for the HA adapter and legacy compatibility bridge.
- [x] 4.2 Serialize concurrent charger commands and schedule mutations where required; include source, requested value, applied value, and outcome in diagnostics.
- [x] 4.3 Ensure failed commands cannot publish requested state as applied state and successful commands trigger normalized state refresh.
- [x] 4.4 Keep HEMS decision logic, arbitration, priorities, timed orchestration, and multi-device planning outside the service.
- [x] 4.5 Ensure future HEMS reaches this path only through Home Assistant entities/services, never by importing or calling this service directly.

## 5. Home Assistant Adapter With Native Entities And Legacy Compatibility

- [x] 5.1 Refactor normalized entity publication out of `main.py` into an HA adapter consuming normalized snapshots; retain legacy publication there for compatibility.
- [x] 5.2 Publish one MQTT Discovery charger device with stable identity, metadata, unique IDs, availability, units, device classes, state classes, and diagnostic categories.
- [x] 5.3 Publish read-only normalized state, online, charging, power, energy, current, voltage, capability, and error entities only when data semantics support them.
- [x] 5.4 Extend shared MQTT Discovery only as needed for native writable number, switch, and button semantics without regressing other add-ons.
- [x] 5.5 Publish `number.*current` only after verified current control and verified limits exist; route `number.set_value` through `ChargerControlService`.
- [x] 5.6 Publish start/stop buttons and enabled switch only after each provider operation is independently verified; do not infer writability from read state.
- [x] 5.7 Preserve REST fallback, existing REST IDs, existing MQTT IDs/topics, and existing names; do not expand `OLD_ENTITIES` with active entities.
- [x] 5.8 Publish truthful command outcomes, capability reasons, and unavailable/offline state without stale live measurements.

## 6. Connect Standalone Scheduling To Charger Boundary

- [x] 6.1 Refactor standalone price scheduling to depend on the schedule-capable internal boundary rather than `ChargerApi` directly.
- [x] 6.2 Preserve week anchoring, price thresholds, selected price levels, period merging, schedule payloads, status entities, and source metadata.
- [x] 6.3 Add schedule read-back/regression coverage for create, update, delete, failure, and safe recovery behavior.
- [x] 6.4 Verify standalone mode remains fully functional without HEMS or future HEMS services.

## 7. Make Legacy HEMS Ingress Truthful Without HEMS Optimization

- [x] 7.1 Preserve existing HEMS schedule topics temporarily as compatibility ingress only.
- [x] 7.2 Route validated set/clear messages through the internal schedule boundary and report actual provider outcomes.
- [x] 7.3 Ensure failed apply/clear operations do not update active schedule state or report success.
- [x] 7.4 Preserve expiration and safe rollback behavior while keeping HEMS optimization, arbitration, and priorities out of the add-on.
- [x] 7.5 Document MQTT as internal legacy compatibility plumbing, never as the target HEMS interface.

## 8. Live/Test Home Assistant Validation And Staged Rollout

- [x] 8.1 Add API tests for authentication, token lifecycle, parsing, errors, timeout behavior, reads, and verified mutations.
- [x] 8.2 Add domain and control tests for capabilities, unknown constraints, invalid commands, unsupported commands, and no-mutation guarantees.
- [x] 8.3 Add HA tests for discovery payloads, metadata, writable gating, command routing, state updates, availability, and legacy IDs.
- [ ] 8.4 Measure request count, polling latency, memory behavior, startup recovery, command serialization, and graceful shutdown on constrained hardware or equivalent.
- [ ] 8.5 Validate MQTT and REST compatibility paths against a test/live Home Assistant instance before changing defaults.
- [ ] 8.6 Roll out read-only/native diagnostics first; enable each writable capability only after provider evidence and tests pass.
- [x] 8.7 Document confirmed entity mappings, aliases, deprecation policy, rollback steps, API unknowns, and the phase that verifies each remaining question.
