<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# AI Agent Guidelines

High-level conventions for AI agents working in this repository. For detailed rules, see `.github/instructions/`.

---

## Repository at a Glance

A collection of **Home Assistant Supervisor add-ons** for home energy management, written in Python 3.12+ and deployed as Docker containers.

### Add-ons

| Directory | Slug | Prefix | Purpose |
|-----------|------|--------|---------|
| `battery-api/` | battery-api | `ba_` | SAJ inverter battery charge/discharge schedule control |
| `battery-manager/` | battery-manager | `bm_` | Battery optimization using prices, solar, grid, and EV data |
| `charge-amps-monitor/` | charge-amps-monitor | `ca_` | Charge Amps EV charger monitoring and control |
| `energy-prices/` | energy-prices | `ep_` | Nord Pool electricity prices with import/export calculations |
| `water-heater-scheduler/` | water-heater-scheduler | `wh_` | Price-based water heater scheduling |

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `shared/` | Common Python modules (source of truth - never edit `<addon>/shared/`) |
| `openspec/specs/` | Canonical specifications per capability |
| `openspec/changes/` | Active change proposals |
| `docs/` | Long-form design documents and plans |

---

## Shared Module Architecture

Each add-on has its own `shared/` copy because Docker builds can only access files within the add-on directory. The root `shared/` is the source of truth.

**Always edit root `shared/`, then sync:**
```bash
python sync_shared.py          # Manual sync
python run_addon.py --addon X  # Auto-syncs before running
```

| Module | Key Exports |
|--------|-------------|
| `addon_base.py` | `setup_logging()`, `setup_signal_handlers()`, `run_addon_loop()` |
| `ha_api.py` | `HomeAssistantApi`, `get_ha_api_config()` |
| `config_loader.py` | `load_addon_config()`, `get_run_once_mode()` |
| `ha_mqtt_discovery.py` | `MqttDiscovery`, `EntityConfig`, `NumberConfig`, `SelectConfig` |
| `mqtt_setup.py` | `setup_mqtt_client()`, `is_mqtt_available()` |

---

## Conventions

### Add-on Structure
Every add-on follows the same layout:
- `app/main.py` - Orchestration and main loop
- `app/models.py` - Data models with `from_dict()`/`to_dict()`
- `app/[name]_api.py` - External API clients
- `app/[feature].py` - Business logic modules
- `config.yaml` - HA metadata and option schema
- `Dockerfile` - Alpine-based container build
- `run.sh` - Entrypoint script

### Python
- PEP 8 style, structured logging, docstrings over comments
- `requests.Session` for connection pooling
- Graceful shutdown via `shutdown_event.is_set()`
- MQTT Discovery preferred over REST API for entity creation

### Entity Naming
Prefix all entities with the add-on identifier (`ca_`, `ep_`, `bm_`, `ba_`, `wh_`).

### Git
- Never commit to `master` directly
- Conventional commits: `feat(scope): description`
- New features require OpenSpec proposals

---

## Local Development

```bash
python run_addon.py --list                        # Available add-ons
python run_addon.py --addon energy-prices         # Run continuously
python run_addon.py --addon energy-prices --once  # Single iteration
python run_addon.py --addon energy-prices --init-env  # Create .env
```

---

## External APIs

| API | Base URL | Auth |
|-----|----------|------|
| Charge Amps Cloud | `https://my.charge.space/api/` | JWT token |
| Nord Pool Day-Ahead | `https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices` | None |
| SAJ Electric | Via `battery-api` add-on | API key |
| HA Supervisor | `http://supervisor/core/api/` | Supervisor token |

---

## Instruction Files

Detailed rules are in `.github/instructions/`:
- `agent.instructions.md` - Workflow steps (branch, plan, implement, verify, document, commit)
- `coding.instructions.md` - Tech stack, project structure, Python patterns, Docker conventions
- `documentation.instructions.md` - Doc hierarchy, prohibited files, README standards
- `openspec.instructions.md` - Change proposals, spec deltas, CLI commands
