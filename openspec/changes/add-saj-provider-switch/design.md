## Context

`battery-manager` currently publishes schedules to the hardcoded MQTT topic `battery_api/text/schedule/set`. The current `battery-api` add-on accepts that JSON payload, validates it, writes the schedule through the SAJ cloud API, polls status from the cloud API, and republishes normalized `battery_api_*` MQTT entities for dashboards and downstream logic.

The SAJ H2 Modbus integration now exposes local telemetry and local write paths in Home Assistant. It already provides writable controls for:

- `AppMode`
- charge and discharge slot start and end times
- charge and discharge slot power percent and day masks
- charge and discharge enable bitmasks
- passive mode registers
- export limit
- battery and grid charge or discharge limits

It also exposes many more diagnostics than the cloud path, including battery pack data, per-phase power, temperatures, faults, and anti-reflux state. At the same time, some Modbus write behaviors are not fully validated:

- slot power is percentage-based, not watts-based
- passive mode uses different behavior than TOU mode
- `Passive Grid Charge Power` appears unreliable based on upstream discussion
- there is no confirmed, supported "PV off" control in the current integration

The lowest-risk path is therefore not to rewrite `battery-manager`, but to keep `battery-api` as the stable adapter and make its backend pluggable.

## Goals / Non-Goals

**Goals:**
- Keep the current `battery_api` MQTT contract stable for `battery-manager` and dashboards.
- Add a clean provider switch between `api` and `modbus_ha`.
- Reach feature parity for current status polling, schedule apply, schedule clear, and mode changes on Modbus.
- Add a safe foundation for validated Modbus-only features such as passive mode and export limit.
- Make unsupported or unvalidated features explicit instead of assuming they work.

**Non-Goals:**
- Remove the `battery-api` add-on from the architecture.
- Rewrite `battery-manager` to speak raw Modbus in phase 1.
- Claim support for "PV off" before a real control path is validated.
- Use all 414 SAJ entities immediately.
- Add a second direct Modbus connection from the add-on in phase 1.

## Decisions

### Decision: Keep `battery-api` as the stable adapter layer

`battery-api` already owns the external contract that the rest of the repo depends on: schedule topic, normalized status entities, mode select, and schedule text input. Keeping that contract stable avoids changes in `battery-manager`, existing dashboards, and automations.

Alternatives considered:
- Make `battery-manager` provider-aware and bypass `battery-api`: rejected for phase 1 because it duplicates control logic and breaks the current stable contract.
- Replace `battery-api` with a new add-on: rejected because the current add-on already provides the right external surface.

### Decision: Add a `BatteryBackend` abstraction inside `battery-api`

`battery-api` should call a provider-neutral backend interface instead of directly calling `SajApiClient` from the main loop. The backend contract should cover:

- `setup()`
- `poll_status()`
- `get_schedule()`
- `save_schedule()`
- `set_mode()`
- `get_capabilities()`

The current SAJ cloud client becomes `ApiBatteryBackend`. A new `ModbusHaBatteryBackend` bridges to Home Assistant entities and services.

Alternatives considered:
- Keep conditionals in `main.py`: rejected because it grows fragile fast and makes testing harder.

### Decision: Use Home Assistant entity reads and service calls for the Modbus backend

The add-on should not open its own Modbus socket in phase 1. Instead it should use the existing SAJ Modbus integration as the one source of truth and call Home Assistant services such as:

- `number.set_value`
- `text.set_value`
- `switch.turn_on`
- `switch.turn_off`

This avoids duplicating register maps, avoids connection contention, and keeps all raw Modbus behavior inside the HACS integration already running in Home Assistant.

Alternatives considered:
- Direct raw Modbus from `battery-api`: rejected because it duplicates the HACS integration and increases drift and maintenance cost.

### Decision: Preserve the current MQTT contract regardless of provider

The following stay stable across providers:

- `battery_api/text/schedule/set`
- normalized status entities like `sensor.battery_api_battery_soc`
- control entities like the battery mode select and schedule text entity

The Modbus backend translates between this stable contract and provider-specific Home Assistant entities. This lets `battery-manager` stay unchanged for phase 1.

Alternatives considered:
- Make `battery-manager` publish to provider-specific topics: rejected because the current contract is already good enough.

### Decision: Implement Modbus parity through TOU slot mapping first

The first Modbus write path should map the current schedule JSON to the Modbus charge and discharge slots and related enable masks. That matches the current `battery-api` behavior closest.

Write order must be deterministic:

1. validate schedule
2. convert watts to Modbus power percent
3. write slot start and end times
4. write slot day masks and power percent values
5. write enable bitmasks
6. set `AppMode` last
7. read back written values or cached state and fail loudly if the result is inconsistent

Clearing a schedule should disable all charge and discharge masks and restore the configured fallback mode, normally self-consumption.

Alternatives considered:
- Use passive mode for all scheduled charge and discharge windows: rejected for phase 1 because passive behavior differs from TOU and some passive registers are only partially validated.

### Decision: Require explicit Modbus mapping and power reference config

Modbus slot power is percentage-based. The add-on therefore needs a reliable conversion reference, not a guess. For the current install we already know the inverter is `8kW`, so phase 1 should use `8000W` as the default reference and still allow config override. Phase 1 should require explicit config for:

- normalized read entity IDs
- writable entity IDs or device-derived defaults
- reference power in watts used to convert schedule watts to Modbus percent values, defaulting to `8000W`

The conversion rule should be centralized, clamped, and logged. If the request cannot be converted safely, the add-on should reject the write instead of guessing.

Alternatives considered:
- Hardcode default `sensor.saj_*` and `number.saj_*` names only: rejected because entity IDs can vary with device naming and translations.
- Infer power reference only from inverter model string: rejected because it is convenient but not robust enough as the only source.

### Decision: Use Home Assistant entity discovery through the configured HA API

The repository already has working Home Assistant API credentials in `.env`, and the live install exposes the actual SAJ Modbus entities. Phase 1 should therefore query Home Assistant directly to discover and validate the live entity IDs instead of treating all mapping as purely manual.

Known live entities already confirmed from Home Assistant include:

- `sensor.saj_battery_energy_percent`
- `sensor.saj_battery_power`
- `sensor.saj_pv_power`
- `sensor.saj_total_load_power`
- `sensor.saj_total_grid_power`
- `number.saj_app_mode_input`
- `number.saj_export_limit_input`
- `number.saj_charge1_power_percent_input` through `number.saj_charge7_power_percent_input`
- `number.saj_discharge1_power_percent_input` through `number.saj_discharge7_power_percent_input`
- `number.saj_charge_time_enable_input`
- `number.saj_discharge_time_enable_input`
- `switch.saj_charging_control`
- `switch.saj_discharging_control`
- `switch.saj_passive_charge_control`
- `switch.saj_passive_discharge_control`
- `text.saj_charge1_start_time_time` through `text.saj_charge7_end_time_time`
- `text.saj_discharge1_start_time_time` through `text.saj_discharge7_end_time_time`

The backend should use discovery plus sensible defaults from these live IDs, while still allowing config override when names differ.

### Decision: Treat advanced Modbus features as capability-gated extensions

Modbus exposes more controls than the cloud API, but not all are equally reliable. Advanced features should therefore be capability-gated and clearly labeled.

Initial advanced feature targets:

- export limit / zero-export, and expose it as a supported advanced control because it is directly useful for negative-price strategies
- passive mode charge and discharge control
- battery and grid charge or discharge limit reads and writes
- richer diagnostics and pack-level telemetry

Explicitly not supported until validated:

- true PV shutdown / PV off
- any advanced anti-reflux write mode not exposed by the current integration
- `Passive Grid Charge Power` as a trusted scheduling control

### Decision: Roll out in parity-first, extension-second phases

Phase 1 should only deliver stable parity and migration safety.

Phase 2 can then evaluate whether `battery-manager` should optionally use Modbus-only strategies such as:

- passive mode for fixed-power charge windows
- export limiting during sell or solar-surplus windows
- more provider-advertised schedule slots when the planner benefits from the extra slots
- recurring day-mask schedules instead of today-only windows

## Risks / Trade-offs

- Watt-to-percent conversion can be wrong if the reference power is wrong -> Default to the known `8000W` inverter size, keep config override, clamp values, and add tests with real examples.
- HA entity names can vary per install -> Use direct HA discovery to prefill the live SAJ IDs and keep explicit override config.
- Multi-step Modbus writes can leave half-applied schedules -> Write in a strict order, verify read-back, and keep the previous schedule cached until apply succeeds.
- Passive mode semantics differ from TOU semantics -> Keep passive mode out of the parity path and add it only as a feature-gated extension.
- Some upstream Modbus controls are unvalidated or unreliable -> Mark them experimental and do not build core behavior on them.
- There is no confirmed PV-off control -> Treat PV-off as unsupported until a real register and read-back flow are validated.

## Migration Plan

1. Add provider abstraction to `battery-api` without changing the current API provider behavior.
2. Implement `ModbusHaBatteryBackend` behind a feature flag and provider config.
3. Configure the existing Home Assistant SAJ Modbus integration as the single local source.
4. Add Modbus entity mapping and reference-power configuration with `8000W` as the default.
5. Query the live Home Assistant instance through the configured HA API and prefill discovered SAJ entity IDs.
6. Run side-by-side validation in a real Home Assistant install by comparing cloud and Modbus telemetry and schedule outcomes.
7. Switch provider from `api` to `modbus_ha` on the same `battery-api` add-on instance.
8. After parity is stable, add optional advanced Modbus controls and strategies.

Rollback stays simple: switch the provider back to `api` and keep the same external MQTT contract.

## Open Questions

- Should HA discovery simply prefill the live IDs, or should phase 1 fully auto-bind to the discovered `saj_*` entities by default?
- Do we want one shared `8000W` reference for both charge and discharge conversion, or separate configurable charge and discharge references from day one?
- Do we want to keep the current today-only schedule semantics in phase 1, or already use Modbus day masks and extra slots for tomorrow or recurring windows?
- Should AI mode remain exposed on Modbus immediately, or only after real-device validation of `AppMode=12`?
- Do we want advanced Modbus-only controls to appear as extra `battery_api` entities, or only as internal capabilities first?
