# Home Assistant Add-on Suite

This repo is no longer a speculative add-on roadmap. It is a working add-on suite with a few older design docs still kept for context.

## Current Production Shape

| Area | Add-on | Responsibility |
| --- | --- | --- |
| Price data | `Energy Prices` | Import/export price curves and derived classifications |
| Battery adapter | `Battery API` | Inverter communication, normalized HA entities, schedule apply |
| Battery strategy | `Battery Manager` | Schedule generation, heuristics, live adaptive control |
| EV | `Charge Amps - EV Charger Monitor` | Charger monitoring and optional integration with battery logic |
| Heating | `Water Heater Scheduler` | Price-aware domestic hot water scheduling |

## Design Rules

### Stable Contracts

- External contracts should stay stable even when backend implementation changes.
- Battery stack example: `Battery Manager` talks to `Battery API`, not directly to provider-specific SAJ controls.
- Provider capabilities belong in diagnostics and capability attributes, not in hardcoded downstream assumptions.

### Shared Code

- Root `shared/` is source of truth.
- Add-on-local `shared/` copies exist for Docker builds.
- Sync shared code after edits.

### Home Assistant Entity Stability

- Entity IDs should remain stable across releases.
- Units, state class, and meaning should not drift silently.
- Diagnostic detail should go in attributes when possible.

### Operational Bias

- Prefer small add-ons with narrow responsibility.
- Prefer explicit clear/apply flows over hidden state mutation.
- Prefer diagnostics that explain current mode, limits, and failures directly in Home Assistant.

## Battery Architecture

Current battery flow:

1. `Energy Prices` publishes import/export curves.
2. `Battery Manager` reads prices plus live HA telemetry and decides schedule.
3. `Battery Manager` publishes schedule to `battery_api/text/schedule/set`.
4. `Battery API` validates and applies schedule through active provider.
5. Dashboards and automations consume normalized `battery_api_*` and `battery_manager_*` entities.

This separation is intentional. It keeps inverter transport concerns out of strategy logic and makes API/Modbus switching low-risk.

## Older Docs

Older names like `Battery Optimizer` describe pre-split concepts. They are retained only as historical context and should not be treated as current implementation docs.
