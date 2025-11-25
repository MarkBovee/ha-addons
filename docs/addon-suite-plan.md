# Home Assistant Add-on Suite – Documentation Plan

## Introduction

We are extracting the most valuable behaviors from the legacy `NetDaemonApps` project and recreating them as self-contained Home Assistant add-ons. Each add-on will ship with:

- Fresh Python implementation under its own `app/` directory (no reuse of legacy .NET code).
- `config.yaml` documenting slug, version, architectures, exposed options, and schema validation.
- README content that mirrors the functionality summaries provided here.
- Consistent entity naming with a standard prefix for new sensors and status updates via input_text entities where users rely on dashboards.

This document captures the functional blueprint we follow when authoring the code, ensuring every add-on exposes clear settings, entity contracts, and diagnostics.

## Add-on Suite

The following add-ons are planned for this repository:

1. **[Battery Optimizer](battery-optimizer-addon.md)** – AI-based battery scheduling with SAJ inverter integration
2. **[Appliance Guard](appliance-guard-addon.md)** – Automatically disable high-load appliances during high price periods or away mode
3. **[Water Heater Scheduler](water-heater-scheduler-addon.md)** – Optimize domestic hot water heating based on electricity prices
4. **[Vacation Alarm](vacation-alarm-addon.md)** – Automate night-only alarm arming when away
5. **[Vacation Lighting](vacation-lighting-addon.md)** – Simulate presence with randomized light scheduling
6. **[Energy Usage Reporter](energy-usage-reporter-addon.md)** – Record and report 15-minute interval energy data
7. **[Price Helper Service](price-helper-service-addon.md)** – Centralized electricity price fetching and normalization

## Documentation Template

Each add-on follows a uniform structure:

1. **Purpose** – What problem it solves and why it exists.
2. **Key Behaviors** – Event loops, scheduling cadence, and state transitions.
3. **User Settings** – Options available in `config.yaml` with defaults and types.
4. **Home Assistant Entities** – Entities read and written, plus any helper sensors we create.
5. **Diagnostics & Logging** – Status and troubleshooting hooks.
6. **Future Extensions** – Pre-vetted ideas for follow-up releases.

## Shared Conventions

### Naming

- **Prefix**: Use a consistent entity prefix for all sensors/binary sensors and services created by add-ons in this suite.
- **Status Entities**: Where we output text (e.g., battery, water heater, appliances, vacation lighting, vacation alarm), ensure `max: 255` and keep messages concise (<200 chars) to avoid truncation.

### Configuration

- **Options Schema**: Every add-on should expose both `options` defaults and `schema` definitions in `config.yaml` (camelCase option keys, validation via types).

### Runtime Behavior

- **Graceful Shutdowns**: Each add-on must honor a `shutdown_flag` and stop scheduling loops promptly so Home Assistant Supervisor can stop/restart containers cleanly.
- **Telemetry**: When emitting sensors, keep units, device classes, and unique IDs stable so dashboards persist across upgrades.

### Dependencies

Several add-ons depend on the **Price Helper Service**:
- Battery Optimizer (AI scheduling)
- Appliance Guard (curtailment decisions)
- Water Heater Scheduler (optimal heating windows)
- Energy Usage Reporter (cost calculations)

## Development Process

When implementing new add-ons:

1. Review the specific add-on documentation for detailed requirements
2. Follow the established add-on structure (app/ directory, config.yaml, README)
3. Ensure all required configuration options are documented
4. Implement comprehensive logging for troubleshooting
5. Add service endpoints where appropriate for manual control
6. Test graceful shutdown behavior
7. Validate entity naming consistency with the suite prefix

## Related Documentation

- [Repository Configuration](../repository.json) – Add-on registry

