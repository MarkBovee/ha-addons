## 1. Contract And Discovery

- [x] 1.1 Freeze the current `battery_api` MQTT contract that must stay stable across providers.
- [x] 1.2 Define the `BatteryBackend` provider interface and split the current SAJ cloud implementation behind it.
- [x] 1.3 Add `battery-api` configuration for provider selection, Modbus entity mapping, and Modbus power-reference settings with `8000W` as the default inverter reference.
- [x] 1.4 Add Home Assistant SAJ entity discovery so live `saj_*` IDs can be prefilled from the configured HA API.
- [x] 1.5 Document which existing `battery-manager` assumptions stay unchanged in phase 1.

## 2. Battery API Refactor

- [x] 2.1 Extract the current cloud logic into an `ApiBatteryBackend` without behavior changes.
- [x] 2.2 Update `battery-api/app/main.py` to depend on the provider interface instead of `SajApiClient` directly.
- [x] 2.3 Add provider diagnostics and capability reporting to the normalized status output.
- [x] 2.4 Add tests for provider selection, invalid provider config, and stable MQTT contract behavior.

## 3. Modbus Parity Backend

- [x] 3.1 Implement a `ModbusHaBatteryBackend` that reads mapped SAJ Modbus entities through `HomeAssistantApi`.
- [x] 3.1a Use the live Home Assistant SAJ entities as default mappings where discovery is unambiguous.
- [x] 3.2 Implement normalized status mapping for SOC, battery power, PV power, grid power, load power, and core diagnostics.
- [x] 3.3 Implement schedule-to-slot translation for Modbus charge and discharge times, day masks, power percent values, and enable masks.
- [x] 3.4 Implement deterministic write sequencing with read-back verification and clear failure reporting.
- [x] 3.5 Implement mode mapping for self-consumption, time-of-use, and any validated optional modes.
- [x] 3.6 Implement safe watts-to-percent conversion with `8000W` default reference-power config, override support, clamping, and tests.

## 4. Modbus Advanced Controls

- [x] 4.1 Add exposed support for export limit writes and wire it for negative-price export suppression strategies.
- [ ] 4.2 Add capability-gated support for passive charge and passive discharge controls.
- [x] 4.3 Add optional diagnostics for power limits, discharge depths, and richer battery telemetry exposed by Modbus.
- [x] 4.4 Mark unsupported or experimental features such as PV-off and unreliable passive-grid behaviors explicitly in diagnostics and docs.

## 5. Validation And Rollout

- [x] 5.1 Validate the backend against the live SAJ Modbus device in Home Assistant and compare key readings with the current API path.
- [x] 5.2 Validate schedule apply, schedule clear, and mode changes end-to-end on Modbus with safe test windows.
- [x] 5.3 Update `battery-api/README.md` and config docs with migration steps, Modbus mapping requirements, and safe power guidance.
- [x] 5.4 Add a provider-switch rollout recipe so an install can move from API to Modbus and back without changing `battery-manager` or dashboard contracts.
