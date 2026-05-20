## Why

The repository currently offers multiple stable Home Assistant add-ons for individual energy use cases, but there is no single universal HEMS add-on that can orchestrate assets together across one installation. A new HEMS foundation is needed now so the project can move from isolated optimizers toward one installable system that discovers Home Assistant entities, explains its decisions, and starts safely in dry-run mode before any real control is enabled.

## What Changes

- Add a new universal `hems` Home Assistant add-on as a modular orchestration platform rather than another single-purpose optimizer.
- Introduce a Python backend with a web interface, persistent configuration, Home Assistant discovery, and modular program lifecycle management.
- Add an asset registry that models batteries, solar, grid, water heaters, EV chargers, heat pumps, and other controllable loads through Home Assistant entity mappings and capability checks.
- Add a normalized entity mapping layer so different Home Assistant installations can configure the HEMS without custom code.
- Add a central decision engine that consumes proposals from enabled modules and produces one total house-level plan.
- Add dry-run, explainability, and decision timeline features as the default first release mode.
- Make the web interface the primary and complete configuration surface for HEMS behavior, asset setup, module strategy, planning inspection, diagnostics, and history rather than relying on Home Assistant add-on options.
- Define a product-style UI structure with onboarding, dashboard, assets, modules, planning, diagnostics, history, and settings screens.
- Add the first functional module as a battery optimization module that reuses the current battery-manager domain logic where practical, but runs inside the new HEMS module contract.
- Keep existing add-ons intact and production-safe while the new HEMS add-on is developed in parallel.

## Capabilities

### New Capabilities
- `hems-core`: Universal HEMS add-on foundation, global modes, primary web UI surface, persistence, and orchestration lifecycle.
- `hems-asset-registry`: Asset definitions, Home Assistant entity mapping, capability validation, and install-time configuration workflow.
- `hems-decision-engine`: Module proposal aggregation, conflict handling, prioritization, and total plan generation.
- `hems-dry-run`: Simulation, explainability, decision previews, and timeline visibility without device writes.
- `hems-battery-module`: Battery-specific normalized inputs, dry-run scheduling, and battery planning proposals under the HEMS module contract.

### Modified Capabilities

None.

## Impact

- Adds a new add-on codebase and deployment surface alongside the existing repository add-ons.
- Introduces a new internal architecture centered on assets, capabilities, modules, and one central decision engine.
- Reuses concepts and selected logic from `battery-manager`, `battery-api`, and `energy-prices`, but does not change their shipped behavior.
- Requires a new web UI, backend API surface, and persisted state/configuration model in `/data`.
- Replaces Home Assistant add-on options as the main configuration mechanism for HEMS functionality.
- Establishes the long-term platform for future modules such as water heater, EV, heat pump, and smart load orchestration.
