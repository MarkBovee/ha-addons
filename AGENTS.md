<!-- OPENSPEC:START -->

# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:

* Mentions planning or proposals (words like proposal, spec, change, plan)
* Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
* Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:

* How to create and apply change proposals
* Spec format and conventions
* Project structure and guidelines

Keep this managed block so `openspec update` can refresh the instructions.

<!-- OPENSPEC:END -->

# AI Agent Guidelines

High-level conventions for AI agents working in this repository. For detailed rules, see `.github/instructions/`.

---

## Repository at a Glance

A collection of **Home Assistant Supervisor add-ons** for home energy management, written in Python 3.12+ and deployed as Docker containers.

### Add-ons

| Directory                 | Slug                   | Prefix | Purpose                                                      |
| ------------------------- | ---------------------- | ------ | ------------------------------------------------------------ |
| `battery-api/`            | battery-api            | `ba_`  | SAJ inverter battery charge/discharge schedule control       |
| `battery-manager/`        | battery-manager        | `bm_`  | Battery optimization using prices, solar, grid, and EV data  |
| `charge-amps-monitor/`    | charge-amps-monitor    | `ca_`  | Charge Amps EV charger monitoring and control                |
| `energy-prices/`          | energy-prices          | `ep_`  | Nord Pool electricity prices with import/export calculations |
| `water-heater-scheduler/` | water-heater-scheduler | `wh_`  | Price-based water heater scheduling                          |

### Key Directories

| Directory           | Purpose                                                                |
| ------------------- | ---------------------------------------------------------------------- |
| `shared/`           | Common Python modules (source of truth - never edit `<addon>/shared/`) |
| `openspec/specs/`   | Canonical specifications per capability                                |
| `openspec/changes/` | Active change proposals                                                |
| `docs/`             | Long-form design documents and plans                                   |

---

# HEMS Architecture

This repository is evolving toward a modular **Home Energy Management System (HEMS)**.

The following architectural rule is fundamental and MUST be preserved by all agents and implementations.

## Home Assistant is the Only Integration Boundary

**Home Assistant entities and Home Assistant services are the only integration boundary between HEMS and modules/devices.**

HEMS MUST be completely independent of the implementation details of individual integrations and add-ons.

The intended architecture is:

```text
                         HEMS
                          │
                          │
                 HA entities / services
                          │
                          ▼
                   Home Assistant
                          │
             ┌────────────┼────────────┐
             │            │            │
             ▼            ▼            ▼
        EV Charger     Battery       Solar
        Integration   Integration   Integration
             │            │            │
             ▼            ▼            ▼
          Vendor/API    Inverter      Inverter
          OCPP/MQTT    Protocol      Protocol
          Whatever     Whatever      Whatever
```

HEMS MUST:

* Read Home Assistant entity states and attributes.
* Call Home Assistant services to control devices.
* Use Home Assistant state changes/events where appropriate.
* Treat configured Home Assistant entity IDs and services as its module interface.
* Remain independent of the underlying vendor, device, protocol, or implementation.
* Work with compatible third-party Home Assistant integrations where possible.

HEMS MUST NOT:

* Connect to MQTT directly.
* Publish or subscribe to MQTT topics.
* Depend on MQTT topics or MQTT message formats.
* Call vendor APIs directly.
* Call another add-on's internal APIs directly.
* Import or depend on another add-on's Python modules.
* Access another add-on's database or internal state.
* Depend directly on OCPP, Modbus, proprietary protocols, or vendor SDKs.
* Create an HEMS-specific MQTT protocol or message bus.
* Create a second communication channel between HEMS modules outside Home Assistant.

### Critical Boundary

The following distinction MUST be maintained:

```text
HEMS
  │
  │ Home Assistant entities/services ONLY
  ▼
Home Assistant
  │
  ▼
Integration / Add-on
  │
  ├── MQTT
  ├── HTTP
  ├── REST API
  ├── OCPP
  ├── Modbus
  ├── vendor SDK
  └── whatever the integration requires
```

Everything below the Home Assistant integration boundary is an implementation detail.

HEMS MUST NOT care how a device is controlled.

---

## Module Responsibility

Each module/integration is responsible for translating implementation-specific capabilities into a clean Home Assistant interface.

For example, an EV charger may internally use:

```text
Charge Amps API
MQTT
OCPP
HTTP
vendor protocol
```

HEMS should only see appropriate Home Assistant entities, for example:

```text
sensor.ev_charger_power
sensor.ev_charger_current
sensor.ev_charger_status
binary_sensor.ev_charger_online
switch.ev_charger_charging
number.ev_charger_charging_current
```

The implementation behind those entities is entirely the responsibility of the integration.

### Capability-Oriented Interfaces

When improving an add-on for future HEMS use:

1. Identify the actual capabilities of the device.
2. Expose those capabilities through appropriate Home Assistant entities/services.
3. Give those entities stable and predictable semantics.
4. Keep vendor/protocol-specific communication inside the integration.
5. Preserve standalone functionality where applicable.
6. Avoid exposing implementation details as part of the HEMS interface.

Prefer Home Assistant-native entities according to their semantics:

* `sensor` — measurements and read-only state
* `binary_sensor` — boolean state
* `switch` — persistent on/off control
* `number` — numeric control such as current or power limits
* `select` — discrete operating modes
* `button` — actions that do not represent persistent state

The exact entity model must reflect the actual device capabilities and Home Assistant conventions.

---

## HEMS Control Semantics

HEMS expresses intent through Home Assistant controls.

For example, an EV charger may expose:

```text
number.ev_charger_charging_current
switch.ev_charger_charging
```

HEMS can therefore request:

```text
number.set_value
  entity_id: number.ev_charger_charging_current
  value: 4
```

and use the appropriate Home Assistant service to start charging.

A requirement such as:

> Charge at 4 A for 10 minutes.

is an **HEMS orchestration concern**.

The underlying integration is responsible only for executing the requested control.

HEMS MUST NOT implement vendor-specific logic to achieve timed operations.

This separation allows the same HEMS logic to work with different Home Assistant integrations.

---

## Third-Party Home Assistant Integrations

HEMS should preferably work with any Home Assistant integration that exposes the required capabilities.

HEMS MUST NOT require that a device is controlled by one of the add-ons in this repository.

The architectural goal is:

```text
HEMS
  ↓
Home Assistant capability/entity interface
  ↓
Any compatible Home Assistant integration
  ↓
Physical device
```

rather than:

```text
HEMS
  ↓
Repository-specific add-on
  ↓
Vendor-specific API
```

An add-on in this repository should therefore be considered one possible implementation of a Home Assistant capability, not a mandatory dependency of HEMS.

---

## No Second Integration Bus

**Home Assistant is the canonical integration surface.**

Do not introduce a parallel communication mechanism between HEMS modules.

MQTT may be used internally by an individual integration if required by that integration, including for Home Assistant MQTT Discovery or device communication.

However:

* HEMS MUST NOT use MQTT.
* HEMS MUST NOT know MQTT topics.
* HEMS MUST NOT depend on MQTT payloads.
* HEMS MUST NOT communicate with another add-on through MQTT.
* MQTT MUST remain invisible to HEMS.

The same applies to HTTP, REST, OCPP, Modbus, databases, vendor APIs, SDKs, and other implementation mechanisms.

---

# Shared Module Architecture

Each add-on has its own `shared/` copy because Docker builds can only access files within the add-on directory.

The root `shared/` directory is the source of truth.

**Always edit root `shared/`, then sync:**

```bash
python sync_shared.py
python run_addon.py --addon X
```

| Module                 | Key Exports                                                      |
| ---------------------- | ---------------------------------------------------------------- |
| `addon_base.py`        | `setup_logging()`, `setup_signal_handlers()`, `run_addon_loop()` |
| `ha_api.py`            | `HomeAssistantApi`, `get_ha_api_config()`                        |
| `config_loader.py`     | `load_addon_config()`, `get_run_once_mode()`                     |
| `ha_mqtt_discovery.py` | `MqttDiscovery`, `EntityConfig`, `NumberConfig`, `SelectConfig`  |
| `mqtt_setup.py`        | `setup_mqtt_client()`, `is_mqtt_available()`                     |

### Shared Module Rule

Never edit:

```text
<addon>/shared/
```

directly.

Edit:

```text
shared/
```

and synchronize the copies.

---

# Add-on Structure

Every add-on should follow the established layout where applicable:

```text
app/main.py             - Orchestration and main loop
app/models.py           - Data models with from_dict()/to_dict()
app/[name]_api.py       - External API clients
app/[feature].py        - Business logic modules
config.yaml             - Home Assistant metadata and option schema
Dockerfile              - Alpine-based container build
run.sh                  - Entrypoint script
```

Keep responsibilities separated.

Avoid turning `main.py` into a monolithic implementation.

---

# Python Conventions

* Python 3.12+
* PEP 8 style
* Use structured logging.
* Prefer docstrings over comments.
* Use `requests.Session` for HTTP connection pooling.
* Handle graceful shutdown through `shutdown_event.is_set()`.
* Keep external API clients separate from business logic.
* Keep Home Assistant integration logic separate from domain logic.
* Prefer explicit data models over loosely structured dictionaries where practical.
* Add tests for meaningful business logic and control semantics.

---

# Home Assistant Entity Naming

Prefix entities with the add-on identifier:

* `ca_` — Charge Amps
* `ep_` — Energy Prices
* `bm_` — Battery Manager
* `ba_` — Battery API
* `wh_` — Water Heater Scheduler

When introducing new entities, maintain backwards compatibility where practical.

For new HEMS-facing entities, prioritize clear capability-oriented semantics over exposing internal implementation details.

---

# Battery Manager Semantics

In `battery-manager`:

* Keep market classification separate from effective operating mode.
* `price_range` may be `adaptive` when the current price is in the adaptive market band.
* `mode` and `current_action` SHALL only use `adaptive` when adaptive discharge control is actively running.
* When no charge/discharge/adaptive control window is active, the operating mode SHALL be `idle` or `passive` as appropriate.
* `current_action` should prefer the next scheduled event over a generic adaptive label.

---

# Backwards Compatibility

Existing add-ons are already used independently.

When professionalizing an add-on for HEMS:

* Do not unnecessarily break existing entities.
* Do not remove existing functionality without an explicit migration strategy.
* Preserve existing standalone operation unless the change explicitly requires otherwise.
* Prefer adding a clean HA-native control surface over replacing working functionality abruptly.
* If entity names or semantics must change, provide a documented migration path.
* HEMS-specific improvements must not make an add-on dependent on HEMS.

**Every module must remain useful without HEMS installed.**

---

# Git

* Never commit directly to `master`.
* Use a dedicated branch for changes.
* Branch naming:

  * `feature/[name]`
  * `fix/[name]`
  * `refactor/[name]`
  * `docs/[name]`
* Use conventional commits:

  * `feat(scope): description`
  * `fix(scope): description`
  * `refactor(scope): description`
  * `docs(scope): description`
* New capabilities require an OpenSpec proposal.
* Breaking changes require explicit OpenSpec documentation.
* Keep changes focused.
* Do not mix unrelated refactoring into feature work.

---

# OpenSpec

Use OpenSpec for:

* New capabilities
* Architecture changes
* Breaking changes
* Significant behavioral changes
* Significant performance/security work

Before implementing a qualifying change:

1. Read `openspec/AGENTS.md`.
2. Inspect the relevant existing specifications.
3. Create or update the appropriate proposal.
4. Define requirements and scenarios.
5. Implement only after the proposal is understood and approved according to repository workflow.
6. Update the canonical specification when the capability is completed.

Do not invent requirements that conflict with existing specifications.

---

# Local Development

```bash
python run_addon.py --list
python run_addon.py --addon energy-prices
python run_addon.py --addon energy-prices --once
python run_addon.py --addon energy-prices --init-env
```

Use the appropriate add-on when testing.

Verify changes before considering the work complete.

---

# External APIs

External APIs are **internal implementation details of individual add-ons**.

| API                 | Base URL                                                      | Auth             |
| ------------------- | ------------------------------------------------------------- | ---------------- |
| Charge Amps Cloud   | `https://my.charge.space/api/`                                | JWT token        |
| Nord Pool Day-Ahead | `https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices` | None             |
| SAJ Electric        | Via `battery-api` add-on                                      | API key          |
| HA Supervisor       | `http://supervisor/core/api/`                                 | Supervisor token |

These APIs MUST NOT become HEMS interfaces.

HEMS communicates through Home Assistant entities/services instead.

---

# Instruction Files

Detailed repository rules are maintained in `.github/instructions/`:

* `agent.instructions.md` — Workflow steps (branch, plan, implement, verify, document, commit)
* `coding.instructions.md` — Tech stack, project structure, Python patterns, Docker conventions
* `documentation.instructions.md` — Documentation hierarchy, prohibited files, README standards
* `openspec.instructions.md` — Change proposals, spec deltas, CLI commands

When a more specific instruction file applies, follow it in addition to this document.

More specific instructions take precedence for the relevant scope.
